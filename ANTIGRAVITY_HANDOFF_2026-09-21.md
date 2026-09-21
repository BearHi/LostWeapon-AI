# LostWeapon AI 인수인계 — 2026-09-21

이 문서는 다음 작업자가 채팅을 읽지 않아도 프로젝트의 목표, 실제 구현 범위,
현재 증거, 실패 원인, 다음 작업 순서를 이해하도록 만든 진입점이다.
문서에 적힌 수치는 작성 시점의 스냅샷이다. 실행 전에는 항상 현재 프로세스,
체크포인트의 `learning_status.json`, 코드 fingerprint를 다시 확인한다.

## 1. 사용자가 만들려는 것

최종 목표는 LostWeapon의 여러 유즈맵에서 현재 플레이어 상태와 지형을 읽고,
깃발까지 갈 다음 행동을 스스로 고르는 이동 두뇌다. 사용자가 직접 플레이하는
모습에서 기술 선택을 배울 수 있으면 좋겠지만, 한 맵의 키 입력열을 그대로
외우는 방식은 목표가 아니다. 용암, 낙하, 피격, 구르기, 누워서 통과, 낙하산,
자석, 스프링, 사다리, 물처럼 맵마다 규칙이 달라질 수 있으므로 행동의 결과를
현재 원본 물리 상태에서 다시 확인해야 한다.

현재의 현실적인 목표 순서는 다음과 같다.

1. 원본 x86 물리에서 짧은 행동 기술의 결과를 안정적으로 예측하고 재현한다.
2. 최근 관측과 국소 지형을 이용해 2~8결정짜리 기술을 고른다.
3. 실제 결과를 다시 읽어 막힘·리스폰·속도 변화에 즉시 대응한다.
4. 이미 본 발판과 실패 원인을 발견 지도/기술 라이브러리에 저장한다.
5. 그 위에 맵 전체의 다음 소목표를 고르는 상위 탐색기를 붙인다.

따라서 “9×9만 보고 모든 맵을 푼다”는 현재 구조로는 맞지 않는다. 9×9는
짧은 이동 기술의 입력으로는 적절하지만, 전체 경로 계획과 시야 밖 기믹의
선택에는 부족하다. 국소 창은 보통 9×9에서 시작하고 앞의 빈틈·벽·발판 끝이
창 밖에 걸릴 때 11, 13, 최대 21까지 넓히며, 별도의 발견 지도와 깃발/다음
소목표 정보를 함께 써야 한다.

## 2. 폴더를 처음 봤을 때 알아둘 사실

작업 폴더에는 제공된 원본 `로스트웨폰 클라이언트\Client.exe`와 데이터가 있고,
루트·`훈련용맵`·`Map`·`OldMap`에 LMF가 있다. 2026-09-21 현재 원본 Client
폴더와 checkpoints를 제외해 세면 LMF는 약 3,870개이며, 루트 49개,
`훈련용맵` 24개, `Map` 210개, `OldMap` 815개다. 파일 수는 변형본과 중복본을
포함한 물리적 개수일 뿐 “플레이 가능한 서로 다른 맵 수”가 아니다.

`훈련용맵`의 `훈1`~`훈20`과 반 단위 맵은 주 이동 커리큘럼이고, 현재
`train_route_curriculum.maps_for("hun")`가 읽는 기본 집합은 훈1~20의 23개다
(6.5, 7.5, 8.5 포함). `혼련용`은 별도 단계다. 사용자 원본 LMF는 덮어쓰지
않고 변형·실험 파일은 별도 폴더에 둔다.

LMF는 현재 파서 기준 32바이트 헤더와 8바이트 레코드들로 읽는다. 목표는
타일 ID 140으로 찾지만, ID만 보고 모든 기믹의 동작을 단정하지 않는다. 정적
LMF 분석은 맵 모양과 후보 발판을 만드는 자료이고, 실제 통과 가능성은 원본
x86 실행 결과로만 확정한다.

## 3. 시스템 구성과 파일 역할

### 원본 물리 기준

