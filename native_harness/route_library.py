"""Topology-keyed native-verified route memory."""
from __future__ import annotations
import json
import os
from pathlib import Path


def load_library(path):
    path = Path(path)
    if not path.exists():
        return {"schema": 1, "routes": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if value.get("schema") == 1 else {"schema": 1, "routes": {}}
    except (OSError, json.JSONDecodeError):
        return {"schema": 1, "routes": {}}


def save_route(path, topology, *, actions_rle, steps, action_repeat,
               source_map_sha256, source_episode):
    path = Path(path); library = load_library(path)
    current = library["routes"].get(topology)
    if current and int(current["steps"]) <= int(steps):
        return False
    library["routes"][topology] = {
        "actions_rle": actions_rle, "steps": int(steps),
        "action_repeat": int(action_repeat),
        "source_map_sha256": source_map_sha256,
        "source_episode": int(source_episode),
        "verification": "must_replay_current_native_world",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(library, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    return True
