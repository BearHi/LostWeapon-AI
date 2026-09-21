@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo Local native physics training: hun 1-20, including intermediate maps.
echo Existing progress is resumed. No API calls. Use the STOP batch to stop safely.
python -u local_physics_train.py --resume %*
echo.
echo Training stopped or finished. See checkpoints\local_physics_v1\SUMMARY.md
pause
