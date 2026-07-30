"""Windows background capture and input for the FH6 game window."""

from __future__ import annotations

import csv
import ctypes
import io
import os
import subprocess
import threading
import time

try:
    import win32api
    import win32con
    import win32gui
    import win32ui
except ImportError:  # Allows parser/unit tests to run on non-Windows hosts.
    win32api = win32con = win32gui = win32ui = None


PROCESS_NAME = "forzahorizon6.exe"
PW_RENDERFULLCONTENT = 3

VK_MAP = {
    "esc": 0x1B,
    "enter": 0x0D,
    "space": 0x20,
    "backspace": 0x08,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "pageup": 0x21,
    "pagedown": 0x22,
    "f8": 0x77,
    "f9": 0x78,
}

SCAN_MAP = {
    "esc": (0x01, False),
    "enter": (0x1C, False),
    "space": (0x39, False),
    "backspace": (0x0E, False),
    "up": (0x48, True),
    "down": (0x50, True),
    "left": (0x4B, True),
    "right": (0x4D, True),
    "pageup": (0x49, True),
    "pagedown": (0x51, True),
    "f8": (0x42, False),
    "f9": (0x43, False),
}


def _require_windows() -> None:
    if os.name != "nt" or win32gui is None:
        raise RuntimeError("FH6 后台控制只支持 Windows")


def find_process_pid(image_name: str) -> int | None:
    _require_windows()
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    output = subprocess.check_output(
        ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/NH", "/FO", "CSV"],
        text=True,
        encoding="utf-8",
        errors="ignore",
        startupinfo=startup,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    for row in csv.reader(io.StringIO(output)):
        if len(row) >= 2 and row[0].lower() == image_name.lower():
            try:
                return int(row[1])
            except ValueError:
                return None
    return None


def process_running(image_name: str) -> bool:
    return find_process_pid(image_name) is not None


def _build_lparam(scan: int, extended: bool, *, down: bool) -> int:
    value = 1 | ((scan & 0xFF) << 16)
    if extended:
        value |= 1 << 24
    if not down:
        value |= (1 << 30) | (1 << 31)
    return value


class BackgroundInput:
    """Send input directly to one HWND without moving physical input devices."""

    def __init__(self, hwnd: int):
        _require_windows()
        self.hwnd = hwnd
        self._pressed: set[str] = set()

    def _send_key(self, key: str, *, down: bool, use_send: bool = False) -> None:
        key = key.lower()
        vk = VK_MAP.get(key)
        if vk is None:
            raise ValueError(f"不支持的按键: {key}")
        scan, extended = SCAN_MAP[key]
        message = win32con.WM_KEYDOWN if down else win32con.WM_KEYUP
        sender = win32gui.SendMessage if use_send else win32gui.PostMessage
        sender(
            self.hwnd,
            message,
            vk,
            _build_lparam(scan, extended, down=down),
        )
        if down:
            self._pressed.add(key)
        else:
            self._pressed.discard(key)

    def press(self, key: str, delay: float = 0.08, use_send: bool = False) -> None:
        self._send_key(key, down=True, use_send=use_send)
        time.sleep(delay)
        self._send_key(key, down=False, use_send=use_send)
        time.sleep(0.02)

    def click(self, client_x: int, client_y: int, hold: float = 0.08) -> None:
        point = win32api.MAKELONG(int(client_x), int(client_y))
        win32gui.PostMessage(self.hwnd, win32con.WM_MOUSEMOVE, 0, point)
        time.sleep(0.04)
        win32gui.PostMessage(
            self.hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, point
        )
        time.sleep(hold)
        win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONUP, 0, point)
        time.sleep(0.08)

    def release_all(self) -> None:
        for key in tuple(self._pressed):
            try:
                self._send_key(key, down=False)
            except Exception:
                pass
        self._pressed.clear()


