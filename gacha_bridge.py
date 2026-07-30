"""Fail-safe bridge between the untouched FH6Auto executable and GachaCore."""

from __future__ import annotations

import glob
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from gacha_backend import send_global_hotkey

EVENT_NEW_LOOP = "new_loop"
EVENT_FINAL = "final"
EVENT_STOPPED = "stopped"
EVENT_PAUSED = "paused"
EVENT_RESUMED = "resumed"


def classify_fh6auto_message(message: str) -> str | None:
    """Map the stable FH6Auto log phrases used by the bridge handshake."""
    if "开启新一轮大循环" in message:
        return EVENT_NEW_LOOP
    if "达到设定的总循环次数" in message:
        return EVENT_FINAL
    if "任务已停止,所有物理按键状态已强制重置" in message:
        return EVENT_STOPPED
    if "任务已暂停" in message:
        return EVENT_PAUSED
    if "任务已恢复" in message:
        return EVENT_RESUMED
    return None


def validate_fh6auto_pipeline(config: dict) -> list[str]:
    """Return reasons the route is unsafe for sell-boundary bridging."""
    errors = []
    expected_next = (2, 3, 4, 1)
    for index, next_step in enumerate(expected_next, 1):
        if not bool(config.get(f"chk_{index}", False)):
            errors.append(f"第{index}阶段未勾选继续")
        try:
            actual = int(config.get(f"next_{index}", 0))
        except (TypeError, ValueError):
            actual = 0
        if actual != next_step:
            errors.append(f"第{index}阶段下一步应为{next_step}，当前为{actual}")
    try:
        if int(config.get("global_loops", 0)) < 1:
            errors.append("大循环次数必须至少为1")
    except (TypeError, ValueError):
        errors.append("大循环次数不是有效整数")
    return errors


class DiagnosticLogFollower:
    """Follow new FH6Auto diagnostic JSONL files without replaying old sessions."""

    def __init__(self, fh6auto_dir: str | os.PathLike[str]):
        self.root = Path(fh6auto_dir) / "diagnostic_reports"
        self._offsets: dict[Path, int] = {}
        self.active_session_dir: Path | None = None
        for path in self._paths():
            self._offsets[path] = path.stat().st_size

    def _paths(self) -> list[Path]:
        return sorted(
            (Path(p) for p in glob.glob(str(self.root / "*" / "logs.jsonl"))),
            key=lambda path: path.stat().st_mtime,
        )

    def _read_events(self):
        for path in self._paths():
            if path not in self._offsets:
                self._offsets[path] = 0
            try:
                with path.open("r", encoding="utf-8-sig") as stream:
                    stream.seek(self._offsets[path])
                    for line in stream:
                        try:
                            payload = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        message = str(payload.get("message", ""))
                        event = classify_fh6auto_message(message)
                        if event:
                            self.active_session_dir = path.parent
                            yield event, message
                    self._offsets[path] = stream.tell()
            except (FileNotFoundError, OSError):
                continue

    def wait(self, timeout=0.5):
        deadline = time.monotonic() + max(0, timeout)
        while True:
            events = list(self._read_events())
            if events:
                return events
            if time.monotonic() >= deadline:
                return []
            time.sleep(0.1)


