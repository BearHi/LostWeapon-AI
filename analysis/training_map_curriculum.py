"""Build a conservative curriculum view for the supplied training LMF files.

The lesson names are layout/resource hypotheses. They are not claims that the
Client executed or cleared a map.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "analysis" / "training_maps_inventory.json"
OUT_JSON = ROOT / "analysis" / "training_map_curriculum.json"
OUT_MD = ROOT / "analysis" / "training_map_curriculum.md"

LESSONS = {
    "훈1.LMF": ("평지 이동 기준선", "걷기·방향 전환·목표 접촉의 기준 trajectory"),
    "훈2.LMF": ("짧은 틈 통과", "3칸 바닥 공백을 점프/구르기로 통과"),
    "훈3.LMF": ("연속 단차와 중앙 장애물", "낮은 발판 두 개와 위쪽 중앙 발판을 조합한 기본 이동"),
    "훈4.LMF": ("역방향 짧은 틈", "훈2의 좌우 반전으로 방향 비대칭 검사"),
    "훈5.LMF": ("장거리 낙하·공중 이동", "왼쪽 상단 시작에서 오른쪽 하단 목표까지 공중 조작"),
    "훈6.LMF": ("JUMP/PARA 표식 구간", "JUMP·PARA 그림 타일과 짧은 발판을 순서대로 통과"),
    "훈6.5.LMF": ("JUMP/PARA 조합 난도 증가", "훈6보다 긴 공백과 PARA 표식 하나 추가"),
    "훈7.LMF": ("사다리 진입", "바닥에서 세로 사다리로 올라가 우측 상단 목표 도달"),
    "훈7.5.LMF": ("사다리 상단 이탈", "훈7과 상단 한 칸 배치가 달라 이탈 경계 비교"),
    "훈8.LMF": ("수직 도달 기준선", "스프링 없는 높은 발판 배치"),
    "훈8.5.LMF": ("스프링 수직 상승", "동일 계열 배치에 스프링 한 개를 추가한 비교군"),
    "훈9.LMF": ("오른쪽 발사대/PARA", "오른쪽 방향 발사대 그림과 PARA 표식 세 개"),
    "훈10.LMF": ("왼쪽 발사대/PARA", "훈9의 반대 방향 발사대와 역방향 진행"),
    "훈11.LMF": ("JUMP 표식 계단", "JUMP 그림 타일로 만든 상승 계단과 용암 접경"),
    "훈12.LMF": ("물 후보 타일", "물보라 그림 타일 150개로 채운 통로"),
    "훈13.LMF": ("선풍기/낙하산 상승", "세로 선풍기 열을 따라 상단 목표 도달"),
    "훈14.LMF": ("자석 54 단일 배치", "시작점 오른쪽의 단일 자석과 지형 상호작용"),
    "훈15.LMF": ("자석 55 단일 배치", "훈14 반대 방향 계열 자석과 역방향 진행"),
    "훈16.LMF": ("자석 53 수직 배치", "발판 위 자석과 높은 목표의 수직 상호작용"),
    "훈17.LMF": ("자석 52 다중 배치", "2×2 자석 묶음의 합성 효과"),
    "훈18.LMF": ("오르막 얼음 경사", "오르막 얼음 한 개와 왼쪽 목표"),
    "훈19.LMF": ("내리막 얼음 경사", "내리막 얼음 한 개와 오른쪽 목표"),
    "훈20.LMF": ("아래 화살표 타일", "시작점 바로 아래의 녹색 아래 화살표 그림 타일"),
}


def main() -> None:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    rows = []
    for item in inventory["maps"]:
        lesson, evidence = LESSONS[item["name"]]
        rows.append({
            "map": item["name"],
            "size": [item["width"], item["height"]],
            "lesson_candidate": lesson,
            "layout_evidence": evidence,
            "static_structure": "PASS" if item["valid"] and not item["duplicate_coordinate_records"] else "CHECK",
            "native_runtime": (
                "PASS: native-built LMF exactly matched captured hun1 for seven 12-tick action traces"
                if item["name"] == "훈1.LMF"
                else "PASS smoke: original x86 map builder plus one world-chain tick; normal-Client parity unverified"
            ),
        })
    result = {
        "scope": "candidate curriculum from LMF layout and editor sprite identity",
        "warning": "No lesson behavior or clearability is certified until the original Client/native oracle runs the exact file.",
        "maps": rows,
        "runtime_plan": [
            "bind an exact LMF SHA-256 to a Client-loaded capture",
            "record deterministic NOOP and lesson-specific input fixtures",
            "compare normal Client and offline oracle state tick by tick",
            "only then expose reset/step/reward for training",
        ],
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 훈1~20 훈련 커리큘럼 후보",
        "",
        "> 맵 배치와 에디터 스프라이트로 분류한 후보이다. 실제 Client 실행·기믹 동작·클리어 검증 결과가 아니다.",
        "",
        "| 맵 | 수업 후보 | 배치 근거 | 정적 구조 | native 검증 |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        native = "7개 상태열 exact" if row["map"] == "훈1.LMF" else "빌드+1 tick PASS"
        lines.append(
            f"| {row['map']} | {row['lesson_candidate']} | {row['layout_evidence']} | "
            f"{row['static_structure']} | {native} |"
        )
    lines += [
        "",
        "## 실행 연결 순서",
        "",
        "1. 실제 Client에 로드된 맵과 LMF SHA-256을 직접 묶는다.",
        "2. 각 맵에서 NOOP와 해당 기믹 입력 시퀀스를 같은 시작 상태로 기록한다.",
        "3. 정상 Client와 offline oracle의 상태를 tick 단위로 비교한다.",
        "4. 일치한 맵부터 `reset / step / observation / reward` 훈련 API에 넣는다.",
        "",
        "훈1은 Client 원본 함수 `0x41e510`으로 LMF 58개 레코드를 재생성한 뒤 캡처본과 object/grid가 "
        "바이트 단위로 같았고, 7개 12-tick 입력 상태열도 전부 같았다. 나머지 22개 맵은 같은 원본 builder로 "
        "생성하고 world-chain 1 tick을 통과했지만 정상 Client와의 tick parity는 아직 별도 검증이 필요하다.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"maps": len(rows), "json": str(OUT_JSON), "markdown": str(OUT_MD)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
