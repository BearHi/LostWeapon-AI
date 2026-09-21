# LostWeapon Native Oracle + AI 다음 세션 인수인계 (2026-09-15)

> 현재 우선순위와 실행 상태는 [2026-09-17 인수인계](NEXT_SESSION_HANDOFF_2026-09-17.md)를 먼저 확인한다. 이 문서는 9월 15일 당시 기록이다.

## 목표

원본 `Client.exe` x86 명령을 Unicorn에서 실행해 LostWeapon의 입력, 이동, 충돌, 기믹, 오브젝트를 재현하는 native oracle을 만들고, 이 환경에서 맵 클리어와 칼전 AI를 로컬 학습한다. Python으로 물리를 흉내 내어 값을 맞추지 않는다. 불일치는 원본 Client의 누락된 호출, 상태, 초기화 순서를 찾아 고친다.

사용자는 진행 채팅을 반복해서 요구하지 않는다. 큰 줄기의 구현과 검증을 마친 뒤 짧게 보고한다. 실제 Client 조작이나 특정 맵 캡처가 꼭 필요할 때만 바로 요청한다.

## 현재 실행 위치

- 프로젝트: `C:\Users\microsoft\Desktop\로스트웨폰 맵`
- 핵심 코드: `native_harness`
- 사용자 실행 파일: `native_harness\LostWeapon_AI_통합실행.bat`
- 원본 캡처: `native_harness\private_snapshots\hun1_full.zip`
- 공용 맵 정책: `native_harness\checkpoints\map_clear_shared_dqn.pt`
- 행동열 기록: `native_harness\checkpoints\map_clear_shared_dqn.episodes.jsonl`
- 전체 경로 기억: `native_harness\checkpoints\map_route_library.json`

## 확인된 native 기반

- LMF 레코드는 원본 Client `0x0041e510`로 runtime object/grid로 만든다.
- gameplay/world chain은 원본 Client x86을 실행한다.
- 훈1의 기본 이동·점프·앞굴·뒷굴·조합 입력은 강한 parity 근거가 있다.
- 훈1~20과 중간 번호를 포함한 훈련 LMF들은 native builder로 로드 가능하다.
- raw14/17 자석, raw20 사라지는 벽돌, 동전블록 점프뒷굴 등은 별도 evidence에 검증 기록이 있다.
- 훈1은 79 decision 경로, 훈2는 최단 283 decision 경로, 훈3은 474 decision 경로가 native 재검증되었다.

## 최근 완료

### 작은 맵 변경 경로 재사용

`global_planner.py`, `route_library.py`, `train_local_dqn.py`를 바꿔 저장 경로를 새 LMF에서 그대로 신뢰하지 않고 현재 native world에서 다시 실행한 뒤 raw140 도달 때만 채택한다.

훈3 검증:

- 원본 훈3: 474 steps 성공
- 깃발 한 칸 이동: 468 steps 성공
- 무관한 지형 타일 한 칸 추가: 474 steps 성공

기록: `native_harness\evidence\hun3_route_transfer.json`

이 결과는 두 변형에서 경로 전이가 됐다는 뜻이다. 임의의 길 막힘을 새로 계획하거나 모든 오브젝트를 이해했다는 증거는 아니다.

### raw87/raw88/raw95/raw96 폭발물 중력 표시

원본 x86은 이 오브젝트들을 일반 OBJECT_BASE가 아닌 별도 type-60 배열 `0xA074460`, count `0xA072AA4`에 만든다. native builder가 이미 위치를 중력으로 이동시키고 있었지만 `native_playground.py`가 LMF 최초 좌표를 정적 그림으로 표시해서 고정된 것처럼 보였다.

변경:

- `lmf_injector.py`: LMF record와 type-60 special array index 연결
- `native_playground.py`: raw87/88/95/96을 정적 배경에서 제외하고 native live position으로 overlay 표시
- `tests\special_bomb_gravity_regression.py` 추가

검증:

- 맵테스트2 특수 폭발물 30/30 mapping
- 30개 모두 LMF 원래 좌표와 다른 native 위치 확인
- 기존 지뢰 접촉 피격 regression 통과
- playground map switch regression 통과

기록: `native_harness\evidence\special_bomb_gravity_regression.json`

## 작업 중 멈춘 부분 — 새 세션에서 먼저 확인

사용자의 중간점검 요청 직전에 발판 전이 단위 지식 저장을 작성하기 시작했다. 아래 변경은 **아직 py_compile이나 실행 검증을 하지 않았다**.

