# LostWeapon AI: Experiment Backlog & Architecture Master Dashboard

> **Project Goal**: 고전 액션 게임 *로스트웨폰(LostWeapon)*에서 유즈맵 자율주행(깃발 도달) 및 칼전(PvP)이 가능한 자율 학습형 AI 에이전트 구축.  
> **Baseline Snapshot**: `native_harness/checkpoints/baseline_snapshot_20260922/` (모든 소스코드 및 가중치 원본 영구 동결 보존)  
> **Last Updated**: 2026-09-22 01:25 KST

---

## 1. System Status & Architecture Overview

```
[Level 1: Native Game Client & Harness]
  - Win32 GDI / Memory Injection: lmf_injector.py, native_playground.py (50ms / 20Hz Tick)
  - 23개 맵 탐색 트라이얼 아카이브: local_physics_v1/*.sqlite3 (총 75,333 샘플)

[Level 2: Shared Physics & Outcome Predictor]
  - Model: OutcomeModel (shared_physics_model.py, Conv2d 400d + Scalar 92d + Plan 512d = 1,004d)
  - Status: 15회 연속 승격 실패 (Heldout Risk Brier 악화로 탈락 중단 상태)

[Level 3: Global Planning & Combat Engine (Target)]
  - 유즈맵: Macro Skill (대시 점프, 2단 점프, 자석 타기) 기반 Platform Graph Search
  - 칼전 PvP: 자율 대전 및 적 탐지/회피/공격 Self-Play 루프
```

---

## 2. Completed Milestones (감사 및 실측 완료)

### [DONE] Step 0 & Step 0.5: 데이터 Split & Trajectory Leakage 전수 정량 감사
* **실측 일시**: 2026-09-22 00:32 KST
* **환경**: NVIDIA GeForce GTX 1060 6GB (Pascal sm_61, PyTorch 2.5.1+cu121 CUDA 가속 활성화)
* **대상**: `dataset.npz` (75,333건) 및 23개 SQLite 파일 원본 트라이얼 1:1 매핑
* **핵심 실측 결과**:
  1. **Exact Duplicate**: 
     - Validation 12,656건 중 Train과 100% 동일한 샘플은 단 **10건 (0.0790%)** $\rightarrow$ Context 해싱 분할은 정상 동작함.
  2. **Trajectory Leakage (핵심 발견)**:
     - Validation Planned 샘플 7,638건 중 **7,518건 (98.43%)**이 Train 데이터와 동일한 트리 궤적 경로(Direct Lineage) 상에 위치.
     - **5,238건 (68.58%)**은 Train 노드와 시간차가 **단 $\le \pm 8$ native ticks 이내**.
     - Validation의 높은 성능은 인접 노드 패턴 암기에 의한 **누설 착시**였음이 실측 입증됨.
  3. **Legacy vs Planned 대조 분석**:
     - **Legacy 데이터**: 미지의 Heldout 맵에서도 Model Brier 0.027492 < Const Brier 0.032460으로 **BSS = +0.1531 (승리)**.
     - **Planned 데이터**: Validation에서는 BSS +0.2311이었으나, Heldout 맵에서는 **BSS = -0.3663으로 폭락**.
     - 15회 연속 탈락의 주범이 **Planned 데이터의 극단적인 일반화 실패**임을 수치로 규명함.
  4. **Heldout 맵 불균형**:
     - Heldout 4개 맵 중 3개(훈13: 0.00%, 훈19: 1.41%, 훈3: 4.51%)가 극단적 저위험률 맵.
     - 위험 사건이 없는 맵에서 모델의 미세한 예측(0.1~0.2)이 일괄 0.098을 찍는 상수 베이스라인에 패배하는 메커니즘 확인.

---

## 3. Experiment Backlog Queue (실험 파이프라인)

