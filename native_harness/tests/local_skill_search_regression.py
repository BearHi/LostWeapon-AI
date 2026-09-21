"""Unknown edges are learned by bounded native outcomes and remain reversible."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from global_planner import Surface
from local_skill_search import search_transition


class API:
    def __init__(self): self.x = 0
    def read_state(self):
        return {"x": float(self.x), "y": 0.0, "motion58": 0.0,
                "38": 0, "c0": 0, "b0": 0}
    def save_state(self): return self.x
    def restore_state(self, value): self.x = value


class Planner:
    def surface_for_player(self, state):
        return Surface(1, 0, 2, 3) if state["x"] >= 16 else Surface(0, 0, 0, 1)


class Env:
    def __init__(self):
        self.api = API(); self.planner = Planner(); self.steps = 0
        self.visited = set(); self.global_visits = {}; self.last_keys = ()
        self.last_goal_distance = 0.0
    def step(self, action):
        self.api.x += 8 if action == 2 else 0; self.steps += 1
        return None, 0.0, False, False, {"state": self.api.read_state()}


target = Surface(1, 0, 2, 3)
env = Env(); found = search_transition(env, target, max_depth=3, beam_width=3,
                                       actions=(0, 2), commit=True)
assert found["native_verified"] and found["actions"] == [2, 2] and env.api.x == 16
env = Env(); missed = search_transition(env, Surface(2, 0, 9, 10), max_depth=2,
                                        beam_width=2, actions=(0, 2))
assert not missed["native_verified"] and env.api.x == 0 and env.steps == 0
print({"ok": True, "learned": found["actions"], "failed_branch_restored": True})
