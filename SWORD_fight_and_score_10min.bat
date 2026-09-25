@echo off
@chcp 65001 > nul
cd /d "%~dp0"
echo Select your existing v9 Client on the sword-practice room.
echo F8: start/pause bot. F9: stop. Maximum run time: 10 minutes.
echo Duel transitions and HP-balance scores append to logs\sword_fight_learning.jsonl.
echo Human-overridden and multiplayer samples are excluded from fight scoring.
"C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe" "%~dp0native_harness\sword_live_bot.py" --act --seconds 600 --wait-seconds 120 --decision-ms 20 --output "%~dp0logs\sword_live_fight_score_run.jsonl" --fight-learning-output "%~dp0logs\sword_fight_learning.jsonl"
pause
