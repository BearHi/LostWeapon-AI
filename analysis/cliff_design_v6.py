"""Single-cavity cliff preview: fill rock first, then carve one route cavity."""

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

# Every non-floor landing is explicitly a left or right wall lip.  There are
# no central bridge tiles; the rest of the map starts as solid rock.
ROUTE = [
    {"name": "S", "x": 15, "y": 177, "width": 6, "side": "floor"},
    {"name": "A", "x": 24, "y": 171, "width": 2, "side": "right"},
    {"name": "B", "x": 11, "y": 163, "width": 2, "side": "left"},
    {"name": "C", "x": 20, "y": 158, "width": 3, "side": "right"},
    {"name": "D", "x": 10, "y": 150, "width": 2, "side": "left"},
    {"name": "E", "x": 22, "y": 143, "width": 4, "side": "right"},
    {"name": "F", "x": 12, "y": 135, "width": 1, "side": "left"},
    {"name": "G", "x": 20, "y": 128, "width": 2, "side": "right"},
    {"name": "H", "x": 11, "y": 120, "width": 3, "side": "left"},
    {"name": "I", "x": 23, "y": 113, "width": 1, "side": "right"},
    {"name": "J", "x": 10, "y": 106, "width": 4, "side": "left"},
    {"name": "K", "x": 20, "y": 100, "width": 2, "side": "right"},
    {"name": "L", "x": 11, "y": 92, "width": 2, "side": "left"},
    {"name": "M", "x": 23, "y": 85, "width": 3, "side": "right"},
    {"name": "N", "x": 12, "y": 78, "width": 1, "side": "left"},
    {"name": "O", "x": 21, "y": 70, "width": 4, "side": "right"},
    {"name": "P", "x": 10, "y": 63, "width": 2, "side": "left"},
    {"name": "Q", "x": 22, "y": 56, "width": 2, "side": "right"},
    {"name": "R", "x": 11, "y": 49, "width": 5, "side": "left"},
    {"name": "T", "x": 20, "y": 42, "width": 1, "side": "right"},
    {"name": "U", "x": 12, "y": 35, "width": 3, "side": "left"},
    {"name": "V", "x": 22, "y": 28, "width": 4, "side": "right"},
    {"name": "W", "x": 10, "y": 21, "width": 3, "side": "left"},
    {"name": "X", "x": 21, "y": 14, "width": 3, "side": "right"},
]


def platform_range(item: dict) -> tuple[int, int]:
    h = item["width"] // 2
    return item["x"] - h, item["x"] + h - (1 if item["width"] % 2 == 0 else 0)


def carve(grid: list[list[int]], x: int, y: int) -> None:
    if 3 <= x <= 27 and 0 <= y < H - 1:
        grid[y][x] = 0


