"""FH6 Gacha GUI: standalone wheelspins and optional FH6Auto bridge mode."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pynput import keyboard

from gacha_backend import process_running
from gacha_bridge import BridgeController, FH6AutoConfigGuard, validate_fh6auto_pipeline
from gacha_core import GachaCore

APP_DIR = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
INTERNAL_DIR = getattr(sys, "_MEIPASS", APP_DIR)
SETTINGS_FILE = os.path.join(APP_DIR, ".gacha_settings.json")

POLICY_LABELS = {
    "threshold": "按价格判断（OCR失败时保留）",
    "sell_all": "重复车辆全部出售",
    "keep_all": "重复车辆全部保留",
}
LABEL_POLICIES = {label: value for value, label in POLICY_LABELS.items()}

DEFAULTS = {
    "mode": "standalone",
    "normal_rounds": 3,
    "super_rounds": 3,
    "normal_until_empty": False,
    "super_until_empty": False,
    "duplicate_policy": "threshold",
    "price_threshold": 100_000,
    "phase_timeout": 1800,
    "fh6auto_dir": APP_DIR,
    "last_stats": {},
}


def _extract_resources(folder_name):
    source = Path(INTERNAL_DIR) / folder_name
    target = Path(APP_DIR) / folder_name
    if not source.is_dir() or source.resolve() == target.resolve():
        return
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(path, destination)


for _folder in ("images", "assets", ".easyocr_models"):
    _extract_resources(_folder)


def load_settings():
    settings = dict(DEFAULTS)
    try:
        payload = json.loads(Path(SETTINGS_FILE).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            settings.update(payload)
    except (OSError, json.JSONDecodeError):
        pass
    if settings.get("duplicate_policy") not in POLICY_LABELS:
        settings["duplicate_policy"] = "threshold"
    return settings


def save_settings(settings):
    temp = Path(SETTINGS_FILE).with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temp, SETTINGS_FILE)


class GachaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FH6 抽奖助手 · 独立 / 联动")
        self.root.geometry("1120x760")
        self.root.minsize(960, 680)
        self.settings = load_settings()
        self.recovered_config = self._recover_pending_config()
        self.running = False
        self.core = None
        self.bridge = None
        self.config_guard = None
        self.worker = None
        self._keyboard_listener = None
        self.closing = threading.Event()
        self._build_ui()
        if self.recovered_config:
            self._append_log("已恢复上次异常退出遗留的 FH6Auto 配置")
        self._setup_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _recover_pending_config(self):
        directory = self.settings.get("fh6auto_dir") or ""
        backup = Path(directory) / ".gacha_bridge_config_backup.json"
        if os.name != "nt" or not backup.is_file() or process_running("FH6Auto.exe"):
            return False
        try:
            FH6AutoConfigGuard(directory).restore()
            return True
        except Exception:
            return False

    def _build_ui(self):
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 20, "bold"))
        style.configure(
            "Value.TLabel",
            font=("Microsoft YaHei UI", 15, "bold"),
            foreground="#087E8B",
        )

        header = ttk.Frame(self.root, padding=(14, 10))
        header.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(header, textvariable=self.status_var, style="Title.TLabel").pack(
            side=tk.LEFT
        )
        ttk.Label(header, text="Steam 后台模式", foreground="#4F6D7A").pack(
            side=tk.RIGHT
        )

        controls = ttk.LabelFrame(self.root, text="运行设置", padding=12)
        controls.pack(fill=tk.X, padx=12, pady=(0, 8))

        self.mode_var = tk.StringVar(value=self.settings["mode"])
        ttk.Radiobutton(
            controls,
            text="独立抽奖",
            variable=self.mode_var,
            value="standalone",
            command=self._update_mode_ui,
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            controls,
            text="跟随 FH6Auto 自动循环",
            variable=self.mode_var,
            value="bridge",
            command=self._update_mode_ui,
        ).grid(row=0, column=1, columnspan=2, sticky="w")

        self.normal_var = tk.StringVar(value=str(self.settings["normal_rounds"]))
        self.super_var = tk.StringVar(value=str(self.settings["super_rounds"]))
        self.normal_empty_var = tk.BooleanVar(
            value=bool(self.settings["normal_until_empty"])
        )
        self.super_empty_var = tk.BooleanVar(
            value=bool(self.settings["super_until_empty"])
        )
        self.price_var = tk.StringVar(value=str(self.settings["price_threshold"]))
        self.timeout_var = tk.StringVar(value=str(self.settings["phase_timeout"]))
        self.policy_var = tk.StringVar(
            value=POLICY_LABELS[self.settings["duplicate_policy"]]
        )

        ttk.Label(controls, text="普通抽奖").grid(row=1, column=0, sticky="e", pady=7)
        ttk.Entry(controls, textvariable=self.normal_var, width=9).grid(
            row=1, column=1, sticky="w", padx=8
        )
        ttk.Checkbutton(controls, text="抽到耗尽", variable=self.normal_empty_var).grid(
            row=1, column=2, sticky="w"
        )
        ttk.Label(controls, text="超级抽奖").grid(
            row=1, column=3, sticky="e", padx=(24, 0)
        )
        ttk.Entry(controls, textvariable=self.super_var, width=9).grid(
            row=1, column=4, sticky="w", padx=8
        )
        ttk.Checkbutton(controls, text="抽到耗尽", variable=self.super_empty_var).grid(
            row=1, column=5, sticky="w"
        )

        ttk.Label(controls, text="重复车策略").grid(row=2, column=0, sticky="e", pady=7)
        policy_box = ttk.Combobox(
            controls,
            textvariable=self.policy_var,
            values=list(POLICY_LABELS.values()),
            state="readonly",
            width=27,
        )
        policy_box.grid(row=2, column=1, columnspan=2, sticky="w", padx=8)
        policy_box.bind("<<ComboboxSelected>>", lambda _event: self._update_mode_ui())
        ttk.Label(controls, text="价格阈值").grid(
            row=2, column=3, sticky="e", padx=(24, 0)
        )
        self.price_entry = ttk.Entry(controls, textvariable=self.price_var, width=14)
        self.price_entry.grid(row=2, column=4, sticky="w", padx=8)
        ttk.Label(controls, text="CR").grid(row=2, column=5, sticky="w")

        ttk.Label(controls, text="阶段超时").grid(row=3, column=0, sticky="e", pady=7)
        ttk.Entry(controls, textvariable=self.timeout_var, width=9).grid(
            row=3, column=1, sticky="w", padx=8
        )
        ttk.Label(controls, text="秒").grid(row=3, column=2, sticky="w")

        self.bridge_frame = ttk.Frame(controls)
        self.bridge_frame.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(6, 0))
        self.fh6auto_dir_var = tk.StringVar(value=self.settings["fh6auto_dir"])
        ttk.Label(self.bridge_frame, text="FH6Auto 目录").pack(side=tk.LEFT)
        ttk.Entry(self.bridge_frame, textvariable=self.fh6auto_dir_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=8
        )
        ttk.Button(
            self.bridge_frame, text="选择", command=self._choose_fh6auto_dir
        ).pack(side=tk.LEFT)
        ttk.Label(
            self.bridge_frame,
            text="联动会启动官方 FH6Auto.exe，你仍需在官方界面点击开始",
            foreground="#B45309",
        ).pack(side=tk.LEFT, padx=12)

        buttons = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        buttons.pack(fill=tk.X)
        self.start_btn = ttk.Button(buttons, text="开始 (F8)", command=self._start)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(
            buttons, text="紧急停止", command=self._stop, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=8)
        ttk.Label(
            buttons,
            text="联动运行时 F8 同时停止 FH6Auto 与抽奖器；F9 由桥接握手专用",
            foreground="#9B2226",
        ).pack(side=tk.LEFT, padx=12)

        stats_frame = ttk.LabelFrame(self.root, text="本次累计", padding=8)
        stats_frame.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.stats_labels = {}
        stats = [
            ("normal_spins", "普通"),
            ("super_spins", "超级"),
            ("total", "重复车"),
            ("kept", "保留"),
            ("sold", "出售"),
            ("earned", "收入 CR"),
            ("ocr_failed", "OCR失败"),
            ("bridge_cycles", "联动轮次"),
        ]
        last_stats = self.settings.get("last_stats") or {}
        for index, (key, label) in enumerate(stats):
            box = ttk.Frame(stats_frame)
            box.grid(row=0, column=index, padx=10, sticky="nsew")
            stats_frame.columnconfigure(index, weight=1)
            ttk.Label(box, text=label).pack()
            value = last_stats.get(key, 0)
            self.stats_labels[key] = ttk.Label(
                box, text=str(value), style="Value.TLabel"
            )
            self.stats_labels[key].pack()

        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.log_text = tk.Text(
            log_frame, state=tk.DISABLED, font=("Consolas", 12), wrap=tk.WORD
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self._update_mode_ui()

    def _update_mode_ui(self):
        if self.mode_var.get() == "bridge":
            self.bridge_frame.grid()
        else:
            self.bridge_frame.grid_remove()
        self.price_entry.configure(
            state="normal"
            if LABEL_POLICIES.get(self.policy_var.get()) == "threshold"
            else "disabled"
        )

    def _choose_fh6auto_dir(self):
        path = filedialog.askdirectory(initialdir=self.fh6auto_dir_var.get() or APP_DIR)
        if path:
            self.fh6auto_dir_var.set(path)

    def _setup_hotkeys(self):
        def on_press(key):
            if key == keyboard.Key.f8:
                self.root.after(0, self._on_f8)
            elif key == keyboard.Key.f9:
                self.root.after(0, self._on_f9)

        self._keyboard_listener = keyboard.Listener(on_press=on_press)
        self._keyboard_listener.start()

    def _on_f8(self):
        if self.running:
            self._stop()
        else:
            self._start()

    def _on_f9(self):
        if self.running and self.mode_var.get() == "standalone":
            self._stop()

    @staticmethod
    def _parse_int(value, default, minimum=0):
        try:
            return max(minimum, int(str(value).replace(",", "").strip()))
        except ValueError:
            return default

    def _collect_settings(self):
        normal = self._parse_int(self.normal_var.get(), 0)
        super_rounds = self._parse_int(self.super_var.get(), 0)
        if self.normal_empty_var.get():
            normal = 999
        if self.super_empty_var.get():
            super_rounds = 999
        if normal <= 0 and super_rounds <= 0:
            raise ValueError("请至少配置一种抽奖次数，或勾选抽到耗尽")
        policy = LABEL_POLICIES[self.policy_var.get()]
        settings = {
            "mode": self.mode_var.get(),
            "normal_rounds": self._parse_int(self.normal_var.get(), 0),
            "super_rounds": self._parse_int(self.super_var.get(), 0),
            "normal_until_empty": bool(self.normal_empty_var.get()),
            "super_until_empty": bool(self.super_empty_var.get()),
            "duplicate_policy": policy,
            "price_threshold": self._parse_int(self.price_var.get(), 100_000),
            "phase_timeout": self._parse_int(self.timeout_var.get(), 1800, 60),
            "fh6auto_dir": self.fh6auto_dir_var.get().strip(),
            "last_stats": self.settings.get("last_stats", {}),
        }
        return settings, normal, super_rounds

    def _start(self):
        if self.running:
            return
        try:
            self.settings, normal, super_rounds = self._collect_settings()
            save_settings(self.settings)
            if self.settings["mode"] == "bridge":
                self._validate_bridge_install()
        except Exception as exc:
            messagebox.showerror("无法开始", str(exc), parent=self.root)
            return

        self.running = True
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_var.set(
            "联动监听中" if self.settings["mode"] == "bridge" else "独立抽奖运行中"
        )
        self.bridge = None
        self.config_guard = None
        self._reset_stats()
        self.core = GachaCore(
            log_callback=self._log,
            stats_callback=self._on_stats,
            duplicate_policy=self.settings["duplicate_policy"],
            price_threshold=self.settings["price_threshold"],
            phase_timeout=self.settings["phase_timeout"],
        )
        if self.settings["mode"] == "bridge":
            self.worker = threading.Thread(
                target=self._run_bridge, args=(normal, super_rounds), daemon=True
            )
        else:
            self.worker = threading.Thread(
                target=self._run_standalone, args=(normal, super_rounds), daemon=True
            )
        self.worker.start()

    def _validate_bridge_install(self):
        directory = Path(self.settings["fh6auto_dir"])
        exe = directory / "FH6Auto.exe"
        config_path = directory / "config.json"
        if not exe.is_file() or not config_path.is_file():
            raise FileNotFoundError("所选目录必须同时包含 FH6Auto.exe 和 config.json")
        if process_running("FH6Auto.exe"):
            raise RuntimeError(
                "请先关闭正在运行的 FH6Auto；桥接器需要在启动前临时启用诊断日志"
            )
        config = json.loads(config_path.read_text(encoding="utf-8"))
        route_errors = validate_fh6auto_pipeline(config)
        if route_errors:
            raise ValueError(
                "FH6Auto 联动要求 1→2→3→4→1 完整回环：\n" + "\n".join(route_errors)
            )

    def _run_standalone(self, normal, super_rounds):
        try:
            ok = self.core.run_sequence(normal, super_rounds)
            self._log("独立抽奖完成" if ok else "独立抽奖未安全完成")
        except Exception as exc:
            self._log(f"独立抽奖异常: {exc}")
        finally:
            self.root.after(0, self._on_done)

    def _run_bridge(self, normal, super_rounds):
        directory = self.settings["fh6auto_dir"]
        try:
            self.config_guard = FH6AutoConfigGuard(directory)
            self.config_guard.apply()
            self.bridge = BridgeController(
                directory,
                lambda: self.core.run_sequence(normal, super_rounds, reset_stats=False),
                log=self._log,
                cycle_callback=lambda count: self.root.after(
                    0, self._update_bridge_cycles, count
                ),
            )
            os.startfile(str(Path(directory) / "FH6Auto.exe"))
            ok = self.bridge.run()
            self._log("联动任务完成" if ok else "联动任务已停止或需要人工检查")
        except Exception as exc:
            self._log(f"联动启动/运行失败: {exc}")
        finally:
            try:
                if self.config_guard:
                    if process_running("FH6Auto.exe") and not self.closing.is_set():
                        self._log("请关闭 FH6Auto；关闭后桥接器会恢复其关机/调试配置")
                    while process_running("FH6Auto.exe") and not self.closing.wait(1.0):
                        pass
                    still_running = process_running("FH6Auto.exe")
                    self.config_guard.restore(keep_backup=still_running)
                    if still_running:
                        self._log(
                            "FH6Auto 仍在运行，已保留配置恢复备份；"
                            "下次联动会继续使用原始值"
                        )
            except Exception as exc:
                self._log(f"恢复 FH6Auto 配置失败，已保留备份供下次恢复: {exc}")
            finally:
                try:
                    self.root.after(0, self._on_done)
                except tk.TclError:
                    pass

    def _stop(self):
        if self.core:
            self.core.stop()
        if self.bridge:
            self.bridge.stop()
        self.status_var.set("正在停止...")
        self._log("收到紧急停止请求")

    def _on_done(self):
        if self.core:
            self.core.close()
        self.running = False
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_var.set("就绪")

    def _reset_stats(self):
        zeros = {key: 0 for key in self.stats_labels}
        for label in self.stats_labels.values():
            label.configure(text="0")
        self.settings["last_stats"] = zeros
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _on_stats(self, stats):
        self.root.after(0, self._update_stats, dict(stats))

    def _update_stats(self, stats):
        if self.settings.get("mode") == "bridge" and self.bridge:
            stats["bridge_cycles"] = self.bridge.completed_cycles
        for key, value in stats.items():
            if key in self.stats_labels:
                self.stats_labels[key].configure(
                    text=f"{value:,}" if isinstance(value, int) else str(value)
                )
        self.settings["last_stats"] = {
            key: int(stats.get(key, 0)) for key in self.stats_labels
        }
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _update_bridge_cycles(self, count):
        self.stats_labels["bridge_cycles"].configure(text=str(count))
        self.settings.setdefault("last_stats", {})["bridge_cycles"] = count
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _log(self, message):
        self.root.after(0, self._append_log, str(message))

    def _append_log(self, message):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _on_closing(self):
        self.closing.set()
        self._stop()
        try:
            if self._keyboard_listener:
                self._keyboard_listener.stop()
        finally:
            self.root.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    root = tk.Tk()
    app = GachaApp(root)
    if "--smoke-test" in sys.argv:
        root.after(2000, app._on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