| ID | 실험명 (Experiment) | 목적 및 가설 | 변경 변수 | 통제 변수 | 성공 기준 (Pass) | 우선순위 | 상태 |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| **Exp 1A** | Zero-Weight Temperature / Platt Calibration | 모델 재학습 없이, 저빈도 맵 확률 눈금 보정만으로 Heldout BSS 양수 전환 가능한지 검증 | Validation 기반 Platt 파라미터 $(T, b)$ 적용 | 모델 가중치 100% 불변, 데이터셋 불변 | Heldout BSS $> 0$ (상수 대비 개선) | P0 | **READY** |
| **Exp 1B** | Leakage-Free Clean Split Evaluation | 궤적 누설(98.43%)이 배제된 독립 Episode/Subtree 단위 검증 셋 구축 및 실성능 측정 | Data Split 로직 (Episode 단위 Group Split) | 모델 가중치 불변, feature 불변 | 누설 없는 진짜 일반화 지표 확립 | P1 | QUEUED |
| **Exp 1C** | Class-Imbalanced Weighted BCE Retrain | 극단적 저위험률 맵에 대응하기 위해 pos_weight 및 Focal Loss 적용 재학습 | Loss Function (BCE pos_weight) | 아키텍처 불변, 데이터셋 불변 | Heldout 훈13, 훈19 BSS 양수 전환 | P1 | QUEUED |
| **Exp 2A** | Macro Action & Skill Library 정의 | 1틱 단위 무작위 연타 탈피, 대시점프/칼질/자석타기 등 12~16개 인간 기술 래핑 | Action Tokenization (Skill Abstraction) | 물리 엔진 불변 | 긴 점프 및 장애물 돌파율 대폭 상승 | P1 | QUEUED |
| **Exp 2B** | Platform Graph Edge Parameterization | 단순 도달 여부(Boolean)가 아닌 속도/체류시간/위험도를 가중치로 갖는 그래프 네비게이션 | Navigation Graph Representation | 지형 파서 불변 | 깃발 경로 탐색 시간 10배 단축 | P2 | QUEUED |
| **Exp 3A** | Autonomous Multi-Map Curriculum Runner | 사람이 맵을 수동 지정하지 않고, AI가 23개 맵을 스스로 순회하며 데이터 자율 수집/학습 | Training Loop (Auto Map Selector) | 물리 클라이언트 불변 | 사람 개입 없는 무인 자율 학습 달성 | P2 | QUEUED |
| **Exp 3B** | Combat PvP AI (Self-Play Prototype) | 상대방 봇과의 거리/행동을 인지하고 칼질/회피/카운터를 구사하는 전투 지능 탑재 | Combat Policy Network & Self-Play Loop | 네이티브 물리 엔진 | 사람 수준의 칼전 승률 달성 | P3 | QUEUED |

---

## 4. Operational & Rollback Rules (안전 운영 수칙)

1. **불변 원칙 (Immutability)**:
   - `native_harness/checkpoints/baseline_snapshot_20260922/`는 절대 수정하거나 삭제하지 않는다.
   - 새로운 모델 가중치 학습 시 반드시 `checkpoints/exp_XXX/` 하위로 격리 저장한다.
2. **실험 실행 전 세이브 (Pre-experiment Save)**:
   - 코드를 수정하는 모든 실험(Exp 1B 이후)은 수정 전 해당 파일의 백업 사본을 생성한다.
3. **단정적 어조 금지 (Evidence-based Reporting)**:
   - 모든 보고는 "추정" 대신 실제 텐서 순전파 및 오차 계산 수치(Table)로만 입증한다.

---

## 5. Incident & Failure Log (실패 및 결함 투명 기록)

### [SWORD-20260925] 수직 추적 정체와 실패 edge 재시도
* trial2에서 같은 출발 발판의 airborne transition이 `(212,736)`에서 정체 후 다시 선택됨. 발판 위에서도 아래 목표 X로만 정렬했고, 실패 제외가 5초 뒤 해제됐음.
* 출발 가장자리 이탈 → 비행 조정 → 후속 관측 확인으로 보강. 같은 상대 영역/자세의 실패 edge는 세션 중 유지하고 대체 경로 선택. 실제 송신된 이동에만 결과 추적 적용.
* 오프라인 회귀 75개 PASS (신규 25개). 전체 검사 중 기존 MPC 테스트의 옛 helper import 오류를 발견하여 현재 모듈 import로 수정; assertion 유지.
* Native Client 실행/실제 이동 검증은 하지 않음. `SWORD_navigation_60s.bat`으로 사용자 실행 후 착지/사다리 진입 및 실패 재선택 로그 확인 필요.
* 시연 전용 `--record-demonstration` 추가. 실제 키 표본과 v9 상태를 기록하며 학습기는 아직 없음. 기존 혼합 수동/자동 입력 로그의 귀속 오염 가능성은 남아 있음.
* 세부 인수인계: `native_harness/SWORD_NEXT_STEPS_2026-09-25.md`.

