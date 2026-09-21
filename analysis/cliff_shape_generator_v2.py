"""Build a deliberately non-symmetric cliff candidate.

Unlike the first generator, this version uses a few large chambers and an
inner rock spine. The landings are attached to those masses, so the result is
not a row of floating stairs. It is still only a JSON/minimap candidate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cliff_validator import DEFAULT_PARAMS, build_graph, directed_paths, extract_surfaces, solid_grid

W, H = 31, 240


def put(grid: list[list[int]], x: int, y: int, tile: int = 8) -> None:
    if 0 <= x < W and 0 <= y < H:
        grid[y][x] = tile


def rectangle(grid: list[list[int]], x1: int, x2: int, y1: int, y2: int) -> None:
    for y in range(min(y1, y2), max(y1, y2) + 1):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            put(grid, x, y)


def wedge(grid: list[list[int]], side: str, top: int, bottom: int, inner_top: int, inner_bottom: int) -> None:
    """Add a tapered attached mass, with its top edge acting as a ledge."""
    for y in range(top, bottom + 1):
        t = (y - top) / max(1, bottom - top)
        inner = round(inner_top + (inner_bottom - inner_top) * t)
        if side == "left":
            for x in range(0, inner + 1):
                put(grid, x, y)
        else:
            for x in range(inner, W):
                put(grid, x, y)


def build_grid() -> list[list[int]]:
    grid = [[0 for _ in range(W)] for _ in range(H)]

    # Unequal outer walls create a large chamber that shifts from side to side.
    for y in range(4, H - 4):
        left = 3
        right = 27
        if 28 <= y <= 58:
            right = 21                 # deep right-side belly
        elif 66 <= y <= 92:
            left = 7                   # left wall closes in
        elif 112 <= y <= 145:
            right = 24
        elif 151 <= y <= 184:
            left = 8                   # long left hook
        elif 194 <= y <= 222:
            right = 19                 # lower right chamber
        for x in range(0, left + 1):
            put(grid, x, y)
        for x in range(right, W):
            put(grid, x, y)

    # A broken inner spine replaces the old map's empty central shaft.
    rectangle(grid, 12, 17, 69, 92)
    rectangle(grid, 14, 20, 118, 132)
    rectangle(grid, 9, 14, 159, 177)
    rectangle(grid, 17, 22, 200, 210)

    # Large hooked masses. Their top edges are landings, but their bodies are
    # continuous with a wall or the inner spine.
    wedge(grid, "right", 213, 231, 18, 22)
    wedge(grid, "right", 224, 234, 18, 22)
    # The respawn marker sits two cells above the one-cell floor. This first
    # attached ledge is the only deliberate onboarding move.
    rectangle(grid, 16, 20, 228, 230)
    wedge(grid, "left", 187, 207, 8, 12)
    wedge(grid, "right", 160, 181, 18, 23)
    wedge(grid, "left", 132, 153, 4, 9)
    wedge(grid, "right", 104, 124, 21, 26)
    wedge(grid, "left", 78, 98, 6, 11)
    wedge(grid, "right", 43, 63, 19, 24)
    wedge(grid, "left", 17, 36, 4, 10)

    # A few transverse shelves connect the spine to a wall. These are sparse
    # structural turns, not evenly spaced step blocks.
    rectangle(grid, 10, 16, 178, 181)
    rectangle(grid, 15, 21, 171, 174)
    rectangle(grid, 15, 22, 133, 136)
    rectangle(grid, 8, 13, 125, 128)
    rectangle(grid, 18, 23, 108, 110)
    rectangle(grid, 13, 18, 101, 103)
    rectangle(grid, 8, 14, 94, 97)
    rectangle(grid, 8, 13, 77, 79)
    rectangle(grid, 16, 23, 63, 66)
    rectangle(grid, 18, 24, 56, 59)
    rectangle(grid, 17, 20, 50, 52)
    rectangle(grid, 10, 16, 35, 38)
    rectangle(grid, 15, 21, 30, 32)
    rectangle(grid, 17, 23, 22, 24)
    rectangle(grid, 10, 15, 16, 18)
    rectangle(grid, 18, 23, 8, 10)

    # Start floor and offset top cap.
    # Keep the two cells above the floor empty so the respawn marker is not
    # embedded in rock.
    rectangle(grid, 2, 28, H - 1, H - 1)
    rectangle(grid, 20, 28, 4, 15)
    return grid


def analyze(grid: list[list[int]]) -> tuple[dict, list[dict]]:
    cells = {(x, y): 8 for y, row in enumerate(grid) for x, v in enumerate(row) if v == 8}
    cells[(15, H - 3)] = 100
    lmf = {"width": W, "height": H, "cells": cells}
    params = dict(DEFAULT_PARAMS)
    params["minimum_surface_width"] = 1
    collision = solid_grid(lmf, params)
    surfaces = extract_surfaces(lmf, collision, params)
    edges = build_graph(surfaces, collision, params)
    graph = directed_paths(surfaces, edges, H - 3, min((s.y for s in surfaces), default=0))
    route = {"surfaces": len(surfaces), "edges": len(edges), "path": graph["paths"][0] if graph["paths"] else [], "shortcuts": graph["shortcut_count"]}
    runs = [{"x1": s.x1, "x2": s.x2, "y": s.y} for s in surfaces]
    return route, runs


def main() -> None:
    grid = build_grid()
    route, surfaces = analyze(grid)
    output = {
        "name": "암벽 수학형 v2 - 비대칭 공동",
        "status": "route_candidate" if route["path"] else "rejected_no_route",
        "width": W,
        "height": H,
        "rock_tile": 8,
        "start": {"x": 15, "y": H - 3, "tile": 100},
        "goal": {"x": 24, "y": 8, "decorative": True},
        "route": route,
        "surface_runs": surfaces,
        "solid_cells": [[x, y] for y, row in enumerate(grid) for x, v in enumerate(row) if v == 8],
    }
    path = Path(__file__).with_name("암벽_수학형_v2_비대칭공동_후보.json")
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"path": str(path), "status": output["status"], "route": route}, ensure_ascii=False))


if __name__ == "__main__":
    main()
