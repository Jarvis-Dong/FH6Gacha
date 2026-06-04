"""
ROI 区域选择工具 - 用于在截图上标注判定区域
用法: python roi_selector.py
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import os
import json

COLORS = ["red", "lime", "cyan", "yellow", "magenta", "orange", "dodger blue", "white"]


class ROISelector:
    def __init__(self, root):
        self.root = root
        self.root.title("ROI 判定区域选择工具")
        self.root.geometry("1400x900")

        # ---- 数据 ----
        self.img_original = None       # PIL Image (原始尺寸, 只读)
        self.img_display = None        # PIL Image (缩放后用于显示)
        self.tk_image = None           # ImageTk
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.rois = []                 # [{name, x, y, w, h}, ...]
        self.next_color = 0

        # 拖拽状态
        self.drawing = False
        self.start_x = self.start_y = 0
        self.temp_rect_id = None

        self._build_ui()

        # 默认打开 timage 目录
        default_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timage")
        if os.path.isdir(default_dir):
            self._populate_file_list(default_dir)

    # ===================== UI 布局 =====================

    def _build_ui(self):
        # 顶部工具栏
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=5, pady=(5, 0))

        ttk.Button(toolbar, text="打开图像", command=self._browse_image).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="打开 timage 目录", command=self._open_timage).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="清除全部ROI", command=self._clear_rois).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="导出 ROI 配置", command=self._export_rois).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(toolbar, text="提示: 鼠标拖拽即可框选ROI").pack(side=tk.LEFT, padx=4)

        # 主区域: 左侧文件列表 + 右侧画布
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- 左侧: 文件列表 ---
        left_frame = ttk.Frame(main_pane, width=260)
        main_pane.add(left_frame, weight=0)

        ttk.Label(left_frame, text="timage 文件列表:").pack(anchor=tk.W, padx=4, pady=(4, 2))
        self.file_listbox = tk.Listbox(left_frame, width=30)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        self.file_listbox.bind("<<ListboxSelect>>", self._on_file_select)

        # --- 右侧: 画布 + ROI 列表 ---
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=1)

        # 画布 (带滚动条)
        canvas_frame = ttk.Frame(right_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame, bg="#222222", cursor="cross")
        self.h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.h_scroll.set, yscrollcommand=self.v_scroll.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.h_scroll.grid(row=1, column=0, sticky="ew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        # ROI 列表面板
        roi_panel = ttk.Frame(right_frame)
        roi_panel.pack(fill=tk.X, padx=4, pady=(4, 0))

        ttk.Label(roi_panel, text="已标注 ROI:").pack(anchor=tk.W)
        list_frame = ttk.Frame(roi_panel)
        list_frame.pack(fill=tk.X, pady=2)

        self.roi_listbox = tk.Listbox(list_frame, height=4)
        self.roi_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.roi_listbox.bind("<Delete>", self._delete_selected_roi)
        self.roi_listbox.bind("<Double-Button-1>", self._goto_roi)

        btn_col = ttk.Frame(list_frame)
        btn_col.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 0))
        ttk.Button(btn_col, text="删除选中", command=self._delete_selected_roi).pack(fill=tk.X, pady=1)
        ttk.Button(btn_col, text="定位选中", command=self._goto_roi).pack(fill=tk.X, pady=1)
        ttk.Button(btn_col, text="修改名称", command=self._rename_roi).pack(fill=tk.X, pady=1)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪 — 请打开图像或从左侧列表选择")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ===================== 文件列表 =====================

    def _populate_file_list(self, directory):
        self.file_listbox.delete(0, tk.END)
        self._current_dir = directory
        try:
            files = sorted(
                [f for f in os.listdir(directory) if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))]
            )
            for f in files:
                self.file_listbox.insert(tk.END, f)
            self.status_var.set(f"已加载目录: {directory}  ({len(files)} 个图像)")
        except Exception as e:
            self.status_var.set(f"读取目录失败: {e}")

    def _open_timage(self):
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timage")
        if os.path.isdir(d):
            self._populate_file_list(d)
        else:
            messagebox.showwarning("提示", "timage 目录不存在")

    def _on_file_select(self, event):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        fname = self.file_listbox.get(sel[0])
        full = os.path.join(self._current_dir, fname)
        self._load_image(full)

    def _browse_image(self):
        path = filedialog.askopenfilename(
            title="选择图像",
            filetypes=[("图像文件", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")]
        )
        if path:
            self._load_image(path)

    # ===================== 图像加载 =====================

    def _load_image(self, path):
        try:
            pil_img = Image.open(path).convert("RGB")
        except Exception as e:
            messagebox.showerror("错误", f"无法打开图像:\n{e}")
            return

        self.img_original = pil_img
        self.img_path = path
        self.rois = []
        self.next_color = 0
        self._refresh_display()
        self._update_roi_listbox()
        self.status_var.set(f"已加载: {os.path.basename(path)}  ({pil_img.width}x{pil_img.height})")

    def _refresh_display(self):
        """根据当前窗口大小缩放图像并重绘画布"""
        if self.img_original is None:
            return

        self.canvas.delete("all")

        # 计算可用区域
        self.canvas.update_idletasks()
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 50:
            cw = 1000
        if ch < 50:
            ch = 700

        margin = 20
        max_w = cw - margin
        max_h = ch - margin

        ow, oh = self.img_original.size
        self.scale_x = max_w / ow
        self.scale_y = max_h / oh
        sc = min(self.scale_x, self.scale_y)
        self.scale_x = self.scale_y = sc

        dw = int(ow * sc)
        dh = int(oh * sc)

        self.img_display = self.img_original.resize((dw, dh), Image.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(self.img_display)

        self.canvas.configure(scrollregion=(0, 0, dw, dh))
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image, tags="bg_img")

        # 重绘所有ROI
        for i, r in enumerate(self.rois):
            color = COLORS[i % len(COLORS)]
            self._draw_roi_rect(r, color)

    def _to_display(self, x, y):
        return int(x * self.scale_x), int(y * self.scale_y)

    def _to_original(self, dx, dy):
        return int(dx / self.scale_x), int(dy / self.scale_y)

    # ===================== ROI 绘制 =====================

    def _draw_roi_rect(self, roi, color):
        """在画布上绘制一个ROI矩形 (坐标已是原始尺寸)"""
        x1, y1 = self._to_display(roi["x"], roi["y"])
        x2, y2 = self._to_display(roi["x"] + roi["w"], roi["y"] + roi["h"])
        tag = f"roi_{id(roi)}"
        self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, tags=("roi", tag))
        # 标签
        label = f"{roi['name']} ({roi['x']},{roi['y']} {roi['w']}x{roi['h']})"
        self.canvas.create_text(x1 + 4, y1 + 4, anchor=tk.NW, text=label,
                                fill=color, font=("Consolas", 9), tags=("roi", tag))

    # ===================== 鼠标交互 =====================

    def _on_press(self, event):
        if self.img_original is None:
            return
        self.drawing = True
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)

    def _on_drag(self, event):
        if not self.drawing:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        if self.temp_rect_id:
            self.canvas.delete(self.temp_rect_id)
        self.temp_rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, cx, cy,
            outline="#FFA500", width=2, dash=(6, 3)
        )

    def _on_release(self, event):
        if not self.drawing:
            return
        self.drawing = False
        if self.temp_rect_id:
            self.canvas.delete(self.temp_rect_id)
            self.temp_rect_id = None

        ex = self.canvas.canvasx(event.x)
        ey = self.canvas.canvasy(event.y)

        # 转换到原始坐标
        ox1, oy1 = self._to_original(min(self.start_x, ex), min(self.start_y, ey))
        ox2, oy2 = self._to_original(max(self.start_x, ex), max(self.start_y, ey))

        ow = ox2 - ox1
        oh = oy2 - oy1

        if ow < 5 or oh < 5:
            self.status_var.set("区域太小，已忽略")
            return

        color = COLORS[self.next_color % len(COLORS)]
        self.next_color += 1

        roi = {"name": f"ROI_{len(self.rois)+1}", "x": ox1, "y": oy1, "w": ow, "h": oh}
        self.rois.append(roi)
        self._draw_roi_rect(roi, color)
        self._update_roi_listbox()
        self.status_var.set(f"已添加 ROI: {roi['name']} ({ox1},{oy1} {ow}x{oh})")

    def _on_mousewheel(self, event):
        """滚轮上下滚动画布"""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ===================== ROI 管理 =====================

    def _update_roi_listbox(self):
        self.roi_listbox.delete(0, tk.END)
        for r in self.rois:
            self.roi_listbox.insert(tk.END,
                f"{r['name']}: ({r['x']}, {r['y']})  {r['w']}x{r['h']}")

    def _delete_selected_roi(self, event=None):
        sel = self.roi_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        removed = self.rois.pop(idx)
        self._update_roi_listbox()
        self._refresh_display()
        self.status_var.set(f"已删除: {removed['name']}")

    def _goto_roi(self, event=None):
        """画布滚动到选中ROI的中心位置"""
        sel = self.roi_listbox.curselection()
        if not sel or self.img_original is None:
            return
        r = self.rois[sel[0]]
        cx, cy = self._to_display(r["x"] + r["w"] // 2, r["y"] + r["h"] // 2)
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        # 让ROI中心对齐画布中心
        frac_x = max(0, min(1, (cx - cw / 2) / max(1, self.img_display.width - cw)))
        frac_y = max(0, min(1, (cy - ch / 2) / max(1, self.img_display.height - ch)))
        self.canvas.xview_moveto(frac_x)
        self.canvas.yview_moveto(frac_y)

    def _rename_roi(self):
        sel = self.roi_listbox.curselection()
        if not sel:
            return
        r = self.rois[sel[0]]

        dlg = tk.Toplevel(self.root)
        dlg.title("修改 ROI 名称")
        dlg.geometry("300x120")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="ROI 名称:").pack(padx=10, pady=(10, 4))
        var = tk.StringVar(value=r["name"])
        entry = ttk.Entry(dlg, textvariable=var)
        entry.pack(padx=10, fill=tk.X)
        entry.select_range(0, tk.END)
        entry.focus_set()

        def _apply():
            r["name"] = var.get()
            self._update_roi_listbox()
            self._refresh_display()
            dlg.destroy()

        ttk.Button(dlg, text="确定", command=_apply).pack(pady=8)
        entry.bind("<Return>", lambda e: _apply())

    def _clear_rois(self):
        if self.rois and not messagebox.askyesno("确认", f"确定要清除全部 {len(self.rois)} 个ROI吗？"):
            return
        self.rois = []
        self.next_color = 0
        self._update_roi_listbox()
        self._refresh_display()
        self.status_var.set("已清除全部ROI")

    # ===================== 导出 =====================

    def _export_rois(self):
        if not self.rois:
            messagebox.showwarning("提示", "没有ROI可导出")
            return

        img_name = os.path.splitext(os.path.basename(self.img_path))[0] if hasattr(self, "img_path") else "unknown"

        path = filedialog.asksaveasfilename(
            title="导出 ROI 配置",
            initialfile=f"{img_name}_roi.json",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("文本文件", "*.txt")]
        )
        if not path:
            return

        data = {
            "source_image": os.path.basename(self.img_path) if hasattr(self, "img_path") else "",
            "image_size": {"width": self.img_original.width, "height": self.img_original.height},
            "rois": self.rois,
            "python_code": self._gen_python_code()
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.status_var.set(f"ROI 配置已导出到: {os.path.basename(path)}")
        messagebox.showinfo("导出成功",
            f"已导出 {len(self.rois)} 个ROI到:\n{path}\n\n"
            f"可直接复制 python_code 字段中的代码到主程序中使用。")

    def _gen_python_code(self):
        """生成可直接粘贴到 bot 代码中的字典"""
        lines = ["# --- ROI 判定区域配置 ---"]
        lines.append("gacha_rois = {")
        for r in self.rois:
            lines.append(f'    "{r["name"]}": ({r["x"]}, {r["y"]}, {r["w"]}, {r["h"]}),')
        lines.append("}")
        return "\n".join(lines)


def main():
    root = tk.Tk()
    ROISelector(root)
    root.mainloop()


if __name__ == "__main__":
    main()