def build_grid() -> list[list[int]]:
    grid = [[8 for _ in range(W)] for _ in range(H)]
    peak_up = 8.25
    # The cavity is generated from the flight arcs, not from a list of
    # floating platforms.  Varying the carve radius makes different chambers
    # and chimneys while retaining one connected void.
    for i, (a, b) in enumerate(zip(ROUTE, ROUTE[1:])):
        dy, dx = a["y"] - b["y"], b["x"] - a["x"]
        extra = max(0.0, peak_up - dy / 2.0)
        radius_x = [2, 3, 2, 4, 3][i % 5]
        radius_y = [2, 3, 4, 2, 3][i % 5]
        for n in range(5, 96):
            t = n / 100.0
            x = a["x"] + dx * t
            y = (a["y"] - 1) - dy * t - 4 * extra * t * (1 - t)
            for yy in range(max(0, int(math.floor(y - radius_y))), min(H - 2, int(math.ceil(y + 0.5))) + 1):
                for xx in range(max(3, int(math.floor(x - radius_x))), min(27, int(math.ceil(x + radius_x))) + 1):
                    carve(grid, xx, yy)

    # Broaden the connected void into deliberately different chambers.  These
    # are not extra platforms: they are empty space carved out of the same
    # rock mass.  Each band has a different silhouette so the map does not
    # read as one repeated sawtooth.
    chambers = [
        # lower entry: broad bowl with a high right shoulder
        (145, 160, lambda y: 6 + (y - 145) // 5, lambda y: 26 - max(0, (160 - y) // 6)),
        # lower-middle: left chimney with a deep right overhang
        (118, 142, lambda y: 9 + max(0, (130 - y) // 4), lambda y: 22 + max(0, (y - 130) // 5)),
        # middle: wide cavern, intentionally asymmetric
        (91, 117, lambda y: 5 + max(0, (105 - y) // 3), lambda y: 27 - max(0, (y - 104) // 4)),
        # upper-middle: narrow diagonal erosion slot
        (63, 90, lambda y: 8 + max(0, (78 - y) // 3), lambda y: 23 + max(0, (y - 78) // 4)),
        # upper: left hook opening into a domed top chamber
        (35, 62, lambda y: 5 + max(0, (48 - y) // 4), lambda y: 25 - max(0, (y - 48) // 5)),
        (8, 34, lambda y: 10 + max(0, (21 - y) // 3), lambda y: 26),
    ]
    for y1, y2, left_fn, right_fn in chambers:
        for y in range(y1, y2 + 1):
            for x in range(max(3, left_fn(y)), min(27, right_fn(y)) + 1):
                carve(grid, x, y)

    # Pull the wall contour inward around each intended landing.  This keeps
    # the ledge short and embedded in the wall instead of producing a beam
    # from the outer shell to the player.  The amount of inset changes with
    # the local section, so the visible notches are not periodic.
    for i, item in enumerate(ROUTE[1:]):
        y = item["y"]
        x1, x2 = platform_range(item)
        inset = 2 + (i % 3)
        for offset in range(-3, 4):
            yy = y + offset
            if not 1 <= yy < H - 1:
                continue
            if item["side"] == "left":
                edge = max(3, x1 - inset + (abs(offset) % 2))
                for xx in range(3, edge + 1):
                    carve(grid, xx, yy)
            else:
                edge = min(27, x2 + inset - (abs(offset) % 2))
                for xx in range(edge, 28):
                    carve(grid, xx, yy)

    # Carve small irregular chambers above each landing.  They are connected
    # to the flight lane and leave no separate bridge or side route.
    for i, item in enumerate(ROUTE[1:]):
        x1, x2 = platform_range(item)
        radius = 2 + (i % 3)
        for yy in range(max(0, item["y"] - radius - 2), item["y"]):
            spread = max(1, radius - abs(yy - (item["y"] - radius // 2)) // 2)
            for xx in range(max(3, x1 - spread), min(27, x2 + spread) + 1):
                carve(grid, xx, yy)

    # Restore only the wall lip at each landing.  The cavity row itself stays
    # empty everywhere else, so no horizontal bridge can appear.
    for item in ROUTE:
        y = item["y"]
        x1, x2 = platform_range(item)
        for x in range(3, 28):
            grid[y][x] = 0
        if item["side"] == "floor":
            for x in range(2, 29):
                grid[y][x] = 8
        elif item["side"] == "left":
            start = max(3, x1 - (2 + (ROUTE.index(item) % 3)))
            for x in range(start, x2 + 1):
                grid[y][x] = 8
        else:
            end = min(27, x2 + (2 + (ROUTE.index(item) % 3)))
            for x in range(x1, end + 1):
                grid[y][x] = 8
    # Keep the shell continuous and leave a small top rest above X.
    for y in range(H):
        for x in (0, 1, 2, 28, 29, 30):
            grid[y][x] = 8
    for x in range(2, 29):
        grid[H - 1][x] = 8
    return grid


def audit(grid: list[list[int]]) -> dict:
    cells = {(x, y): 8 for y, row in enumerate(grid) for x, value in enumerate(row) if value}
    lmf = {"width": W, "height": H, "cells": cells}
    params = dict(DEFAULT_PARAMS)
    solid = solid_grid(lmf, params)
    surfaces = extract_surfaces(lmf, solid, params)
    selected = []
    for item in ROUTE:
        x1, x2 = platform_range(item)
        same = [s for s in surfaces if s.y == item["y"]]
        selected.append(max(same, key=lambda s: max(0, min(s.x2, x2) - max(s.x1, x1) + 1), default=None))
    links = []
    for a, b in zip(selected, selected[1:]):
        tr = best_trajectory(a, b, solid, params) if a and b else None
        links.append({"from": a.index if a else None, "to": b.index if b else None,
                      "ok": bool(tr and tr[2]), "action": tr[0] if tr else None,
                      "dx": round(tr[1], 2) if tr else None, "dy": a.y - b.y if a and b else None})
    edges = build_graph(surfaces, solid, params)
    graph = directed_paths(surfaces, edges, ROUTE[0]["y"], min(s.y for s in surfaces), ROUTE[0]["x"])
    return {"links": links, "all_links_clear": all(x["ok"] for x in links),
            "strict_graph_path_count": len(graph["paths"]), "strict_graph_shortcut_count": graph["shortcut_count"],
            "surface_count": len(surfaces), "unintended_surface_count": len([s for s in surfaces if s not in selected]),
            "selected_surfaces": [s.__dict__ if s else None for s in selected]}


def render(grid: list[list[int]], path: Path) -> None:
    scale, margin = 12, 80
    image = Image.new("RGB", (W * scale + margin * 2, H * scale + 70), "#101318")
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            if value:
                draw.rectangle((margin + x * scale, 35 + y * scale,
                                margin + (x + 1) * scale - 1, 35 + (y + 1) * scale - 1), fill="#8d6038")
    for item in ROUTE:
        cx, cy = margin + item["x"] * scale + 6, 35 + item["y"] * scale + 6
        draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill="#f3d35b")
        draw.text((cx + 5, cy - 8), item["name"], fill="#ffffff")
    draw.text((margin, 8), "암벽 신설안 v6 · 단일 침식공동 · 다리 타일 없음", fill="#ffffff")
    image.save(path)


def main() -> None:
    grid = build_grid()
    result = {"name": "암벽 신설안 v6 단일침식공동형", "status": "preview_only", "width": W, "height": H,
              "route": ROUTE, "audit": audit(grid),
              "solid_cells": [[x, y] for y, row in enumerate(grid) for x, value in enumerate(row) if value],
              "design_note": "The map is filled with rock first; only one connected cavity is carved. No bridge tiles."}
    json_path = OUT / "암벽_신설안_v6_단일침식공동형_미리보기.json"
    png_path = OUT / "암벽_신설안_v6_단일침식공동형_미리보기.png"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    render(grid, png_path)
    print(json.dumps({"json": str(json_path), "preview": str(png_path), "audit": result["audit"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
