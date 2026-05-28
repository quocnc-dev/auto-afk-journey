@echo off
echo ============================================
echo   AFK Journey Auto Bot - Setup
echo ============================================
echo.
echo [1/3] Kiem tra Python...
python --version
if errorlevel 1 (
    echo ERROR: Chua cai Python! Tai tai https://python.org
    pause
    exit /b 1
)

echo.
echo [2/3] Cai dat thu vien...
python -m pip install -r requirements.txt

echo.
echo [3/3] Tao thu muc can thiet...
if not exist "templates" mkdir templates
if not exist "logs" mkdir logs

echo.
echo ============================================
echo   SETUP HOAN THANH!
echo   Chay bot: python main.py
echo   Chup template: python capture_template.py
echo ============================================
pause
