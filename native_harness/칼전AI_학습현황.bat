@echo off
chcp 65001 >nul
cd /d "%~dp0"
python combat_training_status.py
echo.
pause
