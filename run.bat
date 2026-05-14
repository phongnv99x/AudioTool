@echo off
cd /d "%~dp0"
echo ===================================================
echo    AudioTool - Khoi dong tren VPS / May moi
echo ===================================================

:: 1. Kiem tra Python
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [LOI] Khong tim thay Python! Vui long cai dat Python truoc khi chay.
    echo Luu y: Nho tich vao o "Add Python to PATH" khi cai dat Python.
    pause
    exit /b
)

:: 2. Kiem tra FFmpeg
ffmpeg -version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    IF NOT EXIST "ffmpeg.exe" (
        echo [CANH BAO] Khong tim thay FFmpeg trong may!
        echo Dang tai FFmpeg tu dong - se mat vai phut...
        powershell -Command "Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile 'ffmpeg.zip'"
        echo Dang giai nen FFmpeg...
        powershell -Command "Expand-Archive -Path 'ffmpeg.zip' -DestinationPath '.'"
        move ffmpeg-master-latest-win64-gpl\bin\*.exe . >nul 2>&1
        rmdir /S /Q ffmpeg-master-latest-win64-gpl >nul 2>&1
        del ffmpeg.zip >nul 2>&1
        echo Da cai dat xong FFmpeg!
    )
)

:: Dua thu muc hien tai vao bien moi truong PATH (Giu cho FFmpeg hoat dong du code chuyen CWD)
set PATH=%CD%;%PATH%

:: 3. Tao moi truong ao (Virtual Environment)
if not exist "venv" (
    echo Dang tao moi truong ao Python (Virtual Environment)...
    python -m venv venv
)

:: 4. Kich hoat VENV
call venv\Scripts\activate.bat

:: 5. Cai dat thu vien
echo Dang kiem tra va cai dat cac thu vien can thiet...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt

:: 6. Chay Tool
echo ===================================================
echo Da san sang! Dang khoi dong AudioTool...
echo ===================================================
python main.py

pause
