@echo off
title AFK Journey Bot Builder
echo =======================================
echo     AFK Journey Bot EXE Builder
echo =======================================
echo.

:: Di chuyển vào thư mục của file bat
cd /d "%~dp0"

:: 1. Kiểm tra và cài đặt pyinstaller
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

:: 2. Đóng gói ứng dụng
echo.
echo [*] Dang tien hanh dong goi ung dung...
echo [*] Dung kieu: 1 Thu muc co day du file (Khuyen nghi cho toc do load nhanh hon)
echo.

:: Nhận diện đường dẫn CustomTkinter để add-data tự động (nếu cần)
for /f "delims=" %%i in ('python -c "import customtkinter; import os; print(os.path.dirname(customtkinter.__file__))"') do set "CTK_DIR=%%i"

if "%CTK_DIR%"=="" (
    echo [!] Canh bao: Khong tim thay thu muc customtkinter. PyInstaller tu xu ly.
    python -m PyInstaller --noconfirm --onedir --windowed --add-data "templates;templates" main.py
) else (
    echo [OK] Tim thay CustomTkinter tai: %CTK_DIR%
    python -m PyInstaller --noconfirm --onedir --windowed --add-data "templates;templates" --add-data "%CTK_DIR%;customtkinter" main.py
)

if %errorlevel% neq 0 (
    echo.
    echo [x] Loi: Dong goi that bai.
    pause
    exit /b 1
)

echo.
echo =======================================
echo [OK] Dong goi thanh cong!
echo [+] File .exe nam trong thu muc: dist\main\main.exe
echo [+] Ban can COPY nguyen thu muc "main" trong "dist" de di chuyen sang may khac.
echo =======================================
pause
