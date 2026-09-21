"""Visible offline-native navigation with fresh physics planning, no map memory."""
from __future__ import annotations

import argparse
import json
import struct
from html import escape
from pathlib import Path

from native_env import LostWeaponEnv
from discovered_map import DiscoveredMap
from physics_first_planner import fastest_horizontal_route
from snapshot_selector import snapshot_for_map


def scan_with_memory(env, discovered, state):
    player = [int(state["x"] // 32), int(state["y"] // 32)]
    goal = list(env._nearest_goal(state))
    ahead = discovered.forward_clearance(player, goal)
    # Start at 9x9. Revisit known ground cheaply, and expand only when the
    # current crop cannot describe the obstruction or the landing beyond it.
    size = 9 if "unknown" in ahead else 3
    view = env.navigation_view(state, size=size)
    discovered.update(view)
    ahead = discovered.forward_clearance(player, goal)
    if "blocked" in ahead or "unknown" in ahead:
        requested = 11 if "blocked" in ahead else 9
        if requested > size:
            view = env.navigation_view(state, size=requested)
            discovered.update(view)
    view["forward_clearance"] = discovered.forward_clearance(player, goal)
    view["memory"] = discovered.summary()
    return view


def save_route_svg(env, states, views, discovered, output):
    """Draw native collision geometry and the actually verified player path."""
    scale = 8
    pointer = env.api.oracle.get(env.api.oracle.GRID_POINTERS[1], "I")[0]
    raw = env.api.oracle.u.mem_read(pointer, env.width * env.height * 2)
    grid = struct.unpack(f"<{env.width * env.height}H", raw)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{env.width*scale}" '
             f'height="{env.height*scale}" viewBox="0 0 {env.width*scale} {env.height*scale}">',
             '<rect width="100%" height="100%" fill="#17212e"/>']
    for y in range(env.height):
        for x in range(env.width):
            if grid[y * env.width + x]:
                parts.append(f'<rect x="{x*scale}" y="{y*scale}" width="{scale}" '
                             f'height="{scale}" fill="#71859b"/>')
            if (x, y) not in discovered.cells:
                parts.append(f'<rect x="{x*scale}" y="{y*scale}" width="{scale}" '
                             f'height="{scale}" fill="#071018" fill-opacity=".78"/>')
    for tile, x, y in env.records:
        if tile == 140:
            parts.append(f'<circle cx="{(x+.5)*scale}" cy="{(y+.5)*scale}" '
                         f'r="{scale*.8}" fill="#64d886"/>')
    points = " ".join(f'{float(s["x"])/32*scale:.2f},{float(s["y"])/32*scale:.2f}'
                      for s in states)
    parts.append(f'<polyline points="{points}" fill="none" stroke="#ffcf55" '
                 'stroke-width="2.3" stroke-linejoin="round"/>')
    first = states[0]
    parts.append(f'<circle cx="{float(first["x"])/32*scale:.2f}" '
                 f'cy="{float(first["y"])/32*scale:.2f}" r="4" fill="#31b8ed"/>')
    sizes = sorted({v["size"] for v in views})
    parts.append(f'<title>{escape("native verified route; live view sizes " + str(sizes))}</title>')
    parts.append('</svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(parts), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", nargs="?", type=Path,
                        default=Path("훈련용맵/훈1.LMF"))
    parser.add_argument("--max-steps", type=int, default=130)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    env = LostWeaponEnv(snapshot_for_map(root, args.map), args.map,
                        action_repeat=2, max_steps=args.max_steps)
    _obs, reset = env.reset()
    discovered = DiscoveredMap(env.width, env.height)
    view = scan_with_memory(env, discovered, reset["state"])
    print(json.dumps({"phase": "scan", "player": view["player_tile"],
                      "goal": view["goal_tile"], "view_size": view["size"],
                      "next_gap_tile": view.get("next_gap_tile"),
                      "forward_clearance": view["forward_clearance"]},
                     ensure_ascii=False), flush=True)
    def progress(row):
        print(json.dumps({"phase": "candidate", **row}, ensure_ascii=False), flush=True)

    plan = fastest_horizontal_route(env, max_steps=args.max_steps, progress=progress)
    print(json.dumps({"phase": "plan", "native_verified": plan["verified"],
                      "trial_count": len(plan["trials"]),
                      "decisions": len(plan.get("actions", ())),
                      "reason": plan.get("reason")}, ensure_ascii=False), flush=True)
    if not plan["verified"]:
        raise SystemExit("no verified horizontal route; do not guess")
    env.reset()
    done = False
    replay_states = [env.api.read_state()]
    discovered = DiscoveredMap(env.width, env.height)
    replay_views = [scan_with_memory(env, discovered, replay_states[0])]
    for index, action in enumerate(plan["actions"], start=1):
        if action not in env.valid_action_indices():
            raise SystemExit(f"action became invalid at decision {index}")
        _obs, _reward, done, truncated, info = env.step(action)
        transition = discovered.record_transition(replay_states[-1], action,
                                                   info["state"],
                                                   respawn=bool(info.get("respawn", False)))
        live = scan_with_memory(env, discovered, info["state"])
        replay_states.append(info["state"])
        replay_views.append(live)
        if index % 8 == 0 or done or truncated:
            print(json.dumps({"phase": "move", "decision": index,
                              "player_xy": live["player_xy"],
                              "view_size": live["size"],
                              "forward_clearance": live["forward_clearance"],
                              "transition": transition,
                              "memory": live["memory"],
                              "done": done},
                             ensure_ascii=False), flush=True)
        if done or truncated:
            break
    if not done:
        raise SystemExit("planned route failed clean replay")
    output = args.output or root / "evidence" / f"route_helper_{args.map.stem}.svg"
    save_route_svg(env, replay_states, replay_views, discovered, output)
    print(json.dumps({"phase": "complete", "decisions": index,
                      "native_verified": True, "route_svg": str(output),
                      "discovered_tiles": len(discovered.cells),
                      "memory": discovered.summary(),
                      "view_sizes": sorted({v["size"] for v in replay_views})},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
