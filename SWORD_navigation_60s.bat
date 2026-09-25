@echo off
@chcp 65001 > nul
cd /d "%~dp0"
echo Select your already-running v9 Client. F8: start/pause. F9: stop.
echo Test different-height pursuit and alternate routes for 60 seconds.
"C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe" "%~dp0native_harness\sword_live_bot.py" --act --seconds 60 --wait-seconds 120 --decision-ms 20 --output "%~dp0logs\sword_live_closed_loop_trial.jsonl"
pause
