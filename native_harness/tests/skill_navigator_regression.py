"""Known relative skills chain only after native branch landing validation."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from global_planner import GlobalMapPlanner
from skill_navigator import chain_known_transitions, try_known_transition
from transition_library import extract_transitions, load_library


def state(x, y):
    return {"x": float(x), "y": float(y), "motion58": 0.0, "38": 0,
            "68": 0, "74": 0, "7c": 0, "80": 0, "b0": 0, "c0": 0, "dc": 0}


width = height = 8
grid = [0] * (width * height)
for x in range(1, 4): grid[6 * width + x] = 1
for x in range(4, 7): grid[4 * width + x] = 1
planner = GlobalMapPlanner(width, height, [(140, 5, 3)], grid)
route_states = [state(64, 192), state(96, 170), state(144, 128)]
row = extract_transitions(planner, route_states, [1, 1])[0]
row.update({"action_repeat": 2, "verification": "extracted_from_native_verified_clear"})
library = {"schema": 3, "skills": [row]}


class API:
    def __init__(self): self.index = 0
    def read_state(self): return route_states[self.index]
    def save_state(self): return self.index
    def restore_state(self, value): self.index = value


class Env:
    def __init__(self):
        self.api = API(); self.planner = planner; self.action_repeat = 2
        self.steps = 0; self.visited = set(); self.global_visits = {}
        self.last_keys = (); self.last_goal_distance = 0.0
    def step(self, action):
        self.api.index += 1; self.steps += 1
        return None, 0.0, False, False, {"state": self.api.read_state()}
    def reached_goal(self, state): return state["x"] >= 144


env = Env()
result = try_known_transition(env, library)
assert result["status"] == "advanced" and env.api.index == 2
env = Env(); library["skills"][0]["actions_rle"] = [[1, 1]]
adapted = try_known_transition(env, library)
assert adapted["status"] == "advanced" and adapted["adapted"] and env.api.index == 2
env = Env()
failed = try_known_transition(env, {"schema": 3, "skills": []})
assert failed["status"] == "needs_new_exploration" and env.api.index == 0
env = Env()
excluded = try_known_transition(env, library, excluded_targets={(4, 4, 6)})
assert excluded["status"] == "needs_new_exploration" and env.api.index == 0
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "skills.json"
    env = Env(); empty = {"schema": 3, "skills": []}
    learned = chain_known_transitions(
        env, empty, explore_unknown=True, search_depth=3, beam_width=3,
        library_path=path, source_map_sha256="fixture", source_episode=1)
    assert learned["status"] == "goal_reached"
    assert len(load_library(path)["skills"]) == 1
print({"ok": True, "known_edge": "native_committed",
       "short_skill": "native_adapted", "new_skill": "persisted"})
