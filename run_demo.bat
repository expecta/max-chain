@echo off
chcp 65001 >nul
cd /d "%~dp0"
set MAX_PASSWORD=demo1234
python -m pip install -r requirements.txt
python max.py new-wallet alice
python max.py new-wallet bob
python max.py mine alice
python max.py balance alice
python max.py send alice bob 20
python max.py mine bob
python max.py balance alice
python max.py balance bob
python max.py chain
python max.py validate
python max.py show-key alice
python max.py leaderboard
echo.
echo Demo wallets use the password demo1234 (demo only!)
echo Demo done! To see the explorer run: python max.py explorer
pause
