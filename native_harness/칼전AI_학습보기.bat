@echo off
chcp 65001 >nul
cd /d "%~dp0"
python watch_combat_ai.py
if errorlevel 1 pause
