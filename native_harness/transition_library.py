"""Reusable surface-to-surface skills extracted from native-verified routes."""
from __future__ import annotations
import json
import os
from pathlib import Path

from training_archive import rle_actions


def load_library(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if value.get("schema") == 3 else {"schema": 3, "skills": []}
    except (OSError, json.JSONDecodeError):
        return {"schema": 3, "skills": []}


def _surface_shape(surface):
    return [surface.y, surface.x0, surface.x1]


def _geometry(source, target, relative):
    return {
        "source_width": source.x1 - source.x0 + 1,
        "target_width": target.x1 - target.x0 + 1,
        "dy": target.y - source.y,
        "gap": relative["gap"],
        "direction": 1 if target.x0 > source.x1 else -1 if target.x1 < source.x0 else 0,
    }


def _skill_key(row):
    geometry = row["geometry"]
    return (geometry["source_width"], geometry["target_width"], geometry["dy"],
            geometry["gap"], geometry["direction"],
            round(float(row["relative"]["start_from_left"]), 3),
            int(row["action_repeat"]))


def _state_context(state):
    return {key: state.get(key) for key in
            ("motion58", "38", "68", "74", "7c", "80", "b0", "c0", "dc")}


def _set_distance(left, right):
    left = {tuple(value) for value in left}
    right = {tuple(value) for value in right}
    union = left | right
    return 0.0 if not union else 1.0 - len(left & right) / len(union)


def extract_transitions(planner, states, actions):
    """Split a successful state/action trace at supporting-surface changes."""
    if len(states) != len(actions) + 1:
        raise ValueError("states must contain initial state plus one state per action")
    labels = []
    for state in states:
        surface = planner.surface_for_player(state)
        labels.append(None if surface is None else surface.index)
    result = []
    source_index = next((i for i, label in enumerate(labels) if label is not None), None)
    if source_index is None:
        return result
    source_label = labels[source_index]
    for state_index in range(source_index + 1, len(labels)):
        label = labels[state_index]
        if label == source_label:
            continue
        if label is None:
            continue
        source = planner.surfaces[source_label]
        target = planner.surfaces[label]
        # Keep preparation performed after the previous landing.  Dropping
        # same-surface run-up/crouch actions preserves the geometric jump but
        # loses the native velocity and animation context needed to chain it.
        segment = actions[source_index:state_index]
        if segment:
            start_x = float(states[source_index]["x"]) / 32.0
            end_x = float(states[state_index]["x"]) / 32.0
            relative = {
                "dy": target.y - source.y,
                "gap": max(0, target.x0 - source.x1, source.x0 - target.x1),
                "start_from_left": round(start_x - source.x0, 3),
                "end_from_left": round(end_x - target.x0, 3),
            }
            result.append({
                "source": _surface_shape(source), "target": _surface_shape(target),
                "geometry": _geometry(source, target, relative),
                "context": planner.transition_context(source, target),
                "entry_state": _state_context(states[source_index]),
                "exit_state": _state_context(states[state_index]),
                "relative": relative,
                "actions_rle": rle_actions(segment), "steps": len(segment),
            })
        source_label = label
        source_index = state_index
    return result


def save_transitions(path, transitions, *, action_repeat, source_map_sha256,
                     source_episode, verification="native_verified_transition"):
    path = Path(path)
    try:
        library = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        library = {"schema": 3, "skills": []}
    if library.get("schema") != 3:
        library = {"schema": 3, "skills": []}
    existing = {_skill_key(row): i for i, row in enumerate(library["skills"])}
    changed = 0
    for transition in transitions:
        row = {**transition, "action_repeat": int(action_repeat),
               "source_map_sha256": source_map_sha256,
               "source_episode": int(source_episode),
               "verification": verification}
        key = _skill_key(row)
        index = existing.get(key)
        if index is None:
            library["skills"].append(row); existing[key] = len(library["skills"]) - 1
            changed += 1
        elif row["steps"] < library["skills"][index]["steps"]:
            library["skills"][index] = row; changed += 1
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(library, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    return changed


def find_candidates(library, source, target, *, action_repeat, start_from_left,
                    start_tolerance=0.75, context=None, state=None,
                    max_dy_error=0, max_gap_error=0, max_width_error=0):
    """Find relative-geometry matches; every result still needs native replay."""
    gap = max(0, target.x0 - source.x1, source.x0 - target.x1)
    relative = {"gap": gap}
    wanted = _geometry(source, target, relative)
    candidates = []
    for row in library.get("skills", []):
        geometry = row.get("geometry", {})
        comparable = (
            geometry.get("direction") == wanted.get("direction") and
            abs(int(geometry.get("source_width", 10**6)) -
                int(wanted["source_width"])) <= max_width_error and
            abs(int(geometry.get("target_width", 10**6)) -
                int(wanted["target_width"])) <= max_width_error and
            abs(int(geometry.get("gap", 10**6)) - int(wanted["gap"])) <= max_gap_error)
        if (not comparable or
                abs(int(geometry.get("dy", 10**6)) - int(wanted["dy"])) > max_dy_error or
                row.get("action_repeat") != action_repeat):
            continue
        position_error = abs(float(row["relative"]["start_from_left"]) - float(start_from_left))
        if position_error > start_tolerance:
            continue
        context_error = 0.0
        if context is not None:
            context_error = (_set_distance(row.get("context", {}).get("collision", []),
                                           context.get("collision", [])) +
                             2.0 * _set_distance(row.get("context", {}).get("objects", []),
                                                 context.get("objects", [])))
        state_error = 0.0
        if state is not None:
            remembered = row.get("entry_state", {})
            state_error += abs(float(remembered.get("motion58", 0)) -
                               float(state.get("motion58", 0))) / 1000.0
            state_error += 0.5 * (remembered.get("b0") != state.get("b0"))
            state_error += 0.25 * (remembered.get("38") != state.get("38"))
        dy_error = abs(int(geometry["dy"]) - int(wanted["dy"]))
        geometry_error = (dy_error +
                          abs(int(geometry["gap"]) - int(wanted["gap"])) +
                          abs(int(geometry["source_width"]) - int(wanted["source_width"])) +
                          abs(int(geometry["target_width"]) - int(wanted["target_width"])))
        candidates.append((2.0 * geometry_error + context_error + state_error, position_error,
                           int(row["steps"]), row))
    return [row for _score, _position, _steps, row in
            sorted(candidates, key=lambda value: value[:3])]


def compose_surface_path(library, surfaces, *, action_repeat, start_offsets,
                         start_tolerance=0.75, contexts=None, states=None):
    """Return ordered candidate sets for a surface path, or [] if any edge is unknown."""
    if len(start_offsets) != max(0, len(surfaces) - 1):
        raise ValueError("one start offset is required for each surface edge")
    contexts = contexts or [None] * len(start_offsets)
    states = states or [None] * len(start_offsets)
    result = []
    for source, target, offset, context, state in zip(
            surfaces, surfaces[1:], start_offsets, contexts, states):
        candidates = find_candidates(
            library, source, target, action_repeat=action_repeat,
            start_from_left=offset, start_tolerance=start_tolerance,
            context=context, state=state)
        if not candidates:
            return []
        result.append(candidates)
    return result
