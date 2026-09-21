@echo off
setlocal
cd /d "%~dp0"
set "FIXTURE=%~1"
if "%FIXTURE%"=="" set "FIXTURE"=hun7
python debug_window.py %FIXTURE%
if errorlevel 1 pause
