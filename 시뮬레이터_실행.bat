@echo off
chcp 65001 > nul
title LostWeapon Native Physics Playground
echo =======================================================
echo   로스트웨폰 네이티브 물리 시뮬레이터 (Native Playground)
echo =======================================================
echo.
echo [1/2] 물리 엔진 환경 확인 중...
cd /d "%~dp0native_harness"

echo [2/2] 시뮬레이터 창을 엽니다. 잠시만 기다려주세요...
"C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe" "native_playground.py"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [오류 발생] 시뮬레이터 실행 중 에러가 발생했습니다. (코드: %ERRORLEVEL%)
    pause
)
