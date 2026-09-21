"""Run coarse action-envelope simulations at several safety margins."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cliff_validator import DEFAULT_PARAMS, build_graph, directed_paths, extract_surfaces, solid_grid


def run(candidate: dict, factor: float) -> dict:
    cells = {(x, y): 8 for x, y in candidate["solid_cells"]}
    cells[(candidate["start"]["x"], candidate["start"]["y"])] = 100
    lmf = {"width": candidate["width"], "height": candidate["height"], "cells": cells}
    params = dict(DEFAULT_PARAMS)
    params["minimum_surface_width"] = 1
    for key in ("jump_backroll_max_up", "jump_backroll_max_horizontal", "parachute_max_up", "parachute_max_horizontal"):
        params[key] *= factor
    grid = solid_grid(lmf, params)
    surfaces = extract_surfaces(lmf, grid, params)
    edges = build_graph(surfaces, grid, params)
    goal_y = min((s.y for s in surfaces), default=0)
    graph = directed_paths(surfaces, edges, candidate["start"]["y"], goal_y)
    chosen = graph["paths"][0] if graph["paths"] else []
    by_pair = {(e["from"], e["to"]): e for e in edges}
    jumps = []
    for a, b in zip(chosen, chosen[1:]):
        edge = by_pair[(a, b)]
        up = params["jump_backroll_max_up"] if edge["action"] == "jump_backroll" else params["parachute_max_up"]
        horizontal = params["jump_backroll_max_horizontal"] if edge["action"] == "jump_backroll" else params["parachute_max_horizontal"]
        ratio = max(edge["dy"] / up, abs(edge["dx"]) / horizontal)
        jumps.append({**edge, "load_ratio": round(ratio, 3), "vertical_slack": round(up - edge["dy"], 2), "horizontal_slack": round(horizontal - abs(edge["dx"]), 2)})
    return {
        "factor": factor,
        "pass": bool(chosen),
        "surface_count": len(surfaces),
        "edge_count": len(edges),
        "alternative_paths": graph["shortcut_count"],
        "path_length": len(jumps),
        "near_limit_jumps": sum(1 for j in jumps if j["load_ratio"] >= 0.9),
        "jumps": jumps,
    }


def main() -> None:
    parser = __import__("argparse").ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    report = {"candidate": str(args.candidate), "simulator": "coarse_action_envelope_v1", "runs": [run(candidate, f) for f in (1.0, 0.95, 0.9, 0.85)]}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
