"""Versioned, compact episode archives that survive physics corrections."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def physics_fingerprint(harness):
    """Identify code that determines transitions, without tying data to UI/trainer code."""
    digest = hashlib.sha256()
    for name in ("captured_oracle.py", "lmf_injector.py", "api.py"):
        path = Path(harness) / name
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def rle_actions(actions):
    encoded = []
    for action in actions:
        if encoded and encoded[-1][0] == int(action):
            encoded[-1][1] += 1
        else:
            encoded.append([int(action), 1])
    return encoded


def append_episode(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", buffering=1) as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
