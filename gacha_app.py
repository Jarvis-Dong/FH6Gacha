"""
gacha_app.py - FH6 抽奖助手 正式版 GUI
"""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time
import os
import sys
import json
import shutil
import logging
from datetime import datetime

from gacha_core import GachaCore

# ==================== 自动解压资源 ====================

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_internal_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return APP_DIR


def _auto_extract_dir(folder_name):
    internal = os.path.join(_get_internal_dir(), folder_name)
    external = os.path.join(APP_DIR, folder_name)
    if not os.path.isdir(internal):
        return
    os.makedirs(external, exist_ok=True)
    for root, dirs, files in os.walk(internal):
        rel = os.path.relpath(root, internal)
        target_root = external if rel == "." else os.path.join(external, rel)
        os.makedirs(target_root, exist_ok=True)
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join(target_root, f)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)


_auto_extract_dir("images")
_auto_extract_dir("assets")
_auto_extract_dir(".easyocr_models")

# ==================== 设置持久化 ====================

SETTINGS_FILE = os.path.join(APP_DIR, ".gacha_settings.json")

DEFAULT_SETTINGS = {
    "normal_rounds": 10,
    "super_rounds": 5,
    "price_threshold": 100000,
    "dup_match_threshold": 0.80,
}


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULT_SETTINGS.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ==================== GUI ====================

FONT = ("Microsoft YaHei", 12)
FONT_BOLD = ("Microsoft YaHei", 12, "bold")
FONT_BTN = ("Microsoft YaHei", 14, "bold")
FONT_BIG = ("Microsoft YaHei", 16, "bold")
FONT_LOG = ("Consolas", 11)


class GachaAppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FH6 抽奖助手")
        self.root.geometry("900x680")
        self.root.minsize(800, 600)

        self.settings = load_settings()
        self.core = GachaCore(log_callback=self._on_log, stats_callback=self._on_stats)
        self.running = False
        self._price_fmt_lock = False
        self._log_file = None

        self._setup_log_file()
        self._build_ui()
        self._apply_settings_to_ui()
        self._setup_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ==================== 日志文件 ====================

    def _setup_log_file(self):
        os.makedirs(os.path.join(APP_DIR, "logs"), exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(APP_DIR, "logs", f"gacha_{ts}.log")
        self._log_file = open(path, "w", encoding="utf-8")

    # ==================== 全局热键 ====================

    def _setup_hotkeys(self):
        try:
            from pynput.keyboard import GlobalHotKeys

            def on_f8():
                self.root.after(0, self._start)

            def on_f9():
                self.root.after(0, self._stop)

            self._hotkey_listener = GlobalHotKeys(
                {"<F8>": on_f8, "<F9>": on_f9}
            )
            self._hotkey_listener.start()
            self.log("全局热键已注册: F8=开始  F9=停止")
        except Exception as e:
            self.log(f"热键注册失败: {e}")
            self._hotkey_listener = None

    # ==================== UI ====================

    def _build_ui(self):
        # 顶部状态栏
        top_bar = ttk.Frame(self.root, padding=5)
        top_bar.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(top_bar, textvariable=self.status_var, font=FONT_BIG).pack(side=tk.LEFT)
        ttk.Label(top_bar, text="F8 开始  |  F9 停止", font=FONT).pack(side=tk.RIGHT)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # 中部: 三列布局
        middle = ttk.Frame(self.root)
        middle.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        middle.columnconfigure(1, weight=1)
        middle.columnconfigure(2, weight=1)

        # 左列: 按钮
        left_col = ttk.Frame(middle, padding=5)
        left_col.grid(row=0, column=0, sticky=tk.N, padx=(0, 10))

        self.start_btn = ttk.Button(left_col, text="▶  开始 (F8)", command=self._start)
        self.start_btn.pack(fill=tk.X, pady=3, ipady=8)

        self.stop_btn = ttk.Button(left_col, text="■  停止 (F9)", command=self._stop)
        self.stop_btn.pack(fill=tk.X, pady=3, ipady=8)

        ttk.Separator(left_col, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        self.support_btn = ttk.Button(
            left_col, text="❤  支持 / 检查更新", command=self._open_support
        )
        self.support_btn.pack(fill=tk.X, pady=3, ipady=8)

        # 中列: 设置
        mid_col = ttk.Frame(middle, padding=10)
        mid_col.grid(row=0, column=1, sticky=tk.NSEW, padx=5)

        ttk.Label(mid_col, text="抽奖设置", font=FONT_BOLD).pack(anchor=tk.W, pady=(0, 8))

        for label, var_name, default in [
            ("普通抽奖次数", "normal_rounds", 10),
            ("超级抽奖次数", "super_rounds", 5),
        ]:
            f = ttk.Frame(mid_col)
            f.pack(fill=tk.X, pady=3)
            ttk.Label(f, text=label, font=FONT, width=14).pack(side=tk.LEFT)
            var = tk.StringVar(value=str(default))
            setattr(self, f"{var_name}_var", var)
            ttk.Entry(f, textvariable=var, font=FONT, width=8).pack(side=tk.LEFT)

        ttk.Separator(mid_col, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        f = ttk.Frame(mid_col)
        f.pack(fill=tk.X, pady=3)
        ttk.Label(f, text="价格阈值", font=FONT, width=14).pack(side=tk.LEFT)
        self.price_var = tk.StringVar(value="100,000")
        self.price_var.trace_add("write", self._fmt_price)
        ttk.Entry(f, textvariable=self.price_var, font=FONT, width=12).pack(side=tk.LEFT)

        f = ttk.Frame(mid_col)
        f.pack(fill=tk.X, pady=3)
        ttk.Label(f, text="重复车检测阈值", font=FONT, width=14).pack(side=tk.LEFT)
        self.dup_threshold_var = tk.StringVar(value="0.80")
        ttk.Entry(f, textvariable=self.dup_threshold_var, font=FONT, width=6).pack(side=tk.LEFT)

        # 右列: 统计
        right_col = ttk.Frame(middle, padding=10)
        right_col.grid(row=0, column=2, sticky=tk.N, padx=5)

        ttk.Label(right_col, text="本次统计", font=FONT_BOLD).pack(anchor=tk.W, pady=(0, 8))

        stats_items = [
            ("累计车辆:", "total", "0"),
            ("入库:", "kept", "0"),
            ("出售:", "sold", "0"),
            ("收入:", "earned", "0 CR"),
        ]
        self._stats_vars = {}
        for label, key, default in stats_items:
            f = ttk.Frame(right_col)
            f.pack(fill=tk.X, pady=4)
            ttk.Label(f, text=label, font=FONT, width=9).pack(side=tk.LEFT)
            var = tk.StringVar(value=default)
            self._stats_vars[key] = var
            ttk.Label(f, textvariable=var, font=FONT_BOLD).pack(side=tk.LEFT)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10)

        # 底部: 日志
        log_frame = ttk.Frame(self.root, padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        self.log_text = tk.Text(
            log_frame,
            state=tk.DISABLED,
            font=FONT_LOG,
            bg="white",
            fg="#222",
            wrap=tk.WORD,
        )
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # ==================== 价格格式化 ====================

    def _fmt_price(self, *_):
        if self._price_fmt_lock:
            return
        self._price_fmt_lock = True
        try:
            raw = self.price_var.get().replace(",", "").strip()
            if raw == "" or raw == "-":
                self._price_fmt_lock = False
                return
            if raw.isdigit():
                formatted = f"{int(raw):,}"
                self.price_var.set(formatted)
        finally:
            self._price_fmt_lock = False

    # ==================== 日志 ====================

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"{ts} {msg}"
        if self._log_file:
            try:
                self._log_file.write(line + "\n")
                self._log_file.flush()
            except Exception:
                pass

    def _on_log(self, msg):
        self.log(msg)
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ==================== 统计回调 ====================

    def _on_stats(self, stats):
        self.root.after(0, self._update_stats, stats)

    def _update_stats(self, stats):
        self._stats_vars["total"].set(str(stats["total"]))
        self._stats_vars["kept"].set(str(stats["kept"]))
        self._stats_vars["sold"].set(str(stats["sold"]))
        self._stats_vars["earned"].set(f"{stats['earned']:,} CR")

    # ==================== 设置 ====================

    def _apply_settings_to_ui(self):
        s = self.settings
        self.normal_rounds_var.set(str(s.get("normal_rounds", 10)))
        self.super_rounds_var.set(str(s.get("super_rounds", 5)))
        self.price_var.set(f"{int(s.get('price_threshold', 100000)):,}")
        self.dup_threshold_var.set(str(s.get("dup_match_threshold", 0.80)))

    def _read_ui_settings(self):
        try:
            normal = int(self.normal_rounds_var.get())
        except ValueError:
            normal = 10
        try:
            super_r = int(self.super_rounds_var.get())
        except ValueError:
            super_r = 5
        try:
            price_str = self.price_var.get().replace(",", "").strip()
            price = int(price_str)
        except ValueError:
            price = 100000
        try:
            dup_th = float(self.dup_threshold_var.get())
        except ValueError:
            dup_th = 0.80

        self.core.price_threshold = price
        self.core.dup_match_threshold = dup_th

        s = {
            "normal_rounds": normal,
            "super_rounds": super_r,
            "price_threshold": price,
            "dup_match_threshold": dup_th,
        }
        self.settings = s
        save_settings(s)
        return normal, super_r

    # ==================== 运行控制 ====================

    def _start(self):
        if self.running:
            self._on_log("已有任务在运行")
            return

        normal_rounds, super_rounds = self._read_ui_settings()

        self.running = True
        self.core.is_running = True
        self.status_var.set("运行中...")
        self._on_log(f"===== 启动抽奖 (普通:{normal_rounds}次 | 超级:{super_rounds}次) =====")

        def _run():
            try:
                if normal_rounds > 0:
                    self.core.run_wheelspin(normal_rounds)
                if super_rounds > 0 and self.core.is_running:
                    self.core.run_super_wheelspin(super_rounds)
                self._on_log("===== 全部抽奖完成 =====")
            except Exception as e:
                self._on_log(f"运行异常: {e}")
            finally:
                self.running = False
                self.root.after(0, lambda: self.status_var.set("就绪"))

        threading.Thread(target=_run, daemon=True).start()

    def _stop(self):
        self.core.is_running = False
        self.running = False
        self.status_var.set("已停止")
        self._on_log("⏹ 用户停止")

    # ==================== 支持弹窗 ====================

    def _open_support(self):
        win = tk.Toplevel(self.root)
        win.title("支持 / 检查更新")
        win.geometry("420x480")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        f = ttk.Frame(win, padding=15)
        f.pack(fill=tk.BOTH, expand=True)

        ttk.Label(f, text="FH6 抽奖助手", font=("Microsoft YaHei", 16, "bold")).pack()

        # QR 码
        qr_path = os.path.join(APP_DIR, "assets", "qrcode.png")
        if os.path.exists(qr_path):
            try:
                img = Image.open(qr_path)
                img = img.resize((200, 200), Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(img)
                lbl = ttk.Label(f, image=tk_img)
                lbl.image = tk_img
                lbl.pack(pady=8)
            except Exception:
                ttk.Label(f, text="(二维码加载失败)").pack(pady=8)

        ttk.Label(f, text="扫码赞助支持开发者", font=FONT).pack()

        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Label(f, text="检查更新:", font=FONT_BOLD).pack(anchor=tk.W)
        ttk.Label(
            f,
            text="https://github.com/SaYa-t/FH6-AUTOGacha/releases",
            font=("Consolas", 10),
            foreground="#0366d6",
            cursor="hand2",
        ).pack(anchor=tk.W, pady=2)

        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=10)

    # ==================== 关闭 ====================

    def _on_closing(self):
        self.core.is_running = False
        self.running = False
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass
        self.root.destroy()


def main():
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    root = tk.Tk()
    GachaAppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
