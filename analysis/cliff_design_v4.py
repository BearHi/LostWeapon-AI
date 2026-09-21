"""Preview a more geological cliff: chambers and overhangs first, route second."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from cliff_validator import DEFAULT_PARAMS, best_trajectory, build_graph, directed_paths, extract_surfaces, solid_grid

W, H = 31, 180
OUT = Path(__file__).parent

# The route intentionally has same-side climbs, short rests, wide shelves,
# overhang turns, and only a few cross-cavity transfers.  It is not an
# alternating left/right stair pattern.
ROUTE = [
    {"name": "S", "x": 15, "y": 177, "width": 6},
    {"name": "A", "x": 23, "y": 171, "width": 2},
    {"name": "B", "x": 14, "y": 163, "width": 3},
    {"name": "C", "x": 21, "y": 158, "width": 4},
    {"name": "D", "x": 12, "y": 150, "width": 2},
    {"name": "E", "x": 19, "y": 144, "width": 3},
    {"name": "F", "x": 26, "y": 136, "width": 2},
    {"name": "G", "x": 16, "y": 129, "width": 3},
    {"name": "H", "x": 7, "y": 123, "width": 2},
    {"name": "I", "x": 16, "y": 115, "width": 4},
    {"name": "J", "x": 24, "y": 108, "width": 2},
    {"name": "K", "x": 14, "y": 102, "width": 4},
    {"name": "L", "x": 6, "y": 94, "width": 2},
    {"name": "M", "x": 15, "y": 87, "width": 5},
    {"name": "N", "x": 24, "y": 81, "width": 2},
    {"name": "O", "x": 17, "y": 73, "width": 3},
    {"name": "P", "x": 8, "y": 66, "width": 1},
    {"name": "Q", "x": 16, "y": 60, "width": 5},
    {"name": "R", "x": 24, "y": 52, "width": 2},
    {"name": "T", "x": 14, "y": 47, "width": 4},
    {"name": "U", "x": 22, "y": 39, "width": 3},
    # This landing intentionally absorbs the small rock lip at its right;
    # leaving it as a separate two-cell shelf creates a graph shortcut.
    {"name": "V", "x": 15, "y": 33, "width": 5},
    {"name": "W", "x": 25, "y": 25, "width": 4},
    {"name": "X", "x": 16, "y": 18, "width": 2},
    {"name": "G", "x": 24, "y": 11, "width": 4},
]


def add(grid: list[list[int]], x: int, y: int) -> None:
    if 0 <= x < W and 0 <= y < H:
        grid[y][x] = 8


def box(grid: list[list[int]], x1: int, x2: int, y1: int, y2: int) -> None:
    for y in range(min(y1, y2), max(y1, y2) + 1):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            add(grid, x, y)


def wedge(grid: list[list[int]], side: str, x1: int, x2: int, y1: int, y2: int) -> None:
    for y in range(y1, y2 + 1):
        inset = min(y - y1, y2 - y)
        if side == "left":
            for x in range(x1, max(x1, x2 - inset) + 1):
                add(grid, x, y)
        else:
            for x in range(min(x2, x1 + inset), x2 + 1):
                add(grid, x, y)


def platform(grid: list[list[int]], item: dict) -> None:
    half = item["width"] // 2
    x1 = item["x"] - half
    x2 = item["x"] + half - (1 if item["width"] % 2 == 0 else 0)
    for x in range(x1, x2 + 1):
        add(grid, x, item["y"])
    # A short rock lip makes it attached to a wall without drawing a full
    # horizontal step across the cavity.
    # Central shelves are deliberately freestanding ledges in the cavity;
    # extending them toward a wall makes a large underside and can turn the
    # next jump into an invisible head-bump.  Only edge shelves get a short
    # supporting lip.
    if item["x"] < 10:
        for x in range(max(3, x1 - 3), x1):
            add(grid, x, item["y"])
    elif item["x"] > 22:
        for x in range(x2 + 1, min(28, x2 + 4)):
            add(grid, x, item["y"])


def carve_flight_lanes(grid: list[list[int]]) -> None:
    peak_up = 8.25
    for a, b in zip(ROUTE, ROUTE[1:]):
        dy = a["y"] - b["y"]
        dx = b["x"] - a["x"]
        extra = max(0.0, peak_up - dy / 2.0)
        for n in range(8, 93):
            t = n / 100.0
            x = a["x"] + dx * t
            y = (a["y"] - 1) - dy * t - 4 * extra * t * (1 - t)
            for yy in range(max(0, int(math.floor(y - 2.2))), min(H - 2, int(math.ceil(y + 0.7))) + 1):
                for xx in range(max(3, int(math.floor(x - 1.1))), min(27, int(math.ceil(x + 1.1))) + 1):
                    grid[yy][xx] = 0


def build_grid() -> list[list[int]]:
    grid = [[0 for _ in range(W)] for _ in range(H)]
    # One continuous outer rock shell.
    for y in range(3, H):
        for x in (0, 1, 2, 28, 29, 30):
            add(grid, x, y)
    box(grid, 2, 28, H - 1, H - 1)

    # Five different geological sections.  These are deliberately not copies
    # of one another: the inner contour changes by chamber, hook, chimney,
    # and overhang instead of repeating a shelf every N rows.
    wedge(grid, "right", 20, 27, 160, 176)
    wedge(grid, "left", 3, 12, 145, 161)
    box(grid, 23, 27, 132, 143)
    wedge(grid, "right", 18, 27, 118, 137)
    wedge(grid, "left", 3, 11, 101, 120)
    box(grid, 4, 8, 92, 108)
    wedge(grid, "right", 21, 27, 72, 94)
    wedge(grid, "left", 3, 10, 53, 76)
    box(grid, 22, 27, 39, 55)
    wedge(grid, "left", 5, 14, 21, 42)
    wedge(grid, "right", 19, 27, 8, 28)

    # Distinctive overhangs and notches; each has a different contour.
    box(grid, 15, 22, 136, 139)
    wedge(grid, "left", 3, 16, 126, 132)
    box(grid, 14, 19, 96, 99)
    wedge(grid, "right", 16, 27, 83, 88)
    box(grid, 8, 15, 57, 60)
    wedge(grid, "left", 3, 12, 44, 50)
    box(grid, 17, 24, 30, 33)

    for item in ROUTE:
        platform(grid, item)
    carve_flight_lanes(grid)
    for item in ROUTE:
        platform(grid, item)
    return grid


def audit(grid: list[list[int]]) -> dict:
    cells = {(x, y): 8 for y, row in enumerate(grid) for x, value in enumerate(row) if value}
    lmf = {"width": W, "height": H, "cells": cells}
    params = dict(DEFAULT_PARAMS)
    solid = solid_grid(lmf, params)
    surfaces = extract_surfaces(lmf, solid, params)
    selected = []
    for item in ROUTE:
        half = item["width"] // 2
        x1 = item["x"] - half
        x2 = item["x"] + half - (1 if item["width"] % 2 == 0 else 0)
        same = [s for s in surfaces if s.y == item["y"]]
        selected.append(max(same, key=lambda s: max(0, min(s.x2, x2) - max(s.x1, x1) + 1), default=None))
    links = []
    for a, b in zip(selected, selected[1:]):
        tr = best_trajectory(a, b, solid, params) if a and b else None
        links.append({"from": a.index if a else None, "to": b.index if b else None,
                      "ok": bool(tr and tr[2]), "action": tr[0] if tr else None,
                      "dx": round(tr[1], 2) if tr else None,
                      "dy": a.y - b.y if a and b else None})
    edges = build_graph(surfaces, solid, params)
    graph = directed_paths(surfaces, edges, ROUTE[0]["y"], min(s.y for s in surfaces), ROUTE[0]["x"])
    route_ids = {s.index for s in selected if s}
    return {"links": links, "all_links_clear": all(x["ok"] for x in links),
            "strict_graph_path_count": len(graph["paths"]),
            "strict_graph_shortcut_count": graph["shortcut_count"],
            "selected_surfaces": [s.__dict__ if s else None for s in selected],
            "surface_count": len(surfaces), "unintended_surface_count": len([s for s in surfaces if s.index not in route_ids])}


def render(grid: list[list[int]], path: Path) -> None:
    scale, margin = 12, 80
    image = Image.new("RGB", (W * scale + margin * 2, H * scale + 70), "#101318")
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            if value:
                draw.rectangle((margin + x * scale, 35 + y * scale,
                                margin + (x + 1) * scale - 1, 35 + (y + 1) * scale - 1),
                               fill="#8d6038")
    for i, item in enumerate(ROUTE):
        cx, cy = margin + item["x"] * scale + 6, 35 + item["y"] * scale + 6
        draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill="#f3d35b")
        draw.text((cx + 5, cy - 8), item["name"], fill="#ffffff")
    draw.text((margin, 8), "암벽 신설안 v4 · 암반 구역형 · 노란 점=검증 등반선", fill="#ffffff")
    image.save(path)


def main() -> None:
    grid = build_grid()
    result = {"name": "암벽 신설안 v4 암반구역형", "status": "preview_only", "width": W, "height": H,
              "route": ROUTE, "audit": audit(grid),
              "solid_cells": [[x, y] for y, row in enumerate(grid) for x, value in enumerate(row) if value],
              "design_note": "No LMF export until the preview and strict route audit are accepted."}
    json_path = OUT / "암벽_신설안_v4_암반구역형_미리보기.json"
    png_path = OUT / "암벽_신설안_v4_암반구역형_미리보기.png"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    render(grid, png_path)
    print(json.dumps({"json": str(json_path), "preview": str(png_path), "audit": result["audit"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
