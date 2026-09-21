# LostWeapon AI

고전 액션 게임 **로스트웨폰(LostWeapon)**의 유즈맵 자율주행(깃발 도달) 및 칼전(PvP) 자율 학습 AI 프로젝트입니다.

---

## 📌 핵심 운영 문서 바로가기
* 📖 **[마스터 운영 지침서 (PROJECT_INSTRUCTIONS.md)](PROJECT_INSTRUCTIONS.md)**: 새 세션 투입 시 AI가 반드시 읽어야 할 개발 환경, 기검증된 팩트, 작업 수칙
* 📋 **[실험 백로그 대시보드 (EXPERIMENT_BACKLOG.md)](EXPERIMENT_BACKLOG.md)**: 전체 마일스톤, 실험 대기열, 실패/결함 사고 일지
* 📈 **[실시간 훈련 성장 일지 (TRAINING_LOG.md)](TRAINING_LOG.md)**: AI의 맵별 점프 및 깃발 클리어 실측 기록

---

## 🛠️ 개발 환경
* **OS**: Windows
* **Python**: 3.11 (64-bit)
* **Framework**: PyTorch 2.5.1+cu121 (NVIDIA GeForce GTX 1060 6GB CUDA 가속)
* **Simulator**: 로컬 x86 네이티브 물리 에뮬레이터 (Headless Fast Execution)
