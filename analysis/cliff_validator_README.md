# 암벽맵 수학 검증기 1차

이 도구는 암반을 발판 목록으로 해석하지 않고, LMF의 solid 타일에서 실제로 머리 위가 열린 표면을 추출한다. 각 표면 사이를 보수적인 이동 범위로 연결해서 다음을 검사한다.

- 시작점에서 정상 후보까지 연결되는가
- 연결이 앞/뒤 구르기 범위인지 낙하산 범위인지
- 세로 빈 공간이 2칸 미만인 표면을 걸러내는가
- 루트가 여러 갈래로 과도하게 열려 있는가
- 점프 궤적이 암반에 부딪힐 가능성이 있는가

## 실행

```powershell
$py='C:\Users\microsoft\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py analysis\cliff_validator.py 'Map\새맵.LMF' --params analysis\physics_params.example.json --out analysis\새맵_validator.json
```

`physics_params.example.json`의 이동값은 영상 프레임을 분리해 보정할 수 있는 설정값이다. 현재는 암벽수정1을 기준으로 한 보수적 후보값이며, 정확한 엔진 재현값을 의미하지 않는다.

## 후보 생성 순서

1. `cliff_shape_generator.py`가 좌우 암벽 외곽선을 생성한다.
2. 모양의 반복도와 중앙 빈 공간을 점수화한다.
3. 시작점에서 정상까지 연결되는 후보만 통과시킨다.
4. `render_cliff_candidate.ps1`로 미니맵을 확인한다.
5. 사람이 모양을 승인한 뒤에만 원본 헤더를 사용해 LMF로 내보낸다.

현재 `암벽_수학형_v1_후보.json`은 경로는 있으나 우회 가능성이 많아서 최종맵이 아니다. 이 검증기의 다음 보정 대상은 영상에서 동작별 최대 높이·수평거리와 실제 궤적 충돌 판정이다.
