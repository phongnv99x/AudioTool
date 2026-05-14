@echo off
echo ===================================================
echo    DONG GOI AUDIOTOOL THANH FILE EXE (GPU EDITION)
echo ===================================================

:: 1. Kiem tra ffmpeg.exe
IF NOT EXIST "Downloads\ffmpeg.exe" (
    echo [LOI] Khong tim thay file Downloads\ffmpeg.exe!
    echo Vui long dat file ffmpeg.exe vao thu muc Downloads roi thu lai.
    pause
    exit /b
)

:: 2. Kiem tra va cai dat pyinstaller
echo Dang cai dat cong cu dong goi (PyInstaller)...
python -m pip install pyinstaller >nul 2>&1

echo Dang tien hanh dong goi, qua trinh nay co the mat 5-10 phut...

:: Dong goi bang PyInstaller
:: --collect-all onnxruntime : Thu gom toan bo DLL cua onnxruntime-gpu (bao gom CUDA providers)
:: --collect-all rapidocr_onnxruntime : Thu gom model OCR
:: --collect-all customtkinter : Thu gom giao dien
:: --add-data "Downloads;Downloads" : Nhet TOAN BO thu muc Downloads (ffmpeg, kho nhac, cookies) vao goi
pyinstaller --noconfirm --onedir --windowed --icon=NONE --name "AudioTool_AI" ^
  --collect-all customtkinter ^
  --collect-all rapidocr_onnxruntime ^
  --collect-all onnxruntime ^
  --add-data "Downloads;Downloads" ^
  main.py

:: 3. Copy CUDA DLL tu onnxruntime-gpu vao thu muc dist (neu co)
echo Dang sao chep CUDA runtime vao goi...
set ONNX_LIB="%LOCALAPPDATA%\Programs\Python\Python311\Lib\site-packages\onnxruntime\capi"
if exist %ONNX_LIB% (
    xcopy /s /y %ONNX_LIB%\*.dll "dist\AudioTool_AI\" >nul 2>&1
    echo Da sao chep CUDA DLL thanh cong!
) else (
    echo [CANH BAO] Khong tim thay thu vien CUDA onnxruntime. GPU co the khong hoat dong tren VPS.
    echo (Kiem tra lai duong dan: %ONNX_LIB%)
)

echo ===================================================
echo HOAN TAT! 
echo Ban hay vao thu muc "dist\AudioTool_AI"
echo ZIP toan bo thu muc do lai va gui len VPS.
echo Giai nen ra va chay AudioTool_AI.exe la xong!
echo.
echo LUU Y cho VPS:
echo   - VPS can co NVIDIA Driver (khong can cai CUDA SDK rieng)
echo   - Neu GPU khong chay duoc, Tool tu dong fallback ve CPU
echo ===================================================
pause
