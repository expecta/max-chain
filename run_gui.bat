@echo off
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
start "" pythonw max_gui_classic.py
if errorlevel 1 python max_gui_classic.py
