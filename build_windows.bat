@echo off
setlocal
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --windowed --name ProgressRecorder main.py
echo.
echo Build finished. Check: dist\ProgressRecorder\
pause
