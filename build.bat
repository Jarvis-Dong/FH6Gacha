@echo off
setlocal

cd /d "%~dp0"

set APP_NAME=FH6-Gacha
set MAIN_FILE=gacha_app.py

echo.
echo ==============================
echo Build %APP_NAME%
echo ==============================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found in PATH
    pause
    exit /b 1
)

echo [1/3] Cleaning...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /f /q "%APP_NAME%.spec"

echo [2/3] Updating PyInstaller...
python -m pip install pyinstaller -q

echo [3/3] Building...
python -m PyInstaller ^
    -n "%APP_NAME%" ^
    -F ^
    -w ^
    "%MAIN_FILE%" ^
    --add-data "images;images" ^
    --add-data "assets;assets" ^
    --add-data ".easyocr_models;.easyocr_models" ^
    --collect-all easyocr ^
    --hidden-import pynput.keyboard._win32 ^
    --hidden-import pynput.mouse._win32

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed
    pause
    exit /b 1
)

echo.
echo ===== Build OK =====
echo Output: dist\%APP_NAME%.exe
echo.
pause
