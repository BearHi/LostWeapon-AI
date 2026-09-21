"""Regression checks for contact-based surface transition extraction."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from global_planner import GlobalMapPlanner
from transition_library import compose_surface_path, extract_transitions


width, height = 8, 8
grid = [0] * (width * height)
for x in range(1, 4):
    grid[6 * width + x] = 1
for x in range(4, 7):
    grid[4 * width + x] = 1
planner = GlobalMapPlanner(width, height, [], grid)

# The native collision anchor equals the supporting surface's pixel Y.
# Passing above the upper platform during a jump must not be mistaken for a
# landing on it.
ground = {"x": 64.0, "y": 192.0}
airborne = {"x": 144.0, "y": 110.0}
landed = {"x": 144.0, "y": 128.0}
assert planner.surface_for_player(ground).y == 6
assert planner.surface_for_player(airborne) is None
assert planner.surface_for_player(landed).y == 4

states = [ground, {"x": 96.0, "y": 170.0}, airborne, landed]
transitions = extract_transitions(planner, states, [1, 2, 3])
assert len(transitions) == 1
assert transitions[0]["source"] == [6, 1, 3]
assert transitions[0]["target"] == [4, 4, 6]
assert transitions[0]["steps"] == 3
source_type = type(planner.surfaces[0])
translated_source = source_type(10, 10, 20, 22)
translated_target = source_type(11, 8, 23, 25)
row = {**transitions[0], "action_repeat": 2}
library = {"schema": 3, "skills": [row]}
matches = compose_surface_path(library, [translated_source, translated_target],
                               action_repeat=2, start_offsets=[1.0])
assert len(matches) == 1 and matches[0][0] is row
assert compose_surface_path(library, [translated_source, translated_target],
                            action_repeat=1, start_offsets=[1.0]) == []
raised_target = source_type(12, 7, 23, 25)
from transition_library import find_candidates
assert find_candidates(library, translated_source, raised_target,
                       action_repeat=2, start_from_left=1.0) == []
assert find_candidates(library, translated_source, raised_target,
                       action_repeat=2, start_from_left=1.0,
                       max_dy_error=1) == [row]
print({"ok": True, "transitions": len(transitions)})
