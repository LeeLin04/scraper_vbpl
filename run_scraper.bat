@echo off
chcp 65001 >nul
echo ========================================================
echo   CAI DAT VA CHAY DU AN (Co key2.json, key3.json, requirements.txt)
echo ========================================================

:: 1. Kiem tra Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Khong tim thay Python! Vui long cai dat Python va chon "Add Python to PATH".
    pause
    exit /b 1
)
echo [+] Da tim thay Python.

:: 2. Tao va kich hoat moi truong ao
if not exist "venv" (
    echo [+] Dang tao moi truong ao (venv)...
    python -m venv venv
)
echo [+] Dang kich hoat moi truong ao...
call venv\Scripts\activate

:: 3. Nang cap pip va cai dat thu vien tu requirements.txt cap nhat moi nhat
echo [+] Dang nang cap pip...
python -m pip install --upgrade pip

if exist "requirements.txt" (
    echo [+] Dang cai dat thu vien tu requirements.txt...
    pip install -r requirements.txt
) else (
    echo [CANH BAO] Khong tim thay requirements.txt!
    pip install requests beautifulsoup4 selenium pandas lxml openpyxl
)

:: 4. Kiem tra cac file key cau hinh (key2.json, key3.json)
echo [+] Dang kiem tra cac file key cau hinh...
if exist "key2.json" (
    echo   - Da tim thay key2.json
) else (
    echo   - [CANH BAO] Khong thay file key2.json trong thu muc!
)

if exist "key3.json" (
    echo   - Da tim thay key3.json
) else (
    echo   - [CANH BAO] Khong thay file key3.json trong thu muc!
)

:: 5. Chay du an
echo ========================================================
echo   HOAN TAT! Dang khoi chay chuong trinh...
echo ========================================================

if exist "main.py" (
    python main.py
) else if exist "run.py" (
    python run.py
) else (
    set /p custom_file="Khong tim thay main.py/run.py. Nhap ten file python can chay: "
    python %custom_file%
)

pause