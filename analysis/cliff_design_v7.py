"""Rock-contour-only cliff preview; no straight bridge/platform rows."""

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


def ranges(item: dict) -> tuple[int, int]:
    h = item["width"] // 2
    return item["x"] - h, item["x"] + h - (1 if item["width"] % 2 == 0 else 0)


def carve(grid: list[list[int]], x: int, y: int) -> None:
    if 3 <= x <= 27 and 0 <= y < H - 1:
        grid[y][x] = 0


def carve_flight_lanes(grid: list[list[int]]) -> None:
    peak_up = 8.25
    for i, (a, b) in enumerate(zip(ROUTE, ROUTE[1:])):
        dy, dx = a["y"] - b["y"], b["x"] - a["x"]
        extra = max(0.0, peak_up - dy / 2.0)
        rx, ry = [3, 4, 3, 5, 4][i % 5], [3, 4, 5, 3, 4][i % 5]
        for n in range(5, 96):
            t = n / 100.0
            x = a["x"] + dx * t
            y = (a["y"] - 1) - dy * t - 4 * extra * t * (1 - t)
            for yy in range(max(0, int(math.floor(y - ry))), min(H - 2, int(math.ceil(y + 0.5))) + 1):
                for xx in range(max(3, int(math.floor(x - rx))), min(27, int(math.ceil(x + rx))) + 1):
                    carve(grid, xx, yy)


