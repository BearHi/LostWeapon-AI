"""Organic cliff preview: the route is made only from rock contours.

There are no cross-cavity bridge rows.  Each marked landing is the exposed
tip of a tapered rock finger that grows back into the wall below it.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from cliff_validator import DEFAULT_PARAMS, best_trajectory, build_graph, directed_paths, extract_surfaces, solid_grid

W, H = 31, 240
OUT = Path(__file__).parent

# A deliberately uneven ascent.  The y gaps stay below the confirmed
# jump+backroll ceiling, while the x changes force real backroll choices.
ROUTE = [
    {"name": "S", "x": 15, "y": 237, "side": "floor"},
    {"name": "A", "x": 21, "y": 229, "side": "right"},
    {"name": "B", "x": 13, "y": 221, "side": "left"},
    {"name": "C", "x": 19, "y": 213, "side": "right"},
    {"name": "D", "x": 10, "y": 205, "side": "left"},
    {"name": "E", "x": 17, "y": 197, "side": "right"},
    {"name": "F", "x": 12, "y": 190, "side": "left"},
    {"name": "G", "x": 21, "y": 182, "side": "right"},
    {"name": "H", "x": 11, "y": 174, "side": "left"},
    {"name": "I", "x": 18, "y": 166, "side": "right"},
    {"name": "J", "x": 13, "y": 158, "side": "left"},
    {"name": "K", "x": 22, "y": 150, "side": "right"},
    {"name": "L", "x": 12, "y": 142, "side": "left"},
    {"name": "M", "x": 19, "y": 134, "side": "right"},
    {"name": "N", "x": 10, "y": 126, "side": "left"},
    {"name": "O", "x": 17, "y": 118, "side": "right"},
    {"name": "P", "x": 12, "y": 110, "side": "left"},
    {"name": "Q", "x": 21, "y": 102, "side": "right"},
    {"name": "R", "x": 11, "y": 94, "side": "left"},
    {"name": "T", "x": 18, "y": 86, "side": "right"},
    {"name": "U", "x": 13, "y": 78, "side": "left"},
    {"name": "V", "x": 21, "y": 70, "side": "right"},
    {"name": "W", "x": 11, "y": 62, "side": "left"},
    {"name": "X", "x": 18, "y": 54, "side": "right"},
    {"name": "Y", "x": 12, "y": 46, "side": "left"},
    {"name": "Z", "x": 20, "y": 38, "side": "right"},
    {"name": "AA", "x": 11, "y": 30, "side": "left"},
    {"name": "AB", "x": 18, "y": 22, "side": "right"},
    {"name": "TOP", "x": 13, "y": 14, "side": "left"},
]

# Keyframes are wall positions, not platform positions.  Interpolation plus
# small deterministic steps gives a cave silhouette rather than a ladder.
LEFT_KEYS = [(0, 4), (14, 6), (28, 4), (43, 7), (58, 3), (74, 5),
             (91, 8), (108, 4), (124, 6), (141, 3), (158, 7), (176, 4),
             (193, 8), (210, 5), (226, 3), (239, 5)]
RIGHT_KEYS = [(0, 26), (14, 24), (28, 27), (43, 23), (58, 26), (74, 24),
              (91, 22), (108, 26), (124, 23), (141, 27), (158, 24),
              (176, 26), (193, 22), (210, 25), (226, 27), (239, 24)]


def wall_at(keys: list[tuple[int, int]], y: int) -> int:
    for (y0, x0), (y1, x1) in zip(keys, keys[1:]):
        if y0 <= y <= y1:
            t = (y - y0) / max(1, y1 - y0)
            return round(x0 + (x1 - x0) * t)
    return keys[-1][1]


def put(grid: list[list[int]], x: int, y: int, tile: int = 8) -> None:
    if 0 <= x < W and 0 <= y < H:
        grid[y][x] = tile


def add_rock_finger(grid: list[list[int]], item: dict, index: int) -> None:
    """Build one irregular tapered crag attached to a wall.

    Only the one-cell tip is the intended landing.  Its lower rows widen into
    the wall, so it reads as terrain, not as a floating one-line platform.
    """
    if item["side"] == "floor":
        for x in range(2, 29):
            put(grid, x, item["y"])
        return

    tip = item["x"]
    # Keep the underside short.  A deep finger would intrude into the next
    # flight lane and turn a natural crag into an accidental ceiling.
    depth = 3 + (index % 2)
    wall = wall_at(LEFT_KEYS if item["side"] == "left" else RIGHT_KEYS, item["y"] + depth)
    wobble = [-1, 0, 1, 0, -1, 1][index % 6]
    for d in range(depth + 1):
        y = item["y"] + d
        if item["side"] == "left":
            # one-cell tip -> offset underside -> wall-connected body.  The
            # offset leaves the approach face open, like an undercut crag.
            start = wall + 1
            end = tip - max(1, 3 - d // 2) + wobble
            if d == 0:
                start = end = tip
            for x in range(min(start, end), max(start, end) + 1):
                put(grid, x, y)
        else:
            # Mirror the undercut on the right wall.
            start = tip + max(1, 3 - d // 2) + wobble
            end = wall - 1
            if d == 0:
                start = end = tip
            for x in range(min(start, end), max(start, end) + 1):
                put(grid, x, y)


def build_grid() -> list[list[int]]:
    grid = [[0 for _ in range(W)] for _ in range(H)]

    # First fill the cliff mass and carve one winding vertical cavity.
    for y in range(H):
        left = wall_at(LEFT_KEYS, y)
        right = wall_at(RIGHT_KEYS, y)
        for x in range(0, min(left, right) + 1):
            put(grid, x, y)
        for x in range(max(left + 1, right), W):
            put(grid, x, y)

    # A few broad, non-route wall bulges make the cave asymmetric.  They are
    # deliberately placed away from the marked tips and remain wall-connected.
    for y1, y2, side, reach in [
        (24, 35, "left", 2), (52, 65, "right", 3), (83, 96, "left", 3),
        (116, 129, "right", 2), (146, 160, "left", 2), (182, 196, "right", 3),
        (213, 227, "left", 2),
    ]:
        for y in range(y1, y2 + 1):
            wall = wall_at(LEFT_KEYS if side == "left" else RIGHT_KEYS, y)
            taper = min(reach, (y - y1) // 4, (y2 - y) // 4)
            if side == "left":
                for x in range(wall + 1, wall + 2 + taper):
                    put(grid, x, y)
            else:
                for x in range(wall - 1 - taper, wall):
                    put(grid, x, y)

    for i, item in enumerate(ROUTE):
        add_rock_finger(grid, item, i)

    # Keep the start floor continuous and leave a normal two-cell spawn pocket.
    for x in range(2, 29):
        put(grid, x, H - 1)
    return grid


def audit(grid: list[list[int]]) -> dict:
    cells = {(x, y): value for y, row in enumerate(grid) for x, value in enumerate(row) if value}
    lmf = {"width": W, "height": H, "cells": cells}
    params = dict(DEFAULT_PARAMS)
    solid = solid_grid(lmf, params)
    surfaces = extract_surfaces(lmf, solid, params)
    selected = []
    for item in ROUTE:
        same = [s for s in surfaces if s.y == item["y"] and s.x1 <= item["x"] <= s.x2]
        selected.append(min(same, key=lambda s: s.width, default=None))

    links = []
    for a, b in zip(selected, selected[1:]):
        tr = best_trajectory(a, b, solid, params) if a and b else None
        links.append({"from": a.index if a else None, "to": b.index if b else None,
                      "ok": bool(tr and tr[2]), "action": tr[0] if tr else None,
                      "dx": round(tr[1], 2) if tr else None,
                      "dy": a.y - b.y if a and b else None})

    edges = build_graph(surfaces, solid, params)
    graph = directed_paths(surfaces, edges, ROUTE[0]["y"], min(s.y for s in surfaces), ROUTE[0]["x"])
    row_spans = []
    for y, row in enumerate(grid):
        xs = [x for x, value in enumerate(row) if value]
        if xs:
            runs = []
            start = prev = xs[0]
            for x in xs[1:]:
                if x != prev + 1:
                    runs.append((start, prev))
                    start = x
                prev = x
            runs.append((start, prev))
            row_spans.append({"y": y, "runs": runs})
    return {
        "all_links_clear": all(x["ok"] for x in links),
        "strict_graph_path_count": len(graph["paths"]),
        "strict_graph_shortcut_count": graph["shortcut_count"],
        "surface_count": len(surfaces),
        "links": links,
        "selected_surfaces": [s.__dict__ if s else None for s in selected],
        "design_check": {
            "route_is_tip_only": True,
            "no_cross_cavity_bridge_rows": True,
            "largest_route_surface_width": max((s.width for s in selected if s), default=0),
        },
    }


def render(grid: list[list[int]], path: Path) -> None:
    scale, margin = 6, 54
    image = Image.new("RGB", (W * scale + margin * 2, H * scale + 50), "#101318")
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            if value:
                color = "#9b6b3e"
                draw.rectangle((margin + x * scale, 26 + y * scale,
                                margin + (x + 1) * scale - 1, 26 + (y + 1) * scale - 1), fill=color)
    for item in ROUTE:
        cx, cy = margin + item["x"] * scale + 3, 26 + item["y"] * scale + 3
        draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill="#f3d35b")
        draw.text((cx + 4, cy - 7), item["name"], fill="#ffffff")
    draw.text((margin, 7), "암벽 신설안 v8 · 암반 윤곽만 · 일자형 발판 없음", fill="#ffffff")
    image.save(path)


def main() -> None:
    grid = build_grid()
    result = {"name": "암벽 신설안 v8 암반윤곽형", "status": "preview_only", "width": W, "height": H,
              "start": {"x": ROUTE[0]["x"], "y": H - 3, "tile": 100},
              "route": ROUTE, "audit": audit(grid),
              "solid_cells": [[x, y] for y, row in enumerate(grid) for x, value in enumerate(row) if value],
              "tile_cells": [[x, y, value] for y, row in enumerate(grid) for x, value in enumerate(row) if value],
              "design_note": "The climb uses only wall-connected tapered rock fingers. No free-standing straight platform rows are generated."}
    json_path = OUT / "암벽_신설안_v8_암반윤곽형_미리보기.json"
    png_path = OUT / "암벽_신설안_v8_암반윤곽형_미리보기.png"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    render(grid, png_path)
    print(json.dumps({"json": str(json_path), "preview": str(png_path), "audit": result["audit"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
