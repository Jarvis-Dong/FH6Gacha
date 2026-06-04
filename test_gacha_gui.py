"""
test_gacha_gui.py - 抽奖/超级抽奖 测试GUI
实时显示 ROI 区域捕获画面 + 运行日志
"""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time
import cv2
import numpy as np
from gacha_core import GachaCore, hw_press, hw_click


class GachaTestGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("抽奖测试工具")
        self.root.geometry("1050x750")

        self.core = GachaCore(log_callback=self._on_log)
        self.running = False
        self._preview_job = None  # after id

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ==================== UI ====================

    def _build_ui(self):
        # 顶部控制栏
        bar = ttk.Frame(self.root, padding=5)
        bar.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(bar, textvariable=self.status_var, font=("", 11, "bold")).pack(side=tk.LEFT)

        ttk.Button(bar, text="聚焦窗口", command=self._test_focus).pack(side=tk.LEFT, padx=3)
        ttk.Button(bar, text="检测菜单", command=self._test_menu).pack(side=tk.LEFT, padx=3)
        ttk.Button(bar, text="检测状态", command=self._test_state).pack(side=tk.LEFT, padx=3)
        ttk.Button(bar, text="检测重复车", command=self._test_duplicate).pack(side=tk.LEFT, padx=3)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(bar, text="次数:").pack(side=tk.LEFT, padx=(4, 1))
        self.round_var = tk.StringVar(value="3")
        ttk.Entry(bar, textvariable=self.round_var, width=4).pack(side=tk.LEFT)

        ttk.Label(bar, text="价格阈值:").pack(side=tk.LEFT, padx=(6, 1))
        self.price_var = tk.StringVar(value="100000")
        ttk.Entry(bar, textvariable=self.price_var, width=8).pack(side=tk.LEFT)

        ttk.Label(bar, text="重复车检测阈值:").pack(side=tk.LEFT, padx=(6, 1))
        self.dup_threshold_var = tk.StringVar(value="0.80")
        ttk.Entry(bar, textvariable=self.dup_threshold_var, width=4).pack(side=tk.LEFT)

        ttk.Button(bar, text="普通抽奖", command=self._run_normal).pack(side=tk.LEFT, padx=3)
        ttk.Button(bar, text="超级抽奖", command=self._run_super).pack(side=tk.LEFT, padx=3)
        ttk.Button(bar, text="停止", command=self._stop).pack(side=tk.LEFT, padx=3)

        # 主区: 左侧预览, 右侧日志
        main = ttk.Frame(self.root)
        main.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        # 预览
        preview_frame = ttk.LabelFrame(main, text="ROI 实时预览", padding=3)
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(preview_frame, bg="#111", width=540, height=350)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.roi_info_var = tk.StringVar(value="点击检测按钮开始")
        ttk.Label(preview_frame, textvariable=self.roi_info_var, anchor=tk.W).pack(fill=tk.X, pady=(2, 0))

        # 日志
        log_frame = ttk.LabelFrame(main, text="日志", padding=3)
        log_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(4, 0))

        self.log_text = tk.Text(log_frame, state=tk.DISABLED, font=("Consolas", 9), width=50)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    # ==================== 日志 ====================

    def _on_log(self, msg):
        self.root.after(0, self._append_log, msg)

    def _append_log(self, msg):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ==================== ROI 预览 ====================

    def _show_roi(self, region, title=""):
        """捕获区域并显示在画布上"""
        try:
            screen = self.core.capture_region(region)
            if screen is None:
                return
            h, w = screen.shape[:2]

            # 缩放到画布大小
            cw = self.canvas.winfo_width() or 540
            ch = self.canvas.winfo_height() or 350
            scale = min(cw / w, ch / h, 1.0)
            dw, dh = int(w * scale), int(h * scale)

            rgb = cv2.cvtColor(screen, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb).resize((dw, dh), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(pil_img)

            self.canvas.delete("all")
            self.canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=tk_img)
            self.canvas.image = tk_img

            self.roi_info_var.set(
                f"{title} | 原始: {w}x{h} | 显示: {dw}x{dh} | "
                f"坐标: ({region[0]},{region[1]}) [{region[2]}x{region[3]}]"
            )
        except Exception as e:
            self.roi_info_var.set(f"预览失败: {e}")

    def _show_full_with_roi(self, roi_region, title=""):
        """显示全屏, 并在上面绘制 ROI 矩形 (roi_region 为屏幕绝对坐标)"""
        try:
            full = self.core.regions.get("全界面")
            if not full:
                return
            screen = self.core.capture_region(full)
            if screen is None:
                return

            # ROI 是屏幕绝对坐标, 转为窗口内局部坐标再绘制
            ox, oy = full[0], full[1]
            rx, ry, rw, rh = roi_region
            lx, ly = rx - ox, ry - oy
            cv2.rectangle(screen, (lx, ly), (lx + rw, ly + rh), (0, 255, 0), 3)

            h, w = screen.shape[:2]
            cw = self.canvas.winfo_width() or 540
            ch = self.canvas.winfo_height() or 350
            scale = min(cw / w, ch / h, 1.0)
            dw, dh = int(w * scale), int(h * scale)

            rgb = cv2.cvtColor(screen, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb).resize((dw, dh), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(pil_img)

            self.canvas.delete("all")
            self.canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=tk_img)
            self.canvas.image = tk_img

            self.roi_info_var.set(
                f"{title} | ROI: ({rx},{ry}) {rw}x{rh} (绿框) | 全屏: {w}x{h}"
            )
        except Exception as e:
            self.roi_info_var.set(f"预览失败: {e}")

    # ==================== 按钮操作 ====================

    def _get_prompt_region(self):
        return self.core._scale_roi(13, 1951, 1148, 157)

    def _get_duplicate_region(self):
        return self.core._scale_roi(1025, 221, 1938, 484)

    def _get_price_region(self):
        return self.core._scale_roi(1239, 1675, 1359, 113)

    def _test_focus(self):
        self._on_log("=== 聚焦游戏窗口 ===")
        self.status_var.set("聚焦窗口中...")
        ok = self.core.focus_game()
        self._on_log(f"聚焦结果: {'成功' if ok else '失败'}")
        if ok:
            self._show_full_with_roi(self.core.regions.get("全界面"), "游戏窗口")
        self.status_var.set("就绪")

    def _test_menu(self):
        self._on_log("=== 检测菜单入口 ===")
        self.status_var.set("检测菜单中...")
        self.core._ensure_focus()

        pos_s = self.core.find_image("superclaim.png", "左", 0.65)
        pos_n = self.core.find_image("claim.png", "右", 0.65)
        self._on_log(f"超级抽奖(左): {pos_s or '未找到'}")
        self._on_log(f"普通抽奖(右): {pos_n or '未找到'}")

        # 显示全屏 + 左右搜索区域
        left = self.core.regions.get("左")
        right = self.core.regions.get("右")
        self._show_full_with_multi_rois([
            ("左-超级抽奖", left),
            ("右-普通抽奖", right),
        ], "菜单入口检测")

        if pos_s:
            self._on_log(f"→ 超级抽奖位置: {pos_s}")
        if pos_n:
            self._on_log(f"→ 普通抽奖位置: {pos_n}")

        self.status_var.set("就绪")

    def _test_state(self):
        self._on_log("=== 检测抽奖状态 ===")
        self.status_var.set("检测状态中...")
        self.core._ensure_focus()

        region = self._get_prompt_region()
        self._show_roi(region, "左下判定区域")

        state = self.core.check_gacha_prompt()
        self._on_log(f"抽奖状态: {state}")
        self.status_var.set(f"状态: {state}")

    def _show_full_with_multi_rois(self, rois, title=""):
        """显示全屏, 在上面绘制多个 ROI 矩形 (rois 坐标为屏幕绝对坐标)"""
        try:
            full = self.core.regions.get("全界面")
            if not full:
                return
            screen = self.core.capture_region(full)
            if screen is None:
                return

            ox, oy = full[0], full[1]
            colors = [(0, 255, 0), (0, 200, 255), (255, 200, 0), (255, 0, 200)]
            for i, (label, (rx, ry, rw, rh)) in enumerate(rois):
                color = colors[i % len(colors)]
                lx, ly = rx - ox, ry - oy
                cv2.rectangle(screen, (lx, ly), (lx + rw, ly + rh), color, 3)
                cv2.putText(screen, label, (lx, ly - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

            h, w = screen.shape[:2]
            cw = self.canvas.winfo_width() or 540
            ch = self.canvas.winfo_height() or 350
            scale = min(cw / w, ch / h, 1.0)
            dw, dh = int(w * scale), int(h * scale)

            rgb = cv2.cvtColor(screen, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb).resize((dw, dh), Image.LANCZOS)
            tk_img = ImageTk.PhotoImage(pil_img)

            self.canvas.delete("all")
            self.canvas.create_image(cw // 2, ch // 2, anchor=tk.CENTER, image=tk_img)
            self.canvas.image = tk_img

            self.roi_info_var.set(f"{title} | 全屏: {w}x{h}")
        except Exception as e:
            self.roi_info_var.set(f"预览失败: {e}")

    def _test_duplicate(self):
        self._on_log("=== 检测重复车辆 ===")
        self.status_var.set("检测重复车中...")
        self.core._ensure_focus()

        title_region = self._get_duplicate_region()
        price_region = self._get_price_region()

        self._show_full_with_multi_rois([
            ("已拥有车辆", title_region),
            ("出售价格", price_region),
        ], "重复车辆检测")

        found = self.core.check_duplicate_car()
        self._on_log(f"重复车辆: {'是' if found else '否'}")

        if found:
            price = self.core._read_duplicate_price()
            self._on_log(f"价格识别结果: {price if price else '未能识别'}")
        self.status_var.set(f"重复车辆: {'是' if found else '否'}")

    def _run_normal(self):
        self._start_thread(is_super=False)

    def _run_super(self):
        self._start_thread(is_super=True)

    def _start_thread(self, is_super):
        if self.running:
            self._on_log("已有任务在运行, 请先停止")
            return
        try:
            rounds = int(self.round_var.get())
        except ValueError:
            rounds = 3
        try:
            self.core.price_threshold = int(self.price_var.get())
        except ValueError:
            self.core.price_threshold = 1_000_000
        try:
            self.core.dup_match_threshold = float(self.dup_threshold_var.get())
        except ValueError:
            self.core.dup_match_threshold = 0.80

        self.running = True
        self.core.is_running = True
        label = "超级抽奖" if is_super else "普通抽奖"
        self.status_var.set(f"运行 {label} ({rounds}次)...")
        self._on_log(f"===== 启动 {label} (共 {rounds} 次, 价格阈值={self.core.price_threshold}, 重复车阈值={self.core.dup_match_threshold}) =====")

        def _run():
            try:
                if is_super:
                    self.core.run_super_wheelspin(rounds)
                else:
                    self.core.run_wheelspin(rounds)
            except Exception as e:
                self._on_log(f"运行异常: {e}")
            finally:
                self.running = False
                self.core.is_running = False
                self.root.after(0, lambda: self.status_var.set("就绪"))

        threading.Thread(target=_run, daemon=True).start()

    def _stop(self):
        self.core.is_running = False
        self.running = False
        self.status_var.set("已停止")
        self._on_log("⏹ 停止")

    def _on_closing(self):
        self.core.is_running = False
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
    GachaTestGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