def add_irregular_landing(grid: list[list[int]], item: dict, index: int) -> None:
    """Add a short, jagged rock knuckle instead of a straight platform."""
    if item["side"] == "floor":
        for x in range(2, 29):
            grid[item["y"]][x] = 8
        return
    x1, x2 = ranges(item)
    # A different depth and skew for each knuckle prevents a repeated ledge
    # silhouette.  The landing edge is at most four cells and is backed by
    # irregular rock, not a free horizontal beam.
    depth = 2 + index % 3
    skew = -1 if index % 2 else 1
    if item["side"] == "left":
        start = max(3, x1 - depth)
        for d in range(0, 5):
            yy = item["y"] + d
            if yy >= H - 1:
                continue
            end = min(x2 + 1, x2 + 1 + max(0, 2 - d // 2))
            for xx in range(start + max(0, d + skew) // 2, end + 1):
                grid[yy][xx] = 8
        # A diagonal face at the exposed end; tile 16 is the known walkable
        # triangle block and is shown as a slope in the preview.
        if x2 + 1 < 28:
            grid[item["y"] - 1][x2 + 1] = 16
    else:
        end = min(27, x2 + depth)
        for d in range(0, 5):
            yy = item["y"] + d
            if yy >= H - 1:
                continue
            start = max(x1 - 1, x1 - 1 - max(0, 2 - d // 2))
            for xx in range(start, end - max(0, d - skew) // 2 + 1):
                grid[yy][xx] = 8
        if x1 - 1 >= 3:
            grid[item["y"] - 1][x1 - 1] = 16


def build_grid() -> list[list[int]]:
    grid = [[8 for _ in range(W)] for _ in range(H)]
    carve_flight_lanes(grid)

    # Unequal chambers: lower bowl, middle chimney, right cavern, left hook,
    # and an upper dome.  These are all empty space carved from the one mass.
    chambers = [
        (145, 160, lambda y: 6 + (y - 145) // 5, lambda y: 26 - max(0, (160 - y) // 6)),
        (118, 142, lambda y: 9 + max(0, (130 - y) // 4), lambda y: 22 + max(0, (y - 130) // 5)),
        (91, 117, lambda y: 5 + max(0, (105 - y) // 3), lambda y: 27 - max(0, (y - 104) // 4)),
        (63, 90, lambda y: 8 + max(0, (78 - y) // 3), lambda y: 23 + max(0, (y - 78) // 4)),
        (35, 62, lambda y: 5 + max(0, (48 - y) // 4), lambda y: 25 - max(0, (y - 48) // 5)),
        (8, 34, lambda y: 10 + max(0, (21 - y) // 3), lambda y: 26),
    ]
    for y1, y2, left_fn, right_fn in chambers:
        for y in range(y1, y2 + 1):
            for x in range(max(3, left_fn(y)), min(27, right_fn(y)) + 1):
                carve(grid, x, y)

    for i, item in enumerate(ROUTE):
        add_irregular_landing(grid, item, i)

    # The knuckles above are decorative rock.  Re-open the measured flight
    # lanes through any overlap they created, then restore only the short
    # exposed edge of each landing.  This is what prevents a wall bulge from
    # secretly becoming an impossible ceiling.
    carve_flight_lanes(grid)
    for item in ROUTE:
        y = item["y"]
        x1, x2 = ranges(item)
        if item["side"] == "floor":
            for x in range(2, 29):
                grid[y][x] = 8
        elif item["side"] == "left":
            # Only the tooth at the end is walkable; the rest of the row is
            # empty.  This removes the visual language of a platform/bridge.
            tooth = 1 + (ROUTE.index(item) % 2)
            for x in range(max(3, x2 - tooth + 1), x2 + 1):
                grid[y][x] = 8
        else:
            tooth = 1 + (ROUTE.index(item) % 2)
            for x in range(x1, min(27, x1 + tooth - 1) + 1):
                grid[y][x] = 8

    # Replace every route's remaining flat top with one walkable triangular
    # rock face.  The route is therefore represented by terrain contours and
    # slope tile 16, never by a one-line platform of square blocks.
    for item in ROUTE[1:]:
        y = item["y"]
        x1, x2 = ranges(item)
        for x in range(3, 28):
            if item["side"] == "left" and x > x2:
                grid[y][x] = 0
            elif item["side"] == "right" and x < x1:
                grid[y][x] = 0
        grid[y][x2 if item["side"] == "left" else x1] = 16

    # Restore only the outer shell.  No route row is filled across the cavity.
    for y in range(H):
        for x in (0, 1, 2, 28, 29, 30):
            grid[y][x] = 8
    for x in range(2, 29):
        grid[H - 1][x] = 8
    return grid


def audit(grid: list[list[int]]) -> dict:
    cells = {(x, y): value for y, row in enumerate(grid) for x, value in enumerate(row) if value}
    lmf = {"width": W, "height": H, "cells": cells}
    params = dict(DEFAULT_PARAMS)
    solid = solid_grid(lmf, params)
    surfaces = extract_surfaces(lmf, solid, params)
    selected = []
    for item in ROUTE:
        x1, x2 = ranges(item)
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
            "surface_count": len(surfaces), "selected_surfaces": [s.__dict__ if s else None for s in selected]}


def render(grid: list[list[int]], path: Path) -> None:
    scale, margin = 12, 80
    image = Image.new("RGB", (W * scale + margin * 2, H * scale + 70), "#101318")
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            if value:
                color = "#9b6b3e" if value == 8 else "#caa05e"
                draw.rectangle((margin + x * scale, 35 + y * scale,
                                margin + (x + 1) * scale - 1, 35 + (y + 1) * scale - 1), fill=color)
                if value == 16:
                    draw.line((margin + x * scale, 35 + (y + 1) * scale,
                               margin + (x + 1) * scale, 35 + y * scale), fill="#2d2117", width=2)
    for item in ROUTE:
        cx, cy = margin + item["x"] * scale + 6, 35 + item["y"] * scale + 6
        draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill="#f3d35b")
        draw.text((cx + 5, cy - 8), item["name"], fill="#ffffff")
    draw.text((margin, 8), "암벽 신설안 v7 · 암반 윤곽 등반 · 일자형 발판/다리 없음", fill="#ffffff")
    image.save(path)


def main() -> None:
    grid = build_grid()
    result = {"name": "암벽 신설안 v7 암반윤곽형", "status": "preview_only", "width": W, "height": H,
              "route": ROUTE, "audit": audit(grid),
              "tile_cells": [[x, y, value] for y, row in enumerate(grid) for x, value in enumerate(row) if value],
              "design_note": "No free-standing one-line platforms or bridge rows; route surfaces come from irregular wall knuckles and slope tile 16."}
    json_path = OUT / "암벽_신설안_v7_암반윤곽형_미리보기.json"
    png_path = OUT / "암벽_신설안_v7_암반윤곽형_미리보기.png"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    render(grid, png_path)
    print(json.dumps({"json": str(json_path), "preview": str(png_path), "audit": result["audit"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
