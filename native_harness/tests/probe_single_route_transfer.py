"""Replay one shortest remembered route in a changed native LMF world."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from native_env import LostWeaponEnv
from route_library import load_library

snapshot, lmf, library_path = map(Path, sys.argv[1:4])
env = LostWeaponEnv(snapshot, lmf, action_repeat=2, max_steps=1200)
routes = sorted(load_library(library_path)["routes"].values(), key=lambda row: row["steps"])
route = routes[0]
actions = [int(action) for action, count in route["actions_rle"]
           for _ in range(int(count))]
env.reset(); done = truncated = False; info = {"state": env.api.read_state()}
for action in actions:
    _obs, _reward, done, truncated, info = env.step(action)
    if done or truncated: break
print(json.dumps({"map": str(lmf), "source_steps": route["steps"],
                  "replay_steps": env.steps, "native_verified": bool(done),
                  "final_position": [info["state"]["x"], info["state"]["y"]]},
                 ensure_ascii=False))
