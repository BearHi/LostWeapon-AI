# LostWeapon Client native fast-sim feasibility

조사 대상은 `C:\Users\microsoft\Downloads\NewLostweapon\NewLostweapon3.zip` 안의 `Client.exe`이다. 이 문서는 원본 x86 명령을 그대로 실행한 범위와 아직 증명하지 못한 범위를 구분한다.

## 결론

완전한 Client 전체를 로그인·네트워크·DirectDraw·DirectSound까지 포함해 headless 학습 엔진으로 바로 쓰는 것은 현재 `NO`이다. 대신 실제 Client의 x86 movement/collision/player dispatcher와 후보 world/object/time update chain을 캡처한 월드 상태 안에서 실행하는 native oracle은 `PARTIAL`을 넘어 실험 가능한 프로토타입까지 도달했다. 다음 구조를 추천한다.

```text
LMF/map parser + planner
        |
        v
captured native oracle (original Client x86 movement/collision code)
        |
        v
short action branch / state read / learned world model
```

현재 oracle은 별도 Python 물리식을 재작성하지 않는다. `Client.exe`의 `.text`를 Unicorn x86 에뮬레이터에 매핑하고, 캡처한 Client 메모리 상태를 복원한 뒤 원본 함수 바이트를 실행한다. Windows API 호출 중 입력·시계·문자열 길이·오류 코드만 작은 shim으로 제공한다.

## Client 식별

| 항목 | 값 |
|---|---|
| SHA-256 | `051119bcbd521ce18d1e8636e749dc05eee1958b4cf50d2c13a816ba5898df15` |
| PE machine | `0x14c` (x86/I386) |
| preferred image base | `0x00400000` |
| observed loaded base | `0x00e60000` |
| entry point | `0x0047c4cc` |
| SizeOfImage | `0x0a636000` |
| Client.exe file size | 791,552 bytes |

SHA-256은 인수인계 문서와 일치한다. 압축파일 전체에는 Client 외에 Data 리소스와 맵 파일이 포함되어 있었고, 사운드·배경 리소스가 존재한다.

## 확인된 native 함수와 의존성

| 주소 | 역할 / 증거 |
|---|---|
| `0x004228c0` | 플레이어 입력 처리 진입점. `GetAsyncKeyState` IAT(`0x0049c200`)를 읽는다. |
| `0x00436e30` | 플레이어/월드 업데이트 dispatcher로 확인. 이 함수 단독 호출에서 중력, 지면 접촉, 상태 전이가 발생했다. |
| `0x00459be0` | collision-aware movement 함수. player slot index, movement mode, double 좌표를 읽고 collision reader를 반복 호출한다. |
| `0x0041aba0` | 맵 grid code reader. |
| `0x0041ac80` | bounds 검사 후 grid reader를 호출하는 reader 계열. |
| `0x0041ac30` | hard-block predicate. code `1`, `5..8`을 blocking으로 처리하고, OOB를 blocking으로 처리하는 분기가 보인다. |
| `0x0041ae70` | movement 중 주변 tile/object 판정에 사용되는 별도 predicate 계열. |
| `0x00461ac0` | 시간 기반 object/list 업데이트 계열. full dispatcher 의존성을 보여주는 후보다. |
| `0x00415fc0` | `timeGetTime`(`0x0049c2bc`)로 wall-clock delta를 누적한다. |

`0x436e30 -> 0x455f00 -> 0x453a50 -> 0x476000 -> 0x461ac0 -> 0x436620 -> 0x415f10` 후보 chain도 동일한 캡처 상태에서 함수별 probe를 통과했다. 이 chain은 렌더링·네트워크 main loop가 아니라, 입력 뒤의 gameplay/world/object/time update 후보만 순서대로 실행하는 범위다. `GetFocus` 등 일부 USER32/time import는 deterministic shim으로 제공한다.

Import table에는 `GetAsyncKeyState`, `timeGetTime`, Winsock (`recv`, `send`, `connect` 등), `DDRAW.dll:DirectDrawCreate`, `DSOUND.dll`가 함께 있다. 따라서 full main loop를 그대로 빠르게 호출하면 환경 의존성이 남는다. 현재 prototype은 full main loop를 호출하지 않고, 입력 함수와 gameplay dispatcher closure를 호출한다.

## 실제 실행 증거

훈1 맵에서 Client를 잠시 suspend하여 749개 committed memory region, 약 550 MB를 복사했다. 캡처 시점은 다음과 같았다.

