"""Inventory the supplied 훈1~20 LMF fixtures without modifying them.

This is binary/structural inspection only. Tile behavior and clearability still
require the real Client or the native oracle.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "훈련용맵"
OUT_JSON = ROOT / "analysis" / "training_maps_inventory.json"
OUT_MD = ROOT / "analysis" / "training_maps_inventory.md"

IDENTITIES = {
    3: ("사다리", "ladder"),
    4: ("스프링", "spring"),
    5: ("오른쪽 발사대 그림", "launcher_candidate"),
    6: ("왼쪽 발사대 그림", "launcher_candidate"),
    7: ("밝은 암반", "solid"),
    8: ("갈색 암반", "solid"),
    16: ("상자 그림", "unknown"),
    19: ("사각 얼음", "ice"),
    22: ("오르막 벽돌 경사", "slope"),
    27: ("오르막 삼각 얼음", "ice_slope"),
    32: ("내리막 벽돌 경사", "slope"),
    37: ("내리막 삼각 얼음", "ice_slope"),
    39: ("빈 스프라이트", "unknown"),
    49: ("용암", "instant_reset"),
    51: ("선풍기", "fan"),
    52: ("자석 34", "magnet"),
    53: ("자석 35", "magnet"),
    54: ("자석 36", "magnet"),
    55: ("자석 37", "magnet"),
    82: ("물 모양 장식", "decoration"),
    86: ("가시", "damage"),
    100: ("리스폰 표시 1", "respawn"),
    101: ("리스폰 표시 2", "respawn"),
    102: ("리스폰 표시 3", "respawn"),
    103: ("리스폰 표시 4", "respawn"),
    104: ("리스폰 표시 5", "respawn"),
    105: ("리스폰 표시 6", "respawn"),
    106: ("리스폰 표시 7", "respawn"),
    107: ("리스폰 표시 8", "respawn"),
    108: ("리스폰 표시 9", "respawn"),
    109: ("리스폰 표시 10", "respawn"),
    118: ("용암발사", "projectile_hazard"),
    119: ("들락가시", "periodic_hazard"),
    122: ("대전용 기지", "competitive_base"),
    123: ("물보라 그림 타일", "water_candidate"),
    124: ("아래 화살표 그림 타일", "down_marker_candidate"),
    125: ("파란 JUMP 그림 타일", "jump_marker_candidate"),
    136: ("빨간 JUMP 그림 타일", "jump_marker_candidate"),
    138: ("PARA 그림 타일", "parachute_marker_candidate"),
    140: ("해골 깃발", "goal_candidate"),
}
RESPAWNS = set(range(100, 110))
STRUCTURAL = {7, 8, 22, 32} | RESPAWNS | {140}


def map_key(path: Path) -> float:
    match = re.fullmatch(r"훈(\d+(?:\.\d+)?)\.LMF", path.name, re.I)
    return float(match.group(1)) if match else 9999.0


def bbox(points: list[tuple[int, int]]) -> list[int] | None:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def inspect(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 32:
        return {"name": path.name, "valid": False, "error": "shorter than 32-byte header"}
    width, height = struct.unpack_from("<HH", data, 16)
    count = struct.unpack_from("<I", data, 21)[0]
    expected = 32 + count * 8
    if expected > len(data):
        return {
            "name": path.name,
            "valid": False,
            "width": width,
            "height": height,
            "records_declared": count,
            "bytes": len(data),
            "expected_bytes": expected,
            "error": "record count exceeds file length",
        }
    records = [struct.unpack_from("<Ihh", data, 32 + i * 8) for i in range(count)]
    by_id: dict[int, list[tuple[int, int]]] = defaultdict(list)
    cells = Counter()
    out_of_bounds = []
    for tile_id, x, y in records:
        by_id[tile_id].append((x, y))
        cells[(x, y)] += 1
        if not (0 <= x < width and 0 <= y < height):
            out_of_bounds.append([tile_id, x, y])
    ids = []
    for tile_id in sorted(by_id):
        label, kind = IDENTITIES.get(tile_id, ("미확인", "unknown"))
        ids.append({
            "id": tile_id,
            "label": label,
            "kind": kind,
            "count": len(by_id[tile_id]),
            "bbox": bbox(by_id[tile_id]),
            "positions": [list(p) for p in by_id[tile_id]] if len(by_id[tile_id]) <= 24 else None,
        })
    return {
        "name": path.name,
        "path": str(path.resolve()),
        "valid": expected == len(data) and not out_of_bounds,
        "width": width,
        "height": height,
        "records": count,
        "bytes": len(data),
        "expected_bytes": expected,
        "trailing_bytes": len(data) - expected,
        "sha256": hashlib.sha256(data).hexdigest(),
        "duplicate_coordinate_records": sum(v - 1 for v in cells.values() if v > 1),
        "out_of_bounds": out_of_bounds,
        "spawn_markers": [
            {"id": tile_id, "position": list(point)}
            for tile_id in sorted(RESPAWNS)
            for point in by_id.get(tile_id, [])
        ],
        "ids": ids,
        "gimmicks": [item for item in ids if item["id"] not in STRUCTURAL],
        "unknown_ids": [item["id"] for item in ids if item["kind"] == "unknown"],
    }


def main() -> None:
    paths = sorted(MAP_DIR.glob("훈*.LMF"), key=map_key)
    maps = [inspect(path) for path in paths]
    usage: dict[int, list[str]] = defaultdict(list)
    for item in maps:
        for tile in item.get("ids", []):
            usage[tile["id"]].append(item["name"])
    result = {
        "scope": "static LMF binary/structure inspection; no game execution or clearability claim",
        "map_count": len(maps),
        "maps": maps,
        "tile_usage": {
            str(tile_id): {
                "label": IDENTITIES.get(tile_id, ("미확인", "unknown"))[0],
                "maps": names,
            }
            for tile_id, names in sorted(usage.items())
        },
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 훈련용맵 정적 인벤토리",
        "",
        "> LMF 파일 구조만 검사했다. 실제 기믹 동작, 물리 parity, 학습 성공, 클리어 가능 판정이 아니다.",
        "",
        "| 맵 | 크기 | 레코드 | 리스폰 | 기믹/특수 ID | 미확인 ID | 구조 |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for item in maps:
        gimmicks = ", ".join(
            f"{g['label']}({g['id']})×{g['count']}" for g in item.get("gimmicks", [])
        ) or "없음"
        spawns = ", ".join(
            f"{spawn['id'] - 99}:({spawn['position'][0]},{spawn['position'][1]})"
            for spawn in item.get("spawn_markers", [])
        ) or "없음"
        unknown = ", ".join(map(str, item.get("unknown_ids", []))) or "없음"
        status = "PASS" if item.get("valid") and item.get("duplicate_coordinate_records") == 0 else "확인 필요"
        lines.append(
            f"| {item['name']} | {item.get('width','?')}×{item.get('height','?')} | "
            f"{item.get('records','?')} | {spawns} | {gimmicks} | {unknown} | {status} |"
        )
    lines += ["", "## 타일 ID 사용 맵", ""]
    for tile_id, info in result["tile_usage"].items():
        lines.append(f"- `{tile_id}` {info['label']}: {', '.join(info['maps'])}")
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"maps": len(maps), "json": str(OUT_JSON), "markdown": str(OUT_MD)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