@dataclass
class FH6AutoConfigGuard:
    """Temporarily enable bridge observability and disable final destructive actions."""

    fh6auto_dir: str

    def __post_init__(self):
        self.path = Path(self.fh6auto_dir) / "config.json"
        self.backup_path = Path(self.fh6auto_dir) / ".gacha_bridge_config_backup.json"
        self.original: dict[str, object] = {}
        self.forced = {
            "diagnostic_mode": True,
            "debug_screenshots": True,
            "auto_close_game": False,
            "auto_shutdown": False,
        }

    def apply(self) -> None:
        if not self.path.is_file():
            raise FileNotFoundError(f"找不到 FH6Auto 配置: {self.path}")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if self.backup_path.is_file():
            self.original = json.loads(self.backup_path.read_text(encoding="utf-8"))
        else:
            self.original = {key: data.get(key) for key in self.forced}
            self.backup_path.write_text(
                json.dumps(self.original, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        data.update(self.forced)
        self._write(data)

    def restore(self, *, keep_backup=False) -> None:
        if not self.original and self.backup_path.is_file():
            try:
                self.original = json.loads(self.backup_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return
        if not self.original or not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for key, forced_value in self.forced.items():
            if data.get(key) == forced_value:
                original_value = self.original.get(key)
                if original_value is None:
                    data.pop(key, None)
                else:
                    data[key] = original_value
        self._write(data)
        if not keep_backup:
            try:
                self.backup_path.unlink()
            except FileNotFoundError:
                pass

    def _write(self, data) -> None:
        temp = self.path.with_suffix(".json.gacha-bridge.tmp")
        temp.write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        os.replace(temp, self.path)


class BridgeController:
    """Pause FH6Auto at loop boundaries, run gacha, then resume safely."""

    def __init__(
        self,
        fh6auto_dir,
        run_gacha,
        log=None,
        handshake_timeout=8,
        *,
        follower=None,
        send_hotkey=send_global_hotkey,
        cycle_callback=None,
        final_ready=None,
        final_timeout=120,
    ):
        self.fh6auto_dir = str(fh6auto_dir)
        self.run_gacha = run_gacha
        self.log = log or (lambda _message: None)
        self.handshake_timeout = max(0.1, float(handshake_timeout))
        self.stop_event = threading.Event()
        self.follower = follower or DiagnosticLogFollower(self.fh6auto_dir)
        self.send_hotkey = send_hotkey
        self.cycle_callback = cycle_callback
        self.final_ready = final_ready or self._wait_for_final_report
        self.final_timeout = max(5, int(final_timeout))
        self._pending_events = deque()
        self.final_pending = False
        self.paused_by_bridge = False
        self.takeover_started = False
        self.completed_cycles = 0
        self.last_error = None

    def stop(self):
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        if self.takeover_started:
            self._safe_stop_fh6auto()
            return
        try:
            self.send_hotkey("f8")
            self.log("已向 FH6Auto 发送 F8 安全停止")
        except Exception as exc:
            self.log(f"FH6Auto 安全停止失败，请在官方界面手工停止: {exc}")

    def run(self):
        self.log("联动监听已启动；请在 FH6Auto 中正常开始四阶段流程")
        try:
            while not self.stop_event.is_set():
                for event, message in self._poll_events(0.5):
                    self.log(f"[FH6Auto] {message}")
                    if event == EVENT_NEW_LOOP:
                        if not self._run_intermediate_cycle():
                            return False
                    elif event == EVENT_FINAL:
                        self.final_pending = True
                        self.log("已识别最后一轮完成，等待 FH6Auto 诊断报告落盘")
                        if not self.final_ready():
                            return self._fail(
                                "未确认 FH6Auto 最终诊断会话结束；未开始最后一轮开奖"
                            )
                        self.log("FH6Auto 最终诊断会话已结束，开始最后一轮开奖")
                        ok = self._run_gacha_safely()
                        if ok:
                            self._record_cycle()
                        return ok
                    elif event == EVENT_STOPPED and self.final_pending:
                        # Reserved for a future version that persists this UI-only log.
                        self.log("FH6Auto 已停止，开始最后一轮开奖")
                        ok = self._run_gacha_safely()
                        if ok:
                            self._record_cycle()
                        return ok
        except Exception as exc:
            return self._fail(f"联动控制异常: {exc}")
        return False

    def _run_intermediate_cycle(self):
        self.log("检测到卖车后的循环边界，请求 FH6Auto 暂停")
        self.takeover_started = True
        self.send_hotkey("f9")
        if not self._wait_for(EVENT_PAUSED):
            return self._fail("未收到 FH6Auto 暂停确认；未开始开奖")
        self.paused_by_bridge = True
        # FH6Auto writes the pause log before releasing held keys. Its input
        # layer then blocks on check_pause(), so only a short settle is needed.
        time.sleep(0.5)
        self.log("FH6Auto 已暂停并完成输入释放，开始安全开奖")
        if not self._run_gacha_safely():
            return self._fail("开奖未安全完成；已请求 FH6Auto 安全停止")
        if self.stop_event.is_set():
            return False
        self.log("开奖完成且已回到主菜单，请求 FH6Auto 恢复")
        self.send_hotkey("f9")
        if not self._wait_for(EVENT_RESUMED):
            return self._fail("未收到 FH6Auto 恢复确认；已请求安全停止")
        self.paused_by_bridge = False
        self.takeover_started = False
        self._record_cycle()
        self.log(f"联动第 {self.completed_cycles} 轮完成")
        return True

    def _run_gacha_safely(self):
        try:
            return bool(self.run_gacha())
        except Exception as exc:
            self.log(f"联动开奖异常: {exc}")
            return False

    def _wait_for(self, expected):
        deadline = time.monotonic() + self.handshake_timeout
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            events = self._poll_events(0.25)
            for index, (event, message) in enumerate(events):
                self.log(f"[FH6Auto] {message}")
                if event == expected:
                    self._pending_events.extend(events[index + 1 :])
                    return True
        return False

    def _poll_events(self, timeout):
        if self._pending_events:
            events = list(self._pending_events)
            self._pending_events.clear()
            return events
        return self.follower.wait(timeout)

    def _record_cycle(self):
        self.completed_cycles += 1
        if self.cycle_callback:
            self.cycle_callback(self.completed_cycles)

    def _wait_for_final_report(self):
        session_dir = getattr(self.follower, "active_session_dir", None)
        if not session_dir:
            return False
        report_path = Path(session_dir) / "report.txt"
        deadline = time.monotonic() + self.final_timeout
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            try:
                if report_path.is_file() and report_path.stat().st_size > 0:
                    # report.txt is the final file produced by
                    # finish_diagnostic_trace_session. Leave a short buffer for
                    # OCR/GDI/background-input cleanup in stop_all.
                    time.sleep(2.0)
                    return True
            except OSError:
                pass
            time.sleep(0.2)
        return False

    def _fail(self, message):
        self.last_error = message
        self.log(message)
        self.stop_event.set()
        self._safe_stop_fh6auto()
        return False

    def _safe_stop_fh6auto(self):
        if not self.takeover_started:
            return
        try:
            self.send_hotkey("f8")
            self.log("已向 FH6Auto 发送 F8 安全停止")
        except Exception as exc:
            self.log(f"FH6Auto 安全停止失败，请在任务管理器中结束它: {exc}")
        finally:
            self.takeover_started = False
            self.paused_by_bridge = False
