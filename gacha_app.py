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
from gacha_i18n import LANGUAGE_NAMES, POLICY_LABELS, tr

APP_DIR = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
INTERNAL_DIR = getattr(sys, "_MEIPASS", APP_DIR)
SETTINGS_FILE = os.path.join(APP_DIR, ".gacha_settings.json")

DEFAULTS = {
    "language": "zh",
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


for _folder in ("images", ".easyocr_models"):
    _extract_resources(_folder)


def load_settings():
    settings = dict(DEFAULTS)
    try:
        payload = json.loads(Path(SETTINGS_FILE).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            settings.update(payload)
    except (OSError, json.JSONDecodeError):
        pass
    if settings.get("language") not in LANGUAGE_NAMES:
        settings["language"] = "zh"
    if settings.get("duplicate_policy") not in POLICY_LABELS["zh"]:
        settings["duplicate_policy"] = "threshold"
    return settings


def save_settings(settings):
    temp = Path(SETTINGS_FILE).with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temp, SETTINGS_FILE)


def _smoke_test_embedded_ocr():
    model_dir = Path(APP_DIR) / ".easyocr_models"
    if not (model_dir / "english_g2.pth").is_file():
        return
    import easyocr

    easyocr.Reader(
        ["en"],
        gpu=False,
        download_enabled=False,
        detector=False,
        model_storage_directory=str(model_dir),
        verbose=False,
    )


class GachaApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.language = self.settings["language"]
        self.root.title(self._t("window_title"))
        self.root.geometry("1180x820")
        self.root.minsize(1020, 720)
        self.recovered_config = self._recover_pending_config()
        self.running = False
        self.core = None
        self.bridge = None
        self.config_guard = None
        self.worker = None
        self._keyboard_listener = None
        self.closing = threading.Event()
        self._localized_widgets = []
        self.status_key = "status_ready"
        self._build_ui()
        if self.recovered_config:
            self._append_log(self._t("config_recovered"))
        self._setup_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _t(self, key, **values):
        return tr(self.language, key, **values)

    def _localize(self, widget, key):
        self._localized_widgets.append((widget, key))
        widget.configure(text=self._t(key))
        return widget

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
        colors = {
            "bg": "#0F141B",
            "panel": "#18202B",
            "card": "#171D26",
            "input": "#131923",
            "border": "#2A3442",
            "text": "#F0F6FC",
            "muted": "#8B949E",
            "blue": "#1F6AA5",
            "green": "#2EA043",
            "red": "#DA3633",
            "gold": "#F1C40F",
        }
        self.colors = colors
        self.root.configure(bg=colors["bg"])

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            ".",
            background=colors["bg"],
            foreground=colors["text"],
            font=("Microsoft YaHei UI", 11),
        )
        style.configure("TFrame", background=colors["bg"])
        style.configure("TLabel", background=colors["bg"], foreground=colors["text"])
        style.configure(
            "Card.TLabelframe",
            background=colors["panel"],
            bordercolor=colors["border"],
            relief="solid",
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=colors["panel"],
            foreground=colors["gold"],
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        style.configure("Panel.TFrame", background=colors["panel"])
        style.configure(
            "Panel.TLabel", background=colors["panel"], foreground=colors["text"]
        )
        style.configure(
            "Hint.TLabel", background=colors["panel"], foreground=colors["muted"]
        )
        style.configure(
            "TEntry",
            fieldbackground=colors["input"],
            foreground=colors["text"],
            insertcolor=colors["text"],
            bordercolor=colors["border"],
            lightcolor=colors["border"],
            darkcolor=colors["border"],
        )
        style.configure(
            "TCombobox",
            fieldbackground=colors["input"],
            background=colors["panel"],
            foreground=colors["text"],
            arrowcolor=colors["text"],
            bordercolor=colors["border"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", colors["input"])],
            foreground=[("readonly", colors["text"])],
        )
        style.configure(
            "TRadiobutton",
            background=colors["panel"],
            foreground=colors["text"],
            indicatorcolor=colors["input"],
        )
        style.map(
            "TRadiobutton",
            background=[("active", colors["panel"])],
            indicatorcolor=[("selected", colors["blue"])],
        )
        style.configure(
            "TCheckbutton",
            background=colors["panel"],
            foreground=colors["muted"],
            indicatorcolor=colors["input"],
        )
        style.map(
            "TCheckbutton",
            background=[("active", colors["panel"])],
            foreground=[("active", colors["text"])],
            indicatorcolor=[("selected", colors["green"])],
        )

        header = tk.Frame(self.root, bg=colors["bg"], padx=20, pady=14)
        header.pack(fill=tk.X)
        brand = tk.Frame(header, bg=colors["bg"])
        brand.pack(side=tk.LEFT)
        tk.Label(
            brand,
            text="FH6GACHA",
            bg=colors["bg"],
            fg="#5DADE2",
            font=("Segoe UI", 24, "bold"),
        ).pack(anchor="w")
        self.brand_subtitle = self._localize(
            tk.Label(
                brand,
                bg=colors["bg"],
                fg=colors["muted"],
                font=("Segoe UI", 9, "bold"),
            ),
            "brand_subtitle",
        )
        self.brand_subtitle.pack(anchor="w")

        header_right = tk.Frame(header, bg=colors["bg"])
        header_right.pack(side=tk.RIGHT)
        self.language_label = self._localize(
            tk.Label(
                header_right,
                bg=colors["bg"],
                fg=colors["muted"],
                font=("Microsoft YaHei UI", 10),
            ),
            "language",
        )
        self.language_label.pack(side=tk.LEFT, padx=(0, 6))
        self.language_display_var = tk.StringVar(value=LANGUAGE_NAMES[self.language])
        self.language_box = ttk.Combobox(
            header_right,
            textvariable=self.language_display_var,
            values=list(LANGUAGE_NAMES.values()),
            state="readonly",
            width=9,
        )
        self.language_box.pack(side=tk.LEFT, padx=(0, 14))
        self.language_box.bind("<<ComboboxSelected>>", self._on_language_changed)
        self.status_var = tk.StringVar(value=self._t("status_ready"))
        self.status_label = tk.Label(
            header_right,
            textvariable=self.status_var,
            bg="#222B36",
            fg="#C9D1D9",
            padx=16,
            pady=7,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.status_label.pack(side=tk.LEFT)

        controls = self._localize(
            ttk.LabelFrame(self.root, padding=14, style="Card.TLabelframe"),
            "run_settings",
        )
        controls.pack(fill=tk.X, padx=18, pady=(0, 10))
        for column in range(6):
            controls.columnconfigure(column, weight=1 if column in (1, 4) else 0)

        self.mode_var = tk.StringVar(value=self.settings["mode"])
        self.standalone_radio = self._localize(
            ttk.Radiobutton(
                controls,
                variable=self.mode_var,
                value="standalone",
                command=self._update_mode_ui,
            ),
            "standalone_mode",
        )
        self.standalone_radio.grid(row=0, column=0, columnspan=2, sticky="w")
        self.bridge_radio = self._localize(
            ttk.Radiobutton(
                controls,
                variable=self.mode_var,
                value="bridge",
                command=self._update_mode_ui,
            ),
            "bridge_mode",
        )
        self.bridge_radio.grid(row=0, column=2, columnspan=4, sticky="w", padx=(18, 0))

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
        self.policy_key = self.settings["duplicate_policy"]
        self.policy_var = tk.StringVar()

        normal_label = self._localize(
            ttk.Label(controls, style="Panel.TLabel"), "normal_rounds"
        )
        normal_label.grid(row=1, column=0, sticky="e", pady=9)
        ttk.Entry(controls, textvariable=self.normal_var, width=10).grid(
            row=1, column=1, sticky="w", padx=9
        )
        self.normal_empty_check = self._localize(
            ttk.Checkbutton(controls, variable=self.normal_empty_var), "until_empty"
        )
        self.normal_empty_check.grid(row=1, column=2, sticky="w")

        super_label = self._localize(
            ttk.Label(controls, style="Panel.TLabel"), "super_rounds"
        )
        super_label.grid(row=1, column=3, sticky="e", padx=(20, 0))
        ttk.Entry(controls, textvariable=self.super_var, width=10).grid(
            row=1, column=4, sticky="w", padx=9
        )
        self.super_empty_check = self._localize(
            ttk.Checkbutton(controls, variable=self.super_empty_var), "until_empty"
        )
        self.super_empty_check.grid(row=1, column=5, sticky="w")

        policy_label = self._localize(
            ttk.Label(controls, style="Panel.TLabel"), "duplicate_policy"
        )
        policy_label.grid(row=2, column=0, sticky="e", pady=9)
        self.policy_box = ttk.Combobox(
            controls,
            textvariable=self.policy_var,
            state="readonly",
            width=39,
        )
        self.policy_box.grid(row=2, column=1, columnspan=2, sticky="ew", padx=9)
        self.policy_box.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_mode_ui()
        )
        price_label = self._localize(
            ttk.Label(controls, style="Panel.TLabel"), "price_threshold"
        )
        price_label.grid(row=2, column=3, sticky="e", padx=(20, 0))
        self.price_entry = ttk.Entry(controls, textvariable=self.price_var, width=14)
        self.price_entry.grid(row=2, column=4, sticky="w", padx=9)
        ttk.Label(controls, text="CR", style="Panel.TLabel").grid(
            row=2, column=5, sticky="w"
        )

        timeout_label = self._localize(
            ttk.Label(controls, style="Panel.TLabel"), "phase_timeout"
        )
        timeout_label.grid(row=3, column=0, sticky="e", pady=9)
        ttk.Entry(controls, textvariable=self.timeout_var, width=9).grid(
            row=3, column=1, sticky="w", padx=9
        )
        seconds_label = self._localize(
            ttk.Label(controls, style="Panel.TLabel"), "seconds"
        )
        seconds_label.grid(row=3, column=2, sticky="w")

        self.bridge_frame = ttk.Frame(controls, style="Panel.TFrame")
        self.bridge_frame.grid(row=4, column=0, columnspan=6, sticky="ew", pady=(6, 0))
        self.fh6auto_dir_var = tk.StringVar(value=self.settings["fh6auto_dir"])
        bridge_dir_label = self._localize(
            ttk.Label(self.bridge_frame, style="Panel.TLabel"), "fh6auto_dir"
        )
        bridge_dir_label.pack(side=tk.LEFT)
        ttk.Entry(self.bridge_frame, textvariable=self.fh6auto_dir_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=8
        )
        self.browse_btn = self._localize(
            tk.Button(
                self.bridge_frame,
                command=self._choose_fh6auto_dir,
                bg="#334155",
                fg=colors["text"],
                activebackground="#475569",
                activeforeground=colors["text"],
                relief=tk.FLAT,
                padx=12,
                pady=5,
                cursor="hand2",
            ),
            "browse",
        )
        self.browse_btn.pack(side=tk.LEFT)
        self.bridge_hint = self._localize(
            ttk.Label(self.bridge_frame, style="Hint.TLabel"), "bridge_hint"
        )
        self.bridge_hint.pack(side=tk.LEFT, padx=12)

        buttons = tk.Frame(self.root, bg=colors["bg"], padx=18, pady=2)
        buttons.pack(fill=tk.X)
        self.start_btn = self._localize(
            tk.Button(
                buttons,
                command=self._start,
                bg=colors["green"],
                fg="#FFFFFF",
                activebackground="#238636",
                activeforeground="#FFFFFF",
                disabledforeground="#6E7681",
                relief=tk.FLAT,
                padx=22,
                pady=9,
                font=("Microsoft YaHei UI", 11, "bold"),
                cursor="hand2",
            ),
            "start",
        )
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = self._localize(
            tk.Button(
                buttons,
                command=self._stop,
                state=tk.DISABLED,
                bg=colors["red"],
                fg="#FFFFFF",
                activebackground="#B02A37",
                activeforeground="#FFFFFF",
                disabledforeground="#6E7681",
                relief=tk.FLAT,
                padx=22,
                pady=9,
                font=("Microsoft YaHei UI", 11, "bold"),
                cursor="hand2",
            ),
            "emergency_stop",
        )
        self.stop_btn.pack(side=tk.LEFT, padx=9)
        self.hotkey_hint = self._localize(
            tk.Label(
                buttons,
                bg=colors["bg"],
                fg=colors["muted"],
                font=("Microsoft YaHei UI", 10),
            ),
            "hotkey_hint",
        )
        self.hotkey_hint.pack(side=tk.LEFT, padx=12)

        stats_shell = tk.Frame(self.root, bg=colors["bg"], padx=18, pady=8)
        stats_shell.pack(fill=tk.X)
        self.stats_title = self._localize(
            tk.Label(
                stats_shell,
                bg=colors["bg"],
                fg=colors["gold"],
                font=("Microsoft YaHei UI", 12, "bold"),
            ),
            "stats_title",
        )
        self.stats_title.pack(anchor="w", pady=(0, 4))
        cards = tk.Frame(stats_shell, bg=colors["bg"])
        cards.pack(fill=tk.X)
        for column in range(4):
            cards.columnconfigure(column, weight=1, uniform="stats")
        self.stats_labels = {}
        stats = [
            ("normal_spins", "stat_normal", "#3498DB"),
            ("super_spins", "stat_super", "#8E44AD"),
            ("total", "stat_duplicates", "#E67E22"),
            ("kept", "stat_kept", "#2EA043"),
            ("sold", "stat_sold", "#DA3633"),
            ("earned", "stat_sale_income", "#F1C40F"),
            ("ocr_failed", "stat_ocr_failed", "#8B949E"),
            ("bridge_cycles", "stat_bridge_cycles", "#17A2B8"),
        ]
        last_stats = self.settings.get("last_stats") or {}
        for index, (key, text_key, accent) in enumerate(stats):
            box = tk.Frame(
                cards,
                bg=colors["card"],
                highlightbackground=colors["border"],
                highlightthickness=1,
                padx=13,
                pady=9,
            )
            box.grid(
                row=index // 4,
                column=index % 4,
                padx=4,
                pady=4,
                sticky="nsew",
            )
            title = self._localize(
                tk.Label(
                    box,
                    bg=colors["card"],
                    fg=colors["muted"],
                    font=("Microsoft YaHei UI", 9),
                ),
                text_key,
            )
            title.pack(anchor="w")
            value = last_stats.get(key, 0)
            self.stats_labels[key] = tk.Label(
                box,
                text=f"{value:,}" if isinstance(value, int) else str(value),
                bg=colors["card"],
                fg=accent,
                font=("Segoe UI", 17, "bold"),
            )
            self.stats_labels[key].pack(anchor="w")
        self.income_note = self._localize(
            tk.Label(
                stats_shell,
                bg=colors["bg"],
                fg="#D29922",
                font=("Microsoft YaHei UI", 9),
                anchor="w",
            ),
            "income_note",
        )
        self.income_note.pack(fill=tk.X, padx=5, pady=(3, 0))

        log_frame = tk.Frame(
            self.root,
            bg=colors["panel"],
            highlightbackground=colors["border"],
            highlightthickness=1,
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 16))
        self.log_title = self._localize(
            tk.Label(
                log_frame,
                bg=colors["panel"],
                fg="#5DADE2",
                font=("Microsoft YaHei UI", 11, "bold"),
                padx=12,
                pady=7,
            ),
            "log_title",
        )
        self.log_title.pack(anchor="w")
        log_body = tk.Frame(log_frame, bg=colors["panel"])
        log_body.pack(fill=tk.BOTH, expand=True, padx=7, pady=(0, 7))
        self.log_text = tk.Text(
            log_body,
            state=tk.DISABLED,
            font=("Cascadia Mono", 11),
            wrap=tk.WORD,
            bg=colors["input"],
            fg="#C9D1D9",
            insertbackground=colors["text"],
            selectbackground=colors["blue"],
            relief=tk.FLAT,
            padx=10,
            pady=8,
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_body, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self._refresh_language()
        self._update_mode_ui()

    def _selected_policy(self):
        labels = POLICY_LABELS[self.language]
        return next(
            (key for key, label in labels.items() if label == self.policy_var.get()),
            self.policy_key,
        )

    def _on_language_changed(self, _event=None):
        self.policy_key = self._selected_policy()
        selected = self.language_display_var.get()
        self.language = next(
            (code for code, label in LANGUAGE_NAMES.items() if label == selected),
            "zh",
        )
        self.settings["language"] = self.language
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self._refresh_language()
        self._update_mode_ui()

    def _refresh_language(self):
        self.root.title(self._t("window_title"))
        for widget, key in self._localized_widgets:
            widget.configure(text=self._t(key))
        self.status_var.set(self._t(self.status_key))
        self.language_display_var.set(LANGUAGE_NAMES[self.language])
        self.policy_box.configure(values=list(POLICY_LABELS[self.language].values()))
        self.policy_var.set(POLICY_LABELS[self.language][self.policy_key])

    def _set_status(self, key, color):
        self.status_key = key
        self.status_var.set(self._t(key))
        self.status_label.configure(bg=color, fg="#FFFFFF")

    def _update_mode_ui(self):
        self.policy_key = self._selected_policy()
        if self.mode_var.get() == "bridge":
            self.bridge_frame.grid()
        else:
            self.bridge_frame.grid_remove()
        self.price_entry.configure(
            state="normal" if self.policy_key == "threshold" else "disabled"
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
            raise ValueError(self._t("at_least_one"))
        self.policy_key = self._selected_policy()
        settings = {
            "language": self.language,
            "mode": self.mode_var.get(),
            "normal_rounds": self._parse_int(self.normal_var.get(), 0),
            "super_rounds": self._parse_int(self.super_var.get(), 0),
            "normal_until_empty": bool(self.normal_empty_var.get()),
            "super_until_empty": bool(self.super_empty_var.get()),
            "duplicate_policy": self.policy_key,
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
            messagebox.showerror(self._t("error_title"), str(exc), parent=self.root)
            return

        self.running = True
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        if self.settings["mode"] == "bridge":
            self._set_status("status_bridge", self.colors["blue"])
        else:
            self._set_status("status_standalone", self.colors["green"])
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
            raise FileNotFoundError(self._t("invalid_bridge_dir"))
        if process_running("FH6Auto.exe"):
            raise RuntimeError(self._t("close_running_auto"))
        config = json.loads(config_path.read_text(encoding="utf-8"))
        route_errors = validate_fh6auto_pipeline(config)
        if route_errors:
            raise ValueError(self._t("route_error", errors="\n".join(route_errors)))

    def _run_standalone(self, normal, super_rounds):
        try:
            ok = self.core.run_sequence(normal, super_rounds)
            self._log(self._t("standalone_done" if ok else "standalone_incomplete"))
        except Exception as exc:
            self._log(self._t("standalone_error", error=exc))
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
            self._log(self._t("bridge_done" if ok else "bridge_incomplete"))
        except Exception as exc:
            self._log(self._t("bridge_error", error=exc))
        finally:
            try:
                if self.config_guard:
                    if process_running("FH6Auto.exe") and not self.closing.is_set():
                        self._log(self._t("close_auto_restore"))
                    while process_running("FH6Auto.exe") and not self.closing.wait(1.0):
                        pass
                    still_running = process_running("FH6Auto.exe")
                    self.config_guard.restore(keep_backup=still_running)
                    if still_running:
                        self._log(self._t("backup_retained"))
            except Exception as exc:
                self._log(self._t("restore_failed", error=exc))
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
        self._set_status("status_stopping", self.colors["red"])
        self._log(self._t("stop_requested"))

    def _on_done(self):
        if self.core:
            self.core.close()
        self.running = False
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self._set_status("status_ready", "#222B36")

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
    if "--smoke-test" in sys.argv:
        _smoke_test_embedded_ocr()
    root = tk.Tk()
    app = GachaApp(root)
    if "--smoke-test" in sys.argv:
        root.after(2000, app._on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
