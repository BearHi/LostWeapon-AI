from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from native_env import LostWeaponEnv

env = LostWeaponEnv(ROOT / "private_snapshots" / "hun5_live.zip",
                    ROOT.parent / "훈련용맵" / "훈5.LMF",
                    action_repeat=2, max_steps=600)

for roll_steps in (1, 2, 3, 4, 6, 8, 12, 16, 24):
    env.reset(); done = False; maximum_x = -1; opened = False
    sequence = [9] * roll_steps + [11] * 220
    for step, action in enumerate(sequence, 1):
        _obs, _reward, done, truncated, info = env.step(action)
        state = info["state"]
        maximum_x = max(maximum_x, float(state["x"]))
        opened = opened or bool(state["dc"])
        if done or (step > roll_steps + 5 and float(state["x"]) == 144.0):
            break
    print({"roll_steps": roll_steps, "success": done, "steps": step,
           "max_x": maximum_x, "opened": opened, "final": info["state"]}, flush=True)
    if done:
        break