- `global_planner.py`: `surface_for_player()` 추가
- `transition_library.py`: 새 파일. 성공 행동열을 surface-to-surface 조각으로 분해하고 JSON에 저장
- `train_local_dqn.py`: native-verified route의 state trace를 모아 `map_transition_library.json`에 저장하도록 연결

다음 세션 첫 작업:

1. 위 세 파일만 `python -m py_compile`한다.
2. `train_local_dqn.py ... 훈3.LMF --episodes 0`으로 기존 474-step 경로를 재실행한다.
3. `checkpoints\map_transition_library.json`이 만들어지고 전이 조각 수가 합리적인지 확인한다.
4. 오류가 있으면 이 미완성 부분만 고친다. 기존 native 물리나 검증 완료 코드를 다시 처음부터 분석하지 않는다.
5. 저장된 전이 조각은 아직 자동 계획에 사용하지 않는다. 새 맵의 동일한 상대 발판 형상에서 branch/replay해 raw native 결과가 맞을 때만 reusable skill로 승격한다.

## 학습 구조와 한계

- 현재 DQN은 관측에 player state, goal vector, 네 collision grid local crop, 16x16 global grid, local raw-ID bits를 받는다.
- terminal clear 보상은 실제 raw140 도달에만 준다. 빠른 clear가 더 높다.
- 일반 피격 감점은 없다. 가시·폭발 knockback이 해법인 맵이 있기 때문이다.
- 성공 행동열은 물리 수정 뒤에도 현재 oracle에서 다시 실행해 검증한다. 오래된 next-state 값을 정답으로 고정하지 않는다.
- 훈1~3은 기믹 이해 증거가 약하다. 특히 훈3에는 raw7, raw49 장식, raw100, raw140뿐이다.
- 전체 경로 replay는 작은 편집에 견디지만 아직 물리적 재계획은 아니다. 전이 skill + surface graph + 실패 지점 branch가 다음 구조다.
- 칼전 self-play와 team-base raw122는 별도 축이다. 현재 우선순위는 맵 전역 계획과 기믹 지식 구조를 닫은 뒤 칼전으로 확장하는 것이다.

## 사용자 확인이 필요해지는 경우

- normal Client와 tick parity가 필요한 기믹: 사용자에게 정확한 맵 하나를 켜 달라고 요청하고 짧은 비침습 trace만 수집한다.
- 같은 PC의 두 Client는 P2P가 연결되지 않아 실제 타격 검증이 안 됐다. 전투 parity에는 다른 PC가 필요할 수 있다.
- raw ID 이름이 불확실하면 추측하지 말고 사용자에게 이미지/동작 기준으로 확인한다.

## 토큰 절약 운영 규칙

- `rg`는 한 번에 관련 패턴을 묶고 같은 범위를 반복 검색하지 않는다.
- `Get-Content`로 200~400줄 전체를 반복 출력하지 말고 `rg -n` 후 필요한 30~80줄만 읽는다.
- PE/Capstone은 매번 전체 `.text`를 재디스어셈블하지 않는다. xref/function-window 결과를 JSON 캐시에 저장하는 재사용 probe를 먼저 만든다.
- LMF/raw object 실험은 매번 here-string Python을 새로 쓰지 않는다. `probe_special_object.py`, `probe_builder_diff.py`, `probe_function_writes.py` 같은 인자형 도구로 합친다.
- 대형 `rg` 출력은 파일로 저장하고 요약 통계만 모델에 반환한다.
- 이미 evidence가 있는 parity를 다시 실행하지 않는다. 관련 코드가 바뀐 경우에만 좁은 regression을 실행한다.

## 핵심 문서와 evidence

- `native_harness\NATIVE_FASTSIM_FEASIBILITY.md`
- `native_harness\LOCAL_TRAINING_PLAN.md`
- `native_harness\COMBAT_NATIVE_PLAN.md`
- `native_harness\USER_TEST_PACKAGE.md`
- `native_harness\evidence\mechanic_evidence_ledger.json`
- `native_harness\evidence\hun3_route_transfer.json`
- `native_harness\evidence\special_bomb_gravity_regression.json`

정적 LMF 검사, serialization round-trip, synthetic collision 결과를 실제 게임 clear/parity로 표현하지 않는다. 모든 최종 판단에는 `normal Client`, `original x86 offline`, `static validation` 중 어떤 근거인지 표시한다.
