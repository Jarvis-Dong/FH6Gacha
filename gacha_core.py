"""
gacha_core.py - 抽奖/超级抽奖核心逻辑模块
硬件输入 + 窗口聚焦 + 菜单检测 完全对照 main.py
"""
import os
import sys
import time
import threading
import subprocess
import cv2
import numpy as np
import pyautogui
import pydirectinput
import ctypes
import win32gui
from PIL import Image, ImageGrab

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(SCRIPT_DIR, "images")

# ==============================================
# 硬件输入结构体 —— 完全复制自 main.py
# ==============================================
SendInput = ctypes.windll.user32.SendInput
PUL = ctypes.POINTER(ctypes.c_ulong)


class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]


class Input_I(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    ]


class Input(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii", Input_I),
    ]


# --- 硬件扫描码 (完全复制自 main.py) ---
DIK_CODES = {
    "esc": (0x01, False),
    "enter": (0x1C, False),
    "space": (0x39, False),
    "backspace": (0x0E, False),
    "tab": (0x0F, False),
    "lshift": (0x2A, False),
    "rshift": (0x36, False),
    "lctrl": (0x1D, False),
    "rctrl": (0x1D, True),
    "lalt": (0x38, False),
    "ralt": (0x38, True),
    "capslock": (0x3A, False),
    "a": (0x1E, False), "b": (0x30, False), "c": (0x2E, False), "d": (0x20, False),
    "e": (0x12, False), "f": (0x21, False), "g": (0x22, False), "h": (0x23, False),
    "i": (0x17, False), "j": (0x24, False), "k": (0x25, False), "l": (0x26, False),
    "m": (0x32, False), "n": (0x31, False), "o": (0x18, False), "p": (0x19, False),
    "q": (0x10, False), "r": (0x13, False), "s": (0x1F, False), "t": (0x14, False),
    "u": (0x16, False), "v": (0x2F, False), "w": (0x11, False), "x": (0x2D, False),
    "y": (0x15, False), "z": (0x2C, False),
    "1": (0x02, False), "2": (0x03, False), "3": (0x04, False), "4": (0x05, False),
    "5": (0x06, False), "6": (0x07, False), "7": (0x08, False), "8": (0x09, False),
    "9": (0x0A, False), "0": (0x0B, False),
    "up": (0xC8, True), "down": (0xD0, True),
    "left": (0xCB, True), "right": (0xCD, True),
    "pageup": (0xC9, True), "pagedown": (0xD1, True),
    "home": (0xC7, True), "end": (0xCF, True),
    "insert": (0xD2, True), "delete": (0xD3, True),
    "f1": (0x3B, False), "f2": (0x3C, False), "f3": (0x3D, False),
    "f4": (0x3E, False), "f5": (0x3F, False), "f6": (0x40, False),
    "f7": (0x41, False), "f8": (0x42, False), "f9": (0x43, False),
    "f10": (0x44, False), "f11": (0x57, False), "f12": (0x58, False),
}


def _make_extra():
    return ctypes.c_ulong(0)


def hw_key_down(key):
    if key not in DIK_CODES:
        return
    scan_code, extended = DIK_CODES[key]
    flags = 0x0008 | (0x0001 if extended else 0)
    extra = _make_extra()
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))


def hw_key_up(key):
    if key not in DIK_CODES:
        return
    scan_code, extended = DIK_CODES[key]
    flags = 0x000A | (0x0001 if extended else 0)
    extra = _make_extra()
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii_)
    SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))


def hw_press(key, delay=0.08):
    hw_key_down(key)
    time.sleep(delay)
    hw_key_up(key)


def hw_mouse_move(x, y):
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    left = ctypes.windll.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = ctypes.windll.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = ctypes.windll.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = ctypes.windll.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if width == 0 or height == 0:
        return
    calc_x = int((x - left) * 65535 / width)
    calc_y = int((y - top) * 65535 / height)
    flags = 0x0001 | 0x8000 | 0x4000
    extra = _make_extra()
    ii_ = Input_I()
    ii_.mi = MouseInput(calc_x, calc_y, 0, flags, 0, ctypes.pointer(extra))
    cmd = Input(ctypes.c_ulong(0), ii_)
    SendInput(1, ctypes.pointer(cmd), ctypes.sizeof(cmd))


