@echo off
call .venv\Scripts\activate
pyinstaller --noconsole --onefile --clean --name AlfaDrop ^
  --icon assets\alfadrop.ico ^
  --add-data "assets\alfadrop.ico;assets" ^
  main.py
echo.
echo Done. Your exe is in the dist folder: dist\AlfaDrop.exe
pause