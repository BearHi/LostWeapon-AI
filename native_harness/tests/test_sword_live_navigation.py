from __future__ import annotations

import unittest
import struct

from sword_live_navigation import (choose_target, decide_live_action,
                                   incoming_attack_candidate,
                                   LiveRouteProgressGuard,
                                   needs_parachute_recovery,
                                   OpponentBehaviorWindows,
                                   parachute_glide_action, _route_action)
from sword_navigation_graph import RouteEdge, Stage07RouteGraph
from sword_live_bot import runtime_stage07_match


def two_level_world():
    width = height = 12
    grid = [0] * (width * height)
    for x in range(8, 11):
        grid[10 * width + x] = 1
    for x in range(7, 11):
        grid[3 * width + x] = 1
    ladders = [[10, row] for row in range(4, 10)]
    for x, y in ladders:
        grid[y * width + x] = 3
    return {"size": [width, height],
            "runtime": {"collision_grid": grid, "climbable_cells": ladders}}


def player(slot, x, y, identity, *, policy_targetable=True, hp=100, facing=0):
    return {"room_slot": slot, "global_user_index": slot,
            "identity_key": identity, "nickname": identity,
            "present": True, "policy_targetable": policy_targetable,
            "hp": hp, "pos": [x, y],
            "state": {"0x74": -1, "0xc0": 0, "0xb0": facing}}


