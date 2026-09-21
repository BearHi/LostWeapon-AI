"""No-bridge cliff preview: every landing is attached to a side rock mass."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import cliff_design_v4 as base

OUT = Path(__file__).parent
W, H = base.W, base.H

# No central/floating platforms.  L/R means the landing is part of that wall;
# long transfers happen through the open cavity and are candidates for the
# parachute, not through a bridge tile.
ROUTE = [
    {"name": "S", "x": 15, "y": 177, "width": 6, "side": "floor"},
    {"name": "A", "x": 23, "y": 171, "width": 2, "side": "right"},
    {"name": "B", "x": 11, "y": 163, "width": 3, "side": "left"},
    {"name": "C", "x": 21, "y": 158, "width": 4, "side": "right"},
    {"name": "D", "x": 8, "y": 150, "width": 2, "side": "left"},
    {"name": "E", "x": 22, "y": 144, "width": 3, "side": "right"},
    {"name": "F", "x": 10, "y": 136, "width": 5, "side": "left"},
    {"name": "G", "x": 24, "y": 129, "width": 2, "side": "right"},
    {"name": "H", "x": 7, "y": 121, "width": 1, "side": "left"},
    {"name": "I", "x": 20, "y": 115, "width": 4, "side": "right"},
    {"name": "J", "x": 8, "y": 107, "width": 2, "side": "left"},
    {"name": "K", "x": 23, "y": 102, "width": 3, "side": "right"},
    {"name": "L", "x": 6, "y": 94, "width": 2, "side": "left"},
    {"name": "M", "x": 22, "y": 87, "width": 5, "side": "right"},
    {"name": "N", "x": 9, "y": 81, "width": 2, "side": "left"},
    {"name": "O", "x": 24, "y": 73, "width": 3, "side": "right"},
    {"name": "P", "x": 7, "y": 66, "width": 1, "side": "left"},
    {"name": "Q", "x": 20, "y": 60, "width": 4, "side": "right"},
    {"name": "R", "x": 8, "y": 52, "width": 2, "side": "left"},
    {"name": "T", "x": 23, "y": 47, "width": 4, "side": "right"},
    {"name": "U", "x": 7, "y": 39, "width": 2, "side": "left"},
    {"name": "V", "x": 21, "y": 33, "width": 5, "side": "right"},
    # Absorb the small erosion lip into this landing so it cannot become a
    # separate upper shortcut.
    {"name": "W", "x": 8, "y": 25, "width": 3, "side": "left"},
    {"name": "X", "x": 24, "y": 18, "width": 3, "side": "right"},
    {"name": "G", "x": 10, "y": 11, "width": 4, "side": "left"},
]


def platform_no_bridge(grid: list[list[int]], item: dict) -> None:
    half = item["width"] // 2
    x1 = item["x"] - half
    x2 = item["x"] + half - (1 if item["width"] % 2 == 0 else 0)
    if item["side"] == "floor":
        for x in range(x1, x2 + 1):
            base.add(grid, x, item["y"])
        return
    if item["side"] == "left":
        # The landing is the inner lip of the left wall, never a free island.
        for x in range(3, x2 + 1):
            base.add(grid, x, item["y"])
    else:
        # The landing is the inner lip of the right wall, never a cross-cavity
        # slab.  x1..27 remains on the right side of the open shaft.
        for x in range(x1, 28):
            base.add(grid, x, item["y"])


def audit(grid: list[list[int]]) -> dict:
    from cliff_validator import DEFAULT_PARAMS, best_trajectory, build_graph, directed_paths, extract_surfaces, solid_grid

    cells = {(x, y): 8 for y, row in enumerate(grid) for x, value in enumerate(row) if value}
    lmf = {"width": W, "height": H, "cells": cells}
    params = dict(DEFAULT_PARAMS)
    solid = solid_grid(lmf, params)
    surfaces = extract_surfaces(lmf, solid, params)
    selected = []
    for item in ROUTE:
        h = item["width"] // 2
        x1, x2 = item["x"] - h, item["x"] + h - (1 if item["width"] % 2 == 0 else 0)
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
    return {"links": links, "all_links_clear": all(x["ok"] for x in links),
            "strict_graph_path_count": len(graph["paths"]), "strict_graph_shortcut_count": graph["shortcut_count"],
            "selected_surfaces": [s.__dict__ if s else None for s in selected],
            "surface_count": len(surfaces), "unintended_surface_count": len([s for s in surfaces if s not in selected])}


def main() -> None:
    # Reuse only the irregular geological masses from v4.  Replace its
    # platform and route globals so no v4 bridge can be inherited.
    base.ROUTE = ROUTE
    base.platform = platform_no_bridge
    grid = base.build_grid()
    result = {"name": "암벽 신설안 v5 무교량 암반형", "status": "preview_only", "width": W, "height": H,
              "route": ROUTE, "audit": audit(grid),
              "solid_cells": [[x, y] for y, row in enumerate(grid) for x, value in enumerate(row) if value],
              "design_note": "Every route landing is attached to the left or right wall; no bridge tiles are exported."}
    json_path = OUT / "암벽_신설안_v5_무교량암반형_미리보기.json"
    png_path = OUT / "암벽_신설안_v5_무교량암반형_미리보기.png"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    base.render(grid, png_path)
    print(json.dumps({"json": str(json_path), "preview": str(png_path), "audit": result["audit"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