```text
map size = 30 x 18
controlled slot = 0
pos = (112, 448)
motion58 = -120
hp = 100
state38 = 7
state3c = 1 (캡처 시점에 따라 animation phase는 변함)
```

복사본에서 원본 `0x004228c0`와 `0x00436e30`을 실행했다.

```text
RIGHT 12 ticks: x 112 -> 160, y 448 유지
LEFT 12 ticks:  x 112 -> 64,  y 448 유지
```

같은 캡처 상태를 매번 복원하고 동일 입력열을 두 번 실행했을 때, player state와 실행 중 dirty page hash가 모두 같았다. 다음 11개 시퀀스가 반복 재현되었다.

```text
NOOP, RIGHT, LEFT, jump, front roll, back roll,
jump-backroll, backroll+C, UP+DOWN, LEFT+RIGHT, attack
```

이 결과는 “Client 전체가 완성된 게임 서버 없이도 실행된다”는 뜻이 아니다. 캡처한 local state와 필요한 API shim을 가진 gameplay closure가 실행된다는 뜻이다.

근거 파일:

- `native_harness/evidence/captured_tests.json`
- `native_harness/evidence/oracle_parity_fixtures.json`
- `native_harness/evidence/disassembly.txt`
- `native_harness/evidence/pe.json`

## Snapshot / branch

`native_harness/capture.py`는 선택한 PID를 짧게 suspend하고 읽기 전용으로 committed memory를 저장한 뒤 즉시 resume한다. Client 파일에는 쓰지 않는다. 스냅샷에는 process memory가 들어 있으므로 `private_snapshots` 아래 파일은 외부 공유 대상이 아니다.

`CapturedOracle.begin_branching()`은 전체 캡처를 한 번 로드한 뒤 baseline CPU context와 memory를 보관한다. 한 branch를 실행하고, 해당 branch가 쓴 page만 baseline으로 되돌리는 방식이다. 테스트에서 median branch restore 시간은 약 `0.41 ms`였다. 이 수치는 emulator 내부 복원 시간이며, 실제 Client process를 OS 수준에서 fork/restore하는 시간은 아니다.

현재 snapshot에는 heap, map grid, player, object list, resource/animation state가 함께 들어 있다. player x/y 몇 바이트만 저장하는 방식은 사용하지 않는다.

## 속도

| 모드 | 측정값 | 의미 |
|---|---:|---|
| 원본 x86 closure, bulk input/state dirty tracking 없음 | 585.4 tick/s | nominal 60Hz의 9.76배 |
| 원본 x86 closure + dirty-page hook | 31.6 tick/s | tracking hook 자체의 비용 포함 |
| branch restore | 153.9 restore/s (약 6.5 ms) | 550 MB 초기 로드 이후의 dirty-page 복원 |

측정 파일은 `native_harness/evidence/benchmark_components.json`, `benchmark_untracked.json` 및 `benchmark.json`이다. 새 bulk-input 측정에서는 emulation만 약 602.6 op/s, state read만 약 18,774회/s였다. 따라서 현재 병목은 state read가 아니라 Python/Unicorn emulation과 tracking hook이며, C/C++ embedding 또는 native dirty-page bitmap으로 옮길 여지가 있다. 이전 274 tick/s 수치는 256개 키를 Python에서 매 tick 순회하던 구현의 값이다.

## State subset 후보

7개 시퀀스를 각각 20틱 실행하며 원본 x86 메모리 read/write hook을 켰다. 시나리오별 union은 65~71 page였고, 전체 시나리오의 union은 71 page였다.

```text
client image pages: 54~58 per scenario
mapped private pages: 6~10 per scenario
harness control/stack: 3 pages
union across NOOP/RIGHT/jump/roll/backroll/C: 71 pages
```

이 71-page 집합은 deterministic closure의 후보 범위가 크게 줄었다는 증거다. 아직 allocator/reset/network/object spawn 경로를 포함하지 않으므로 바로 삭제 가능한 최소 상태로 인증하지는 않는다. 결과와 주소 목록은 `native_harness/evidence/subset_analysis.json`에 저장했다.