- `native_harness/oracle.py`, `api.py`, `captured_oracle.py`: 제공된 x86 Client
  명령을 저장된 snapshot에서 실행하거나 읽는 기반 계층이다.
- `native_harness/native_env.py`: `reset/step/observation/reward/done` 형태의
  환경이다. 한 결정은 기본적으로 원본 native 2틱을 유지한다. 21개 행동 조합을
  사용하며 예전 0~18 번호는 보존하고 좌/우+아래+Z를 뒤에 추가했다.
- `native_harness/restriction_fields.py`: LMF 안의 raw136~139 제한 블록을
  각각 점프·구르기·낙하산·무기 제한으로 해석한다. 제한은 요청 행동을 거르는
  장치일 뿐 전이 결과를 대신하지 않는다.
- `native_harness/lmf_injector.py`: Client 메모리에 맵/상태를 주입하는 실험
  도구다. 읽기 전용 도구로 착각해 실행하지 말고, 별도 검증과 사용자 의도가
  있을 때만 다룬다.

### 맵 분석·기술 재사용

- `global_planner.py`, `physics_first_planner.py`, `discovered_map.py`: 전체 LMF
  구조와 현재 native에서 발견한 `open/blocked/unknown/boundary`를 분석한다.
  기하학적 clearance나 발판 연결은 도달 가능성의 증명이 아니다.
- `run_physics_first.py`: 수평 이동 후보를 원본 x86으로 시험하고 후보 경로를
  검증한다. 이것은 bounded planner/검증기이지 전역 최적 정책 학습기가 아니다.
- `transition_library.py`, `skill_replay.py`, `skill_navigator.py`,
  `local_skill_search.py`: 발판 간 native 검증 전이 조각을 저장하고 비슷한
  발판에서 다시 시험한다. 재사용된 조각도 현재 상태에서 native로 재검증한다.
- `train_route_helper_hun1.py`와 `route_helper_train_hun1.bat`은 이름에
  train이 들어가지만 훈1 경로 후보를 검증하는 실행기다. 신경망 가중치를
  학습하는 범용 헬퍼로 설명하면 안 된다.

### 예전 정책 학습 계층

- `train_local_dqn.py`, `train_map_folder.py`, `unified_brain.py` 등은 과거
  공용 DQN/맵별 실험이다. 체크포인트와 episode 기록은 보존하지만 현재의
  공유 outcome 모델과 같은 두뇌로 취급하지 않는다.
- `combat_env.py`, `train_combat_selfplay.py`, `COMBAT_NATIVE_PLAN.md`는
  칼전/기지 설치 실험이다. 이동 헬퍼의 현재 우선 범위가 아니며, 평지 공격과
  팀전 상태가 충분히 검증되기 전 장기 학습을 재시작하지 않는다.
- `live_route_helper.py`는 `user32.keybd_event`로 실제 키를 내보낼 수 있는
  opt-in 도구다. `human_play_recorder.py`와 달리 읽기 전용이 아니므로 실제
  Client에서 실행·자동화하기 전에 반드시 현재 모드와 중지키를 확인한다.

### 현재 공유 outcome 모델

- `shared_physics_model.py`의 schema는 `local-outcome-v1`이다. 9×9 네 개
  native grid, 칸별 object ID, 노출된 플레이어 상태, held keys, 최대 64결정
  plan을 받아 최종 변위·실행 길이·휴리스틱 reset/out-of-bounds 위험을 예측한다.
- 맵 이름, 절대 좌표, 깃발 좌표, 정확한 상황 hash는 모델 입력에 없다. 맵 간
  공유를 시도하려는 의도는 맞지만, 한 장의 9×9와 긴 plan으로 시야 밖 세계의
  결과까지 맞히려는 문제가 남아 있다.
- 모델은 **행동 정책이 아니라 결과 예측기**다. 스스로 맵을 탐험하거나 사람의
  키 선택을 모방하는 기능은 아직 연결되지 않았다.
