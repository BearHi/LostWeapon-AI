@echo off
@chcp 65001 > nul
cd /d "%~dp0"
echo Select your already-running v9 Client and play YOUR character on this PC.
echo No bot input. F8: start/pause recording. F9: stop. Maximum: 180 seconds.
echo Pause recording during chat. Capture ladder exits, rolls, jumps and sword exchanges.
"C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe" "%~dp0native_harness\sword_live_bot.py" --record-demonstration --seconds 180 --wait-seconds 120 --decision-ms 20 --output "%~dp0logs\sword_human_demonstration.jsonl"
pause
