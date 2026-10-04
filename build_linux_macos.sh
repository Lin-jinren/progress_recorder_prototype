#!/usr/bin/env bash
set -e
python3 -m pip install -r requirements.txt
python3 -m PyInstaller --noconfirm --clean --windowed --name ProgressRecorder main.py
echo "Build finished. Check: dist/ProgressRecorder/"
