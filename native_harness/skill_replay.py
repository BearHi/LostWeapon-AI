"""Native branch validation for remembered surface-to-surface skills."""
from __future__ import annotations
from copy import deepcopy


def expand_actions(row):
    return [int(action) for action, count in row["actions_rle"]
            for _ in range(int(count))]


def _same_surface(left, right):
    return (left is not None and right is not None and
            (left.y, left.x0, left.x1) == (right.y, right.x0, right.x1))


def save_env_state(env):
    return env.api.save_state(), {
        "steps": env.steps, "visited": deepcopy(env.visited),
        "global_visits": deepcopy(env.global_visits), "last_keys": env.last_keys,
        "last_goal_distance": env.last_goal_distance,
    }


def restore_env_state(env, saved):
    branch, bookkeeping = saved
    env.api.restore_state(branch)
    for key, value in bookkeeping.items():
        setattr(env, key, value)


def replay_candidate(env, target_surface, row, *, commit=False):
    """Run a skill through original x86; retain state only after verified landing."""
    saved = save_env_state(env)
    trace = []
    landed = False
    terminated = truncated = False
    attempted_actions = expand_actions(row)
    for action in attempted_actions:
        _obs, _reward, terminated, truncated, info = env.step(action)
        state = info["state"]
        trace.append(state)
        if _same_surface(env.planner.surface_for_player(state), target_surface):
            landed = True
            break
        if terminated or truncated:
            break
    if not (landed and commit):
        restore_env_state(env, saved)
    return {"native_verified": landed, "steps": len(trace),
            "actions": attempted_actions[:len(trace)],
            "trace": trace,
            "terminated": terminated, "truncated": truncated,
            "final_state": trace[-1] if trace else env.api.read_state()}
