@echo off
setlocal
cd /d "%~dp0"

set APP_NAME=FH6-Gacha
set MAIN_FILE=gacha_app.py

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found in PATH
    pause
    exit /b 1
)

echo [1/3] Cleaning previous build...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo [2/3] Running PyInstaller...
python -m PyInstaller -n "%APP_NAME%" -F -w "%MAIN_FILE%" ^
    --add-data "images;images" ^
    --add-data "assets;assets" ^
    --add-data ".easyocr_models;.easyocr_models" ^
    --collect-all easyocr ^
    --hidden-import pynput.keyboard._win32 ^
    --hidden-import pynput.mouse._win32

if errorlevel 1 (
    echo [ERROR] PyInstaller failed
    pause
    exit /b 1
)

echo [3/3] Done. EXE is in dist\%APP_NAME%.exe
pause
