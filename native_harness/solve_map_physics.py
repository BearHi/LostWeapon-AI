"""Small physics-only route probe: no human traces, DQN, or map-specific actions.

The map supplies the goal and surfaces. Every candidate is executed against
the original x86 transition, and a success is replayed from a clean start.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from contextual_routes import (try_air_traverse_route, try_ladder_route,
                               try_diagonal_spring_route, try_vertical_spring_route,
                               try_water_route)
from native_env import LostWeaponEnv
from route_library import load_library, save_route
from snapshot_selector import snapshot_for_map
from training_archive import rle_actions, sha256_file


def replay_from_start(env, actions):
    env.reset()
    for index, action in enumerate(actions):
        if action not in env.valid_action_indices():
            return {"verified": False, "steps": index,
                    "reason": "action_forbidden_at_current_block"}
        _obs, _reward, done, truncated, _info = env.step(action)
        if done:
            return {"verified": True, "steps": index + 1}
        if truncated:
            break
    return {"verified": False, "steps": min(len(actions), env.steps)}


def solve(env, *, max_steps=600, margins=(4.0, 24.0, 48.0), remembered=None,
          progress=None):
    mode = ("diagonal_spring" if any(tile in (5, 6) for tile, _x, _y in env.records)
            else "vertical_spring" if any(tile == 4 for tile, _x, _y in env.records)
            else env.mechanic_profile["mode"])
    trials = []
    if remembered is not None:
        replay = replay_from_start(env, remembered)
        trials.append({"hypothesis": "remembered_route", "clean_replay": replay})
        if progress:
            progress(trials[-1])
        if replay["verified"]:
            return {"solved": True, "mode": mode, "trials": trials,
                    "route": remembered[:replay["steps"]]}
    if mode == "ladder":
        hypotheses = [("ladder", None, None, None)]
    elif mode == "water":
        hypotheses = [("water", None, None, None)]
    elif mode == "vertical_spring":
        hypotheses = [("vertical_spring", None, None, None)]
    elif mode == "diagonal_spring":
        hypotheses = [("diagonal_spring", runup, None, None)
                      for runup in (8, 6, 10)]
    elif mode == "special_transport":
        hypotheses = [("air", margin, style, None)
                      for style in ("up", "roll") for margin in margins]
        hypotheses += [("air", margin, "roll", pulse)
                       for pulse in (2, 3, 4) for margin in margins[:2]]
    else:
        hypotheses = [("air", margin, "up", None) for margin in margins]
    start = env.planner.starts[0]
    goal = min(env.goals, key=lambda item: abs(item[0] - start[0]) +
               abs(item[1] - start[1]))
    direction = 1 if goal[0] >= start[0] else -1
    start_x = (start[0] * 32 + 16) * direction
    for kind, margin, style, pulse in hypotheses:
        env.reset()
        began = time.monotonic()
        if kind == "ladder":
            result = try_ladder_route(env, max_steps=max_steps)
        elif kind == "water":
            result = try_water_route(env, max_steps=max_steps)
        elif kind == "vertical_spring":
            result = try_vertical_spring_route(env, max_steps=max_steps)
        elif kind == "diagonal_spring":
            result = try_diagonal_spring_route(env, max_steps=max_steps,
                                               runup_ticks=margin)
        else:
            result = try_air_traverse_route(env, max_steps=max_steps,
                                            launch_margin_px=margin,
                                            launch_style=style,
                                            chute_pulse_period=pulse)
        states = result.get("states") or []
        furthest = max((float(s["x"]) * direction - start_x for s in states),
                       default=0.0)
        trial = {"hypothesis": kind,
                 "runup_ticks": margin if kind == "diagonal_spring" else None,
                 "launch_margin_px": margin if kind == "air" else None,
                 "launch_style": style, "chute_pulse_period": pulse,
                 "native_goal_contact": bool(result["native_verified"]),
                 "reason": result["reason"], "stage": result["stage"],
                 "steps": len(result["actions"]),
                 "furthest_px": round(furthest, 1),
                 "seconds": round(time.monotonic() - began, 2)}
        trials.append(trial)
        if result["native_verified"]:
            replay = replay_from_start(env, result["actions"])
            trial["clean_replay"] = replay
            if progress:
                progress(trial)
            if replay["verified"]:
                return {"solved": True, "mode": mode, "trials": trials,
                        "route": result["actions"]}
        elif progress:
            progress(trial)
    return {"solved": False, "mode": mode, "trials": trials, "route": []}


def write_status(path, payload):
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("maps", nargs="+", type=Path)
    parser.add_argument("--max-steps", type=int, default=600)
    parser.add_argument("--memory", type=Path,
                        default=Path(__file__).resolve().parent / "checkpoints" /
                                "physics_route_library.json")
    parser.add_argument("--status", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    for lmf in args.maps:
        write_status(args.status, {"state": "running", "map": str(lmf.resolve()),
                                   "phase": "loading"})
        from identify_live_map import parse_lmf
        _width, _height, raw_records, _runtime = parse_lmf(lmf)
        repeat = 1 if any(tile in (5, 6) for tile, _x, _y in raw_records) else 2
        env = LostWeaponEnv(snapshot_for_map(root, lmf), lmf,
                            action_repeat=repeat, max_steps=args.max_steps)
        topology = env.planner.topology_signature()
        # Keep pre-restriction routes intact. Their inputs may be invalid in
        # local ban fields even if they once touched the goal natively.
        has_restrictions = bool(env.restrictions.at_tile)
        memory_key = f"{topology}:repeat={env.action_repeat}"
        if has_restrictions:
            memory_key += ":localban5x4v1"
        routes = load_library(args.memory)["routes"]
        stored = routes.get(memory_key)
        if stored is None and not has_restrictions:
            stored = routes.get(topology)
        remembered = None
        if stored and int(stored.get("action_repeat", -1)) == env.action_repeat:
            remembered = [int(action) for action, count in stored["actions_rle"]
                          for _ in range(int(count))]
        def report(trial):
            write_status(args.status, {"state": "running", "map": str(lmf.resolve()),
                                       "phase": "testing", "trial": trial})
        result = solve(env, max_steps=args.max_steps, remembered=remembered,
                       progress=report)
        if result["solved"]:
            save_route(args.memory, memory_key,
                       actions_rle=rle_actions(result["route"]),
                       steps=len(result["route"]), action_repeat=env.action_repeat,
                       source_map_sha256=sha256_file(lmf), source_episode=-1)
        summary = {"map": str(lmf.resolve()),
                          "scope": "offline original-x86 native simulation",
                          "goal": env.goals, "surfaces": len(env.planner.surfaces),
                          "solved": result["solved"], "mode": result["mode"],
                          "trials": result["trials"],
                          "route_steps": len(result["route"])}
        write_status(args.status, {"state": "complete", **summary})
        print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
