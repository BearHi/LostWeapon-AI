@echo off
cd /d "%~dp0"
if exist checkpoints\route_rule_helper.stop del checkpoints\route_rule_helper.stop
python -u train_route_curriculum.py --stage hun %*
echo.
echo Training ended. Press any key to close this window.
pause >nul
