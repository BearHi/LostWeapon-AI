@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "private_snapshots\team_p2p_combat_live.zip" (
  echo Missing combat snapshot.
  pause
  exit /b 1
)
set EPISODES=1000
set /p EPISODES=Episodes to train [1000]: 
if "%EPISODES%"=="" set EPISODES=1000
echo Training %EPISODES% episodes. Progress is printed after every episode.
python train_combat_selfplay.py --resume --episodes %EPISODES% --max-steps 256
if errorlevel 1 pause
