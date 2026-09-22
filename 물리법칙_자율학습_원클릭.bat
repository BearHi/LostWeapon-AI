@echo off
setlocal
cd /d "%~dp0"
title LostWeapon Physics Curriculum Runner

echo ======================================================================
echo   LostWeapon Physics Curriculum 21-Stage Autonomous Runner
echo ======================================================================
echo.
echo [1/2] Checking and generating 21 physics curriculum LMF maps...
"C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe" -u generate_physics_curriculum.py
if errorlevel 1 (
    echo [ERROR] Map generation failed.
    pause
    exit /b 1
)

echo.
echo [2/2] Running 21-stage autonomous physics training on x86 native emulator...
"C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe" -u train_physics_curriculum.py
if errorlevel 1 (
    echo [ERROR] Training run failed.
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo   Training Completed!
echo   Results saved to:
echo     - checkpoints\physics_curriculum_routes.json
echo     - TRAINING_LOG.md
echo ======================================================================
pause
