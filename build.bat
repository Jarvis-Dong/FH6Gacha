@echo off
setlocal

cd /d "%~dp0"

set APP_NAME=FH6Gacha
set MAIN_FILE=gacha_app.py
set PYTHON_EXE=python
if exist ".venv\Scripts\python.exe" set PYTHON_EXE=.venv\Scripts\python.exe

echo.
echo ==============================
echo Build %APP_NAME%
echo ==============================
echo.

"%PYTHON_EXE%" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python not found in PATH
    pause
    exit /b 1
)

echo [1/7] Checking dependencies...
"%PYTHON_EXE%" -c "import cv2,easyocr,numpy,pynput,win32gui" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    "%PYTHON_EXE%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed
        pause
        exit /b 1
    )
)

echo [2/7] Preparing EasyOCR models...
"%PYTHON_EXE%" -c "import easyocr; easyocr.Reader(['en'],gpu=False,download_enabled=True,model_storage_directory=r'.easyocr_models',verbose=False)"
if errorlevel 1 echo [WARN] OCR model download failed; runtime download fallback remains enabled
set OCR_DATA=
if exist ".easyocr_models" set OCR_DATA=--add-data ".easyocr_models;.easyocr_models"

echo [3/7] Running tests...
set PYTHONDONTWRITEBYTECODE=1
"%PYTHON_EXE%" -m unittest discover -s tests -v
if errorlevel 1 (
    echo [ERROR] Tests failed
    pause
    exit /b 1
)

echo [4/7] Cleaning...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /f /q "%APP_NAME%.spec"

echo [5/7] Checking PyInstaller...
"%PYTHON_EXE%" -c "import PyInstaller" >nul 2>nul
if errorlevel 1 "%PYTHON_EXE%" -m pip install pyinstaller

echo [6/7] Building...
"%PYTHON_EXE%" -m PyInstaller ^
    -n "%APP_NAME%" ^
    -F ^
    -w ^
    --noupx ^
    "%MAIN_FILE%" ^
    --add-data "images;images" ^
    --add-data "assets;assets" ^
    %OCR_DATA% ^
    --collect-all easyocr ^
    --hidden-import gacha_backend ^
    --hidden-import gacha_bridge ^
    --hidden-import gacha_core ^
    --hidden-import gacha_i18n ^
    --hidden-import gacha_policy ^
    --hidden-import pynput.keyboard._win32 ^
    --hidden-import pynput.mouse._win32 ^
    --noconfirm

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed
    pause
    exit /b 1
)

echo [7/7] Running packaged smoke test...
start /wait "" "dist\%APP_NAME%.exe" --smoke-test
if errorlevel 1 (
    echo [ERROR] Packaged smoke test failed
    pause
    exit /b 1
)

echo.
echo ===== Build OK =====
echo Output: dist\%APP_NAME%.exe
echo.
pause
