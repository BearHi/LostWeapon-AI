"""Bounded native macro search for routes that are not platform graphs."""
from __future__ import annotations

from skill_replay import restore_env_state, save_env_state


ACTION_SETS = {
    "air_traverse": (0, 2, 5, 11),
    "ladder": (0, 2, 3, 7),
    "water": (0, 1, 2, 3, 6, 7),
    "ice_slope": (0, 1, 2, 8, 9),
    "special_transport": (0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12),
}


def _key(state):
    return (round(float(state["x"]) / 16), round(float(state["y"]) / 16),
            round(float(state.get("motion58", 0)) / 160), state.get("38"),
            state.get("c0"), state.get("dc"))


def _score(env, state, seen_cells):
    cell = (round(float(state["x"]) / 16), round(float(state["y"]) / 16))
    novelty = -48.0 if cell not in seen_cells else 0.0
    return env._goal_distance(state) + novelty


def search_mechanic_route(env, mode, *, max_depth=10, beam_width=12,
                          durations=(8, 16, 32), progress=None, commit=True):
    """Search macro inputs using only original-x86 outcomes."""
    origin = save_env_state(env)
    initial = env.api.read_state()
    frontier = [(origin, [], initial)]
    seen = {_key(initial)}
    seen_cells = {(round(float(initial["x"]) / 16), round(float(initial["y"]) / 16))}
    expanded = 0
    actions = ACTION_SETS.get(mode, ACTION_SETS["special_transport"])
    for depth in range(1, max_depth + 1):
        candidates = []
        for saved, prefix, _state in frontier:
            for action in actions:
                restore_env_state(env, saved)
                if (hasattr(env, "valid_action_indices") and
                        action not in env.valid_action_indices()):
                    continue
                for duration in durations:
                    restore_env_state(env, saved)
                    sequence = list(prefix)
                    terminated = truncated = False
                    state = env.api.read_state()
                    for _ in range(duration):
                        _obs, _reward, terminated, truncated, info = env.step(action)
                        state = info["state"]; sequence.append(int(action)); expanded += 1
                        if env.reached_goal(state):
                            result_state = save_env_state(env)
                            if not commit:
                                restore_env_state(env, origin)
                            return {"native_verified": True, "actions": sequence,
                                    "steps": len(sequence), "expanded": expanded,
                                    "depth": depth, "final_state": state,
                                    "saved_state": result_state if commit else None}
                        if terminated or truncated:
                            break
                    if terminated or truncated:
                        continue
                    key = _key(state)
                    if key in seen:
                        continue
                    seen.add(key)
                    rank = _score(env, state, seen_cells)
                    seen_cells.add((round(float(state["x"]) / 16),
                                    round(float(state["y"]) / 16)))
                    candidates.append((rank, save_env_state(env), sequence, state))
        candidates.sort(key=lambda row: row[0])
        frontier = [(saved, sequence, state)
                    for _rank, saved, sequence, state in candidates[:beam_width]]
        if progress:
            progress({"phase": "mechanic_search", "mode": mode, "depth": depth,
                      "max_depth": max_depth, "frontier": len(frontier),
                      "expanded": expanded})
        if not frontier:
            break
    restore_env_state(env, origin)
    return {"native_verified": False, "actions": [], "steps": 0,
            "expanded": expanded, "depth": depth, "final_state": initial,
            "saved_state": None}
