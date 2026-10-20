@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python max_app.py
pause