실행된 code page까지 포함한 112-page sparse mapping을 만들고, 전체 550,215,680-byte capture 대신 458,752 bytes만 매핑해 player closure 7개 시퀀스를 다시 실행했다. 전부 `PASS`였고, sparse oracle도 약 444.4 tick/s(7.41x)를 냈다. 이후 world/object/time chain까지 포함한 footprint는 158 pages, 647,168 bytes로 늘었지만, 같은 7개 시퀀스를 다시 sparse 매핑에서 전부 `PASS`로 재현했다. 이 chain의 첫 capture benchmark는 약 314.9 tick/s(5.25x), 158-page sparse benchmark는 약 321.1 tick/s(5.35x)였다.

정상 Client를 재시작한 뒤 같은 훈1 맵에서 두 번째 독립 캡처도 만들었다. 새 캡처는 `map=30x18`, `slot=0`, 시작 위치 `(350,448)`였고, full world-chain 7개 시퀀스가 모두 `PASS`였다. `RIGHT` 12틱은 `(350,448) -> (398,448)`로 재현됐다. 첫 캡처에서 만든 158-page subset을 새 캡처에 그대로 적용하면 unmapped read가 발생했지만, 새 캡처에서 footprint를 다시 만들면 157 pages, 643,072 bytes로 줄어들고 sparse 7개 시퀀스가 전부 `PASS`였다. 새 상태 benchmark는 full 약 290.7 tick/s(4.84x), sparse 약 381.4 tick/s(6.36x)였다. 즉 원본 x86 closure는 동일 맵의 독립 캡처 사이에서도 유지되지만, private/map state subset은 캡처별로 재생성해야 한다. 결과는 `world_chain_hun1_live.json`, `sparse_world_hun1_live.json`, `world_subset_hun1_live.json`, `benchmark_world_chain_hun1_live.json`에 있다.

다른 room/map(`25x400`, room 2, slot 4)에서는 dispatcher가 순회하는 두 목록의 캡처 값이 `5243`과 `3153`으로 훈1의 `58`보다 컸다. 그래서 기본 2,000,000 명령 guard는 짧았지만, 10,000,000 명령의 명시적 bounded call로 world-chain 7개가 전부 `PASS`했다. `RIGHT` 12틱은 `(662,10848) -> (710,10848)`, jump/roll도 해당 맵 좌표에서 재현됐다. 이 맵의 full benchmark는 약 7.03 tick/s, adaptive sparse(726 pages, 2,973,696 bytes)는 약 8.32 tick/s였다. 즉 훈1만 가능한 것이 아니라, 맵별 object-list 크기에 따라 필요한 명령 예산과 속도가 달라진다. 근거 파일은 `world_chain_current_live_10m.json`, `sparse_world_current_live_adaptive.json`, `adaptive_sparse_current_live.json`, `benchmark_world_chain_current_live.json`이다.

## LMF 직접 주입 첫 단계

훈1 캡처는 맵 크기 `30x18`, runtime object count `58`이 제공된 `훈1.LMF`와 일치했다. object array `0x027a5998`의 58개 레코드는 LMF 레코드와 같은 순서였고, 각 중심 좌표는 `x*32+16`, `y*32+16`으로 일치했다. 네 runtime grid 중 solid grid에는 훈1의 ID 7 바닥 28칸만 code 1로 들어 있었다. 두 독립 훈1 캡처의 네 grid hash도 모두 같았다.

이 대응을 이용해 `SimpleLmfOracle`을 추가했다. 원본 훈1에서 ID `7/49/100/140`의 Client runtime object template을 가져와 좌표와 bounds만 옮기고, LMF 크기에 맞춰 Client grid 포인터와 row offset을 재구성한다. 이 상태에서 실행되는 입력·이동·충돌·object/world update는 계속 원본 Client x86 명령이다.

재구성한 훈1은 원본 훈1 캡처와 다음 7개 12-tick 상태열이 전부 정확히 같았다.

```text
NOOP, RIGHT, jump, front roll, back roll, jump-backroll, backroll+C
```

동일 방식으로 훈2~5도 LMF에서 offline world state를 만들고 원본 world-chain을 실행했다. 이 단계의 결과 자체는 실행 smoke이며 실제 기믹 동작·목표 도달·클리어 판정은 아니다. 훈2의 normal Client parity는 아래 별도 절에서 추가로 검증했다. `SimpleTrainingAPI`는 `reset / set_input / step / read_state / save_state / restore_state`를 제공하고, 훈2에서 reset 뒤 동일 RIGHT 12-tick 결과를 정확히 재현했다. 근거는 `native_harness/evidence/simple_lmf_injector.json`이다.