### [INCIDENT-001] 자율 훈련 루프 가짜 낙사 버그 및 무한 루프 중단
* **발생 일시**: 2026-09-22 01:40 ~ 02:18 KST
* **스크립트**: `autonomous_curriculum_trainer.py`
* **현상**: Stage 1(2칸 점프) 실행 시 6,000회 이상 X=152.0px에서 연속 낙사 처리되며 프로세스가 종료되지 않고 장시간 실행되어 사용자가 수동 취소함.
* **원인 분석**:
  1. **임계값 하드코딩 오류**: 로스트웨폰 x86 엔진에서 플레이어가 발판(y=14) 위를 정상 보행할 때의 실제 Y좌표는 `448.0`임. 그러나 스크립트 작성 시 `cur_y > 430.0`을 낙사로 잘못 정의하여, 정상 보행 상태임에도 10틱(0.5초) 만에 강제 낙사 처리 및 에피소드 리셋이 반복됨.
  2. **무한 루프 제어 부재**: 미해결 상태에서 프로세스가 계속 헛돌며 종료되지 않음.
* **수정 조치**:
  1. 진짜 낙사 기준을 발판 하단 추락(`cur_y > 480.0`)으로 정정.
  2. 에피소드 시도 횟수를 5회 단위(약 2초)로 명시적 제한하고 자동 종료되도록 수정.

### [INCIDENT-003] 대화창 내 에뮬레이터 직접 구동 및 파일 전면 교체로 인한 토큰 폭발 사고
* **발생 일시**: 2026-09-22 14:40 ~ 15:00 KST
* **스크립트**: `train_physics_curriculum.py`
* **현상**: 대화창에서 x86 에뮬레이터 21종 순회 훈련을 `run_command`로 직접 발주하고 타이머 폴링을 반복하여 로그 텍스트가 대화창으로 쏟아져 들어옴. 직후 400줄짜리 파이썬 코드를 전면 재작성하려다 토큰 한계 도달로 코드가 중간에 잘려 `IndentationError` 발생 및 유저 토큰 급속 소진.
* **원인 분석**:
  1. **로컬 실행 원칙 위반**: 사용자 PC에서 `.bat`으로 돌려야 할 무거운 연산을 대화창 내부 서브프로세스로 돌림.
  2. **미세 편집(Surgical Edit) 미준수**: 부분 수정 대신 파일 전체 덮어쓰기 시도로 토큰 폭발 및 구문 오류 발생.
* **수정 조치**:
  1. `PROJECT_INSTRUCTIONS.md` 및 마스터 법전에 **3중 토큰 방어벽** 영구 명문화 (로컬 강제, 외부 수학 질의 위임, 부분 편집 강제).
  2. `train_physics_curriculum.py` 하단 죽은 코드 26줄 제거하여 문법 완전 복원.

### [INCIDENT-004] 붕괴 발판 타이밍 오판 및 장거리 협곡 순수 활강 불가 규명
* **발생 일시**: 2026-09-22 16:15 KST
* **스크립트**: `train_physics_curriculum.py`, `generate_physics_curriculum.py`
* **현상**: 붕괴 발판(stg4) 돌파 실패 및 18칸/22칸 심연 협곡(stg5) 도달 불가.
* **원인 분석 (유저 정밀 수식 검산 규명)**:
  1. **붕괴 발판**: 12틱 시간제한보다 발판 폭 32px(8틱) 도달 한계가 먼저 걸림. 접촉 후 정확히 `delay=8`(X=288px)에서 엣지 점프해야 최장 비거리(520px) 착지 가능함을 수식으로 확정.
  2. **장거리 협곡**: 순수 점프+낙하산의 물리적 한계는 388px(추락선 한계 417px)에 불과하여, 18칸(576px)·22칸(704px)은 순수 활강만으로는 물리적 도달이 절대 불가능함을 규명. 정점 직후 낙하산 전개 시 자연낙하보다 오히려 손해(t=36 최적).
* **수정 조치**:
  1. 붕괴 발판 감지 조건을 `st['x'] >= 256.0`, 최적 도약 딜레이를 `8`로 정밀 수정.
  2. 장거리 협곡은 향후 칼질 돌진(+119px) 및 점프뒷굴 복합 연계 기믹으로 개정 계획 수립.

---

