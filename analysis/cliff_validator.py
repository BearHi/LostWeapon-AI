"""LMF cliff-map validator.

Legacy heuristic, NOT a conservative playability proof. A live regression on
the user-cleared 암벽수정1.LMF finds no path even from its starting floor.
Its arc exceeds its configured apex, collision endpoints are skipped, and
body dimensions/ranges are uncalibrated. Preserved for comparison with old
designs; use collision_kernel for isolated rectangle geometry tests instead.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Surface:
    index: int
    x1: int
    x2: int
    y: int

    @property
    def center(self) -> float:
        return (self.x1 + self.x2 + 1) / 2.0

    @property
    def width(self) -> int:
        return self.x2 - self.x1 + 1


DEFAULT_PARAMS = {
    "solid_ids": [7, 8],
    "slope_ids": [16],
    "minimum_walkable_clearance": 2,
    # A one-cell landing is allowed. The two-cell rule applies to empty
    # vertical passages, not to the width of a landing surface.
    "minimum_surface_width": 1,
    # User-confirmed probe: jump + airborne backroll reaches a little over
    # eight cells.  Integer-cell landings are therefore capped at eight in
    # the conservative design pass.
    "jump_backroll_max_up": 8.25,
    # Horizontal range is not yet an isolated measurement.  This is a
    # deliberately conservative provisional limit, kept separate from the
    # measured vertical cap.
    "jump_backroll_max_horizontal": 9.0,
    "parachute_max_up": 8.25,
    "parachute_max_horizontal": 16.0,
    "body_width": 0.8,
    "body_height": 1.8,
    "clearance_margin": 0.25,
    "enforce_corridor_clearance": True,
}


def read_lmf(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError("LMF header is shorter than 32 bytes")
    width = struct.unpack_from("<H", data, 16)[0]
    height = struct.unpack_from("<H", data, 18)[0]
    count = struct.unpack_from("<I", data, 21)[0]
    if 32 + count * 8 > len(data):
        raise ValueError(f"record count exceeds file length: {count}")
    cells = {}
    records = []
    for i in range(count):
        offset = 32 + i * 8
        tile_id, x, y = struct.unpack_from("<Ihh", data, offset)
        cells[(x, y)] = tile_id
        records.append({"id": tile_id, "x": x, "y": y})
    return {"header": data[:32], "width": width, "height": height, "records": records, "cells": cells}


def solid_grid(lmf: dict, params: dict) -> list[list[bool]]:
    solids = set(params["solid_ids"]) | set(params.get("slope_ids", []))
    grid = [[False for _ in range(lmf["width"])] for _ in range(lmf["height"])]
    # LMF permits multiple records at one coordinate.  A gimmick can be
    # layered over a solid tile, so reading only cells[(x, y)] would lose the
    # collision layer when the last record happens to be non-solid.
    if "records" in lmf:
        tile_records = ((record["x"], record["y"], record["id"]) for record in lmf["records"])
    else:
        tile_records = ((x, y, tile_id) for (x, y), tile_id in lmf["cells"].items())
    for x, y, tile_id in tile_records:
        if 0 <= x < lmf["width"] and 0 <= y < lmf["height"] and tile_id in solids:
            grid[y][x] = True
    return grid


def _column_has_clearance(grid: list[list[bool]], y: int, x: int, params: dict) -> bool:
    need = int(math.ceil(params["minimum_walkable_clearance"]))
    for dy in range(1, need + 1):
        yy = y - dy
        if yy < 0 or grid[yy][x]:
            return False
    return True


def extract_surfaces(lmf: dict, grid: list[list[bool]], params: dict) -> list[Surface]:
    width, height = lmf["width"], lmf["height"]
    min_width = params["minimum_surface_width"]
    surfaces = []
    for y in range(1, height):
        top_cells = [x for x in range(width) if grid[y][x] and not grid[y - 1][x]]
        start = None
        for x in range(width + 1):
            active = x in top_cells
            if active and start is None:
                start = x
            if (not active or x == width) and start is not None:
                end = x - 1
                # A long top edge may contain a low ceiling at one end. Split
                # it at those columns instead of rejecting the whole edge.
                clear_start = None
                for xx in range(start, end + 2):
                    clear = xx <= end and _column_has_clearance(grid, y, xx, params)
                    if clear and clear_start is None:
                        clear_start = xx
                    if (not clear or xx == end + 1) and clear_start is not None:
                        clear_end = xx - 1
                        if clear_end - clear_start + 1 >= min_width:
                            surfaces.append(Surface(len(surfaces), clear_start, clear_end, y))
                        clear_start = None
                start = None
    return surfaces


def free_clearance(grid: list[list[bool]], surface: Surface, params: dict) -> bool:
    """Reject a surface when the standing pocket is visibly less than 2 cells high."""
    need = int(math.ceil(params["minimum_walkable_clearance"]))
    for x in range(surface.x1, surface.x2 + 1):
        for dy in range(1, need + 1):
            y = surface.y - dy
            if y < 0 or grid[y][x]:
                return False
    return True


def corridor_clear(grid: list[list[bool]], a: Surface, b: Surface, params: dict, action: str) -> bool:
    """Coarse swept-body check along a jump/glide arc.

    The real engine will be calibrated later. This only rejects obvious rock
    collisions and keeps the first map drafts conservative.
    """
    if b.y >= a.y:
        return False
    dy = a.y - b.y
    dx = b.center - a.center
    # A jump has a fixed upward impulse.  The old draft incorrectly made the
    # apex proportional to the target height, which could both reject valid
    # high landings and accept impossible low ones.  Construct the arc so its
    # peak rise is the calibrated maximum, independent of target height.
    peak_up = (params["jump_backroll_max_up"] if action == "jump_backroll"
               else params["parachute_max_up"])
    extra = max(0.0, peak_up - dy / 2.0)
    samples = max(12, int(abs(dx) * 4 + dy * 3))
    margin = params["clearance_margin"]
    for i in range(samples + 1):
        t = i / samples
        x = a.center + dx * t
        y = (a.y - 1) - dy * t - 4 * extra * t * (1 - t)
        left = max(0, int(math.floor(x - params["body_width"] / 2 - margin)))
        right = min(len(grid[0]) - 1, int(math.ceil(x + params["body_width"] / 2 + margin)))
        top = max(0, int(math.floor(y - params["body_height"] - margin)))
        bottom = min(len(grid) - 1, int(math.ceil(y + margin)))
        # The character is standing on the source surface at launch and
        # overlaps the destination surface while settling.  Those endpoint
        # contacts are intentional; only the open flight corridor is tested.
        if t < 0.08 or t > 0.92:
            continue
        for yy in range(top, bottom + 1):
            for xx in range(left, right + 1):
                if grid[yy][xx]:
                    return False
    return True


def edge_type(a: Surface, b: Surface, params: dict) -> str | None:
    if b.y >= a.y:
        return None
    dy = a.y - b.y
    # A player can choose where to launch and where to land on a platform.
    # Center-to-center distance was the source of a major false negative in
    # the earlier draft, so use the closest valid points on the two surfaces.
    dx = min(abs(xb - xa) for xa in (a.x1, a.x2) for xb in (b.x1, b.x2))
    if dy <= params["jump_backroll_max_up"] and dx <= params["jump_backroll_max_horizontal"]:
        return "jump_backroll"
    if dy <= params["parachute_max_up"] and dx <= params["parachute_max_horizontal"]:
        return "parachute"
    return None


def best_trajectory(a: Surface, b: Surface, grid: list[list[bool]], params: dict) -> tuple[str, float, bool] | None:
    """Find one legal takeoff/landing pair and test its open flight lane."""
    dy = a.y - b.y
    if dy <= 0:
        return None
    candidates = []
    # Wide surfaces are not forced to launch only from their two corners.  A
    # player can walk to an interior cell before jumping; include the center
    # as well so a broad start floor does not produce a false long-distance
    # requirement.
    launch_points = sorted({a.x1, a.x2, round(a.center)})
    landing_points = sorted({b.x1, b.x2, round(b.center)})
    for xa in launch_points:
        for xb in landing_points:
            dx = float(xb - xa)
            action = edge_type(Surface(a.index, xa, xa, a.y), Surface(b.index, xb, xb, b.y), params)
            if action:
                candidates.append((abs(dx), action, dx, xa, xb))
    for _, action, dx, xa, xb in sorted(candidates):
        launch = Surface(a.index, int(xa), int(xa), a.y)
        land = Surface(b.index, int(xb), int(xb), b.y)
        if corridor_clear(grid, launch, land, params, action):
            return action, dx, True
    if candidates:
        _, action, dx, _, _ = sorted(candidates)[0]
        return action, dx, False
    return None


def build_graph(surfaces: list[Surface], grid: list[list[bool]], params: dict) -> list[dict]:
    edges = []
    for a in surfaces:
        if not free_clearance(grid, a, params):
            continue
        for b in surfaces:
            if a.index == b.index or not free_clearance(grid, b, params):
                continue
            trajectory = best_trajectory(a, b, grid, params)
            if trajectory:
                action, dx, geometry_clear = trajectory
                if params.get("enforce_corridor_clearance", False) and not geometry_clear:
                    continue
                edges.append({"from": a.index, "to": b.index, "action": action, "dx": round(dx,2), "dy": a.y-b.y, "geometry_clear": geometry_clear})
    return edges


def directed_paths(surfaces: list[Surface], edges: list[dict], start_y: int, goal_y: int, start_x: int | None = None) -> dict:
    if not surfaces:
        return {"start_candidates": [], "goal_candidates": [], "paths": [], "shortcut_count": 0}
    if start_x is None:
        start_candidates = [s.index for s in surfaces if s.y >= start_y - 8]
    else:
        start_candidates = [s.index for s in surfaces
                            if start_y - 2 <= s.y <= start_y + 2
                            and s.x1 <= start_x <= s.x2]
    goal_candidates = [s.index for s in surfaces if s.y <= goal_y + 8]
    outgoing = {s.index: [] for s in surfaces}
    for e in edges:
        outgoing.setdefault(e["from"], []).append(e)
    paths = []
    for start in start_candidates:
        queue=deque([(start,[start])])
        seen={(start,)}
        while queue and len(paths)<64:
            node,path=queue.popleft()
            if node in goal_candidates and len(path)>1:
                paths.append(path)
                continue
            for e in outgoing.get(node,[]):
                if e["to"] in path or len(path)>=32: continue
                nxt=path+[e["to"]]
                marker=tuple(nxt[-4:])
                if marker not in seen:
                    seen.add(marker);queue.append((e["to"],nxt))
    unique=[]
    for path in paths:
        if path not in unique: unique.append(path)
    return {"start_candidates": start_candidates, "goal_candidates": goal_candidates, "paths": unique[:20], "shortcut_count": max(0,len(unique)-1)}


def validate(path: Path, params: dict | None = None) -> dict:
    cfg = dict(DEFAULT_PARAMS)
    if params:
        cfg.update(params)
    lmf=read_lmf(path)
    grid=solid_grid(lmf,cfg)
    surfaces=extract_surfaces(lmf,grid,cfg)
    edges=build_graph(surfaces,grid,cfg)
    start_records=[r for r in lmf["records"] if r["id"]==100]
    start_y=start_records[0]["y"] if start_records else lmf["height"]-1
    top_y=min((s.y for s in surfaces), default=0)
    spawn_x = start_records[0]["x"] if start_records else None
    graph=directed_paths(surfaces,edges,start_y,top_y,spawn_x)
    counts=Counter(r["id"] for r in lmf["records"])
    issues=[]
    if not start_records: issues.append("start_tile_100_missing")
    if not surfaces: issues.append("no_walkable_surface_found")
    if not graph["paths"]: issues.append("no_conservative_path_from_start_to_top")
    if graph["shortcut_count"]>0: issues.append("multiple_conservative_paths_or_shortcuts")
    narrow=[]
    for s in surfaces:
        if not free_clearance(grid,s,cfg): narrow.append(s.index)
    if narrow: issues.append("surfaces_with_insufficient_clearance")
    return {
        "file": str(path),
        "validation_status": "legacy_uncalibrated_heuristic_not_playability_proof",
        "engine_clear_certified": False,
        "warnings": [
            "known_cleared_reference_has_false_negative",
            "arc_exceeds_configured_peak",
            "launch_and_landing_collision_checks_skipped",
            "body_shape_horizontal_range_and_gimmicks_not_calibrated",
            "slope_ids_have_legacy_hex_decimal_ambiguity",
            "no_path_means_model_did_not_find_path_not_game_impossible",
        ],
        "width": lmf["width"], "height": lmf["height"], "record_count": len(lmf["records"]),
        "tile_counts": dict(sorted(counts.items())),
        "parameters": cfg,
        "surface_count": len(surfaces),
        "surfaces": [s.__dict__ | {"width":s.width,"center":round(s.center,2)} for s in surfaces],
        "edge_count": len(edges), "edges": edges,
        "graph": graph,
        "issues": issues,
    }


def main() -> None:
    parser=argparse.ArgumentParser(description="Conservative LMF cliff reachability validator")
    parser.add_argument("lmf", type=Path)
    parser.add_argument("--params", type=Path)
    parser.add_argument("--out", type=Path)
    args=parser.parse_args()
    params=json.loads(args.params.read_text(encoding="utf-8")) if args.params else None
    report=validate(args.lmf,params)
    text=json.dumps(report,ensure_ascii=False,indent=2)
    if args.out: args.out.write_text(text,encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
