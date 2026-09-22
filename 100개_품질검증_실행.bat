@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
title LostWeapon AI Generator V1 100 Quality and Distribution Audit

set PYTHON_EXE=C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python 실행 파일을 찾을 수 없습니다: %PYTHON_EXE%
    pause
    exit /b 1
)

echo ===============================================================================
echo   [LostWeapon AI] Generator V1 100개 대량 생성 및 품질/분포 실측 검증
echo   - 8개 아키타입 x 13개 무작위 시드 샘플링 = 총 104개 맵 전수 평가
echo   - 정적 물리 / x86 오라클 / 날먹 우회 3단계 파이프라인 전수 통과 여부 측정
echo   - 중복률, 기술별 분포, 이상 맵 및 단계별 탈락율 실측 보고서 생성
echo ===============================================================================
echo.
echo [*] 100개 훈련맵 품질 검증을 시작합니다 (예상 소요 시간: 약 30~50초)...
echo.

"%PYTHON_EXE%" -u audit_generator_100.py

echo.
echo ===============================================================================
echo   검증이 완료되었습니다!
echo   - 결과 요약 보고서: 훈련용맵\audit_run_100\audit_100_summary.json
echo   - 통과된 LMF 맵:    훈련용맵\audit_run_100\
echo   - 결함/우회 격리:   훈련용맵\audit_run_100\quarantine\
echo ===============================================================================
echo.
pause
