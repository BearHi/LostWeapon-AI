"""Generate irregular wall-only cliff candidates.

This deliberately creates collision from two wall profiles instead of placing
platform points.  The candidate is scored for shape variety, non-repetition,
open fall space, and sparse surface clusters before it is exported.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cliff_validator import DEFAULT_PARAMS, build_graph, directed_paths, extract_surfaces, solid_grid

W, H = 31, 240
KINDS = ("wedge", "round", "hook", "overhang", "notch")


def pulse(t: float, kind: str) -> float:
    if kind == "wedge":
        return t if t < 0.55 else max(0.0, 1.0 - (t - 0.55) / 0.45)
    if kind == "round":
        return math.sin(math.pi * max(0.0, min(1.0, t))) ** 1.7
    if kind == "hook":
        return 1.0 if 0.22 <= t <= 0.72 else (t / 0.22 if t < 0.22 else max(0.0, (1.0 - t) / 0.28))
    if kind == "overhang":
        return 1.0 if t < 0.42 else max(0.0, 1.0 - (t - 0.42) / 0.58)
    return -0.72 * math.sin(math.pi * max(0.0, min(1.0, t)))


def add_feature(profile: list[float], start: int, length: int, depth: int, kind: str) -> None:
    for y in range(max(4, start), min(H - 8, start + length)):
        t=(y-start)/max(1, length-1)
        profile[y] += depth*pulse(t, kind)


def build_candidate(seed: int) -> tuple[list[list[int]], dict]:
    rng=random.Random(seed)
    left=[0.0]*H; right=[0.0]*H
    features=[]; cursor=10
    last_side=None; same_side=0
    for _ in range(40):
        cursor += rng.randint(2, 7)
        if cursor >= H-25: break
        length=rng.randint(6, 17)
        side="left" if rng.random()<0.5 else "right"
        if side==last_side: same_side+=1
        else: same_side=0
        if same_side>=3: side="right" if side=="left" else "left"; same_side=0
        kind=rng.choice(KINDS)
        depth=rng.randint(3, 10)
        target=left if side=="left" else right
        add_feature(target,cursor,length,depth,kind)
        features.append({"side":side,"start":cursor,"length":length,"depth":depth,"shape":kind})
        cursor += rng.randint(1, 6)
    for y in range(H):
        left[y]=max(0,min(13,left[y]+0.65*math.sin(y/13.0)+0.35*math.sin(y/5.7)))
        right[y]=max(0,min(13,right[y]+0.55*math.sin(y/17.0+1.1)+0.3*math.sin(y/7.2)))
    grid=[[0]*W for _ in range(H)]
    for y in range(H):
        l=int(round(2+left[y])); r=int(round(28-right[y]))
        if l>=r-5: l= min(l, r-6)
        for x in range(W):
            if x<=l or x>=r or y<4 or y>=H-4: grid[y][x]=8
    # Add a single irregular bottom landing and a non-central top cap.
    for y in range(H-15,H-4):
        for x in range(2, min(W-2, 8+rng.randint(0,5))): grid[y][x]=8
    for y in range(4, 16):
        for x in range(max(2, W-10-rng.randint(0,4)), W-2): grid[y][x]=8
    return grid, {"seed":seed,"features":features}


def surface_runs(grid: list[list[int]]) -> list[dict]:
    out=[]
    for y in range(1,H-1):
        xs=[x for x in range(W) if grid[y][x]==8 and grid[y-1][x]!=8]
        start=None
        for x in range(W+1):
            here=x in xs
            if here and start is None: start=x
            if (not here or x==W) and start is not None:
                end=x-1
                if end-start+1>=2: out.append({"x1":start,"x2":end,"y":y})
                start=None
    return out


def reachability(grid: list[list[int]]) -> dict:
    cells={(x,y):8 for y,row in enumerate(grid) for x,v in enumerate(row) if v==8}
    cells[(15,H-5)]=100
    lmf={"width":W,"height":H,"cells":cells}
    params=dict(DEFAULT_PARAMS)
    params["minimum_surface_width"]=1
    collision=solid_grid(lmf,params)
    surfaces=extract_surfaces(lmf,collision,params)
    edges=build_graph(surfaces,collision,params)
    if not surfaces:
        return {"path":[],"surfaces":0,"edges":0,"shortcuts":0}
    graph=directed_paths(surfaces,edges,H-5,min(s.y for s in surfaces))
    return {"path":graph["paths"][0] if graph["paths"] else [],"surfaces":len(surfaces),"edges":len(edges),"shortcuts":graph["shortcut_count"]}


def score(grid: list[list[int]], runs: list[dict], features: list[dict]) -> tuple[float, dict]:
    if not runs: return -1e9, {"path":[],"surfaces":0,"edges":0,"shortcuts":0}
    rows=sorted({r["y"] for r in runs})
    gaps=[rows[i]-rows[i-1] for i in range(1,len(rows))]
    gap_var=0 if len(gaps)<2 else sum((g-sum(gaps)/len(gaps))**2 for g in gaps)/len(gaps)
    repeated=sum(1 for a,b in zip(gaps,gaps[1:]) if a==b)
    central=sum(max(0,min(20,r["x2"])-max(10,r["x1"])+1) for r in runs)
    closed=sum(1 for y in range(4,H-4) if all(grid[y][x]==8 for x in range(W)))
    kinds=len({f["shape"] for f in features})
    reach=reachability(grid)
    max_gap=max(gaps,default=0)
    # A candidate without a start-to-top path is not a map candidate.
    route_bonus=420 if reach["path"] else -1000
    shortcut_penalty=3.0*reach["shortcuts"]
    value=(4*min(gap_var,100)-7*repeated-0.15*central-50*closed
           +10*min(len(runs),45)+20*kinds+route_bonus
           -2.0*max(0,max_gap-13)-shortcut_penalty)
    return value,reach


def main() -> None:
    best=None
    for seed in range(1200):
        grid,meta=build_candidate(seed)
        runs=surface_runs(grid)
        value,reach=score(grid,runs,meta["features"])
        meta["reachability"]=reach
        if best is None or value>best[0]: best=(value,grid,meta,runs)
    value,grid,meta,runs=best
    output={"name":"암벽 수학형 v1","status":"route_candidate" if meta["reachability"]["path"] else "rejected_no_route","width":W,"height":H,"rock_tile":8,"start":{"x":15,"y":H-5,"tile":100},"goal":{"x":W-8,"y":8,"decorative":True},"score":round(value,3),"reachability":meta["reachability"],"features":meta["features"],"surface_runs":runs,"solid_cells":[[x,y] for y,row in enumerate(grid) for x,v in enumerate(row) if v==8]}
    path=Path(__file__).with_name("암벽_수학형_v1_후보.json")
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"path":str(path),"score":round(value,3),"features":len(meta["features"]),"surface_runs":len(runs),"solid_cells":len(output["solid_cells"])},ensure_ascii=False))


if __name__ == "__main__":
    main()
