@echo off
cd /d "%~dp0"
python -u train_route_curriculum.py --stage hun %*
echo.
echo Training ended. Press any key to close this window.
pause >nul
