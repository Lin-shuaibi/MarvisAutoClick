@echo off
chcp 65001 >nul
echo ============================================
echo   AutoConfirm - Build Script
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

:: Install deps
echo [1/3] Installing dependencies...
pip install --upgrade pyinstaller pywin32 opencv-python numpy pillow
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Clean old builds
echo [2/3] Cleaning old builds...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist *.spec del /q *.spec

:: Build
echo [3/3] Compiling...
python -m PyInstaller --onefile --windowed --name "MarvisAutoClick" --clean --noconfirm auto_confirm.py

if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo   ^> Build Successful!
    echo   Output: dist\MarvisAutoClick.exe
    echo ============================================
) else (
    echo.
    echo [ERROR] Build failed. Check error messages above.
)

pause
