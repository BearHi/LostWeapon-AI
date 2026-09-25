"""Offline observations only: never start a Client or native emulator."""
from __future__ import annotations

import unittest
from dataclasses import asdict

from sword_live_navigation import decide_live_action, _route_action
from sword_live_route_feedback import LiveRouteProgressGuard
from sword_navigation_graph import RouteEdge, Stage07RouteGraph
from sword_stage07_world import load_stage07_static_world


def player(x, y, identity="own", state38=7, ladder=-1):
    return {"pos": [x, y], "hp": 100, "identity_key": identity,
            "state": {"0x38": state38, "0x74": ladder, "0xdc": 0, "0xc0": 0}}


def graph_fixture():
    size = 20
    grid = [0] * (size * size)
    for y, x0, x1 in ((4, 4, 8), (8, 2, 10), (12, 3, 12)):
        for x in range(x0, x1):
            grid[y * size + x] = 1
    return Stage07RouteGraph({"size": [size, size], "runtime": {
        "collision_grid": grid, "climbable_cells": []}})


class LiveRouteFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.graph = graph_fixture()
        self.own = player(192, 128)
        self.target = player(192, 256, "opponent")
        self.edge = asdict(RouteEdge("surface:4:4-7", "surface:8:2-9",
                                     "airborne_horizontal_transition", (192, 256)))
        self.guard = LiveRouteProgressGuard(stuck_seconds=1, attempt_seconds=3)

    def start(self, *, sent=True, keys=("LEFT",)):
        self.guard.record_action(0, self.own, self.edge, graph=self.graph,
                                 target=self.target, keys=keys, sent=sent)

    def observe(self, now, **kwargs):
        return self.guard.observe(now, self.own, graph=self.graph, target=self.target,
                                  control_available=kwargs.get("control_available", True))

    def excluded(self, now=10):
        return self.guard.excluded_edges(now, graph=self.graph, target=self.target)

    def test_grounded_air_transition_leaves_ledge_even_when_target_x_matches(self):
        keys, edge = _route_action(self.graph, {"path": [RouteEdge(**self.edge)]}, self.own)
        self.assertTrue(keys)
        self.assertEqual(edge["phase"], "leave_source_ledge")
        self.assertNotEqual(edge["control_waypoint"][0], 192)
        self.assertNotIn("DOWN", keys)

    def test_unsent_and_shadow_decisions_never_become_failed_edges(self):
        self.start(sent=False)
        self.assertIsNone(self.observe(20))
        self.assertEqual(self.excluded(), ())

    def test_ledge_exit_does_not_turn_back_before_observed_fall(self):
        self.own["pos"] = [112, 128]
        keys, edge = _route_action(self.graph, {"path": [RouteEdge(**self.edge)]}, self.own)
        self.assertEqual(keys, ("LEFT",))
        self.assertEqual(edge["phase"], "leave_source_ledge")
        self.own["pos"] = [112, 140]
        self.own["state"]["0x38"] = 9
        keys, edge = _route_action(self.graph, {"path": [RouteEdge(**self.edge)]}, self.own)
        self.assertEqual(keys, ("RIGHT",))
        self.assertEqual(edge["phase"], "air_steer")

    def test_safe_drop_keeps_departure_direction_until_falling(self):
        edge = RouteEdge(self.edge["source"], self.edge["target"], "safe_drop", (120, 256))
        self.own["pos"] = [120, 128]
        keys, _ = _route_action(self.graph, {"path": [edge]}, self.own)
        self.assertEqual(keys, ("LEFT",))

    def test_no_input_does_not_start_new_attempt(self):
        self.start(keys=())
        self.assertIsNone(self.guard.continuation_edge())

    def test_stuck_failure_does_not_expire_after_five_seconds(self):
        self.start()
        event = self.observe(1.1)
        self.assertEqual(event["status"], "failed")
        self.assertEqual(event["reason"], "no_route_progress")
        self.assertEqual(len(self.excluded(6.2)), 1)
        self.assertEqual(self.excluded(6.2), self.excluded(100))

    def test_target_region_change_allows_other_context_but_return_stays_blocked(self):
        self.start()
        self.observe(1.1)
        self.target["pos"] = [192, 384]
        self.assertEqual(self.excluded(), ())
        self.target["pos"] = [192, 256]
        self.assertEqual(len(self.excluded()), 1)

    def test_manual_override_cancels_without_learning_failure(self):
        self.start()
        event = self.observe(2, control_available=False)
        self.assertEqual(event["status"], "cancelled")
        self.assertEqual(self.excluded(), ())

    def test_damage_cancels_instead_of_attributing_knockback_to_route(self):
        self.start()
        self.own["hp"] = 90
        self.assertEqual(self.observe(.1)["reason"], "damage_confounds_navigation")
        self.assertEqual(self.excluded(), ())

    def test_combat_override_does_not_keep_timing_navigation(self):
        self.start()
        self.guard.record_action(.1, self.own, self.edge, graph=self.graph,
                                 target=self.target, keys=("Z",), sent=False)
        self.assertIsNone(self.observe(20))
        self.assertEqual(self.excluded(), ())

    def test_airborne_projection_on_target_never_counts_as_landing(self):
        self.start()
        self.own["pos"] = [192, 256]
        self.own["state"]["0x38"] = 9
        for now in (.1, .2):
            event = self.observe(now)
            self.assertNotEqual((event or {}).get("status"), "landed")
        self.assertIsNotNone(self.guard.continuation_edge())

    def test_target_landing_requires_two_stable_ground_observations(self):
        self.start()
        self.own["pos"] = [192, 200]
        self.own["state"]["0x38"] = 9
        self.observe(.1)
        self.own["pos"] = [192, 256]
        self.own["state"]["0x38"] = 7
        self.assertNotEqual((self.observe(.2) or {}).get("status"), "landed")
        self.assertEqual(self.observe(.3)["status"], "landed")
        self.assertEqual(self.edge["verification"], "native_required")

    def test_wrong_surface_landing_fails_pending_edge(self):
        self.start()
        self.own["pos"] = [192, 300]
        self.own["state"]["0x38"] = 9
        self.observe(.1)
        self.own["pos"] = [192, 384]
        self.own["state"]["0x38"] = 7
        self.observe(.2)
        self.assertEqual(self.observe(.3)["reason"], "landed_wrong_surface")
        self.assertEqual(len(self.excluded()), 1)

    def test_progress_requires_improvement_not_back_and_forth_jitter(self):
        self.start()
        self.own["pos"] = [180, 128]
        self.observe(.3)
        self.own["pos"] = [192, 128]
        self.observe(.6)
        self.own["pos"] = [180, 128]
        self.assertEqual(self.observe(1.1)["reason"], "no_route_progress")

    def test_attempt_deadline_bounds_motion_without_completion(self):
        self.start()
        self.own["state"]["0x38"] = 9
        for i in (1, 2, 3):
            self.own["pos"] = [192, 128 + 10 * i]
            self.observe(i * .8)
        self.assertEqual(self.observe(3.1)["reason"], "transition_deadline_exceeded")

    def test_ladder_entry_requires_actual_matching_ladder_state(self):
        self.graph = Stage07RouteGraph({"size": [20, 20], "runtime": {
            "collision_grid": [0] * 400, "climbable_cells": [[6, 5], [6, 6]]}})
        self.edge = asdict(RouteEdge("surface", "ladder:0", "ladder_attach", (208, 160)))
        self.start(keys=("UP",))
        self.own["pos"] = [208, 160]
        self.assertNotEqual((self.observe(.1) or {}).get("status"), "ladder_entered")
        self.own["state"]["0x74"] = 1
        self.assertEqual(self.observe(.2)["status"], "ladder_entered")

    def test_inflight_edge_continues_instead_of_replanning_from_nearest_surface(self):
        self.own["pos"] = [192, 200]
        self.own["state"]["0x38"] = 9
        mode, keys, nav = decide_live_action(self.graph, self.own, self.target,
            now=1, started=0, map_verified=True, active_edge=self.edge)
        self.assertEqual((mode, keys), ("NAV_TRANSITION_WAIT", ()))
        self.assertEqual(nav["next_edge"]["source"], self.edge["source"])

    def test_jump_releases_up_after_takeoff(self):
        edge = RouteEdge("low", "high", "jump_or_running_jump", (220, 100))
        self.own["state"]["0x38"] = 9
        keys, _ = _route_action(self.graph, {"path": [edge]}, self.own)
        self.assertNotIn("UP", keys)

    def test_roll_state_does_not_request_another_jump(self):
        self.own["state"]["0xc0"] = 4
        mode, keys, _ = decide_live_action(self.graph, self.own, self.target,
            now=1, started=0, map_verified=True, active_edge=self.edge)
        self.assertEqual((mode, keys), ("NAV_MOTION_WAIT", ()))

    def test_non_executable_shortcut_is_skipped_for_alternate_route(self):
        bad = RouteEdge(self.edge["source"], self.edge["target"], "unsupported", (192, 256))
        good = RouteEdge(self.edge["source"], self.edge["target"], "safe_drop", (120, 256))
        self.graph.edges = (bad, good)
        # Unknown primitive has cost 3; force it ahead by replacing walk with
        # a no-action walk at the current X, followed by a usable parallel drop.
        bad = RouteEdge(bad.source, bad.target, "walk", (192, 256))
        self.graph.edges = (bad, good)
        mode, keys, nav = decide_live_action(self.graph, self.own, self.target,
                                             now=1, started=0, map_verified=True)
        self.assertEqual(mode, "NAVIGATE")
        self.assertEqual(keys, ("LEFT",))
        self.assertEqual(nav["next_edge"]["primitive"], "safe_drop")
        self.assertTrue(nav["non_executable_edges"])

    def test_stage07_trial2_stall_position_selects_alternative_after_failure(self):
        graph = Stage07RouteGraph(load_stage07_static_world())
        own, target = player(212, 736), player(187, 1600, "opponent")
        _, keys, nav = decide_live_action(graph, own, target, now=0, started=0, map_verified=True)
        edge = nav["next_edge"]
        self.assertEqual(edge["primitive"], "airborne_horizontal_transition")
        self.assertEqual(keys, ("LEFT",))
        self.assertEqual(edge["control_waypoint"], [144, 736])
        guard = LiveRouteProgressGuard(stuck_seconds=1)
        guard.record_action(0, own, edge, graph=graph, target=target, keys=keys, sent=True)
        self.assertEqual(guard.observe(1.1, own, graph=graph, target=target,
                                      control_available=True)["status"], "failed")
        for now in (1.1, 6.2, 30):
            mode, keys, nav = decide_live_action(graph, own, target, now=now, started=0,
                map_verified=True, excluded_edges=guard.excluded_edges(now, graph=graph, target=target))
            self.assertEqual(mode, "NAVIGATE")
            self.assertNotEqual(guard.edge_key(nav["next_edge"]), guard.edge_key(edge))
            self.assertEqual(nav["next_edge"]["primitive"], "safe_drop")
            self.assertEqual(keys, ("RIGHT",))


if __name__ == "__main__":
    unittest.main()
