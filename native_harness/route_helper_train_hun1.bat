@echo off
cd /d "%~dp0"
python -u "train_route_helper_hun1.py" %*
echo.
echo Helper check ended. Press any key to close this window.
pause >nul