class SwordLiveNavigationTests(unittest.TestCase):
    def setUp(self):
        self.graph = Stage07RouteGraph(two_level_world())

    def test_idle_until_a_policy_eligible_opponent_appears(self):
        own = player(0, 288, 320, "own")
        self.assertIsNone(choose_target([own], 0, own))
        mode, keys, nav = decide_live_action(
            self.graph, own, None, now=1, started=0, map_verified=True)
        self.assertEqual((mode, keys), ("WAIT_OPPONENT", ()))
        self.assertEqual(nav["reason"], "no_policy_targetable_opponent")

    def test_sticky_target_survives_while_eligible_and_jaja_is_excluded(self):
        own = player(0, 288, 320, "own")
        near = player(1, 300, 320, "near")
        selected = player(2, 500, 320, "selected")
        jaja = player(3, 290, 320, "sleep", policy_targetable=False)
        self.assertIs(choose_target([own, near, selected, jaja], 0, own,
                                    "selected"), selected)
        self.assertIs(choose_target([own, near, jaja], 0, own,
                                    "selected"), near)

    def test_different_surface_uses_first_ladder_route_edge(self):
        own = player(0, 288, 320, "own")
        target = player(1, 256, 96, "target")
        mode, keys, nav = decide_live_action(
            self.graph, own, target, now=1, started=0, map_verified=True)
        self.assertEqual(mode, "NAVIGATE")
        self.assertEqual(nav["next_edge"]["primitive"], "ladder_attach")
        self.assertEqual(keys, ("RIGHT",))
        self.assertTrue(nav["route_connected_to_target"])

    def test_ladder_alignment_can_reverse_inside_horizontal_hysteresis(self):
        own = player(0, 298, 320, "own")
        target = player(1, 256, 96, "target")
        mode, keys, nav = decide_live_action(
            self.graph, own, target, now=1, started=0,
            previous_direction="LEFT", map_verified=True)
        self.assertEqual(mode, "NAVIGATE")
        self.assertEqual(nav["next_edge"]["primitive"], "ladder_attach")
        self.assertEqual(keys, ("RIGHT",))

    def test_ladder_attach_does_not_press_up_before_center_alignment(self):
        edge = RouteEdge("surface", "ladder", "ladder_attach", (528.0, 1600.0))
        keys, _ = _route_action(
            self.graph, {"path": [edge]}, {"pos": [551.0, 1600.0]},
            previous_direction="LEFT")
        self.assertEqual(keys, ("LEFT",))

    def test_stacked_different_height_surfaces_choose_an_exposed_drop_edge(self):
        width = height = 16
        grid = [0] * (width * height)
        for x in range(4, 7):
            grid[4 * width + x] = 1
        for x in range(4, 9):
            grid[8 * width + x] = 1
        graph = Stage07RouteGraph({
            "size": [width, height],
            "runtime": {"collision_grid": grid, "climbable_cells": []}})
        own = player(0, 160, 128, "own")
        target = player(1, 240, 256, "target")
        mode, keys, nav = decide_live_action(
            graph, own, target, now=1, started=0, map_verified=True)
        self.assertEqual(mode, "NAVIGATE")
        self.assertEqual(nav["next_edge"]["primitive"], "safe_drop")
        self.assertEqual(nav["next_edge"]["waypoint"], [232.0, 256.0])
        self.assertEqual(keys, ("RIGHT",))

    def test_parachute_glide_releases_vertical_keys(self):
        own = player(0, 100, 200, "own")
        target = player(1, 240, 400, "target")
        keys, evidence = parachute_glide_action(
            own, target,
            {"next_edge": {"waypoint": [140.0, 400.0]}},
            previous_direction="LEFT")
        self.assertEqual(keys, ("RIGHT",))
        self.assertTrue(evidence["vertical_keys_released"])
        self.assertNotIn("UP", keys)
        self.assertNotIn("DOWN", keys)

    def test_safe_drop_does_not_press_down_roll_key(self):
        edge = RouteEdge("upper", "lower", "safe_drop", (320.0, 640.0))
        keys, _ = _route_action(
            self.graph, {"path": [edge]}, {"pos": [316.0, 320.0]},
            previous_direction="LEFT")
        self.assertEqual(keys, ("RIGHT",))
        self.assertNotIn("DOWN", keys)

    def test_players_on_same_ladder_chase_vertically_instead_of_replanning_to_floor(self):
        own = player(0, 336, 200, "own")
        target = player(1, 336, 280, "target")
        own["state"]["0x74"] = 1
        target["state"]["0x74"] = 1
        mode, keys, nav = decide_live_action(
            self.graph, own, target, now=1, started=0, map_verified=True)
        self.assertEqual(mode, "COMBAT_LADDER_APPROACH")
        self.assertEqual(keys, ("DOWN",))
        self.assertEqual(nav["reason"], "both_players_on_same_ladder")

    def test_stalled_dispatched_edge_stays_rejected_in_same_context(self):
        guard = LiveRouteProgressGuard(stuck_seconds=1.0)
        own = player(0, 336, 200, "own")
        target = player(1, 256, 96, "target")
        edge = {"source": "surface:a", "target": "ladder:0",
                "primitive": "ladder_attach", "condition": "always", "waypoint": [336, 200]}
        guard.record_action(10, own, edge, graph=self.graph, target=target,
                            keys=("UP",), sent=True)
        self.assertIsNone(guard.observe(10.9, own, graph=self.graph, target=target,
                                        control_available=True))
        event = guard.observe(11.1, own, graph=self.graph, target=target, control_available=True)
        self.assertEqual(event["reason"], "no_route_progress")
        self.assertIn(("surface:a", "ladder:0", "ladder_attach", "always"),
                      guard.excluded_edges(11.1, graph=self.graph, target=target))
        self.assertEqual(guard.excluded_edges(11.1, graph=self.graph, target=target),
                         guard.excluded_edges(100, graph=self.graph, target=target))

    def test_parachute_recovery_requires_fall_without_support_and_dc_zero(self):
        falling_over_support = player(0, 288, 150, "own")
        falling_over_support["state"]["0x38"] = 9
        falling_over_gap = player(0, 160, 150, "own")
        falling_over_gap["state"]["0x38"] = 9
        already_nonzero_dc = player(0, 160, 150, "own")
        already_nonzero_dc["state"].update({"0x38": 9, "0xdc": 1})
        self.assertFalse(needs_parachute_recovery(
            self.graph, falling_over_support, previous_y=149))
        self.assertTrue(needs_parachute_recovery(
            self.graph, falling_over_gap, previous_y=149))
        self.assertFalse(needs_parachute_recovery(
            self.graph, falling_over_gap, previous_y=150))
        self.assertFalse(needs_parachute_recovery(
            self.graph, already_nonzero_dc, previous_y=149))

    def test_incoming_attack_candidate_checks_raw_state_facing_and_range(self):
        own = player(0, 288, 320, "own")
        attacker = player(1, 320, 320, "attacker", facing=1)
        attacker["state"]["0x38"] = 15
        candidate = incoming_attack_candidate(own, attacker)
        self.assertEqual(candidate["identity"], "attacker")
        self.assertEqual(candidate["roll_direction"], "LEFT")
        attacker["state"]["0xb0"] = 0
        self.assertIsNone(incoming_attack_candidate(own, attacker))
        attacker["state"]["0xb0"] = 1
        attacker["pos"] = [600, 320]
        self.assertIsNone(incoming_attack_candidate(own, attacker))

    def test_five_second_opponent_window_prefers_recent_incoming_swing(self):
        own = player(0, 288, 320, "own")
        attacker = player(1, 320, 320, "attacker", facing=1)
        attacker["state"]["0x38"] = 15
        idle = player(2, 300, 320, "idle")
        windows = OpponentBehaviorWindows(window_seconds=5.0)
        profiles, preferred, candidates = windows.update(
            1.0, own, [own, attacker, idle], 0)
        self.assertEqual(preferred, "attacker")
        self.assertEqual(len(candidates), 1)
        selected = choose_target([own, attacker, idle], 0, own,
                                 sticky_identity="idle",
                                 preferred_identity=preferred)
        self.assertIs(selected, attacker)
        attacker["state"]["0x38"] = 7
        _, preferred, candidates = windows.update(
            7.0, own, [own, attacker, idle], 0)
        self.assertIsNone(preferred)
        self.assertEqual(candidates, [])

    def test_refuses_input_until_exact_map_gate_is_passed(self):
        own = player(0, 288, 320, "own")
        target = player(1, 256, 96, "target")
        mode, keys, _ = decide_live_action(
            self.graph, own, target, now=1, started=0, map_verified=False)
        self.assertEqual((mode, keys), ("WAIT_STAGE07_MAP", ()))

    def test_same_surface_approach_and_attack_baseline(self):
        width = height = 24
        grid = [0] * (width * height)
        for x in range(4, 16):
            grid[10 * width + x] = 1
        graph = Stage07RouteGraph({
            "size": [width, height],
            "runtime": {"collision_grid": grid, "climbable_cells": []}})
        own = player(0, 192, 320, "own", facing=0)
        target = player(1, 320, 320, "target")
        mode, keys, _ = decide_live_action(
            graph, own, target, now=0.02, started=0, map_verified=True)
        self.assertEqual(mode, "COMBAT_APPROACH")
        self.assertEqual(keys, ("RIGHT",))

    def test_airborne_vertical_separation_keeps_horizontal_control_live(self):
        own = player(0, 290, 360, "own")
        target = player(1, 320, 500, "target")
        mode, keys, nav = decide_live_action(
            self.graph, own, target, now=1, started=0, map_verified=True)
        self.assertEqual(mode, "COMBAT_AIR_ALIGN")
        self.assertEqual(keys, ("RIGHT",))
        self.assertEqual(nav["reason"], "airborne_same_region_horizontal_alignment")

    def test_airborne_no_route_target_above_requests_jump_without_unbound_dy(self):
        class DisconnectedAirGraph:
            surfaces = ()

            @staticmethod
            def surface_at(_state, **_kwargs):
                return None

            @staticmethod
            def route_candidates(*_args, **_kwargs):
                return {"source": "surface:local", "target": "surface:target",
                        "path": []}

        own = player(0, 288, 360, "own")
        own["state"]["0x38"] = 7
        target = player(1, 292, 240, "target")
        mode, keys, nav = decide_live_action(
            DisconnectedAirGraph(), own, target,
            now=1, started=0, map_verified=True)
        self.assertEqual((mode, keys), ("COMBAT_JUMP_ALIGN", ("UP",)))
        self.assertEqual(nav["relative_dy"], -120.0)

    def test_live_map_gate_requires_exact_runtime_collision_grid(self):
        expected = [0] * 3600
        expected[10] = 1
        expected[11] = 3

        class ReaderStub:
            def __init__(self, cells):
                self.cells = cells

            def get(self, address, fmt):
                self.asserted = (address, fmt)
                return (0x10000,)

            def read(self, address, size):
                if address != 0x10000 or size != 7200:
                    raise AssertionError("unexpected collision grid read")
                return struct.pack("<3600H", *self.cells)

        matches, evidence = runtime_stage07_match(
            ReaderStub(expected), (60, 60), expected)
        self.assertTrue(matches)
        self.assertEqual(evidence["collision_cells"], 3600)

        changed = expected.copy()
        changed[11] = 1
        matches, evidence = runtime_stage07_match(
            ReaderStub(changed), (60, 60), expected)
        self.assertFalse(matches)
        self.assertEqual(evidence["mismatch_count"], 1)


if __name__ == "__main__":
    unittest.main()
