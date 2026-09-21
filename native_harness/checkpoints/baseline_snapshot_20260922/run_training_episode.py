"""Run a short NativeTrainingAPI episode from a JSON action schedule.

This is an integration runner, not a claim that every fixture has normal-
Client parity. Use it with a captured resource/state base and keep the output
as a reproducible evidence artifact.

Example:
  python run_training_episode.py \
    private_snapshots/hun7_live.zip ../훈련용맵/훈7.LMF \
    '[{"keys":["RIGHT"],"ticks":64},{"keys":["UP"],"ticks":30}]'
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from api import NativeTrainingAPI


def main() -> None:
    if len(sys.argv) < 4:
        raise SystemExit("usage: run_training_episode.py SNAPSHOT LMF ACTION_JSON [OUTPUT]")
    snapshot = Path(sys.argv[1])
    lmf = Path(sys.argv[2])
    schedule = json.loads(sys.argv[3])
    output = Path(sys.argv[4]) if len(sys.argv) > 4 else None
    api = NativeTrainingAPI(snapshot, lmf)
    states = [{"tick": 0, "state": api.read_state()}]
    tick = 0
    for segment in schedule:
        keys = segment.get("keys", [])
        ticks = int(segment.get("ticks", 0))
        if ticks < 0:
            raise ValueError("segment ticks must be non-negative")
        for _ in range(ticks):
            tick += 1
            states.append({"tick": tick, "keys": keys, "state": api.step(1, keys)})
    result = {
        "scope": "NativeTrainingAPI episode runner; parity scope is determined by the fixture ledger",
        "snapshot": str(snapshot),
        "lmf": str(lmf),
        "schedule": schedule,
        "ticks": tick,
        "start": states[0]["state"],
        "end": states[-1]["state"],
        "states": states,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if output:
        output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
