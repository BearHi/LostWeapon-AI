"""Generate a preview-only vertical cliff design from a single intended route.

This file deliberately stops before LMF export.  The route is represented by
landings attached to a continuous rock mass; the validator must approve it
before an LMF is written.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


W, H = 31, 180
OUT = Path(__file__).parent

# Bottom-to-top route.  Y decreases upward.  The irregular spacing is
# intentional: these are ledges in one cavity, not a staircase of equal steps.
ROUTE = [
    {"name": "S", "x": 15, "y": 177, "width": 5, "side": "both"},
    {"name": "A", "x": 23, "y": 169, "width": 3, "side": "right"},
    {"name": "B", "x": 14, "y": 162, "width": 2, "side": "left"},
    {"name": "C", "x": 21, "y": 156, "width": 4, "side": "right"},
    {"name": "D", "x": 12, "y": 148, "width": 2, "side": "left"},
    {"name": "E", "x": 19, "y": 143, "width": 3, "side": "right"},
    {"name": "F", "x": 25, "y": 135, "width": 2, "side": "right"},
    {"name": "G", "x": 16, "y": 128, "width": 3, "side": "both"},
    {"name": "H", "x": 7, "y": 122, "width": 2, "side": "left"},
    {"name": "I", "x": 15, "y": 114, "width": 4, "side": "both"},
    {"name": "J", "x": 24, "y": 107, "width": 2, "side": "right"},
    {"name": "K", "x": 17, "y": 102, "width": 2, "side": "both"},
    {"name": "L", "x": 8, "y": 94, "width": 3, "side": "left"},
    {"name": "M", "x": 16, "y": 87, "width": 2, "side": "both"},
    {"name": "N", "x": 25, "y": 81, "width": 3, "side": "right"},
    {"name": "O", "x": 18, "y": 73, "width": 2, "side": "both"},
    {"name": "P", "x": 9, "y": 68, "width": 3, "side": "left"},
    {"name": "Q", "x": 15, "y": 60, "width": 2, "side": "both"},
    {"name": "R", "x": 24, "y": 53, "width": 3, "side": "right"},
    {"name": "T", "x": 13, "y": 45, "width": 2, "side": "left"},
    {"name": "U", "x": 21, "y": 39, "width": 4, "side": "right"},
    {"name": "V", "x": 16, "y": 31, "width": 2, "side": "both"},
    {"name": "W", "x": 25, "y": 24, "width": 3, "side": "right"},
    {"name": "G", "x": 17, "y": 16, "width": 4, "side": "both"},
]


def add(grid: list[list[int]], x: int, y: int) -> None:
    if 0 <= x < W and 0 <= y < H:
        grid[y][x] = 8


def add_platform(grid: list[list[int]], item: dict) -> None:
    y = item["y"]
    half = item["width"] // 2
    x1, x2 = item["x"] - half, item["x"] + half
    if item["width"] % 2 == 0:
        x2 -= 1
    side = item["side"]
    # Only the short landing itself is exposed.  A previous draft filled
    # every cell from the wall to the landing and visually became a staircase.
    # The support below is deliberately short; the large wall bellies carry
    # the rest of the mass.
    for x in range(x1, x2 + 1):
        add(grid, x, y)
    if side == "left":
        for x in range(max(3, x1 - 4), x1):
            add(grid, x, y)
    elif side == "right":
        for x in range(x2 + 1, min(28, x2 + 5)):
            add(grid, x, y)


def carve_route_corridors(grid: list[list[int]]) -> None:
    """Keep the intended flight lanes open through the decorative rock.

    This is the important difference from placing platforms by eye: the
    corridor is generated from the same conservative eight-cell motion model
    used by the validator, then the remaining rock is allowed to form the
    silhouette.  Endpoint overlap is left intact for landing/support.
    """
    import math

    peak_up = 8.25
    for a, b in zip(ROUTE, ROUTE[1:]):
        dy = a["y"] - b["y"]
        dx = b["x"] - a["x"]
        extra = max(0.0, peak_up - dy / 2.0)
        for n in range(8, 93):
            t = n / 100.0
            x = a["x"] + dx * t
            y = (a["y"] - 1) - dy * t - 4 * extra * t * (1 - t)
            left = max(3, int(math.floor(x - 1.1)))
            right = min(27, int(math.ceil(x + 1.1)))
            top = max(0, int(math.floor(y - 2.2)))
            bottom = min(H - 2, int(math.ceil(y + 0.7)))
            for yy in range(top, bottom + 1):
                for xx in range(left, right + 1):
                    grid[yy][xx] = 0


def build_grid() -> list[list[int]]:
    grid = [[0 for _ in range(W)] for _ in range(H)]
    # Continuous outer rock.  The central cavity is carved by leaving columns
    # 3..27 empty except for the route's attached ledges.
    for y in range(3, H):
        for x in (0, 1, 2, 28, 29, 30):
            add(grid, x, y)
    for x in range(2, 29):
        add(grid, x, H - 1)

    # A few large, uneven wall bellies give the cavity a cliff-like silhouette.
    # They stop short of the intended ledges and never create a full-width
    # intermediate staircase.
    bellies = [
        (3, 13, 154, 165), (17, 25, 145, 154), (4, 11, 126, 139),
        (20, 27, 116, 128), (3, 9, 98, 110), (21, 27, 84, 96),
        (4, 12, 70, 82), (20, 27, 56, 66), (3, 10, 40, 52),
        # Keep this upper-right mass vertical.  A tapered inner edge here
        # creates several one-cell ledges between V and W and becomes a
        # hidden shortcut.
        (24, 27, 25, 36), (5, 12, 10, 22),
    ]
    for x1, x2, y1, y2 in bellies:
        for y in range(y1, y2 + 1):
            # taper the inner edge by one cell at each end
            inset = min(y - y1, y2 - y)
            if x1 < 10:
                for x in range(x1, min(x2, x2 - inset) + 1):
                    add(grid, x, y)
            else:
                for x in range(max(x1, x1 + inset), x2 + 1):
                    add(grid, x, y)

    for item in ROUTE:
        add_platform(grid, item)
    carve_route_corridors(grid)
    # Restore the actual landing tiles after carving the flight lanes.
    for item in ROUTE:
        add_platform(grid, item)

    # Top cap leaves a visible rest area above the goal, but no route continues.
    for x in range(18, 29):
        add(grid, x, 5)
    return grid


def write_preview(grid: list[list[int]], path: Path) -> None:
    scale = 12
    margin = 80
    image = Image.new("RGB", (W * scale + margin * 2, H * scale + 70), "#101318")
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(grid):
        for x, value in enumerate(row):
            if value:
                color = "#6c4a2f" if x in (0, 1, 2, 28, 29, 30) else "#9a6b3e"
                draw.rectangle((margin + x * scale, 35 + y * scale,
                                margin + (x + 1) * scale - 1, 35 + (y + 1) * scale - 1), fill=color)
    for i, item in enumerate(ROUTE):
        cx = margin + item["x"] * scale + scale // 2
        cy = 35 + item["y"] * scale + scale // 2
        draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill="#f3d35b")
        draw.text((cx + 5, cy - 8), item["name"], fill="#ffffff")
        if i:
            prev = ROUTE[i - 1]
            px = margin + prev["x"] * scale + scale // 2
            py = 35 + prev["y"] * scale + scale // 2
            draw.line((px, py, cx, cy), fill="#66d9ef", width=2)
    draw.text((margin, 8), "암벽 신설안 v3 · 노란 점=의도한 단일 등반선 · 파랑선=검증 대상 연결", fill="#ffffff")
    image.save(path)


def audit_route(grid: list[list[int]]) -> dict:
    """Audit intended links against exposed surfaces without exporting LMF."""
    import sys

    sys.path.insert(0, str(OUT))
    from cliff_validator import (DEFAULT_PARAMS, best_trajectory, build_graph,
                                 directed_paths, extract_surfaces, solid_grid)

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
        same_y = [s for s in surfaces if s.y == item["y"]]
        chosen = max(same_y, key=lambda s: max(0, min(s.x2, x2) - max(s.x1, x1) + 1), default=None)
        selected.append(chosen)
    links = []
    for a, b in zip(selected, selected[1:]):
        result = best_trajectory(a, b, solid, params) if a and b else None
        links.append({
            "from": a.index if a else None,
            "to": b.index if b else None,
            "ok": bool(result and result[2]),
            "action": result[0] if result else None,
            "dx": round(result[1], 2) if result else None,
            "dy": a.y - b.y if a and b else None,
        })
    route_ids = {s.index for s in selected if s}
    extras = [s.index for s in surfaces if s.index not in route_ids and s.y < H - 2]
    edges = build_graph(surfaces, solid, params)
    graph = directed_paths(surfaces, edges, ROUTE[0]["y"], min(s.y for s in surfaces), ROUTE[0]["x"])
    return {
        "selected_surfaces": [s.__dict__ if s else None for s in selected],
        "links": links,
        "all_links_clear": all(item["ok"] for item in links),
        "unintended_surface_count": len(extras),
        "unintended_surface_ids": extras,
        "strict_graph_path_count": len(graph["paths"]),
        "strict_graph_shortcut_count": graph["shortcut_count"],
        "strict_graph_path": graph["paths"][0] if graph["paths"] else [],
        "note": "Unintended surfaces are reported for review; only route links are used for this preview audit.",
    }


def main() -> None:
    grid = build_grid()
    candidate = {
        "name": "암벽 신설안 v3 단일굴곡선",
        "status": "preview_only",
        "width": W,
        "height": H,
        "rock_tile": 8,
        "start": {"x": 15, "y": H - 3, "tile": 100},
        "goal": {"x": 17, "y": 16, "decorative": True},
        "route": ROUTE,
        "audit": audit_route(grid),
        "solid_cells": [[x, y] for y, row in enumerate(grid) for x, value in enumerate(row) if value],
        "design_note": "LMF export is intentionally withheld until the calibrated reachability check passes.",
    }
    json_path = OUT / "암벽_신설안_v3_단일굴곡선_미리보기.json"
    png_path = OUT / "암벽_신설안_v3_단일굴곡선_미리보기.png"
    json_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
    write_preview(grid, png_path)
    print(json.dumps({"json": str(json_path), "preview": str(png_path), "route_nodes": len(ROUTE)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
