@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
title 로스트웨폰 물리법칙 기반 21종 변형 맵 자율 학습 및 검증

echo ======================================================================
echo   로스트웨폰 물리 법칙 마스터 커리큘럼 21종 변형 맵 자율 학습기
echo ======================================================================
echo.
echo • 기반 법전: LOSTWEAPON_PHYSICS_MASTER_RULES.md (단일 최고 규범)
echo • 대상: 물리 임계치(186px, 270px, 506px 등) 기반 21종 절차적 변형 맵
echo • 기존 훈1~20 맵 완전 배제 (일반화 오염 차단)
echo.
echo [1/2] 21종 물리 변형 LMF 맵 상태 점검 및 자동 생성 중...
"C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe" -u generate_physics_curriculum.py

echo.
echo [2/2] x86 네이티브 물리 엔진 가속 기반 21종 자율 학습 및 검증 구동...
"C:\Users\sang\AppData\Local\Programs\Python\Python311\python.exe" -u train_physics_curriculum.py

echo.
echo ======================================================================
echo   모든 물리 변형 맵의 자율 학습 및 검증이 완료되었습니다!
echo   결과는 checkpoints\physics_curriculum_routes.json 및 TRAINING_LOG.md에
echo   영구 보존되었습니다. 창을 닫으려면 아무 키나 누르세요.
echo ======================================================================
pause
