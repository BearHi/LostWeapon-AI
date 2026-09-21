# LostWeapon 다음 세션 인수인계 — 2026-09-17

이 문서를 현재 작업의 진입점으로 사용한다. 과거 설계·실험의 상세 근거는 아래 기존 문서와 `native_harness/evidence/`에 있다. 채팅 전체가 프로젝트 안에 자동 저장된다고 가정하지 않는다. 이 문서와 옛 문서의 날짜가 다르면 **현재 실행 상태는 먼저 프로세스·코드·로그로 재확인**한다.

## 사용자 목표와 현재 우선순위

- 최우선: 로컬에서 돌아가는 **지형 경로 헬퍼 훈련기**. 깃발 좌표와 현재 위치, 주변 충돌·오브젝트·물리 상태를 보고 이동한다. 한 맵의 고정 입력열 암기가 목적이 아니다.
- 이미 본 칸은 시야 밖으로 나가도 기억한다. `open / blocked / unknown`을 구분한다. 빈칸이어도 실제 이동 가능하다고 단정하지 않는다. 작은 창에서 시작해 판단에 필요한 때만 넓혀 반응속도를 지킨다.
- 행동과 지형 전이는 원본 `Client.exe` x86을 실행하는 오프라인 native harness로 검사한다. 정적 LMF 검사·Python 추정·오프라인 native·실제 온라인 Client의 근거 수준을 섞지 않는다.
- 사용자 계정으로 온라인에 들어가는 AI와 칼전은 장기 목표다. 지금은 맵 이동 헬퍼가 우선이다. 허락 없이 칼전 맵을 선정하거나 장기 칼전 학습을 재시작하지 않는다.
- 사용자는 토큰 절약, **보이는 CMD 진행 상황**, 중단·재개, 학습 여부를 과장하지 않는 설명을 원한다. 루프에 빠질 것 같으면 멈추고 묻는다.

## 2026-09-17 실제 상태

- `native_harness/discovered_map.py`: 실행 중 관측한 native 충돌 칸을 누적하며 `open / blocked / unknown / boundary`를 구분한다. `clearance()`는 기하학적 공간 판정이지 물리적으로 도달 가능하다는 증명이 아니다.
- `native_harness/native_env.py`: 별도 계획 센서 `navigation_view`는 홀수 3~21칸을 읽는다. `adaptive_navigation_view`는 발판 끝·앞벽이 가까울 때 확대한다. DQN 기존 관측 스키마는 별개다.
- `native_harness/physics_first_planner.py`: 수평 목표에 대해 걷기·점프·구르기 고정 후보 19개를 native 실행으로 비교한다. 발견한 지도를 후보 실행 중 유지하고, 바로 앞의 **기억된 벽**이 구르기 방향에 있으면 점프를 시험한다. 이는 한 가지 국소 규칙이지 범용 실시간 재계획이 아니다. 점검한 후보 중 빠른 경로만 주장한다.
- `native_harness/run_physics_first.py`: 후보별 `candidate 1/19 ...` 진행 상황을 보이고, 깨끗한 시작점 재생으로 깃발 접촉을 검증한 후 지형·발견 영역·이동선 SVG를 저장한다. 훈1 결과는 53 decision, 처음 9x9 이후 이미 본 구간은 3x3, `native_harness/evidence/route_helper_훈1.svg`.
- `native_harness/route_helper_train_hun1.bat` → `train_route_helper_hun1.py` → `run_physics_first.py`는 현재 **훈1 한 번 검증하는 실행기**다. 이름에 `train`이 있어도 가중치나 경험을 학습·저장하지 않는다. 사용자가 한 번 실행해 출력과 `done:true`를 확인했다. 이 파일을 실제 훈련기라고 설명하면 안 된다.
- 오래 돌던 `run_overnight_candidate.py` 부모와 `train_local_dqn.py` 자식은 사용자 요청으로 중지했다. `checkpoints/physics_first_local/`의 모델·경로·전이·episode·로그는 보존했다. `status.json`의 `state: running`은 종료 전 기록일 수 있으므로 실행 중이라는 증거가 아니다. 다음 세션에서 PID를 새로 확인한다.

## 무엇이 실패했고 왜 방향을 바꾸는가

