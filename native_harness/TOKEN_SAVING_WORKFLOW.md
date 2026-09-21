# 작업 분담과 토큰 절약 규칙

## 사용자가 하는 일

일반 Client의 실제 입력이 필요한 순간에만 직접 조작한다. Codex가 다음 정보를 한 번에 전달한다.

- 맵과 시작 상태
- 누를 키와 순서
- 유지 시간 또는 종료 조건
- 완료 후 Client를 그대로 둘지 여부

사용자는 지시된 동작만 수행하고 `완료`라고 알린다. 물리 해석이나 파일 수정은 하지 않는다.

## Codex가 하는 일

- Client read-only 캡처와 normal Client/native oracle 비교
- LMF, ZIP, snapshot, JSON, Python 코드의 분석·수정
- native x86 closure 실행, branch replay, 테스트와 evidence ledger 관리
- 중복 맵 실험을 줄이고 기믹별 대표 fixture만 깊게 검증

## 다른 ChatGPT에 넘길 수 있는 일

작은 텍스트·JSON·로그의 설명, 요약, 가설 정리는 가능하다. Codex가 필요한 부분만 뽑은 compact packet을 만들고 사용자가 그 내용을 다른 ChatGPT에 전달한다. 다른 ChatGPT는 이 로컬 workspace를 직접 읽거나 수정하지 못하므로, 결과는 다시 Codex가 검토한 뒤 코드와 증거에 반영한다.

## 토큰 절약 원칙

1. 이미 캡처한 snapshot과 fixture를 재사용한다.
2. 23개 맵을 매번 깊게 반복하지 않고, mechanic별 대표 맵만 normal Client parity를 확인한다.
3. 정상적인 offline 작업은 한 번에 묶어서 실행하고 중간 보고를 생략한다.
4. full log 대신 digest, mismatch count, 핵심 상태만 저장한다.
5. 물리 규칙은 native/original Client 증거가 없으면 확정하지 않는다.
6. 훈련맵의 시작점부터 기믹까지의 공략 경로가 실제 학습 목표가 아니면, 경로 탐색을 반복하지 않고 기믹 접촉 상태만 검증한다.
7. 새 맵은 전체 구조를 한 번 스캔한 뒤 동일 topology 경로만 통째로 재생한다. 작은 변경은 긴 타 맵 경로를 반복하지 않고 발판 전환 조각을 native 재검증·국소 보정한다.