별도 `25x400` 캡처의 5,243개 object record에서도 LMF ID가 `+0xd0`에 유지되는 것을 확인해 ID 3 사다리, ID 37 얼음 경사, ID 101~109 리스폰 template을 추가로 추출했다. 이 template을 훈1 기반 oracle에 옮긴 뒤 훈7, 훈7.5, 훈19를 직접 주입했고, 12-tick 실행과 reset/replay가 모두 deterministic하게 통과했다. 훈7의 UP 입력에서는 `y 576.0 -> 458.4`, 훈19의 LEFT 입력에서는 `(432,352) -> (384,374)`가 나왔다. 이는 cross-capture template이 실행 가능하다는 smoke 증거이며, 각 기믹의 정상 Client parity 증거는 아니다. 근거는 `object_templates.json`, `extended_lmf_injector_smoke.json`이다.

그 다음 원본 Client 함수 `0x0041e510(tile_id, x, y)`가 LMF 레코드 하나를 runtime object와 collision grid로 materialize하는 함수임을 확인했다. 빈 훈1 상태에 58개 레코드를 이 함수로 다시 넣자 object array 전체와 네 grid의 SHA-256이 캡처 원본과 각각 정확히 같았다. 생성된 훈1을 캡처 원본과 다시 비교한 결과 NOOP/RIGHT/jump/front roll/back roll/jump-backroll/backroll+C의 7개 12-tick 상태열도 전부 exact match였다.

`NativeLmfOracle`은 이 함수로 훈1~20 및 6.5/7.5/8.5를 포함한 23개 LMF를 모두 생성했다. 모든 맵에서 record materialization과 gameplay/world chain 1 tick이 `PASS`했다. 따라서 현재는 훈1 template에 있는 ID만 가능한 단계가 아니라, 제공된 모든 훈련맵을 원본 Client 생성 코드와 원본 update 코드로 offline 실행하는 단계다. 훈2의 걷기·점프·gap collision은 아래 normal Client trace까지 검증했고, 훈3~20의 개별 기믹은 아직 smoke보다 높은 등급으로 말하지 않는다. 근거는 `native_lmf_builder_probe.json`, `native_lmf_hun1_parity.json`, `native_lmf_all_training_maps.json`이다.

## 훈2 normal Client parity

훈2를 실행한 정상 Client에서 debugger나 process-memory write 없이 동일 시작 경계의 snapshot과 키 입력 trace를 만들었다. 전체 메모리는 Client를 실행한 채 먼저 읽고, 원본 x86 world-chain이 실제로 접근한 155 pages만 suspend 상태에서 다시 읽었다. 이 방식으로 Client 정지시간을 `0.49초`에서 `2.21~2.79 ms`로 줄여 wall-clock backlog를 제거했다. 입력은 일반 Windows 키 이벤트만 사용했다.

첫 RIGHT 12-tick 비교에서는 시작 `(224,448)`부터 `(272,448)`까지 13개 movement boundary가 모두 exact match였다. 비교 필드는 x/y, motion58, state `38/3c/68/74/b0/c0/c4/d0/dc`, player animation header이다.

첫 gap은 양방향으로 `RIGHT+UP` 및 `LEFT+UP`을 40 tick 유지한 뒤 입력을 해제해 착지할 때까지 비교했다. 정상 Client와 offline oracle 모두 상승 시작 속도 `+1160`, tick당 `-40`의 수직속도 변화, 정점, 하강, 착지 속도 `-1240`, 22 release ticks 뒤의 지면 상태 전환과 최종 위치가 일치했다. 정상 Client를 실행 중 여러 `ReadProcessMemory` 호출로 읽으므로 일부 표본은 인접 두 tick의 필드가 섞이거나 중간 tick을 놓쳤다. 비교기는 이를 `TORN_READ`, `MID_TICK_SAMPLE`, `INPUT_RELEASE_EDGE`, `MISSED_SAMPLE`로 따로 기록한다. 완성된 tick과 비교 가능한 표본에서 coherent mismatch는 양방향 모두 0개였다.

근거 파일은 `hun2_normal_oracle_right_parity.json`, `hun2_normal_oracle_gap_jump_full_parity.json`, `hun2_normal_oracle_gap_jump_landing_parity.json`이다. 이것은 훈2의 걷기·점프·gap collision player closure에 대한 normal Client parity 증거이며, 아직 훈2의 목표 판정이나 훈3 이후 기믹 parity까지 뜻하지 않는다.