- 폴더 DQN은 약 5시간 이상 실행해 당시 46개 플레이 가능 맵 중 23개 맵에 클리어 기록이 있었지만, 최근 기록 30회 중 6회 성공이었다. 특정 맵의 skill replay에 20분 이상 소요됐다. 이 수치는 **범용 헬퍼의 판단력 향상 증거가 아니다**.
- 저장 경로 재생과 발판 전이 조각은 유용하지만, 다른 상황에서 스스로 경로를 다시 그리는 단계가 아니다. 전체 경로 성공과 독립 정책의 일반화 성공을 구분한다.
- 훈1 고정 19후보 검증은 1회 약 53 decision 성공을 보이지만, 같은 실험을 반복해도 새로운 경험이 쌓이지 않는다. 사용자는 이를 학습기로 기대했고, 실제로는 검증기였던 점을 명시적으로 인정했다.
- 단순 깃발 직선거리 보상만으로는 벽·우회로를 이해하지 못한다. `LOCAL_TRAINING_PLAN.md`의 탐색/경로 그래프 아이디어는 설계이며 현재 구현 완료로 취급하지 않는다.

## 다음 작업: 진짜 로컬 헬퍼 훈련기

1. 작은 범위부터: 훈1에서 **시작 위치·깃발·간단한 벽/발판 변형**을 안전하게 생성/로딩할 수 있는지 기존 native LMF builder와 snapshot 제약을 확인한다. 사용자 원본 LMF를 덮어쓰지 않는다. 단순 좌표 변경이 native 상태까지 반영되는지 검증한다.
2. 각 결정에서 발견 지도, 목표 방향, 플레이어 물리 상태를 입력으로 삼아 가능한 국소 행동을 고른다. 앞이 막히거나 미지의 칸이면 시야 확대·우회·점프 후보를 선택한다. 기하학적 예측은 후보 생성용이고 성공 판정은 native 실행 결과만 사용한다.
3. `(상대 지형/물리 맥락, 행동, native 결과)`를 성공·실패 모두 저장한다. 특정 맵 절대 좌표만 키로 쓰지 않는다. 재사용한 조각은 현재 맵에서 다시 실행해 검증한다.
4. 반복 실행은 보이는 CMD에 현재 변형, 시도 수, native 검증 수, 성공률, 평균 결정 수, 저장 위치를 표시하고 안전하게 중지·재개한다. 원본/기존 체크포인트를 자동 교체하지 않는다.
5. 학습에 쓴 변형과 **보지 않은 변형**을 분리 평가한다. 고정 후보·기존 DQN·새 헬퍼의 성공률과 결정 수를 같은 native 기준으로 비교한다. 성능 향상이 확인되기 전에는 `훈련 완료`라고 말하지 않는다.

## 보존할 것 / 함부로 지우지 말 것

- `native_harness/private_snapshots/`의 원본 Client 캡처 ZIP: 로컬 민감 자료일 수 있다. 외부 공개 금지. 특히 `hun1_full.zip`은 훈1 native 실험 기반이다.
- `native_harness/checkpoints/` 전체: 공용 맵·전투 모델, `physics_first_local/brain.pt`, episode JSONL, route/transition library, ledger/log 및 후보 체크포인트. 오래 걸려 얻은 기록이다. **오래된 `running` 상태 파일만 보고 모델을 삭제하지 않는다.**
- `훈련용맵/`의 사용자 LMF 원본 및 변형, `native_harness/evidence/`의 검증 결과, `Client.exe`와 게임 파일. 생성 테스트맵은 별도 경로에 두고 원본을 덮어쓰지 않는다.
- 기존 `NEXT_SESSION_HANDOFF_2026-09-15.md`, `native_harness/LEARNING_SYSTEM.md`, `LOCAL_TRAINING_PLAN.md`, `COMBAT_NATIVE_PLAN.md`는 과거 결정과 기술 근거가 담겨 있다. 일부 현황 숫자와 실행 설명은 지금보다 오래됐으므로 이 문서와 라이브 상태로 교차 확인한다.

## 읽기 순서

1. 이 문서 → 현재 코드/프로세스/체크포인트 상태 확인.
2. `native_harness/LEARNING_SYSTEM.md`: 공용 두뇌 구조, 사용자 키·금지블록 규칙, 기존 단독 평가. 날짜가 적힌 수치는 과거 시점 사실이다.
3. `native_harness/LOCAL_TRAINING_PLAN.md`: 원래 학습 설계. 구현 완료 목록이 아니다.
4. `NEXT_SESSION_HANDOFF_2026-09-15.md`: native oracle, 전이 조각, 특수 오브젝트 역설계의 과거 인수인계.
5. 전투가 다시 범위에 들어올 때만 `native_harness/COMBAT_NATIVE_PLAN.md`와 관련 evidence를 읽는다.

## 검증 경계

훈1의 53-decision 성공은 **캡처된 원본 x86 오프라인 native world**에서 깃발 접촉한 증거다. 일반 Client 화면에서의 자동 플레이, 온라인 계정 행동, 모든 맵의 범용 해결, 전역 최단 경로, 학습된 모델의 일반화는 아직 입증되지 않았다.
