"""Extract the pre-goal gimmick layout from 학습용/암벽11.LMF."""

from __future__ import annotations

import json
import struct
from collections import defaultdict, deque
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parents[1]
LMF = ROOT / "학습용" / "암벽11.LMF"
OUT = ROOT / "analysis"

NAMES = {
    3: "ladder",
    8: "solid_rock",
    19: "ice",
    27: "ice_triangle_editor_1B",
    37: "ice_triangle_editor_25",
    49: "lava",
    51: "fan",
    52: "magnet_editor_34",
    53: "magnet_editor_35",
    54: "magnet_editor_36",
    55: "magnet_editor_37",
    82: "water_appearance_decoration_user_corrected_lab04",
    86: "spike",
    118: "lava_launcher",
    119: "moving_spike",
    122: "competitive_base_not_disappearing_user_corrected_lab04",
    100: "respawn",
}


def read_lmf(path: Path) -> tuple[int, int, list[tuple[int, int, int]]]:
    data = path.read_bytes()
    width, height = struct.unpack_from("<HH", data, 16)
    count = struct.unpack_from("<I", data, 21)[0]
    records = [struct.unpack_from("<Ihh", data, 32 + i * 8) for i in range(count)]
    return width, height, records


def components(cells: set[tuple[int, int]]) -> list[dict]:
    result = []
    unseen = set(cells)
    while unseen:
        start = unseen.pop()
        q = deque([start])
        comp = {start}
        while q:
            x, y = q.popleft()
            for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nxt in unseen:
                    unseen.remove(nxt)
                    comp.add(nxt)
                    q.append(nxt)
        xs = [x for x, _ in comp]
        ys = [y for _, y in comp]
        result.append({"count": len(comp), "x1": min(xs), "x2": max(xs), "y1": min(ys), "y2": max(ys)})
    return sorted(result, key=lambda item: (item["y1"], item["x1"]))


def render(width: int, height: int, records: list[tuple[int, int, int]], path: Path) -> None:
    # Crop just before the fan/spike finish section. Higher y is lower in the map.
    y_top, y_bottom = 40, 220
    scale = 7
    colors = {
        8: (145, 99, 55), 19: (91, 210, 228), 27: (235, 120, 240),
        37: (245, 190, 55), 49: (245, 75, 45), 51: (75, 165, 245),
        82: (155, 90, 230), 86: (245, 55, 55), 118: (255, 155, 45),
        119: (255, 80, 190), 122: (245, 230, 70), 100: (80, 235, 135),
        3: (165, 165, 165),
        52: (235, 195, 70), 53: (235, 195, 70),
        54: (235, 195, 70), 55: (235, 195, 70),
    }
    image = Image.new("RGB", (width * scale + 140, (y_bottom - y_top) * scale + 48), (18, 21, 27))
    draw = ImageDraw.Draw(image)
    for tile_id, x, y in records:
        if y_top <= y <= y_bottom:
            color = colors.get(tile_id, (220, 220, 220))
            px, py = x * scale, 32 + (y - y_top) * scale
            draw.rectangle((px, py, px + scale - 1, py + scale - 1), fill=color)
    draw.text((4, 8), "암벽11 기믹 배치 · y=40~220 · 위쪽이 골인 방향", fill=(240, 240, 240))
    labels = [(19, "평면 얼음"), (27, "삼각 얼음 1B"), (37, "삼각 얼음 25"), (51, "선풍기"),
              (82, "물 모양 장식"), (86, "가시"), (118, "용암발사"), (119, "들락가시"), (49, "용암"),
              (54, "자석 34~37")]
    lx = width * scale + 8
    for i, (tile_id, label) in enumerate(labels):
        yy = 34 + i * 18
        draw.rectangle((lx, yy, lx + 10, yy + 10), fill=colors[tile_id])
        draw.text((lx + 15, yy - 2), f"{tile_id}: {label}", fill=(240, 240, 240))
    image.save(path)


def main() -> None:
    width, height, records = read_lmf(LMF)
    grouped = defaultdict(set)
    for tile_id, x, y in records:
        grouped[tile_id].add((x, y))
    report = {
        "file": str(LMF), "width": width, "height": height,
        "goal_excluded_above_y": 51,
        "numbering": "Record IDs are decimal; editor labels are hexadecimal. LMF 37 is editor 25, not magnet 37 (LMF 55).",
        "magnet_record_count": sum(tile_id in (52, 53, 54, 55) for tile_id, _, _ in records),
        "tiles": {
            str(tile_id): {"name": NAMES.get(tile_id, "unknown"), "count": len(cells),
                           "components": components(cells)}
            for tile_id, cells in sorted(grouped.items())
        },
    }
    json_path = OUT / "암벽11_골인전_기믹분석.json"
    png_path = OUT / "암벽11_골인전_기믹배치_미리보기.png"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    render(width, height, records, png_path)
    print(json.dumps({"report": str(json_path), "preview": str(png_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
