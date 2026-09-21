"""Branch replay must commit only a native-confirmed target landing."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from global_planner import Surface
from skill_replay import replay_candidate


class FakeAPI:
    def __init__(self): self.value = 0
    def save_state(self): return self.value
    def restore_state(self, value): self.value = value
    def read_state(self): return {"x": float(self.value), "y": 0.0}


class FakePlanner:
    def surface_for_player(self, state):
        return Surface(1, 4, 4, 6) if state["x"] >= 2 else Surface(0, 6, 1, 3)


class FakeEnv:
    def __init__(self):
        self.api = FakeAPI(); self.planner = FakePlanner(); self.steps = 0
        self.visited = set(); self.global_visits = {}; self.last_keys = ()
        self.last_goal_distance = 0.0
    def step(self, action):
        self.api.value += 1; self.steps += 1
        state = self.api.read_state()
        return None, 0.0, False, False, {"state": state}


row = {"actions_rle": [[1, 3]]}
target = Surface(1, 4, 4, 6)
env = FakeEnv()
probe = replay_candidate(env, target, row)
assert probe["native_verified"] and probe["steps"] == 2 and env.api.value == 0
committed = replay_candidate(env, target, row, commit=True)
assert committed["native_verified"] and env.api.value == 2 and env.steps == 2
wrong = replay_candidate(env, Surface(2, 3, 7, 8), row, commit=True)
assert not wrong["native_verified"] and env.api.value == 2 and env.steps == 2
print({"ok": True, "probe_restored": True, "commit_after_landing": True})
