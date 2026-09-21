@echo off
cd /d "%~dp0"
python -u train_route_curriculum.py --stage hon %*
echo.
echo Hon stage ended. Press any key to close this window.
pause >nul
