@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo Upgraded shared learner: fit - validate - collect - repeat. Maximum 4 hours.
echo Existing experience is reused. Use the STOP batch to stop safely.
python -u run_shared_learning.py --hours 4 %*
echo.
echo Training stopped or finished. See checkpoints\shared_physics_v1\MODEL_SUMMARY.md
pause