class GameWindow:
    """Locate, capture, and control the Steam FH6 client window."""

    def __init__(self, log=None):
        self.log = log or (lambda _message: None)
        self.hwnd: int | None = None
        self.bounds = (0, 0, 0, 0)
        self.input: BackgroundInput | None = None
        self._capture_lock = threading.Lock()

    @staticmethod
    def _find_pid() -> int | None:
        return find_process_pid(PROCESS_NAME)

    @staticmethod
    def _find_hwnd(pid: int) -> int | None:
        matches: list[int] = []

        def collect(hwnd, _extra):
            if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                return True
            window_pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(
                hwnd, ctypes.byref(window_pid)
            )
            if window_pid.value == pid:
                matches.append(hwnd)
            return True

        win32gui.EnumWindows(collect, None)
        return matches[0] if matches else None

    def attach(self) -> bool:
        try:
            self.close()
            pid = self._find_pid()
            if not pid:
                self.log("未发现 ForzaHorizon6.exe")
                return False
            hwnd = self._find_hwnd(pid)
            if not hwnd:
                self.log("已发现游戏进程，但没有可见游戏窗口")
                return False
            self.hwnd = hwnd
            self.input = BackgroundInput(hwnd)
            self.refresh_bounds()
            self.log(f"已连接游戏窗口: hwnd={hwnd}, 区域={self.bounds}")
            return True
        except Exception as exc:
            self.log(f"连接游戏窗口失败: {exc}")
            return False

    def ensure_attached(self) -> bool:
        if self.hwnd and win32gui and win32gui.IsWindow(self.hwnd):
            try:
                self.refresh_bounds()
                return True
            except Exception:
                pass
        self.close()
        return self.attach()

    def refresh_bounds(self) -> tuple[int, int, int, int]:
        if not self.hwnd:
            raise RuntimeError("尚未连接游戏窗口")
        left, top = win32gui.ClientToScreen(self.hwnd, (0, 0))
        _x1, _y1, right, bottom = win32gui.GetClientRect(self.hwnd)
        self.bounds = (left, top, right, bottom)
        return self.bounds

    def capture(self, region=None):
        """Capture the client through PrintWindow.

        A screen-coordinate region can optionally be cropped from the result.
        """
        if not self.ensure_attached() or not self.hwnd:
            return None
        with self._capture_lock:
            try:
                screen = self._capture_client()
                if screen is None or region is None:
                    return screen
                rx, ry, rw, rh = map(int, region)
                wx, wy, ww, wh = self.bounds
                x1 = max(0, min(rx - wx, ww))
                y1 = max(0, min(ry - wy, wh))
                x2 = max(x1, min(x1 + rw, ww))
                y2 = max(y1, min(y1 + rh, wh))
                return screen[y1:y2, x1:x2].copy()
            except Exception as exc:
                self.log(f"PrintWindow 截图失败: {exc}")
                return None

    def _capture_client(self):
        import numpy as np

        _x, _y, width, height = self.bounds
        if width <= 0 or height <= 0 or not self.hwnd:
            return None
        hwnd_dc = win32gui.GetWindowDC(self.hwnd)
        mfc_dc = save_dc = bitmap = None
        try:
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(bitmap)
            ok = ctypes.windll.user32.PrintWindow(
                self.hwnd,
                save_dc.GetSafeHdc(),
                PW_RENDERFULLCONTENT,
            )
            if ok != 1:
                return None
            raw = bitmap.GetBitmapBits(True)
            bgra = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 4))
            return bgra[:, :, :3].copy()
        finally:
            if bitmap is not None:
                win32gui.DeleteObject(bitmap.GetHandle())
            if save_dc is not None:
                save_dc.DeleteDC()
            if mfc_dc is not None:
                mfc_dc.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, hwnd_dc)

    def press(self, key: str, delay: float = 0.08, use_send: bool = False) -> None:
        if not self.ensure_attached() or not self.input:
            raise RuntimeError("游戏窗口已断开")
        self.input.press(key, delay, use_send=use_send)

    def click_screen(self, x: int, y: int) -> None:
        if not self.ensure_attached() or not self.input:
            raise RuntimeError("游戏窗口已断开")
        wx, wy, _ww, _wh = self.bounds
        self.input.click(int(x - wx), int(y - wy))

    def close(self) -> None:
        with self._capture_lock:
            if self.input:
                self.input.release_all()
            self.input = None
            self.hwnd = None

    def release_all(self) -> None:
        if self.input:
            self.input.release_all()


def send_global_hotkey(key: str) -> None:
    """Send F8/F9 through the real input queue so FH6Auto's pynput listener sees it."""
    _require_windows()
    vk = VK_MAP.get(key.lower())
    if key.lower() not in ("f8", "f9") or vk is None:
        raise ValueError("桥接器只允许发送 F8/F9")
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.06)
    user32.keybd_event(vk, 0, 0x0002, 0)
