# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the main GUI
python gacha_app.py

# ROI selection tool for finding template coordinates
python roi_selector.py

# Build single-file EXE (requires PyInstaller)
build.bat
```

No test suite exists for this project.

## Architecture

**Two-layer design**: `gacha_core.py` is the headless engine; `gacha_app.py` is the tkinter GUI. The core has no tkinter imports and communicates via three callbacks:

| Callback | Signature | Purpose |
|---|---|---|
| `log_callback` | `(msg: str)` | Log messages |
| `stats_callback` | `(stats: dict)` | Dup vehicle stats `{total, kept, sold, earned}` |
| `preview_callback` | `(image: np.ndarray, title: str)` | ROI preview for debug overlays |

`gacha_app.py` creates a new `GachaCore` instance on each Start click (the old instance is discarded). This means `dup_stats` resets per run session. The GUI also resets stat labels in `_start()` before creating the core.

## Hardware input

Keyboard input uses Windows `SendInput` API with DirectInput scan codes (`DIK_CODES` dict in `gacha_core.py`), not virtual-key codes. This is required because the game reads DirectInput, not Windows messages. Mouse clicks use a hybrid: `hw_mouse_move` via SendInput + `pydirectinput.mouseDown/Up`. After each click, the mouse is moved to (5,5) to prevent hover tooltips from blocking screenshots.

## Template matching

All matching uses reference resolution **3835×2159**. ROIs are defined in `_scale_roi()` at this reference size and mapped to the actual game window via `scale_x`/`scale_y` computed from the window's client area. `find_image()` and `_find_in_screen()` try 7 scale variations (base ±2%/5%/8%) via `_get_scales()`. The `ref_w` parameter selects the template's reference width: `3835` for gacha templates, `2560` for the main menu anchor (`collectionjournal.png`) which comes from the older FH6Auto project.

## State machine (`_gacha_loop`)

The main loop in `gacha_core.py` alternates between three states driven by template matching on a fixed lower-left ROI:

1. **Duplicate car** — `check_duplicate_car()` scans a region for `duplicate_car.png`. If found, `handle_duplicate_vehicle()` reads the price via EasyOCR and either keeps (Enter) or sells (Down×2 + Enter).
2. **Skip prompt** — `enter_skip_prompt.png` matches → press Enter to skip animation.
3. **Claim prompt** — `gacha_prompt_area.png` matches → Enter to claim and continue, or ESC on the final round.

If `none` is seen 10 consecutive times, the loop checks whether it's back at the menu (wheelspin buttons visible) and exits if so.

## Resource extraction

Both `gacha_core.py` and `gacha_app.py` have module-level `_auto_extract_dir()` calls that copy `images/`, `assets/`, and `.easyocr_models/` from `sys._MEIPASS` (PyInstaller's internal temp) to the exe's directory on first run. Files that already exist are skipped.

## Global hotkeys

F8 = start, F9 = stop. Implemented in `gacha_app.py` via `pynput.keyboard.Listener` (not GlobalHotKeys — the listener pattern allows checking `is_running` state). These work even when the GUI is not focused.

## Cancellation

The `GachaCore.is_running` boolean is checked at every loop iteration and between template matching attempts. Setting it to `False` causes all loops to exit cleanly. The GUI's `_stop()` sets this flag; F9 hotkey and the Stop button both call `_stop()`.

## EasyOCR

Used for reading duplicate car prices. The reader is loaded asynchronously via `_preload_ocr()` (called after `focus_game()` succeeds). The price region is cropped, grayscaled, thresholded at 160, then OCR'd with whitelist `"0123456789,"`. The reader expects models in `.easyocr_models/`.
