@echo off
cd /d "%~dp0"

if exist "FH6Gacha.exe" (
    start "" "FH6Gacha.exe"
    exit /b 0
)

if exist "dist\FH6Gacha.exe" (
    start "" "dist\FH6Gacha.exe"
    exit /b 0
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "gacha_app.py"
    exit /b 0
)

pythonw "gacha_app.py"
