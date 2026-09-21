from pathlib import Path
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from combat_env import LostWeaponCombatEnv

env = LostWeaponCombatEnv(HARNESS / "private_snapshots/team_p2p_combat_live.zip",
                          peer_snapshot=HARNESS / "private_snapshots/team_slot1_live.zip",
                          max_steps=4)
observations, info = env.reset(spawn_distance=96)
assert observations[0].shape == observations[1].shape == (env.observation_size,)
assert abs(info["players"][1]["x"] - info["players"][0]["x"] - 96) < 1e-9
for _ in range(4):
    observations, rewards, done, truncated, info = env.step({0: 12, 1: 12})
assert truncated and set(rewards) == {0, 1}
print("PASS", env.observation_size, env.action_size, rewards)