훈5에서는 시작 발판에서 `RIGHT`로 이탈한 뒤 공중에서 `C`를 한 번 누르는 입력을 사용했다. 정상 Client와 offline oracle 모두 C 입력 뒤 `state38=3`, `dc=1`로 낙하산 상태에 들어갔고, 이후 수직 낙하속도 변화와 x/y 곡선이 일치했다. 64개 비교 틱의 완성된 player physics state에서 coherent mismatch는 0개였다. 일부 animation phase/header 차이는 캡처 시점의 표시 타이머 차이로 별도 집계했다. 근거는 `hun5_normal_oracle_parachute_parity.json`이며, 이 결과는 훈5의 공중 이동·낙하산 closure 증거다.

리소스 썸네일 다섯 장의 명칭은 이미지 외형만 보고 추정한 내부 ID 이름이 아니다. 사용자 확인에 따라 표시 순서를 `다리벽 → 얼음벽 → 미끄럼얼음 → 거북이 → 폭탄`으로 기록한다. 이 순서와 LMF 숫자 ID의 일대일 대응은 별도 타일 배치·runtime object trace가 확인될 때까지 확정하지 않는다.

훈6에서는 LMF 44개 레코드와 object array, collision grid 4개를 원본 `0x41e510`으로 재생성해 모두 exact match했다. 시작 상태에서 `RIGHT+UP`을 유지해 첫 틈으로 이동한 정상 Client trace도 같은 입력의 offline oracle과 41개 경계 중 관측된 40개가 exact match였고, 1개는 정상 Client 표본 누락이었다. coherent mismatch는 0개였다. 이 실험에서 `UP`만으로 자동 점프가 발생하지 않는 결과까지 원본 코드로 확인했으며, JUMP/PARA 그림 리소스가 곧바로 물리 효과를 의미한다고 가정하지 않고 별도 object interaction trace로 확인할 대상으로 남겼다. 근거는 `native_lmf_hun6_builder_probe.json`, `hun6_normal_oracle_right_up_parity.json`이다.

## 요구 질문에 대한 답

| 질문 | 판정 | 근거 |
|---|---|---|
| Q1. 임의 1 tick 실행 | PARTIAL | input + gameplay/world update 후보 chain을 1회씩 실행. 일반 Client main-loop 전체는 미검증. |
| Q2. 렌더링 없이 update | YES (closure) | DirectDraw/DirectSound 없이 캡처된 local gameplay closure 실행. |
| Q3. wall-clock 제거 | YES (closure) | `timeGetTime`을 deterministic logical tick으로 대체한 emulator shim. full loop에는 미적용. |
| Q4. snapshot/restore | YES (emulator) | full captured memory + CPU context, dirty-page branch restore. |
| Q5. 동일 snapshot + 동일 input deterministic | YES (tested closure) | 11개 시퀀스에서 player state와 dirty-page hash 일치. |
| Q6. 여러 input branch | YES (tested closure) | baseline restore 후 입력열별 branch 실행. |
| Q7. 필요한 state subset 식별 | PARTIAL | player/map/resource 경계는 보였지만 full deterministic subset을 아직 닫지 못함. |
| Q8. Python simulator보다 parity 높은 oracle | YES (검증된 closure) | 훈2 RIGHT/gap jump와 훈5 공중 C 입력에서 coherent mismatch 0. 다른 기믹은 계속 PARTIAL. |
| Q9. speed-up | MEASURED | 훈1 world chain 4.84x(full)/6.36x(sparse), room2 25x400 world chain 0.117x(full)/0.139x(sparse) at 12-tick benchmark, dirty 0.53x. full Client speed-up 아님. |
| Q10. full-native가 어려울 때 현실적인 범위 | YES | movement `0x459be0`, collision `0x41aba0/0x41ac30/0x41ac80`, input `0x4228c0`, dispatcher `0x436e30`, world/object/time 후보 chain. |

## 남은 막힘

정상 실행 중인 Client에 debugger breakpoint를 설치해 real-client tick 경계를 직접 수집하는 시도에서 Client가 종료됐다. 사용자가 말한 인터넷/세션 의존성 또는 기존 Client의 자체 종료 조건과 구분되지 않았으므로, 이것을 parity 실패의 증거로 사용하지 않는다. 이후 작업에서는 정상 Client에 live debugger를 다시 붙이지 않고, 새로 캡처한 상태를 emulator에서 검증한다.

아직 확인하지 않은 것은 다음과 같다.

