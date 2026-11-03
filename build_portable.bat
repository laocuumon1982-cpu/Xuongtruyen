@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo == Build Xuong Truyen portable ==
if not exist .venv python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name XuongTruyen --icon assets/icon.ico ^
  --add-data "app/web;app/web" --collect-all webview --collect-all clr_loader --collect-all pythonnet ^
  --collect-data docx XuongTruyen.py
echo.
echo Xong! Ban portable nam o: dist\XuongTruyen\XuongTruyen.exe
pause
