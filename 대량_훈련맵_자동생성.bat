@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
title LostWeapon AI 대량 훈련맵 자동 생성기 (Procedural Generator)

echo ===============================================================================
echo   [LostWeapon AI] 절차적 훈련맵 대량 자동 생성 및 검증 파이프라인 V1
echo   - LLM 없이 100%% 로컬 수학적 물리 법칙(LOSTWEAPON_PHYSICS_MASTER_RULES) 기반
echo   - Map Validation Pipeline V1 (정적 물리 + x86 오라클 + 날먹 우회 차단)
echo ===============================================================================
echo.

set PYTHON_EXE=C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python 실행 파일을 찾을 수 없습니다: %PYTHON_EXE%
    pause
    exit /b 1
)

echo [선택 1] 전체 8종 아키타입 표준 그리드 생성 (권장: 약 15~25개 전수 생성 및 검증)
echo [선택 2] 특정 아키타입 선택 실행
echo [선택 3] 아키타입별 랜덤 시드 대량 샘플링 (아키타입당 N개)
echo.
set /p MENU_CHOICE="실행할 번호를 입력하세요 (기본값: 1): "

if "%MENU_CHOICE%"=="" set MENU_CHOICE=1

if "%MENU_CHOICE%"=="1" (
    echo.
    echo [*] 전체 8개 아키타입에 대한 결정론적 그리드 생성 및 전수 검증을 시작합니다...
    "%PYTHON_EXE%" -u batch_map_pipeline.py --mode grid
    goto FINISH
)

if "%MENU_CHOICE%"=="2" (
    echo.
    echo 1. ARCH_01_BASIC_GAP      (기본 수평 갭 점프)
    echo 2. ARCH_02_STEP_UP        (수직 단차 등반)
    echo 3. ARCH_03_BACKROLL_WALL  (점프뒷굴 고벽 등반)
    echo 4. ARCH_04_KNIFE_DASH     (천장 차단 공중 칼1 돌진)
    echo 5. ARCH_05_PILLAR_BRAKE   (1칸 기둥 에어브레이크)
    echo 6. ARCH_06_PARACHUTE_CHASM (낙하산 장거리 협곡)
    echo 7. ARCH_07_SPRING_LAUNCH  (수직 스프링 고벽 도약)
    echo 8. ARCH_08_COLLAPSE_BRIDGE (시간차 붕괴 발판 다리)
    echo.
    set /p ARCH_NAME="아키타입 ID를 입력하세요 (예: ARCH_01_BASIC_GAP): "
    "%PYTHON_EXE%" -u batch_map_pipeline.py --archetype %ARCH_NAME% --mode grid
    goto FINISH
)

if "%MENU_CHOICE%"=="3" (
    set /p SAMPLE_COUNT="아키타입당 생성할 맵 개수를 입력하세요 (예: 5): "
    if "%SAMPLE_COUNT%"=="" set SAMPLE_COUNT=5
    echo.
    echo [*] 아키타입당 %SAMPLE_COUNT%개 랜덤 샘플링 생성 및 검증을 시작합니다...
    "%PYTHON_EXE%" -u batch_map_pipeline.py --mode sample --count %SAMPLE_COUNT%
    goto FINISH
)

:FINISH
echo.
echo ===============================================================================
echo   생성 및 검증 작업이 완료되었습니다.
echo   - 출력 저장소: 훈련용맵\generated_curriculum\
echo   - 색인 파일:   훈련용맵\generated_curriculum\dataset_manifest.json
echo ===============================================================================
echo.
pause