1. 실제 Client의 모든 object update와 서버 동기화가 없는 상태의 완전한 독립 실행.
2. 훈2에서는 같은 boundary의 normal Client trace와 emulator 비교가 완료됐다. 같은 방법을 object state까지 포함해 다른 기믹으로 일반화해야 한다.
3. DirectDraw/DirectSound/network import 전체를 제거한 full dispatcher.
4. snapshot을 수십만 episode 동안 안정적으로 재사용할 때의 memory/time 비용.
5. room/map이 바뀔 때 world-chain 호출 예산과 private-state subset을 자동으로 재구성하는 일반화. room2에서는 목록 크기가 커져 10,000,000 명령 예산이 필요했고, 다른 맵의 모든 목록 규모를 아직 측정하지 않았다.
6. 훈3~20 기믹별 normal Client parity. 훈2 걷기·점프·gap collision, 훈5 공중 C, 훈6 첫 틈 이동은 비교했지만, JUMP/PARA marker interaction과 ladder/spring/water/fan/magnet/ice의 실제 효과는 동일 입력 trace로 더 비교해야 한다.

## 실행 파일

```text
native_harness/inspect_binary.py       PE + x86 disassembly evidence
native_harness/live_state.py           read-only live state reader
native_harness/capture.py              short suspend/read/resume capture
native_harness/capture_fast_boundary_trace.py rolling copy + 155-page fast boundary capture
native_harness/oracle.py               synthetic native x86 fixture
native_harness/captured_oracle.py      captured-memory native oracle
native_harness/tests/run_captured.py   deterministic branch fixtures
native_harness/tests/parity_fixture.py offline tick-by-tick comparator
native_harness/api.py                  save/restore/input/step/read API
native_harness/tests/api_smoke.py      API branch smoke test
native_harness/benchmark/run_benchmark.py old end-to-end benchmark
native_harness/benchmark/components.py cost breakdown
native_harness/analysis/subset_analysis.py read/write-page footprint
native_harness/sparse_oracle.py         sparse closure mapping validator
native_harness/benchmark/sparse.py      sparse mapping benchmark
native_harness/analysis/world_footprint.py candidate world-chain footprint
native_harness/tests/run_world_chain.py  candidate gameplay/world chain test
native_harness/tests/run_sparse_world.py sparse world-chain test
native_harness/benchmark/world_chain.py  world-chain benchmark
native_harness/tests/probe_snapshot_chain.py per-snapshot bounded function probe
native_harness/tests/adaptive_sparse_world.py adaptive sparse-page growth
native_harness/lmf_injector.py          simple LMF -> captured Client world state
native_harness/tests/test_simple_lmf_injector.py 훈1 exact replay + 훈2~5 smoke
native_harness/tests/simple_training_api_smoke.py resettable training API test
native_harness/analysis/extract_object_templates.py captured object template bank
native_harness/tests/extended_lmf_injector_smoke.py cross-capture 훈7/7.5/19 smoke
native_harness/tests/probe_native_lmf_builder.py original 0x41e510 byte-exact probe
native_harness/tests/test_native_lmf_hun1_parity.py native-built 훈1 7-scenario parity
native_harness/tests/test_native_lmf_all_training_maps.py all 23 maps build + tick
native_harness/tests/compare_normal_boundary.py normal Client movement-boundary comparator
native_harness/tests/compare_normal_sequence.py held input + release + landing comparator
native_harness/tests/compare_normal_parachute.py walk-off + C parachute comparator
analysis/training_map_inventory.py      훈1~20 static structure inventory
analysis/training_map_curriculum.py     layout/resource-based lesson candidates
```

필요한 Python 패키지는 `native_harness/vendor`에 넣어 두었다. 원본은 `native_harness/original/Client.exe`에 보존되어 있으며 SHA-256 확인 없이는 실행하지 않도록 oracle이 검사한다.

## 추천 개발 순서

현재 결과를 바탕으로는 full Client를 억지로 통째로 분리하기보다, 캡처된 native oracle을 planner의 검증기·discrepancy detector로 먼저 사용한다. 그 다음에는 실제 Client를 다시 건드리지 않고, 별도 프로세스에서 맵별 캡처를 만들고 `0x4228c0 -> 0x436e30` 및 후보 world chain의 input/state parity fixture를 늘리는 것이 가장 안전하다. 이 closure가 안정화된 뒤에만 object list, water/ice/magnet, weapon/projectile update를 한 계열씩 추가한다.
