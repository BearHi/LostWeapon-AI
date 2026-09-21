"""Bounded native-physics route selection for mostly horizontal goals.

Candidate controls are generic movement primitives. A route is accepted only
after the original x86 world reaches the actual flag; no map name is used.
This proves the fastest *tested candidate*, not the globally optimal key stream.
"""
from __future__ import annotations

from native_env import ACTIONS
from discovered_map import DiscoveredMap


def fastest_horizontal_route(env, *, max_steps=130, progress=None):
    starts, goals = env.planner.starts, env.goals
    if not starts or not goals:
        return {"verified": False, "reason": "missing_endpoint", "trials": []}
    start = starts[0]
    goal = min(goals, key=lambda g: abs(g[0] - start[0]) + abs(g[1] - start[1]))
    if abs(goal[1] - start[1]) > 1 or goal[0] == start[0]:
        return {"verified": False, "reason": "not_horizontal", "trials": []}
    direction = "RIGHT" if goal[0] > start[0] else "LEFT"
    roll = ACTIONS.index((direction, "DOWN"))
    jump = ACTIONS.index((direction, "UP"))
    walk = ACTIONS.index((direction,))
    # Probe the fastest ground primitive first. Jump durations are measured
    # in decisions, not estimated from a hand-written motion formula.
    candidates = ([(0, jump_decisions) for jump_decisions in
                   (0, 2, 4, 6, 8, 10, 12, 16)] +
                  [(walk_decisions, 0) for walk_decisions in
                   (4, 8, 10, 11, 12, 13, 14, 15, 16, 20, 24)])
    best, trials = None, []
    discovered = DiscoveredMap(env.width, env.height)
    for walk_decisions, jump_decisions in candidates:
        obs, reset = env.reset()
        view = env.adaptive_navigation_view(reset["state"])
        discovered.update(view)
        scanned_tile = tuple(view["player_tile"])
        actions, demonstration, states = [], [], [reset["state"]]
        done = False
        stalled = 0
        no_progress = 0
        furthest = float(reset["state"]["x"]) * (1 if direction == "RIGHT" else -1)
        blocked_xy = None
        last_supported_xy = None
        reason = "limit"
        # Once a clear in N decisions exists, a branch that has not cleared
        # by N-1 can never improve it. This is an exact time bound, not a
        # learned guess or a reward heuristic.
        budget = min(max_steps, env.max_steps,
                     len(best["actions"]) - 1 if best is not None else max_steps)
        for index in range(budget):
            state = env.api.read_state()
            player_tile = (int(state["x"] // 32), int(state["y"] // 32))
            if player_tile != scanned_tile:
                view = env.adaptive_navigation_view(state)
                discovered.update(view)
                scanned_tile = player_tile
            action = (walk if index < walk_decisions else
                      jump if index < walk_decisions + jump_decisions else roll)
            # A remembered wall is not erased when it leaves the crop. Avoid
            # rolling straight into it; the native trial still decides whether
            # the jump works. Unknown cells are not certified traversable.
            next_x = player_tile[0] + (1 if direction == "RIGHT" else -1)
            if action == roll and discovered.clearance(next_x, player_tile[1] - 1) == "blocked":
                action = jump
            if action not in env.valid_action_indices():
                reason = "masked"
                break
            nxt, _reward, done, truncated, info = env.step(action)
            discovered.record_transition(states[-1], action, info["state"])
            actions.append(action)
            demonstration.append((obs.copy(), action))
            states.append(info["state"])
            obs = nxt
            if done or truncated:
                reason = "goal" if done else "limit"
                break
            moved = (info["state"]["x"] - states[-2]["x"]) * (1 if direction == "RIGHT" else -1)
            if moved < -64:
                reason = "respawn"
                break
            projected_x = float(info["state"]["x"]) * (1 if direction == "RIGHT" else -1)
            if projected_x > furthest + 0.5:
                furthest = projected_x
                no_progress = 0
            else:
                no_progress += 1
            if abs(moved) < 1 and blocked_xy is None:
                blocked_xy = [round(info["state"]["x"], 1),
                              round(info["state"]["y"], 1)]
            if env.planner.surface_for_player(info["state"]) is not None:
                last_supported_xy = [round(info["state"]["x"], 1),
                                     round(info["state"]["y"], 1)]
            stalled = stalled + 1 if abs(moved) < 1 and abs(
                info["state"]["y"] - states[-2]["y"]) < 1 else 0
            if stalled >= 4:
                reason = "blocked"
                break
            if no_progress >= 24:
                reason = "no_forward_progress"
                break
        if not done and best is not None and reason == "limit":
            reason = "cannot_beat_verified_route"
        trials.append({"view_size": view["size"],
                       "next_gap_tile": view["next_gap_tile"],
                       "walk_decisions": walk_decisions,
                       "jump_decisions": jump_decisions, "steps": len(actions),
                       "reason": reason, "blocked_xy": blocked_xy,
                       "last_supported_xy": last_supported_xy,
                       "furthest_x": round(furthest * (1 if direction == "RIGHT" else -1), 1),
                       "native_goal_contact": bool(done)})
        if progress is not None:
            progress({"trial": len(trials), "total": len(candidates),
                      "steps": len(actions), "result": reason,
                      "best_steps": len(best["actions"]) if best else None})
        if done and (best is None or len(actions) < len(best["actions"])):
            best = {"verified": True, "actions": actions,
                    "demonstration": demonstration, "states": states}
    if best is not None:
        return {**best, "trials": trials, "memory": discovered.summary()}
    return {"verified": False, "reason": "no_native_clear", "trials": trials,
            "memory": discovered.summary()}