- `run_shared_learning.py`는 fit → native 자료 수집 → 재fit을 반복한다.
  `active.pt`로 승격되는 모델만 후보 순위에 반영하며, 실제 후보 결과는 항상
  native가 판정한다.

### 사람 플레이 기록 계층

- `human_play_recorder.py`는 선택한 foreground `Client.exe`의 상태, 키, 실제
  네 개 지형 grid, 런타임 object 목록을 JSONL로 기록한다. 게임 tick과 동기화된
  영상·정답 action 라벨이 아니다.
- `F6`/`F7` 표시는 사용자가 좋은 구간/실수를 표시하는 힌트이고 native 성공
  판정이 아니다. `F9`는 기록 일시정지다. 다른 foreground 앱의 입력은 기록하지
  않는다.
- `week_mode.py`와 `이번주_자료수집.bat`은 모델을 재학습하지 않고 짧은 native
  자료만 제한적으로 모은다. `내플레이_기록시작.bat`은 최대 30분/256MiB,
  전체 사람 기록 약 2GiB 한도다.
- 기록은 다음 검토에서 시간 정렬, 누락, 맵 식별, marker와 실제 native 결과의
  관계를 확인한 뒤에만 imitation 자료로 쓴다. 기록을 바로 “사람이 선택한
  최적 action”으로 학습시키면 실수와 지연까지 정답으로 굳어진다.

### 실시간 읽기/검증 도구

- `live_state.py`, `identify_live_map.py`, `sample_normal_noop.py`,
  `normal_trace_readonly.py`, `passive_live_trace.py`는 선택한 Client를
  읽기 위한 도구다. Client 빌드/ASLR/메모리 상태가 바뀌면 주소와 fingerprint를
  다시 검증한다.
- `capture.py`는 짧게 프로세스를 멈추고 메모리를 읽는 캡처 도구다. 일반 Client
  패리티를 자동으로 보장하지 않는다.
- `native_harness/evidence`는 실험 증거이고, `private_snapshots`는 원본
  프로세스 자료가 포함될 수 있어 외부에 공개하지 않는다.

## 4. 현재 실제 상태

2026-09-19 마지막 공유 학습 상태는 `time_budget_complete`, cycle 15,
학습 자료 75,333건이다. 마지막 fit의 context 검증은 endpoint MAE 40.84px,
상수 기준 84.69px였지만, 고정 제외 맵 훈3·훈7.5·훈13·훈19에서는 MAE
56.83px, risk Brier 0.03736으로 상수 위험 기준 0.03225보다 나빴다.

같은 저장 후보 500개를 고른 비교에서는 새 모델의 utility 0.897, 선택 reset
2.6%가 기존 active utility 0.856, reset 3.4%보다 좋아 보였다. 그러나 이
비교는 이미 저장된 후보 중에서 고르는 고정 native 자료이고, 새 맵을 끝까지
푸는 독립 주행 평가가 아니다. held-out risk 회귀 방지 게이트가 실패했기
때문에 새 모델은 승격되지 않았고 기존 `active.pt`가 유지됐다. 최근 15회
학습에서 승격은 0회다.

현재 보관 중인 모델 파일은 `latest.pt`와 `active.pt`가 다를 수 있다.
`latest.pt`는 최근 fit 산출물이고, `active.pt`는 검증 게이트를 통과해 후보
안내에 사용되는 모델이다. 둘을 임의로 바꾸지 않는다.

기존 local physics 자료의 초기 문제는 exact context가 지나치게 세분화되어
상황/기술 항목 28,150개 중 93.7%가 한 번만 관측된 점이었다. 공유 모델을
추가했지만, 데이터량을 늘리는 것만으로 그 문제가 해결됐다는 증거는 없다.
짧은 행동·최근 관측·상태 이력·맵 밖 기억이 필요하다.

검증된 현재 사실:

- 2026-09-21 `native_harness/tests` 전체 24개 테스트가 통과했다.
- 이 테스트는 synthetic fixture, 저장된 native snapshot, 코드 수준 branch
  parity를 검증한다. 실제 일반 Client에서 자동 주행이 성공했다는 뜻이 아니다.
