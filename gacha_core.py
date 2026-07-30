"""FH6 normal/super wheelspin automation with safe duplicate handling."""

import os
import shutil
import sys
import threading
import time

import cv2
import numpy as np

from gacha_backend import GameWindow
from gacha_policy import decide_duplicate_action


def _get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_internal_dir():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return _get_app_dir()


APP_DIR = _get_app_dir()
INTERNAL_DIR = _get_internal_dir()


def _auto_extract_dir(folder_name):
    """从打包内部释放资源文件夹到外部, 已存在文件不覆盖"""
    internal = os.path.join(INTERNAL_DIR, folder_name)
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

IMAGES_DIR = os.path.join(APP_DIR, "images")
LOGS_DIR = os.path.join(APP_DIR, "logs")
SETTINGS_FILE = os.path.join(APP_DIR, ".gacha_settings.json")
SCRIPT_DIR = APP_DIR


class GachaCore:
    TEMPLATE_REF_W = 3835
    TEMPLATE_REF_H = 2159
    MIN_CLIENT_W = 1600
    MIN_CLIENT_H = 900

    def __init__(
        self,
        log_callback=None,
        preview_callback=None,
        stats_callback=None,
        *,
        duplicate_policy="threshold",
        price_threshold=100_000,
        phase_timeout=1800,
    ):
        self.log_cb = log_callback or print
        self.preview_cb = preview_callback
        self.stats_cb = stats_callback
        self.is_running = True
        self.duplicate_policy = duplicate_policy
        self.price_threshold = max(0, int(price_threshold))
        self.phase_timeout = max(60, int(phase_timeout))
        self.dup_match_threshold = 0.80
        self.stats = self._empty_stats()
        self.dup_stats = self.stats  # Backwards-compatible alias for the GUI callback.
        self.regions = {}
        self.scale_x = 1.0
        self.scale_y = 1.0
        self._init_regions()
        self.template_cache = {}
        os.makedirs(LOGS_DIR, exist_ok=True)
        self._log_file = open(
            os.path.join(LOGS_DIR, f"gacha_{time.strftime('%Y%m%d_%H%M%S')}.log"),
            "w",
            encoding="utf-8",
        )
        self._easyocr_reader = None
        self._easyocr_ready = threading.Event()
        self._easyocr_done = threading.Event()
        self._easyocr_loading = False
        self.window = GameWindow(self.log)
        if self.duplicate_policy != "keep_all":
            self._preload_ocr()

    @staticmethod
    def _empty_stats():
        return {
            "normal_spins": 0,
            "super_spins": 0,
            "total": 0,
            "kept": 0,
            "sold": 0,
            "earned": 0,
            "ocr_failed": 0,
        }

    def reset_stats(self):
        self.stats = self._empty_stats()
        self.dup_stats = self.stats
        self._notify_stats()

    def stop(self):
        self.is_running = False
        self._easyocr_done.set()
        self.window.release_all()

    def close(self):
        self.stop()
        try:
            self._log_file.close()
        except Exception:
            pass

    def log(self, msg):
        self.log_cb(msg)
        try:
            self._log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
            self._log_file.flush()
        except Exception:
            pass

    def _preview(self, image, title=""):
        """发送预览画面到 GUI (非阻塞, GUI 端自行调度到主线程)"""
        if self.preview_cb:
            try:
                self.preview_cb(image, title)
            except Exception:
                pass

    def _notify_stats(self):
        if self.stats_cb:
            try:
                self.stats_cb(self.stats.copy())
            except Exception:
                pass

    def _init_regions(self):
        self._update_regions_by_window(0, 0, self.TEMPLATE_REF_W, self.TEMPLATE_REF_H)

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
        self.log(
            f"[scale] 预计算缩放比: x={self.scale_x:.4f} "
            f"y={self.scale_y:.4f} (窗口={w}x{h})"
        )

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
        if not self.is_running:
            return None
        return self.window.capture(region)

    def hw_press(self, key, delay=0.08, use_send=False):
        if not self.is_running:
            return
        self.window.press(key, delay, use_send=use_send)

    def game_click(self, pos):
        if self.is_running and pos:
            self.window.click_screen(int(pos[0]), int(pos[1]))

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
        curr_w = full[2] if full else self.TEMPLATE_REF_W
        curr_h = full[3] if full else self.TEMPLATE_REF_H
        scales = []

        def add(s):
            s = round(float(s), 3)
            if 0.25 <= s <= 1.8 and s not in scales:
                scales.append(s)

        if ref_w is not None:
            ref_h = ref_w * self.TEMPLATE_REF_H / self.TEMPLATE_REF_W
            primary_scale = (curr_w / ref_w + curr_h / ref_h) / 2
        else:
            primary_scale = (
                curr_w / self.TEMPLATE_REF_W + curr_h / self.TEMPLATE_REF_H
            ) / 2

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
                for v in [
                    s2560,
                    s2560 * 0.98,
                    s2560 * 1.02,
                    s2560 * 0.95,
                    s2560 * 1.05,
                ]:
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
        region_tuple = (
            self.regions.get(region, region) if isinstance(region, str) else region
        )
        screen = self.capture_region(region_tuple)
        if screen is None or screen.size == 0:
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
                rx = region_tuple[0] if region_tuple else 0
                ry = region_tuple[1] if region_tuple else 0
                pos = (max_loc[0] + nw // 2 + rx, max_loc[1] + nh // 2 + ry)
                self.log(
                    f"[match] {template_name} score={max_val:.3f} "
                    f"scale={scale:.3f} @ {pos}"
                )
                return pos
        return None

    def focus_game(self):
        """Attach without stealing foreground focus."""
        self.log("正在连接游戏窗口 (ForzaHorizon6.exe)...")
        if not self.window.attach():
            return False
        if not self._sync_window_bounds():
            self.window.close()
            return False
        return True

    @classmethod
    def _window_size_supported(cls, width, height):
        return width >= cls.MIN_CLIENT_W and height >= cls.MIN_CLIENT_H

    def _sync_window_bounds(self):
        gx, gy, gw, gh = self.window.bounds
        if not self._window_size_supported(gw, gh):
            self.log(
                f"游戏客户区 {gw}x{gh} 低于最低支持的 "
                f"{self.MIN_CLIENT_W}x{self.MIN_CLIENT_H}，停止"
            )
            return False
        full = self.regions.get("全界面")
        if full != (gx, gy, gw, gh):
            self._update_regions_by_window(gx, gy, gw, gh)
        return True

    def _ensure_focus(self):
        if not self.window.ensure_attached():
            self.log("游戏窗口连接已丢失")
            return False
        return self._sync_window_bounds()

    def _refind_window(self):
        self.window.close()
        return self.focus_game()

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

            pos_menu = self.find_image(
                "collectionjournal.png", region="左", threshold=0.70, ref_w=2560
            )
            if pos_menu:
                self.log(f"已进入主菜单 (第 {i + 1}/60 次)")
                time.sleep(0.2)
                self.log("PgDn×2 切换到抽奖标签页...")
                self.hw_press("pagedown", delay=0.08)
                time.sleep(0.2)
                self.hw_press("pagedown", delay=0.08)
                time.sleep(0.3)
                return True

            self.log(f"未在主菜单, 按 ESC... ({i + 1}/60)")
            self.hw_press("esc", delay=0.12)
            time.sleep(1.0)

        self.log("60 次尝试均未进入菜单!")
        return False

    def return_to_main_menu(self, timeout=30):
        """Return to the main menu and verify its stable anchor before handoff."""
        deadline = time.monotonic() + max(3, timeout)
        while self.is_running and time.monotonic() < deadline:
            if self.find_image(
                "collectionjournal.png", region="左", threshold=0.70, ref_w=2560
            ):
                self.log("已确认回到游戏主菜单")
                return True
            self.hw_press("esc", delay=0.10)
            time.sleep(0.5)
        self.log("未能确认回到游戏主菜单")
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
        self.log(
            f"[prompt] 判态={result} skip={score_skip:.3f} "
            f"claim={score_claim:.3f} 耗时={dt:.0f}ms"
        )
        return result

    def _get_best_score(self, template_name, region):
        """在区域中搜索模板, 返回最佳匹配分数 (不设阈值)"""
        path = self._get_img_path(template_name)
        if not path:
            return 0.0
        region_tuple = (
            self.regions.get(region, region) if isinstance(region, str) else region
        )
        screen = self.capture_region(region_tuple)
        if screen is None or screen.size == 0:
            return 0.0
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
            best = max(best, max_val)
        return best

    _DUPLICATE_TEMPLATES = ("duplicate_car.png",)

    _MAX_MATCH_DIM = 800  # 匹配前降采样上限, 大幅减少 matchTemplate 计算量

    def _find_in_screen(
        self, template_name, screen, region, threshold=0.75, ref_w=None
    ):
        """在预捕获的截图中搜索模板 (不重复截图, 供多线程并行搜索使用)"""
        path = self._get_img_path(template_name)
        if not path:
            return None
        tpl = self._load_template(path)
        if tpl is None:
            return None

        # 对大尺寸截图/模板降采样到工作分辨率, 避免 matchTemplate 万亿级像素运算
        max_dim = max(screen.shape[1], screen.shape[0], tpl.shape[1], tpl.shape[0])
        ds = 1.0
        if max_dim > self._MAX_MATCH_DIM:
            ds = self._MAX_MATCH_DIM / max_dim
            screen = cv2.resize(
                screen,
                (int(screen.shape[1] * ds), int(screen.shape[0] * ds)),
                interpolation=cv2.INTER_AREA,
            )
            tpl = cv2.resize(
                tpl,
                (int(tpl.shape[1] * ds), int(tpl.shape[0] * ds)),
                interpolation=cv2.INTER_AREA,
            )

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
                # 坐标从降采样空间映射回原始截图空间
                px = int((max_loc[0] + nw / 2) / ds + rx)
                py = int((max_loc[1] + nh / 2) / ds + ry)
                self.log(
                    f"[match] {template_name} score={max_val:.3f} scale={scale:.3f}"
                )
                return (px, py)
        return None

    def check_duplicate_car(self):
        """Return True/False for a valid capture, or None when capture failed."""
        t0 = time.time()
        rx, ry, rw, rh = self._scale_roi(1025, 221, 1938, 484)
        dup_region = (
            max(0, rx - rw // 4),
            max(0, ry - rh // 2),
            int(rw * 1.5),
            int(rh * 2.5),
        )
        full = self.regions.get("全界面")
        if full:
            fx, fy, fw, fh = full
            dx, dy, dw, dh = dup_region
            cx = max(fx, dx)
            cy = max(fy, dy)
            cw = min(fx + fw, dx + dw) - cx
            ch = min(fy + fh, dy + dh) - cy
            dup_region = (cx, cy, max(1, cw), max(1, ch))
        screen = self.capture_region(dup_region)
        if screen is None or screen.size == 0:
            return None
        self._preview(screen, "重复车检测中...")

        found = False
        for name in self._DUPLICATE_TEMPLATES:
            if self._find_in_screen(name, screen, dup_region, self.dup_match_threshold):
                found = True
                break

        dt = (time.time() - t0) * 1000
        if found:
            self.log(f"[dup] 判态=True 耗时={dt:.0f}ms")
            self._preview(screen, "重复车: 已发现")
        return found

    # ==================== 重复车辆处理 ====================

    def handle_duplicate_vehicle(self, exit_menu=False):
        """处理重复车辆弹窗. exit_menu=True 时处理完加一次 ESC 退出抽奖菜单"""
        if not self._ensure_focus():
            return False

        price = None
        if self.duplicate_policy != "keep_all":
            price = self._read_duplicate_price()
        threshold = self.price_threshold
        self.log(
            f"[duplicate] 策略={self.duplicate_policy} | "
            f"识别价值={price if price is not None else '?'} | 阈值={threshold}"
        )

        action, ocr_failed = decide_duplicate_action(
            self.duplicate_policy, price, threshold
        )
        if ocr_failed:
            if self.duplicate_policy == "threshold":
                self.log("[duplicate] OCR 失败，按安全策略保留车辆")
            else:
                self.log("[duplicate] OCR 失败，仍按全部出售策略执行；本车收入不计")

        if action == "keep":
            self.log("[duplicate] 保留车辆 (回车)")
            self.hw_press("enter", use_send=True)
        else:
            self.log("[duplicate] 出售车辆 (下移2+回车)")
            self.hw_press("down", delay=0.12, use_send=True)
            time.sleep(0.1)
            self.hw_press("down", delay=0.12, use_send=True)
            time.sleep(0.1)
            self.hw_press("enter", use_send=True)

        if not self._wait_duplicate_dismissed():
            self.log("[duplicate] 未确认弹窗消失，操作结果不计入统计并停止")
            return False

        self.stats["total"] += 1
        if ocr_failed:
            self.stats["ocr_failed"] += 1
        if action == "keep":
            self.stats["kept"] += 1
        else:
            self.stats["sold"] += 1
            if price is not None:
                self.stats["earned"] += price
        self._notify_stats()
        time.sleep(0.15)

        if exit_menu:
            # 处理完回到抽奖入口页, 补 ESC 退出菜单
            self.log("[duplicate] ESC 退出菜单归位")
            self.hw_press("esc")
            time.sleep(0.5)
        return True

    def _wait_duplicate_dismissed(self, timeout=5):
        deadline = time.monotonic() + timeout
        while self.is_running and time.monotonic() < deadline:
            state = self.check_duplicate_car()
            if state is False:
                return True
            time.sleep(0.1)
        return False

    def _read_duplicate_price(self):
        """读取重复车辆价格——easyocr 识别 'CR X,XXX,XXX' 中的数字"""
        if not self._ensure_ocr_ready():
            return None
        rx, ry, rw, rh = self._scale_roi(1239, 1675, 1359, 113)
        price_region = (rx, ry, rw, rh)

        try:
            # 先确认价格区域存在
            price_pos = self.find_image("duplicate_car_price.png", price_region, 0.60)
            if not price_pos:
                self.log("[price] 未检测到价格区域")
                return None

            price_img = self.capture_region(price_region)
            if price_img is None or price_img.size == 0:
                return None
            self._preview(price_img, "价格识别区域")
            gray = cv2.cvtColor(price_img, cv2.COLOR_BGR2GRAY)

            # 裁剪右半部分 (跳过 "出售价格：CR " 前缀)
            # 参考分辨率下前缀约占 600px/1359px
            prefix_ratio = 600 / 1359
            crop_x = int(gray.shape[1] * prefix_ratio)
            number_roi = gray[:, crop_x:]

            # 放大 2x 提高 OCR 精度
            number_roi = cv2.resize(
                number_roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC
            )

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

    def _ensure_ocr_ready(self):
        if self._easyocr_ready.is_set():
            return True
        self._preload_ocr()
        self.log("[price] 等待 EasyOCR 初始化完成...")
        self._easyocr_done.wait(timeout=min(120, self.phase_timeout))
        if self._easyocr_ready.is_set():
            return True
        self.log("[price] EasyOCR 未能在安全时限内就绪")
        return False

    def _preload_ocr(self):
        """后台线程预加载 easyocr 模型, 避免首次使用时卡顿.
        daemon=True 确保主线程退出时自动终止.
        """
        if (
            self._easyocr_ready.is_set()
            or self._easyocr_reader is not None
            or self._easyocr_loading
        ):
            return
        self._easyocr_done.clear()
        self._easyocr_loading = True

        def _load():
            try:
                self.log("[price] 正在准备 EasyOCR；首次运行可能需要下载模型...")
                import easyocr

                reader = easyocr.Reader(
                    ["en"],
                    gpu=False,
                    download_enabled=True,
                    model_storage_directory=os.path.join(SCRIPT_DIR, ".easyocr_models"),
                    verbose=False,
                )
                if not self.is_running:
                    return
                self._easyocr_reader = reader
                self._easyocr_ready.set()
                self.log("[price] easyocr 模型就绪")
            except Exception as e:
                self.log(f"[price] easyocr 预加载失败: {e}")
            finally:
                self._easyocr_loading = False
                self._easyocr_done.set()

        threading.Thread(target=_load, daemon=True).start()

    def _ocr_digits_easyocr(self, binary_img):
        """使用 easyocr 识别二值化后的数字, 只保留数字和逗号"""
        if not self._easyocr_ready.is_set():
            self.log("[price] easyocr 尚未就绪, 跳过")
            return None
        try:
            results = self._easyocr_reader.readtext(
                binary_img, detail=0, allowlist="0123456789,"
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
        """Run normal wheelspins without resetting shared sequence statistics."""
        self.log(f"===== 开始普通抽奖 (共 {rounds} 次) =====")
        ok = self._gacha_loop(rounds, is_super=False)
        self._log_dup_stats()
        return ok

    def run_super_wheelspin(self, rounds=10):
        """Run super wheelspins without resetting shared sequence statistics."""
        self.log(f"===== 开始超级抽奖 (共 {rounds} 次) =====")
        ok = self._gacha_loop(rounds, is_super=True)
        self._log_dup_stats()
        return ok

    def run_sequence(self, normal_rounds=0, super_rounds=0, *, reset_stats=True):
        if reset_stats:
            self.reset_stats()
        if normal_rounds > 0 and not self.run_wheelspin(normal_rounds):
            return False
        if self.is_running and super_rounds > 0:
            return self.run_super_wheelspin(super_rounds)
        return self.is_running

    def _log_dup_stats(self):
        s = self.stats
        self.log(
            f"===== 重复车辆统计: 共{s['total']}辆 | 入库{s['kept']}辆 | "
            f"出售{s['sold']}辆 | 收入{s['earned']:,} CR | "
            f"OCR失败{s['ocr_failed']}次 ====="
        )

    def _gacha_loop(self, max_rounds, is_super):
        if max_rounds <= 0:
            return True
        phase_deadline = time.monotonic() + self.phase_timeout
        if not self.focus_game():
            self.log("无法连接游戏窗口")
            return False
        if not self.enter_menu():
            self.log("无法进入主菜单")
            return False

        btn_name = "super_wheelspin_btn.png" if is_super else "wheelspin_btn.png"
        search_region = "左" if is_super else "右"
        label = "超级抽奖" if is_super else "普通抽奖"
        pos = self.find_image(btn_name, search_region, 0.65, ref_w=3835)
        if not pos:
            self.log(f"未找到{label}按钮")
            return False
        self.log(f"点击{label}入口: {btn_name}")
        self.game_click(pos)

        for rnd in range(1, max_rounds + 1):
            if not self.is_running:
                return False
            self.log(f"--- 第 {rnd}/{max_rounds} 轮 ---")
            none_count = 0
            recovery_presses = 0
            while self.is_running:
                if time.monotonic() >= phase_deadline:
                    self.log(f"{label}阶段超过安全时限 {self.phase_timeout}s，停止")
                    return False
                if not self._ensure_focus():
                    return False

                if self.check_duplicate_car():
                    none_count = 0
                    self.log("[state] 重复车辆页面 → 处理")
                    if not self.handle_duplicate_vehicle(exit_menu=False):
                        return False
                    continue

                state = self.check_gacha_prompt()
                if state == "none":
                    none_count += 1
                    if none_count >= 30:
                        at_menu = self.find_image(
                            "super_wheelspin_btn.png",
                            region="左",
                            threshold=0.65,
                            ref_w=3835,
                        ) or self.find_image(
                            "wheelspin_btn.png", region="右", threshold=0.65, ref_w=3835
                        )
                        if at_menu:
                            self.log("检测到抽奖菜单 → 次数已耗尽")
                            self.hw_press("esc", delay=0.08)
                            return self.return_to_main_menu()
                        recovery_presses += 1
                        if recovery_presses > 3:
                            self.log("页面连续无法识别，已达到安全推进上限")
                            return False
                        self.log("未识别页面状态, 尝试 Enter 推进...")
                        self.hw_press("enter")
                        time.sleep(0.15)
                        none_count = 5
                    time.sleep(0.2)
                    continue

                none_count = 0
                if state == "skip":
                    self.log("跳过动画 → Enter")
                    self.hw_press("enter")
                    time.sleep(0.15)
                    continue

                if state == "claim":
                    stat_key = "super_spins" if is_super else "normal_spins"
                    self.stats[stat_key] += 1
                    self._notify_stats()
                    if rnd >= max_rounds:
                        self.log("最后一轮 → ESC 领取奖励")
                        self.hw_press("esc", delay=0.08)
                        time.sleep(0.2)
                        if not self._handle_all_duplicates():
                            return False
                        self.log("最后一轮 → ESC 退出菜单归位")
                        self.hw_press("esc", delay=0.08)
                        return self.return_to_main_menu()
                    self.log("领取并继续 → Enter")
                    self.hw_press("enter")
                    time.sleep(0.3)
                    if not self._handle_all_duplicates():
                        return False
                    break

                time.sleep(0.2)
        return True

    def _handle_all_duplicates(self):
        for _ in range(60):
            if not self.is_running:
                return False
            if self.check_duplicate_car():
                if not self.handle_duplicate_vehicle(exit_menu=False):
                    return False
                continue
            prompt = self.check_gacha_prompt()
            if prompt == "skip":
                self.log("[state] 检测到 'skip', 下一轮已开始 → Enter 跳过")
                self.hw_press("enter")
                time.sleep(0.15)
                return True
            if prompt == "claim":
                self.log("[state] 检测到 'claim' 提示, 回到主循环")
                return True
            at_menu = self.find_image(
                "super_wheelspin_btn.png", region="左", threshold=0.65, ref_w=3835
            ) or self.find_image(
                "wheelspin_btn.png", region="右", threshold=0.65, ref_w=3835
            )
            if at_menu:
                self.log("[state] 抽奖菜单页面, 全部重复车已处理")
                return True
            time.sleep(0.05)
        self.log("处理重复车辆超时")
        return False


def main():
    print("GachaCore 模块加载成功。")
    print("运行 test_gacha_gui.py 获取 GUI 测试界面。")


if __name__ == "__main__":
    main()
