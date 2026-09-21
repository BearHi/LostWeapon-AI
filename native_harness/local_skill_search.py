"""Bounded native beam search for one previously unknown platform edge."""
from __future__ import annotations

from skill_replay import restore_env_state, save_env_state


DEFAULT_ACTIONS = (0, 1, 2, 3, 6, 7, 10, 11, 12, 13, 14, 18)


def _same_surface(left, right):
    return (left is not None and right is not None and
            (left.y, left.x0, left.x1) == (right.y, right.x0, right.x1))


def _key(state):
    return (round(float(state["x"]) / 8), round(float(state["y"]) / 8),
            round(float(state.get("motion58", 0)) / 80), state.get("38"),
            state.get("c0"), state.get("b0"))


def _score(state, target):
    target_x = (target.x0 + target.x1) * 16.0
    target_y = target.y * 32.0
    return abs(float(state["x"]) - target_x) + 1.5 * abs(float(state["y"]) - target_y)


def search_transition(env, target_surface, *, max_depth=32, beam_width=16,
                      actions=DEFAULT_ACTIONS, durations=(1, 2, 4, 8, 16), commit=True,
                      progress=None):
    """Search original-x86 outcomes only; returns no guessed physics result."""
    origin = save_env_state(env)
    initial = env.api.read_state()
    frontier = [(origin, [], [], initial)]
    seen = {_key(initial)}
    expanded = 0
    for _depth in range(1, max_depth + 1):
        next_frontier = []
        for saved, prefix, prefix_trace, _state in frontier:
            for action in actions:
                restore_env_state(env, saved)
                if (hasattr(env, "valid_action_indices") and
                        action not in env.valid_action_indices()):
                    continue
                for duration in durations:
                    restore_env_state(env, saved)
                    sequence = list(prefix); trace = list(prefix_trace)
                    terminated = truncated = False
                    for _ in range(int(duration)):
                        _obs, _reward, terminated, truncated, info = env.step(action)
                        expanded += 1
                        state = info["state"]
                        sequence.append(int(action)); trace.append(state)
                        if _same_surface(env.planner.surface_for_player(state), target_surface):
                            result_state = save_env_state(env)
                            if not commit:
                                restore_env_state(env, origin)
                            return {"native_verified": True, "actions": sequence,
                                    "steps": len(sequence), "expanded": expanded,
                                    "final_state": state, "trace": trace,
                                    "saved_state": result_state if commit else None}
                        if terminated or truncated:
                            break
                    if terminated or truncated:
                        continue
                    key = _key(state)
                    if key in seen:
                        continue
                    seen.add(key)
                    next_frontier.append((_score(state, target_surface),
                                          save_env_state(env), sequence, trace, state))
        next_frontier.sort(key=lambda row: row[0])
        frontier = [(saved, sequence, trace, state)
                    for _rank, saved, sequence, trace, state in next_frontier[:beam_width]]
        if progress is not None:
            progress({"depth": _depth, "max_depth": max_depth,
                      "frontier": len(frontier), "expanded": expanded})
        if not frontier:
            break
    restore_env_state(env, origin)
    return {"native_verified": False, "actions": [], "steps": 0,
            "expanded": expanded, "final_state": initial, "trace": [],
            "saved_state": None}