- 현재 실행 중인 `Client`/`python` 장기 학습 프로세스는 없음을 확인했다.
- 사람 기록기는 실제 Client에서 지형 read 지연, 맵 식별, `terrain_unavailable`
  비율을 아직 검증하지 않았다.

## 5. 지금까지 막힌 핵심 이유 — 동의하지 말고 검증할 부분

첫째, 9×9 자체가 잘못된 것이 아니라 사용 범위가 너무 넓었다. 짧은 기술의
결과를 매번 재관측하는 센서로는 쓸 수 있지만, 64결정 뒤의 결과와 시야 밖
기믹을 한 번에 예측하는 입력으로는 정보가 부족하다. 보이는 지형이 같은데
다음 화면의 발판/속도/동적 오브젝트가 다른 경우를 구분할 수 없다.

둘째, 현재 모델은 “어떤 행동을 선택할지”보다 “주어진 계획이 어떻게 끝날지”를
배운다. 그래서 후보 정렬 점수가 좋아져도 새 맵 전체를 스스로 발견하거나,
사용자의 실수를 보고 올바른 대체 행동을 찾는다는 결론을 내릴 수 없다.

셋째, native goal-region, reset 추정, 위치 급변은 실제 게임의 모든 성공·사망·
리스폰 이벤트와 동일하지 않을 수 있다. 용암 타일 접촉을 실패로 고정하면
구르기/피격/누운 상태로 통과하는 실제 경로를 버린다. 반대로 위치가 앞으로
갔다고 성공으로 고정해도 막힌 상태일 수 있다.

넷째, 사용자 플레이 로그를 모으는 것과 학습하는 것은 별개다. 현재 로그의 키
샘플은 wall-clock이며 native tick과 원자적으로 맞지 않는다. 사용자가 좋은
구간으로 표시한 F6도 최적성 증명이 아니다. 정렬·구간화·상태 전이 재현 없이
그대로 behavior cloning하면 사람이 눌렀던 지연, 실패, 회복 행동도 복제한다.

다섯째, 맵 수가 많아도 한 맵의 절대 좌표와 긴 route를 저장하면 새 맵에
일반화되지 않는다. 재사용해야 하는 단위는 “이 지형 관계와 물리 상태에서
이 짧은 기술이 native로 어떤 결과를 냈는가”이지 맵 이름이나 경로 문자열이
아니다.

## 6. 다음 작업자가 지켜야 할 실행 순서

1. 이 문서를 읽은 뒤 `learning_status.json`, `active.pt`/`latest.pt`의 시간,
   현재 PID, source/output lock을 확인한다. 오래된 `state: running`만 보고
   프로세스가 살아 있다고 판단하지 않는다.
2. `WEEK_HANDOFF_2026-09-19.md`와 `SHARED_LEARNING_DESIGN_2026-09-18.md`를
   읽어 최근 수집기와 게이트의 의도를 확인한다. 이전 문서의 날짜가 더 새로워
   보여도 현재 코드/상태 파일이 우선이다.
3. 이번 주에는 `내플레이_기록시작.bat`으로 사용자의 실제 플레이를 몇 세션
   기록하는 것이 가장 정보 가치가 높다. 자동 native collection은 예산 안에서
   보조로만 실행하고, 공유 model 장시간 fit은 held-out 회귀 원인을 해결하기
   전 재개하지 않는다.
4. 기록 검사를 먼저 한다. sample/terrain/object 비율, 맵 식별, wall-clock
   간격, Client 창 전환, 지형 읽기 실패, marker 주변 상태를 요약한다. 실제
   Client로 기록 기능 자체가 정상인지 확인되기 전에는 imitation 학습을
   시작하지 않는다.
5. 그 다음 현재 관측을 과거 몇 개까지 묶고, 2~8결정 skill 단위로 정렬한다.
   각 skill에는 시작 state, held keys, 9×9/확장 지형, 실제 native 결과,
   회복/리스폰 여부, 사용자가 표시한 힌트를 별도 필드로 둔다.