def hw_click(pos, delay=0.1):
    x, y = int(pos[0]), int(pos[1])
    hw_mouse_move(x, y)
    time.sleep(0.2)
    pydirectinput.mouseDown()
    time.sleep(delay)
    pydirectinput.mouseUp()
    time.sleep(delay)
    # 点击后移开鼠标到安全位置, 防止游戏悬浮提示遮挡截图 (对照 main.py game_click)
    try:
        # 移到屏幕左上角 5px 处
        hw_mouse_move(5, 5)
    except Exception:
        pass
    time.sleep(0.1)


# ==============================================
# GachaCore
# ==============================================
class GachaCore:
    TEMPLATE_REF_W = 3835
    TEMPLATE_REF_H = 2159

    def __init__(self, log_callback=None, stats_callback=None):
        self.log_cb = log_callback or print
        self.stats_cb = stats_callback
        self.is_running = True
        self.price_threshold = 100_000
        self.dup_match_threshold = 0.80
        self.dup_stats = {"total": 0, "kept": 0, "sold": 0, "earned": 0}
        self.regions = {}
        self.scale_x = 1.0
        self.scale_y = 1.0
        self._init_regions()
        self.template_cache = {}
        # easyocr 异步预加载
        self._easyocr_reader = None
        self._easyocr_ready = threading.Event()
        self._game_hwnd = None  # 游戏窗口句柄, focus_game 后缓存

    def log(self, msg):
        self.log_cb(msg)

    def _notify_stats(self):
        if self.stats_cb:
            try:
                self.stats_cb(self.dup_stats.copy())
            except Exception:
                pass

    def _init_regions(self):
        sw, sh = pyautogui.size()
        self._update_regions_by_window(0, 0, sw, sh)

    def _update_regions_by_window(self, x, y, w, h):
        self.regions = {
            "全界面": (x, y, w, h),
            "左上": (x, y, w // 2, h // 2),
            "右上": (x + w // 2, y, w // 2, h // 2),
            "左下": (x, y + h // 2, w // 2, h // 2),
            "右下": (x + w // 2, y + h // 2, w // 2, h // 2),
            "上": (x, y, w, h // 2),
            "下": (x, y + h // 2, w, h // 2),
            "左": (x, y, w // 2, h),
            "右": (x + w // 2, y, w // 2, h),
            "中间": (x + w // 4, y + h // 4, w // 2, h // 2),
        }
        self.scale_x = w / self.TEMPLATE_REF_W
        self.scale_y = h / self.TEMPLATE_REF_H
        self.log(f"[scale] 预计算缩放比: x={self.scale_x:.4f} y={self.scale_y:.4f} (窗口={w}x{h})")

    def _scale_roi(self, x, y, w, h):
        """将参考分辨率(3835x2159)的ROI映射到当前窗口的屏幕绝对坐标"""
        full = self.regions.get("全界面")
        ox, oy = (full[0], full[1]) if full else (0, 0)
        return (
            int(ox + x * self.scale_x),
            int(oy + y * self.scale_y),
            int(w * self.scale_x),
            int(h * self.scale_y),
        )

    def capture_region(self, region=None):
        try:
            if region:
                x, y, w, h = region
                screen = ImageGrab.grab(bbox=(int(x), int(y), int(x + w), int(y + h)), all_screens=True)
            else:
                screen = ImageGrab.grab(all_screens=True)
        except Exception:
            screen = pyautogui.screenshot(region=region)
        return cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)

    def _get_img_path(self, filename):
        p = os.path.join(IMAGES_DIR, filename)
        if os.path.exists(p):
            return p
        return None

    def _load_template(self, path):
        if path in self.template_cache:
            return self.template_cache[path]
        tpl = cv2.imread(path)
        if tpl is not None:
            self.template_cache[path] = tpl
        return tpl

    def _get_scales(self, fast=True, ref_w=None):
        """多尺度缩放列表 —— 对照 main.py get_scales_to_try

        ref_w: 模板参考宽度, 3835=gacha新模板, 2560=main.py旧模板, None=自动
               fast模式返回 7 个值(基准 ±2/5/8%), 与 main.py 保持一致
        """
        full = self.regions.get("全界面")
        curr_w = full[2] if full else pyautogui.size()[0]
        scales = []
        def add(s):
            s = round(float(s), 3)
            if 0.25 <= s <= 1.8 and s not in scales:
                scales.append(s)

        if ref_w is not None:
            primary_scale = curr_w / ref_w
        else:
            # 自动模式: 优先 3835 (gacha 新模板)
            primary_scale = curr_w / 3835

        # 基准 + 微调 (对照 main.py: ±2%/±5%/±8%)
        add(primary_scale)
        add(primary_scale * 0.98)
        add(primary_scale * 1.02)
        add(primary_scale * 0.95)
        add(primary_scale * 1.05)
        add(primary_scale * 0.92)
        add(primary_scale * 1.08)

        if not fast:
            # 扩展: 2560 旧模板 + 其他常见分辨率
            if ref_w is None:
                s2560 = curr_w / 2560
                for v in [s2560, s2560 * 0.98, s2560 * 1.02, s2560 * 0.95, s2560 * 1.05]:
                    add(v)
            for bw in [1920, 1600]:
                s = curr_w / bw
                add(s)
                add(s * 0.98)
                add(s * 1.02)
            for s in [1.0, 0.95, 1.05, 0.9, 1.1, 0.85, 1.15, 0.8, 0.75, 0.7]:
                add(s)
        return scales

    def find_image(self, template_name, region=None, threshold=0.75, ref_w=None):
        """多尺度模板匹配 —— 对照 main.py find_image_in_screen

        ref_w: 模板参考宽度, 3835=新gacha模板, 2560=main.py旧模板, None=自动(3835)
        """
        if not self.is_running:
            return None
        path = self._get_img_path(template_name)
        if not path:
            return None
        region_tuple = self.regions.get(region, region) if isinstance(region, str) else region
        screen = self.capture_region(region_tuple)
        tpl = self._load_template(path)
        if tpl is None:
            return None

        for scale in self._get_scales(fast=True, ref_w=ref_w):
            h, w = tpl.shape[:2]
            nw, nh = int(w * scale), int(h * scale)
            if nw < 5 or nh < 5 or nw > screen.shape[1] or nh > screen.shape[0]:
                continue
            tpl_s = cv2.resize(tpl, (nw, nh), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(screen, tpl_s, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= threshold:
                rx = region_tuple[0] if region_tuple else 0
                ry = region_tuple[1] if region_tuple else 0
                pos = (max_loc[0] + nw // 2 + rx, max_loc[1] + nh // 2 + ry)
                self.log(f"[match] {template_name} score={max_val:.3f} scale={scale:.3f} @ {pos}")
                return pos
        return None

    # ==================== 窗口聚焦 (对照 main.py check_and_focus_game) ====================

    def set_english_input(self):
        """强制切换为英文输入法"""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return
            hkl = ctypes.windll.user32.LoadKeyboardLayoutW("00000409", 1)
            ctypes.windll.user32.PostMessageW(hwnd, 0x0050, 0, hkl)
            WM_IME_CONTROL = 0x0283
            IMC_SETOPENSTATUS = 0x0006
            ctypes.windll.user32.SendMessageW(hwnd, WM_IME_CONTROL, IMC_SETOPENSTATUS, 0)
            self.log("已切换英文输入法")
        except Exception as e:
            self.log(f"切换输入法失败: {e}")

    def focus_game(self):
        """查找游戏窗口, 置顶, 更新区域"""
        self.log("正在查找游戏窗口 (forzahorizon6.exe)...")
        try:
            CREATE_NO_WINDOW = 0x08000000
            cmd = 'tasklist /FI "IMAGENAME eq forzahorizon6.exe" /NH /FO CSV'
            output = subprocess.check_output(cmd, shell=True, text=True, creationflags=CREATE_NO_WINDOW)

            if "forzahorizon6.exe" not in output.lower():
                self.log("未发现游戏进程! 请确保游戏已运行")
                return False

            target_pid = None
            for line in output.strip().split("\n"):
                parts = line.split('","')
                if len(parts) >= 2 and "forzahorizon6.exe" in parts[0].lower():
                    target_pid = int(parts[1].replace('"', ""))
                    break

            if not target_pid:
                self.log("解析PID失败")
                return False

            hwnds = []

            def foreach_window(hwnd, lParam):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        window_pid = ctypes.c_ulong()
                        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                        if window_pid.value == target_pid:
                            hwnds.append(hwnd)
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(foreach_window), 0)

            if not hwnds:
                self.log("未找到游戏窗口句柄")
                return False

            hwnd = hwnds[0]
            self._game_hwnd = hwnd  # 缓存句柄
            if ctypes.windll.user32.IsIconic(hwnd):
                ctypes.windll.user32.ShowWindow(hwnd, 9)
            else:
                ctypes.windll.user32.ShowWindow(hwnd, 5)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.5)

            self.set_english_input()

            # 更新识图区域为游戏窗口实际区域
            client_rect = win32gui.GetClientRect(hwnd)
            pt = win32gui.ClientToScreen(hwnd, (0, 0))
            gx, gy = pt[0], pt[1]
            gw, gh = client_rect[2], client_rect[3]
            self._update_regions_by_window(gx, gy, gw, gh)
            self.log(f"游戏窗口已聚焦, 区域: ({gx},{gy}) {gw}x{gh}")
            self._preload_ocr()  # 后台预加载 OCR 模型
            time.sleep(0.5)
            return True

        except Exception as e:
            self.log(f"聚焦游戏窗口失败: {e}")
            return False

    # ==================== 菜单进入 (对照 main.py enter_menu) ====================

    def _ensure_focus(self):
        """确保游戏窗口在前台, 并同步窗口位置 (处理拖动/移动/关闭)"""
        # 检查窗口句柄是否仍然有效
        if self._game_hwnd and not ctypes.windll.user32.IsWindow(self._game_hwnd):
            self.log("[focus] 窗口句柄失效, 重新查找游戏窗口...")
            self._game_hwnd = None
            if not self._refind_window():
                self.log("[focus] 重新查找失败, 无法继续")
                return
        if not self._game_hwnd:
            if not self._refind_window():
                return
        # 检查并更新窗口位置
        try:
            client_rect = win32gui.GetClientRect(self._game_hwnd)
            pt = win32gui.ClientToScreen(self._game_hwnd, (0, 0))
            new_x, new_y = pt[0], pt[1]
            new_w, new_h = client_rect[2], client_rect[3]
            full = self.regions.get("全界面")
            if not full or full[0] != new_x or full[1] != new_y or full[2] != new_w or full[3] != new_h:
                self._update_regions_by_window(new_x, new_y, new_w, new_h)
        except Exception:
            pass
        # 检查并恢复焦点
        fg = ctypes.windll.user32.GetForegroundWindow()
        if fg != self._game_hwnd:
            self.log("[focus] 游戏窗口失焦, 重新置顶")
            if ctypes.windll.user32.IsIconic(self._game_hwnd):
                ctypes.windll.user32.ShowWindow(self._game_hwnd, 9)
            else:
                ctypes.windll.user32.ShowWindow(self._game_hwnd, 5)
            ctypes.windll.user32.SetForegroundWindow(self._game_hwnd)
            time.sleep(0.15)

    def _refind_window(self):
        """轻量重新查找游戏窗口 (不重新加载 OCR)"""
        self.log("正在重新查找游戏窗口...")
        try:
            CREATE_NO_WINDOW = 0x08000000
            cmd = 'tasklist /FI "IMAGENAME eq forzahorizon6.exe" /NH /FO CSV'
            output = subprocess.check_output(cmd, shell=True, text=True, creationflags=CREATE_NO_WINDOW)
            if "forzahorizon6.exe" not in output.lower():
                self.log("未发现游戏进程!")
                return False
            target_pid = None
            for line in output.strip().split("\n"):
                parts = line.split('","')
                if len(parts) >= 2 and "forzahorizon6.exe" in parts[0].lower():
                    target_pid = int(parts[1].replace('"', ""))
                    break
            if not target_pid:
                return False
            hwnds = []
            def foreach_window(hwnd, lParam):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        window_pid = ctypes.c_ulong()
                        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                        if window_pid.value == target_pid:
                            hwnds.append(hwnd)
                return True
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(foreach_window), 0)
            if not hwnds:
                return False
            self._game_hwnd = hwnds[0]
            client_rect = win32gui.GetClientRect(self._game_hwnd)
            pt = win32gui.ClientToScreen(self._game_hwnd, (0, 0))
            self._update_regions_by_window(pt[0], pt[1], client_rect[2], client_rect[3])
            self.log(f"重新找到游戏窗口: ({pt[0]},{pt[1]}) {client_rect[2]}x{client_rect[3]}")
            return True
        except Exception as e:
            self.log(f"重新查找窗口失败: {e}")
            return False

    def enter_menu(self):
        """
        按 ESC 并检测主菜单锚点 collectionjournal.png (2560基准旧模板)
        最多尝试 60 次, 确认进入主菜单后 PgDn×2 切换到抽奖菜单页
        """
        if not self.is_running:
            return False

        self.log("正在进入主菜单...")
        for i in range(60):
            if not self.is_running:
                return False

            pos_menu = self.find_image("collectionjournal.png", region="左", threshold=0.70, ref_w=2560)
            if pos_menu:
                self.log(f"已进入主菜单 (第 {i+1}/60 次)")
                time.sleep(0.2)
                self._ensure_focus()  # 确保按键能到达游戏
                self.log("PgDn×2 切换到抽奖标签页...")
                hw_press("pagedown", delay=0.08)
                time.sleep(0.2)
                hw_press("pagedown", delay=0.08)
                time.sleep(0.3)
                return True

            self.log(f"未在主菜单, 按 ESC... ({i+1}/60)")
            hw_press("esc", delay=0.12)
            time.sleep(1.0)

        self.log("60 次尝试均未进入菜单!")
        return False

    # ==================== 抽奖状态判定 ====================

    def check_gacha_prompt(self):
        """检查左下角抽奖提示: 'skip' / 'claim' / 'none'"""
        t0 = time.time()
        rx, ry, rw, rh = self._scale_roi(13, 1951, 1148, 157)
        prompt_region = (rx, ry, rw, rh)

        score_skip = self._get_best_score("enter_skip_prompt.png", prompt_region)
        score_claim = self._get_best_score("gacha_prompt_area.png", prompt_region)

        result = "none"
        if score_skip >= 0.65:
            result = "skip"
        elif score_claim >= 0.65:
            result = "claim"

        dt = (time.time() - t0) * 1000
        self.log(f"[prompt] 判态={result} skip={score_skip:.3f} claim={score_claim:.3f} 耗时={dt:.0f}ms")
        return result

    def _get_best_score(self, template_name, region):
        """在区域中搜索模板, 返回最佳匹配分数 (不设阈值)"""
        path = self._get_img_path(template_name)
        if not path:
            return 0.0
        region_tuple = self.regions.get(region, region) if isinstance(region, str) else region
        screen = self.capture_region(region_tuple)
        tpl = self._load_template(path)
        if tpl is None:
            return 0.0
        best = 0.0
        for scale in self._get_scales(fast=True):
            h, w = tpl.shape[:2]
            nw, nh = int(w * scale), int(h * scale)
            if nw < 5 or nh < 5 or nw > screen.shape[1] or nh > screen.shape[0]:
                continue
            tpl_s = cv2.resize(tpl, (nw, nh), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(screen, tpl_s, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            if max_val > best:
                best = max_val
        return best

    _DUPLICATE_TEMPLATES = [
        "duplicate_car_title.png", "duplicate_car.png", "duplicate_car_2.png"
    ]

    def _find_in_screen(self, template_name, screen, region, threshold=0.75, ref_w=None):
        """在预捕获的截图中搜索模板 (不重复截图, 供多线程并行搜索使用)"""
        path = self._get_img_path(template_name)
        if not path:
            return None
        tpl = self._load_template(path)
        if tpl is None:
            return None
        for scale in self._get_scales(fast=True, ref_w=ref_w):
            h, w = tpl.shape[:2]
            nw, nh = int(w * scale), int(h * scale)
            if nw < 5 or nh < 5 or nw > screen.shape[1] or nh > screen.shape[0]:
                continue
            tpl_s = cv2.resize(tpl, (nw, nh), interpolation=cv2.INTER_AREA)
            res = cv2.matchTemplate(screen, tpl_s, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= threshold:
                rx = region[0] if region else 0
                ry = region[1] if region else 0
                self.log(f"[match] {template_name} score={max_val:.3f} scale={scale:.3f}")
                return (max_loc[0] + nw // 2 + rx, max_loc[1] + nh // 2 + ry)
        return None

    def check_duplicate_car(self):
        """多线程并行检测重复车辆弹窗 (捕获一次截图, 3模板并行搜索, cv2.matchTemplate 释放 GIL)"""
        t0 = time.time()
        rx, ry, rw, rh = self._scale_roi(1025, 221, 1938, 484)
        dup_region = (
            max(0, rx - rw // 4), max(0, ry - rh // 2),
            int(rw * 1.5), int(rh * 2.5)
        )
        screen = self.capture_region(dup_region)

        found = [False]

        def search_one(name):
            if found[0]:
                return
            if self._find_in_screen(name, screen, dup_region, self.dup_match_threshold):
                found[0] = True

        threads = []
        for name in self._DUPLICATE_TEMPLATES:
            t = threading.Thread(target=search_one, args=(name,), daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        dt = (time.time() - t0) * 1000
        if found[0]:
            self.log(f"[dup] 判态=True 耗时={dt:.0f}ms")
        return found[0]

    # ==================== 重复车辆处理 ====================

    def handle_duplicate_vehicle(self, exit_menu=False):
        """处理重复车辆弹窗. exit_menu=True 时处理完加一次 ESC 退出抽奖菜单"""
        self._ensure_focus()  # 确保按键能到达游戏窗口

        self.dup_stats["total"] += 1
        price = self._read_duplicate_price()
        threshold = self.price_threshold
        self.log(f"[duplicate] 识别车辆价值≈{price if price else '?'} | 阈值={threshold}")

        if price is not None and price > threshold:
            self.log(f"[duplicate] 价值 > {threshold} → 保留车辆 (回车)")
            self.dup_stats["kept"] += 1
            hw_press("enter")
        else:
            self.log(f"[duplicate] 价值 ≤ {threshold} → 出售车辆 (下移2+回车)")
            self.dup_stats["sold"] += 1
            if price is not None:
                self.dup_stats["earned"] += price
            hw_press("down", delay=0.12)
            time.sleep(0.1)
            hw_press("down", delay=0.12)
            time.sleep(0.1)
            hw_press("enter")
        self._notify_stats()
        time.sleep(0.15)

        if exit_menu:
            # 处理完回到抽奖入口页, 补 ESC 退出菜单
            self.log("[duplicate] ESC 退出菜单归位")
            hw_press("esc")
            time.sleep(0.5)

    def _read_duplicate_price(self):
        """读取重复车辆价格——easyocr 识别 'CR X,XXX,XXX' 中的数字"""
        rx, ry, rw, rh = self._scale_roi(1239, 1675, 1359, 113)
        price_region = (rx, ry, rw, rh)

        try:
            # 先确认价格区域存在
            price_pos = self.find_image("duplicate_car_price.png", price_region, 0.60)
            if not price_pos:
                self.log(f"[price] 未检测到价格区域")
                return None

            price_img = self.capture_region(price_region)
            gray = cv2.cvtColor(price_img, cv2.COLOR_BGR2GRAY)

            # 裁剪右半部分 (跳过 "出售价格：CR " 前缀)
            # 参考分辨率下前缀约占 600px/1359px
            prefix_ratio = 600 / 1359
            crop_x = int(gray.shape[1] * prefix_ratio)
            number_roi = gray[:, crop_x:]

            # 放大 2x 提高 OCR 精度
            number_roi = cv2.resize(number_roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

            # 二值化: 浅色文字 = 价格数字
            _, thresh = cv2.threshold(number_roi, 160, 255, cv2.THRESH_BINARY)

            text = self._ocr_digits_easyocr(thresh)
            if text:
                val = int(text.replace(",", "").replace(" ", "").replace(".", ""))
                self.log(f"[price] OCR 识别: {val:,} CR")
                return val

            avg_b = float(np.mean(gray))
            self.log(f"[price] 区域已确认, 平均亮度={avg_b:.1f} (OCR 未识别)")
            return None
        except Exception as e:
            self.log(f"[price] 读取失败: {e}")
            return None

    def _preload_ocr(self):
        """后台线程预加载 easyocr 模型, 避免首次使用时卡顿.
        daemon=True 确保主线程退出时自动终止.
        """
        if self._easyocr_ready.is_set() or self._easyocr_reader is not None:
            return
        def _load():
            if not self.is_running:
                return
            try:
                self.log("[price] 后台预加载 easyocr 模型...")
                import easyocr
                reader = easyocr.Reader(
                    ["en"], gpu=False,
                    model_storage_directory=os.path.join(SCRIPT_DIR, ".easyocr_models")
                )
                if not self.is_running:
                    return
                self._easyocr_reader = reader
                self._easyocr_ready.set()
                self.log("[price] easyocr 模型就绪")
            except Exception as e:
                self.log(f"[price] easyocr 预加载失败: {e}")
        threading.Thread(target=_load, daemon=True).start()

    def _ocr_digits_easyocr(self, binary_img):
        """使用 easyocr 识别二值化后的数字, 只保留数字和逗号"""
        if not self._easyocr_ready.is_set():
            self.log("[price] easyocr 尚未就绪, 跳过")
            return None
        try:
            results = self._easyocr_reader.readtext(
                binary_img, detail=0,
                allowlist="0123456789,"
            )
            if results:
                # 取最长的数字串 (过滤噪声)
                best = max(results, key=lambda s: len(s.strip()))
                return best.strip().lstrip(",").rstrip(",")
        except Exception as e:
            self.log(f"[price] easyocr 失败: {e}")
        return None

    # ==================== 抽奖主循环 ====================

    def run_wheelspin(self, rounds=10):
        """普通抽奖 (单抽)"""
        self.log(f"===== 开始普通抽奖 (共 {rounds} 次) =====")
        ok = self._gacha_loop(rounds, is_super=False)
        self._log_dup_stats()
        return ok

    def run_super_wheelspin(self, rounds=10):
        """超级抽奖 (三连抽)"""
        self.log(f"===== 开始超级抽奖 (共 {rounds} 次) =====")
        ok = self._gacha_loop(rounds, is_super=True)
        self._log_dup_stats()
        return ok

    def _log_dup_stats(self):
        s = self.dup_stats
        self.log(f"===== 重复车辆统计: 共{s['total']}辆 | "
                 f"入库{s['kept']}辆 | 出售{s['sold']}辆 | "
                 f"收入{s['earned']:,} CR =====")

    def _gacha_loop(self, max_rounds, is_super):
        # 1. 聚焦游戏窗口
        if not self.focus_game():
            self.log("无法聚焦游戏窗口")
            return False

        # 2. 进入菜单并切换到抽奖标签页
        if not self.enter_menu():
            self.log("无法进入主菜单")
            return False

        # 3. 找到并点击入口按钮 (对照 collectionjournal 的查找方式)
        if is_super:
            btn_name = "super_wheelspin_btn.png"
            search_region = "左"
        else:
            btn_name = "wheelspin_btn.png"
            search_region = "右"
        label = "超级抽奖" if is_super else "普通抽奖"
        self._ensure_focus()  # PgDn 后确保焦点
        pos = self.find_image(btn_name, search_region, 0.65, ref_w=3835)
        if not pos:
            self.log(f"未找到{label}按钮")
            return False
        self.log(f"点击{label}入口: {btn_name}")
        hw_click(pos)

        # 4. 主循环 (点击后立即进入抽奖, 直接判定状态)
        for rnd in range(1, max_rounds + 1):
            if not self.is_running:
                return False
            self.log(f"--- 第 {rnd}/{max_rounds} 轮 ---")

            none_count = 0
            while self.is_running:
                self._ensure_focus()

                # 1. 先检测重复车辆 — 低分辨率下"Enter选择"易与"Enter跳过"混淆
                if self.check_duplicate_car():
                    none_count = 0
                    self.log("[state] 重复车辆页面 → 处理")
                    self.handle_duplicate_vehicle(exit_menu=False)
                    continue

                # 2. 再检测 skip/claim/none
                state = self.check_gacha_prompt()

                if state == "none":
                    none_count += 1
                    if none_count >= 10:
                        self.log("连续10次未检测到提示, 判定当前页面...")
                        at_menu = (
                            self.find_image("super_wheelspin_btn.png", region="左", threshold=0.65, ref_w=3835)
                            or self.find_image("wheelspin_btn.png", region="右", threshold=0.65, ref_w=3835)
                        )
                        if at_menu:
                            self.log("检测到抽奖菜单 → 次数已耗尽, ESC 退出")
                            hw_press("esc", delay=0.08)
                            time.sleep(0.5)
                            return True
                        self.log("未识别页面状态, 继续等待...")
                        none_count = 5
                    time.sleep(0.2)
                    continue

                none_count = 0

                if state == "skip":
                    self.log("跳过动画 → Enter")
                    hw_press("enter")
                    time.sleep(0.15)
                    continue

                if state == "claim":
                    self._ensure_focus()
                    if rnd >= max_rounds:
                        self.log("最后一轮 → ESC 领取奖励")
                        hw_press("esc", delay=0.08)
                        time.sleep(0.2)
                        self._handle_all_duplicates()
                        self.log("最后一轮 → ESC 退出菜单归位")
                        hw_press("esc", delay=0.08)
                        time.sleep(0.5)
                        return True
                    else:
                        self.log("领取并继续 → Enter")
                        hw_press("enter")
                        time.sleep(0.3)
                        self._handle_all_duplicates()
                        break

                time.sleep(0.2)

        return True

    def _handle_all_duplicates(self):
        """状态机: 循环处理所有重复车辆弹窗, 直到回到抽奖菜单页"""
        for i in range(5):
            if not self.is_running:
                return
            if self.check_duplicate_car():
                self.log(f"[state] 重复车辆页面 → 处理 (第{i+1}次)")
                self.handle_duplicate_vehicle(exit_menu=False)
                time.sleep(0.15)
            else:
                # 优先检测 skip/claim (可能下一轮已开始)
                prompt = self.check_gacha_prompt()
                if prompt == "skip":
                    self.log(f"[state] 检测到 'skip', 下一轮已开始 → Enter 跳过")
                    self._ensure_focus()
                    hw_press("enter")
                    time.sleep(0.15)
                    break
                if prompt == "claim":
                    self.log(f"[state] 检测到 'claim' 提示, 回到主循环")
                    break
                # 再检测抽奖菜单
                at_menu = (
                    self.find_image("super_wheelspin_btn.png", region="左", threshold=0.65, ref_w=3835)
                    or self.find_image("wheelspin_btn.png", region="右", threshold=0.65, ref_w=3835)
                )
                if at_menu:
                    self.log(f"[state] 抽奖菜单页面, 全部重复车已处理")
                    break
                self.log(f"[state] 未识别页面, 等待重试...")
                time.sleep(0.5)


def main():
    print("GachaCore 模块加载成功。")
    print("运行 test_gacha_gui.py 获取 GUI 测试界面。")


if __name__ == "__main__":
    main()
