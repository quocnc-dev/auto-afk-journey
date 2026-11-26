@echo off
title AFK Journey Bot Builder
echo =======================================
echo     AFK Journey Bot EXE Builder
echo =======================================
echo.

cd /d "%~dp0"

echo [*] Dang kiem tra PyInstaller...
python -m pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] PyInstaller chua duoc cai dat. Dang tien hanh cai dat...
    python -m pip install pyinstaller
    python -c "import PyInstaller" >nul 2>&1
    if %errorlevel% neq 0 (
        echo [x] Loi: Khong the cai dat pyinstaller.
        pause
        exit /b 1
    )
    echo [OK] Cai dat PyInstaller thanh cong!
) else (
    echo [OK] PyInstaller da duoc cai dat.
)

echo.
echo [*] Dang tien hanh dong goi ung dung (kem model RapidOCR + CustomTkinter)...
echo.

python -m PyInstaller --noconfirm --onedir --windowed --name "AFKJourneyBot" --collect-all rapidocr_onnxruntime --collect-all customtkinter --collect-data certifi --add-data "templates;templates" main.py

if %errorlevel% neq 0 (
    echo.
    echo [x] Loi: Dong goi that bai.
    pause
    exit /b 1
)

echo.
echo =======================================
echo [OK] Dong goi thanh cong!
echo [+] File .exe nam trong thu muc: dist\AFKJourneyBot\AFKJourneyBot.exe
echo [+] Ban can COPY nguyen thu muc "AFKJourneyBot" trong "dist" de di chuyen sang may khac.
echo =======================================
pause
