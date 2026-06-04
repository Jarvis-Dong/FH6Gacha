"""
gacha_app.py - FH6 抽奖自动化 日常使用GUI
日志本地持久化 + 设置记忆 + F8紧急停止
"""
import sys
import tkinter as tk
from tkinter import ttk
import threading
import time
import json
import os
import shutil
import webbrowser
import ctypes
from PIL import Image, ImageTk
from pynput import keyboard

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_internal_dir():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return APP_DIR


def _auto_extract_dir(folder_name):
    """从打包内部释放资源文件夹到外部, 已存在文件不覆盖"""
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
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass


_auto_extract_dir("images")
_auto_extract_dir("assets")
_auto_extract_dir(".easyocr_models")

SETTINGS_FILE = os.path.join(APP_DIR, ".gacha_settings.json")


def load_settings():
    defaults = {"normal_rounds": 3, "super_rounds": 3, "price_threshold": 100000}
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in defaults:
                if k not in data:
                    data[k] = defaults[k]
            return data
    except Exception:
        pass
    return defaults


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass


class GachaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FH6 抽奖助手")
        self.root.geometry("960x700")
        self.root.minsize(800, 500)

        self.settings = load_settings()
        self.running = False
        self._gacha_thread = None
        self.core = None
        self._support_win = None

        self._build_ui()
        self._apply_dpi()
        self._setup_hotkey()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ==================== DPI ====================
    def _apply_dpi(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    # ==================== F8/F9 热键 ====================
    def _setup_hotkey(self):
        def on_press(k):
            if k == keyboard.Key.f8:
                self.root.after(0, self._on_f8)
            elif k == keyboard.Key.f9:
                self.root.after(0, self._on_f9)

        self._keyboard_listener = keyboard.Listener(on_press=on_press)
        self._keyboard_listener.start()

    def _on_f8(self):
        if not self.running:
            self._start()

    def _on_f9(self):
        if self.running:
            self._stop()

    # ==================== UI ====================
    def _build_ui(self):
        style = ttk.Style()
        style.configure("Large.TButton", font=("Microsoft YaHei UI", 20))
        style.configure("Large.TLabelframe.Label", font=("Microsoft YaHei UI", 20, "bold"))

        # ── 顶部状态栏 ──
        status_bar = ttk.Frame(self.root, padding=(8, 8, 8, 2))
        status_bar.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status_bar, textvariable=self.status_var, font=("Microsoft YaHei UI", 22, "bold"),
                  foreground="#2196F3").pack(side=tk.LEFT)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8)

        # ── 主控区：左(按钮) | 中(设置) | 右(统计) ──
        main_area = ttk.Frame(self.root, padding=8)
        main_area.pack(fill=tk.X)

        # 左列：按钮
        left_col = ttk.Frame(main_area)
        left_col.pack(side=tk.LEFT, padx=(0, 12))

        self.start_btn = ttk.Button(left_col, text="▶ 开始 (F8)", command=self._start, style="Large.TButton", width=14)
        self.start_btn.pack(pady=3)
        self.stop_btn = ttk.Button(left_col, text="■ 停止 (F9)", command=self._stop, state=tk.DISABLED, style="Large.TButton", width=14)
        self.stop_btn.pack(pady=3)
        self.update_btn = ttk.Button(left_col, text="❤ 支持 / 更新", command=self._open_support, style="Large.TButton", width=14)
        self.update_btn.pack(pady=3)

        # 垂直分隔
        ttk.Separator(main_area, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # 中列：设置
        mid_col = ttk.Frame(main_area)
        mid_col.pack(side=tk.LEFT, expand=True, padx=8)

        row1 = ttk.Frame(mid_col)
        row1.pack(fill=tk.X, pady=3)
        ttk.Label(row1, text="普通抽奖次数", font=("Microsoft YaHei UI", 20), width=12).pack(side=tk.LEFT)
        self.normal_var = tk.StringVar(value=str(self.settings["normal_rounds"]))
        ttk.Entry(row1, textvariable=self.normal_var, width=8, font=("Microsoft YaHei UI", 20)).pack(side=tk.LEFT, padx=(8, 0))

        row2 = ttk.Frame(mid_col)
        row2.pack(fill=tk.X, pady=3)
        ttk.Label(row2, text="超级抽奖次数", font=("Microsoft YaHei UI", 20), width=12).pack(side=tk.LEFT)
        self.super_var = tk.StringVar(value=str(self.settings["super_rounds"]))
        ttk.Entry(row2, textvariable=self.super_var, width=8, font=("Microsoft YaHei UI", 20)).pack(side=tk.LEFT, padx=(8, 0))

        row3 = ttk.Frame(mid_col)
        row3.pack(fill=tk.X, pady=3)
        ttk.Label(row3, text="价格阈值", font=("Microsoft YaHei UI", 20), width=12).pack(side=tk.LEFT)
        self.price_var = tk.StringVar(value=f"{self.settings['price_threshold']:,}")
        self._price_fmt_lock = False

        def fmt_price(*args):
            if self._price_fmt_lock:
                return
            raw = self.price_var.get().replace(",", "")
            if raw.isdigit():
                self._price_fmt_lock = True
                self.price_var.set(f"{int(raw):,}")
                self._price_fmt_lock = False
        self.price_var.trace_add("write", fmt_price)
        ttk.Entry(row3, textvariable=self.price_var, width=12, font=("Microsoft YaHei UI", 20)).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=(4, 0))

        # ── 统计面板（横向）──
        stats_frame = ttk.LabelFrame(self.root, text="本次统计", padding=8, style="Large.TLabelframe")
        stats_frame.pack(fill=tk.X, padx=8, pady=(4, 0))

        self.stats_labels = {}
        cols = [("total", "累计车辆"), ("kept", "入库"), ("sold", "出售"), ("earned", "收入")]
        for key, label in cols:
            row = ttk.Frame(stats_frame)
            row.pack(side=tk.LEFT, expand=True, padx=10)
            ttk.Label(row, text=label, font=("Microsoft YaHei UI", 18)).pack()
            val = ttk.Label(row, text="0" if key != "earned" else "0 CR",
                            font=("Microsoft YaHei UI", 20, "bold"), foreground="#4CAF50")
            val.pack()
            self.stats_labels[key] = val

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8, pady=(4, 0))

        # ── 日志区域 ──
        log_frame = ttk.LabelFrame(self.root, text="日志", padding=6, style="Large.TLabelframe")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 8))

        self.log_text = tk.Text(log_frame, state=tk.DISABLED, font=("Consolas", 20),
                                bg="white", fg="black", insertbackground="black",
                                wrap=tk.WORD)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL,
                                  command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    # ==================== 日志 ====================
    def _log(self, msg):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ==================== 统计回调 ====================
    def _on_stats(self, stats):
        self.root.after(0, self._update_stats, stats.copy())

    def _update_stats(self, stats):
        if "total" in self.stats_labels:
            self.stats_labels["total"].config(text=str(stats["total"]))
        if "kept" in self.stats_labels:
            self.stats_labels["kept"].config(text=str(stats["kept"]))
        if "sold" in self.stats_labels:
            self.stats_labels["sold"].config(text=str(stats["sold"]))
        if "earned" in self.stats_labels:
            self.stats_labels["earned"].config(text=f"{stats['earned']:,} CR")

    # ==================== 启动 / 停止 ====================
    def _parse_int(self, var, default):
        try:
            return max(0, int(var.get().strip().replace(",", "")))
        except ValueError:
            return default

    def _start(self):
        if self.running:
            return

        normal_rounds = self._parse_int(self.normal_var, 0)
        super_rounds = self._parse_int(self.super_var, 0)
        price_threshold = self._parse_int(self.price_var, 100000)

        if normal_rounds <= 0 and super_rounds <= 0:
            self._log("[!] 请至少设置一种抽奖次数 > 0")
            return

        # 保存设置
        self.settings["normal_rounds"] = normal_rounds
        self.settings["super_rounds"] = super_rounds
        self.settings["price_threshold"] = price_threshold
        save_settings(self.settings)

        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_var.set("运行中...")

        # 重置统计
        for key in self.stats_labels:
            self.stats_labels[key].config(text="0" if key != "earned" else "0 CR")

        from gacha_core import GachaCore
        self.core = GachaCore(
            log_callback=self._log,
            stats_callback=self._on_stats,
        )
        self.core.price_threshold = price_threshold

        self._gacha_thread = threading.Thread(target=self._run_gacha,
                                              args=(normal_rounds, super_rounds),
                                              daemon=True)
        self._gacha_thread.start()

    def _run_gacha(self, normal_rounds, super_rounds):
        try:
            if normal_rounds > 0:
                self.core.run_wheelspin(normal_rounds)
            if super_rounds > 0 and self.core.is_running:
                self.core.run_super_wheelspin(super_rounds)
        except Exception as e:
            self._log(f"运行异常: {e}")
        finally:
            self.running = False
            self.root.after(0, self._on_done)

    def _stop(self):
        if self.core:
            self.core.is_running = False
        self.running = False
        self._log("⏹ 紧急停止 (F9)")
        self.status_var.set("已停止")

    def _on_done(self):
        self.running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("就绪")
        self._log("===== 全部任务完成 =====")

    # ==================== 支持 & 检查更新 ====================
    def _open_support(self):
        if self._support_win is not None and self._support_win.winfo_exists():
            self._support_win.focus()
            return

        self._support_win = tk.Toplevel(self.root)
        self._support_win.title("支持 & 检查更新")
        self._support_win.geometry("420x600")
        self._support_win.resizable(False, False)
        self._support_win.configure(bg="#f5f5f5")

        # 居中于主窗口
        self._support_win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 420) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 600) // 2
        self._support_win.geometry(f"+{x}+{y}")

        # 标题
        tk.Label(self._support_win, text="感谢您的支持！", font=("Microsoft YaHei UI", 18, "bold"),
                 fg="#F97316", bg="#f5f5f5").pack(pady=(20, 6))
        tk.Label(self._support_win, text="您的支持是持续优化的动力",
                 font=("Microsoft YaHei UI", 12), fg="#666", bg="#f5f5f5").pack(pady=4)

        # 二维码
        qr_path = os.path.join(APP_DIR, "assets", "qrcode.png")
        try:
            if os.path.exists(qr_path):
                img = Image.open(qr_path)
                img = img.resize((220, 220), Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(img)
                qr_label = tk.Label(self._support_win, image=tk_img, bg="#f5f5f5")
                qr_label.image = tk_img
                qr_label.pack(pady=10)
            else:
                tk.Label(self._support_win, text="（未找到赞助二维码）",
                         fg="gray", bg="#f5f5f5").pack(pady=40)
        except Exception as e:
            tk.Label(self._support_win, text=f"（二维码加载失败: {e}）",
                     fg="gray", bg="#f5f5f5").pack(pady=40)

        # 分隔线
        ttk.Separator(self._support_win, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=30, pady=12)

        # 版本信息
        tk.Label(self._support_win, text="FH6 抽奖助手",
                 font=("Microsoft YaHei UI", 13, "bold"), fg="#333", bg="#f5f5f5").pack()
        tk.Label(self._support_win, text="GitHub: SaYa-t/FH6-AUTOGacha",
                 font=("Consolas", 10), fg="#888", bg="#f5f5f5").pack(pady=(2, 10))

        # 按钮区
        btn_frame = tk.Frame(self._support_win, bg="#f5f5f5")
        btn_frame.pack(pady=6)

        tk.Button(btn_frame, text="检查更新",
                  font=("Microsoft YaHei UI", 13), width=12, height=1,
                  bg="#444", fg="white", cursor="hand2",
                  command=lambda: webbrowser.open(
                      "https://github.com/SaYa-t/FH6-AUTOGacha/releases")
                  ).pack(side=tk.LEFT, padx=6)

        tk.Button(btn_frame, text="GitHub 主页",
                  font=("Microsoft YaHei UI", 13), width=12, height=1,
                  bg="#2EA043", fg="white", cursor="hand2",
                  command=lambda: webbrowser.open(
                      "https://github.com/SaYa-t/FH6-AUTOGacha")
                  ).pack(side=tk.LEFT, padx=6)

    def _on_closing(self):
        if self.core:
            self.core.is_running = False
        try:
            self._keyboard_listener.stop()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    GachaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
