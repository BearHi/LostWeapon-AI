"""Generic native speed planner must beat walking and avoid the gap."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_env import LostWeaponEnv
from physics_first_planner import fastest_horizontal_route
from snapshot_selector import snapshot_for_map

root = Path(__file__).resolve().parents[1]
for name, expected_steps, expected_first in (
        ("훈1.LMF", 53, 9), ("훈2.LMF", 54, 7),
        ("훈3.LMF", 63, 7), ("훈4.LMF", 58, 6)):
    lmf = root.parent / "훈련용맵" / name
    env = LostWeaponEnv(snapshot_for_map(root, lmf), lmf,
                        action_repeat=2, max_steps=130)
    result = fastest_horizontal_route(env)
    assert result["verified"], (name, result["trials"])
    assert len(result["actions"]) == expected_steps, (name, result["trials"])
    assert result["actions"][0] == expected_first
    if name == "훈3.LMF":
        roll_only = result["trials"][0]
        assert roll_only["reason"] == "respawn" and roll_only["steps"] < 30
    env.reset()
    for action in result["actions"]:
        _, _, done, _, _ = env.step(action)
    assert done, name
    print("PASS", name, len(result["actions"]), result["trials"], flush=True)
