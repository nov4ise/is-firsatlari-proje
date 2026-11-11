@echo off
chcp 65001 >nul
title IS FIRSATLARI - EXE KURULUMU
echo ==========================================
echo   IS FIRSATLARI - EXE HAZIRLANIYOR
echo ==========================================
py -m pip install --upgrade pip
if errorlevel 1 python -m pip install --upgrade pip
py -m pip install -r requirements.txt
if errorlevel 1 python -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --clean --onefile --windowed --name IsFirsatlari --icon logo_is_firsatlari.ico --add-data "logo_is_firsatlari.png;." is_firsatlari.py
if errorlevel 1 (
  echo.
  echo EXE olusturulamadi. Python kurulumunu ve internet baglantisini kontrol edin.
  pause
  exit /b 1
)
echo.
echo BASARILI! EXE dosyasi dist\IsFirsatlari.exe konumunda.
pause
