"""Read-only native replay of original clears in the corresponding variants."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from native_env import LostWeaponEnv
from snapshot_selector import snapshot_for_map

archive = ROOT / "checkpoints" / "map_clear_shared_dqn.episodes.jsonl"
source = defaultdict(list)
for line in archive.read_text(encoding="utf-8").splitlines():
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    if row.get("success") and "혼련용" not in row.get("map", ""):
        source[Path(row["map"]).stem].append(row)

for number in sys.argv[1:] or ("2", "3", "6", "16", "18", "19"):
    original = f"훈{number}"
    candidates = sorted(source[original], key=lambda row: row["steps"])
    if not candidates:
        print(number, {"error": "no_original_clear"}, flush=True)
        continue
    row = candidates[0]
    lmf = ROOT.parent / "훈련용맵" / "혼련용" / f"혼{number}.LMF"
    env = LostWeaponEnv(snapshot_for_map(ROOT, lmf), lmf,
                        action_repeat=row["action_repeat"], max_steps=1500)
    _obs, reset = env.reset()
    states = [reset["state"]]
    sequence = [action for action, count in row["actions_rle"]
                for _ in range(count)]
    done = False
    masked = 0
    for index, action in enumerate(sequence):
        masked += action not in env.valid_action_indices()
        _obs, _reward, done, truncated, info = env.step(action)
        states.append(info["state"])
        if done or truncated:
            break
    gx, gy = env.goals[0]
    nearest = min(states, key=lambda s: abs(s["x"] - gx * 32) +
                  abs(s["y"] - gy * 32))
    print(number, {"source_episode": row["episode"],
                   "source_steps": row["steps"], "replayed": index + 1,
                   "clear": done, "masked": masked,
                   "start": [states[0]["x"], states[0]["y"]],
                   "nearest": [round(nearest["x"], 1), round(nearest["y"], 1)],
                   "final": [round(states[-1]["x"], 1),
                             round(states[-1]["y"], 1)]}, flush=True)