6. 후보 기술은 매번 native branch 또는 실제 Client 결과로 검증한다. 결과 예측
   모델은 우선순위 힌트로만 사용하고, 위험 행동을 영구 금지하는 규칙으로 쓰지
   않는다. 용암은 `접촉 여부`가 아니라 `행동·상태·속도·HP·다음 상태`의
   조건부 결과로 비교한다.
7. 상위 planner는 발견 지도와 다음 발판/소목표 graph를 관리하고, 짧은 skill
   controller에게만 다음 구간을 맡긴다. 전체 경로를 한 번에 신경망에 넣지
   않는다.
8. 새 모델 승격 전에는 학습에 쓰지 않은 새 맵/새 시작 상태에서 모델 선택,
   무작위 선택, 기존 규칙/기술 라이브러리를 같은 native 예산으로 비교한다.
   endpoint 예측 개선만으로 “맵을 깼다”고 보고하지 않는다.

## 7. 실행 파일의 안전한 분류

이번 주 자료를 추가할 때는 `native_harness/내플레이_기록시작.bat`,
`이번주_자료수집.bat`, `이번주_결과정리.bat`만 사용한다. `이번주_중지.bat`은
그 주 수집/녹화를 중지한다.

`공유두뇌_학습시작.bat`과 `로컬물리_훈련시작.bat`은 4시간 공유 fit/수집을
실행하는 기존 장시간 실행기다. 현재 held-out 게이트가 실패한 상태이므로
다음 설계 검토 전 반복 실행하지 않는다. 기존 DB와 checkpoints는 삭제·초기화
하지 않는다.

`로컬물리_결과보기.bat`은 기존 local physics 결과 확인용이다. 결과의
`offline_x86_goal_region`은 온라인 Client 클리어가 아니다. `live_route_helper.py`
는 실제 키를 보낼 수 있으므로 자동 실행 대상으로 분류하지 않는다.

## 8. 보존·보고 규칙

- `native_harness/private_snapshots`와 Client 프로세스 캡처는 민감 자료로
  취급하고 외부 공유하지 않는다.
- `checkpoints`의 DB, `active.pt`, `latest.pt`, route/transition library,
  episode JSONL, evidence는 장시간 생성물이라 임의 삭제하지 않는다.
- 물리 코드, Client build, snapshot이 바뀌면 fingerprint가 달라질 수 있으므로
  옛 경험을 새 정답으로 이어 붙이지 말고 native 재생 가능 여부부터 검사한다.
- 보고할 때는 항상 `정적 LMF 분석`, `offline original-x86 native`,
  `captured normal Client read`, `normal Client actual play`를 구분한다.
- “학습됐다”는 dataset/validation 지표를 뜻할 뿐이고, “새 맵을 풀었다”는
  independent policy-only 주행의 반복 성공으로만 말한다.
- 루프가 반복되어 새 정보가 생기지 않거나 같은 게이트가 계속 실패하면 학습을
  더 돌리지 말고 상태·자료 분포·평가 설계를 다시 확인한다.

## 9. 다음 인수인계 때 남길 최소 기록

새 작업자는 아래를 한 번에 남긴다.

- 시작/종료 시각, 실행한 정확한 명령, 사용한 source/output 경로
- 새로 생긴 sample/trial/terrain/marker 수와 오류 수
- 학습·검증·held-out·후보 비교의 원본 수치와 baseline
- 모델 승격 여부와 거절 이유
- 실제 Client에서 관측했는지, offline native만 실행했는지
- 다음 실험이 해결하려는 한 가지 가설과 중단 조건

이 문서의 핵심 결론은 기존 물리 구현을 버리자는 것이 아니다. 물리는 현재
가장 신뢰할 수 있는 교사이므로 보존한다. 바꿔야 하는 것은 물리 위에 바로
긴 경로 모델을 얹은 부분이며, 짧은 폐루프 기술·사람 시범 정렬·발견 지도·
독립 평가를 분리해 쌓아야 한다.
