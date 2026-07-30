# CLAUDE.md

## Commands

```bash
python gacha_app.py
python -m unittest discover -s tests -v
python -m py_compile gacha_app.py gacha_backend.py gacha_bridge.py gacha_core.py gacha_policy.py
build.bat
```

`build.bat` is Windows-only. It prepares EasyOCR models, runs tests, builds the
single-file `FH6Gacha.exe`, and smoke-tests the packaged GUI.

## Boundaries

- Never modify, unpack, inject, or repackage the official `FH6Auto.exe`.
- Never inject into the FH6 game process.
- Game screenshots use `PrintWindow`; game input uses `PostMessage`. Do not
  reintroduce foreground focus, physical mouse movement, or game `SendInput`.
- Bridge hotkeys F8/F9 use the global input queue only because FH6Auto listens
  through `pynput`.
- At an intermediate loop boundary, require the FH6Auto pause log and leave a
  short settling delay for its key-release loop. The official input mixin calls
  `check_pause()` before every key press and game click.
- On any takeover failure, deliver F8 and stop the official task. Never resume
  the next FH6Auto loop after unsafe gacha.

## Architecture

- `gacha_app.py`: tkinter GUI, settings, standalone/bridge workers, global keys.
- `gacha_backend.py`: Steam process/window discovery, background capture/input,
  bridge hotkeys.
- `gacha_core.py`: normal/super state machine, OCR, duplicate handling, stats.
- `gacha_bridge.py`: diagnostic follower, temporary config guard, handshakes.
- `gacha_policy.py`: pure duplicate decision logic.

Templates use a 3835x2159 reference except `collectionjournal.png`, which uses
the original 2560-wide FH6Auto reference. The primary validation target is
1600x900 or larger; smaller windows remain best-effort and must not be blocked.
EasyOCR models are loaded from
`.easyocr_models/`; the first price read waits for initialization, threshold
mode keeps on failure, sell-all still sells, and keep-all skips OCR. Duplicate
actions use synchronous background messages and commit stats only after the
popup is confirmed dismissed.

F8 starts when idle and emergency-stops when running. F9 stops standalone mode;
bridge mode reserves it for FH6Auto pause/resume handshakes. Statistics are
cumulative across normal and super spins in one run and across bridge cycles.
