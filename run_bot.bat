@echo off
:: Kiểm tra quyền Admin
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Dang chay duoi quyen Administrator.
    cd /d "%~dp0"
    python main.py
) else (
    echo [!] Tool dang khong co quyen Admin. Dang tu dong yeu cau quyen...
    powershell -Command "Start-Process '%~dpnx0' -Verb RunAs"
    exit /b
)
pause
