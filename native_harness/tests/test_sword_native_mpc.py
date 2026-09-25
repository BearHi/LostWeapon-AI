from __future__ import annotations

import unittest

from sword_native_mpc import SwordNativeMPC, generate_primitives
from sword_live_navigation import hysteretic_horizontal as _hysteretic_horizontal


def world_with_ladders():
    cells = []
    for x, y0, y1 in ((11, 23, 33), (16, 34, 49), (23, 16, 27),
                      (35, 23, 33), (50, 34, 49), (53, 12, 22)):
        cells.extend([[x, y] for y in range(y0, y1 + 1)])
    return {"size": [60, 60], "runtime": {"climbable_cells": cells,
             "collision_grid": [0] * 3600},
            "room": {"global_wind_active": False}}


class SwordNativeMpcTests(unittest.TestCase):
    def test_grounded_candidates_cover_walk_jump_and_nearby_ladder(self):
        world = world_with_ladders()
        state = {"x": 23 * 32 + 16, "y": 22 * 32,
                 "38": 0, "74": -1, "dc": 0}
        target = {"x": 48 * 32, "y": 10 * 32}
        primitives = generate_primitives(world, state, target, False)
        names = {name for p in primitives for name in (p.name, *p.aliases)}
        self.assertIn("walk", names)
        self.assertIn("running_jump", names)
        self.assertIn("jump", names)
        self.assertIn("ladder_ascend", names)
        self.assertIn("ladder_descend", names)
        self.assertIn("safe_drop_probe", names)

    def test_global_wind_parachute_candidate_is_conditional(self):
        world = world_with_ladders()
        airborne = {"x": 500, "y": 700, "38": 9, "74": -1, "dc": 0}
        off = generate_primitives(world, airborne, None, False)
        on = generate_primitives(world, airborne, None, True)
        self.assertNotIn("wind_parachute_up_hold", {p.name for p in off})
        self.assertIn("wind_parachute_up_hold", {p.name for p in on})
        self.assertTrue(all(p.condition == "observed_global_wind_active"
                            for p in on if p.name == "wind_parachute_up_hold"))

    def test_same_surface_deadzone_and_hysteresis_suppress_direction_flip(self):
        world = world_with_ladders()
        state = {"x": 500, "y": 600, "38": 0, "74": -1, "dc": 0}
        near = {"x": 480, "y": 600}
        primitives = generate_primitives(world, state, near, False,
                                         previous_direction="RIGHT")
        self.assertFalse(any("LEFT" in p.keys or "RIGHT" in p.keys
                             for p in primitives))
        far_left = {"x": 450, "y": 600}
        primitives = generate_primitives(world, state, far_left, False,
                                         previous_direction="RIGHT")
        self.assertEqual(primitives[0].keys, ("LEFT",))

    def test_live_baseline_horizontal_hysteresis(self):
        self.assertIsNone(_hysteretic_horizontal(18, "RIGHT"))
        self.assertIsNone(_hysteretic_horizontal(-35, "RIGHT"))
        self.assertEqual(_hysteretic_horizontal(-48, "RIGHT"), "LEFT")

    def test_floor_trap_event_is_rejected(self):
        planner = object.__new__(SwordNativeMPC)
        planner.height = 60
        planner.world = {"runtime": {"collision_grid": [0] * 3600},
                         "room": {"global_wind_active": False}}
        planner.visited_cells = set()
        planner.wind_active = False
        start = {"x": 500, "y": 1500, "hp": 100, "7c": 0,
                 "anchor_x": 500, "anchor_y": 1500}
        trap = dict(start, y=1800, **{"7c": 7})
        score, reason = planner._score([start, trap], None, None)
        self.assertLess(score, -100_000)
        self.assertEqual(reason, "stage07_type220_event7")


if __name__ == "__main__":
    unittest.main()
