@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo Shared local outcome learning: fit - validate - collect - repeat.
echo Maximum 4 hours. Use 로컬물리_훈련중지.bat to stop safely.
python -u run_shared_learning.py --hours 4 %*
echo.
echo See checkpoints\shared_physics_v1\MODEL_SUMMARY.md
pause
