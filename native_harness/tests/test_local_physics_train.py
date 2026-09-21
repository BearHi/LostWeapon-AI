"""Focused contract tests; native integration is a separate --preflight run."""
import copy
from pathlib import Path
import random
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_physics_train import (Search, Store, programs, pack, unpack, TimeSliceComplete,
                                 learning_progress, adaptive_budget)
from native_env import ACTIONS


class FakeWorld:
    width, height = 100, 30
    records = [(49, 1, 2)]

    def __init__(self):
        self.api = self
        self.state = dict(x=0., y=64., motion58=0., **{
            "38": 9, "3c": 0, "68": 0, "74": 0, "b0": 0, "c0": 0, "dc": 0})
        self.clock = 0
        self.sent = []
        self.terrain = 0

    def read_state(self):
        return dict(self.state)

    def save_state(self):
        return {"state": dict(self.state), "clock": self.clock, "pages": {0: b"x"*4096}}

    def restore_state(self, snapshot):
        self.state = dict(snapshot["state"])
        self.clock = snapshot["clock"]

    def step(self, n, keys):
        self.clock += n
        self.sent.append(keys)
        self.state["x"] += n*(2*("RIGHT" in keys)-2*("LEFT" in keys))
        if "C" in keys and self.clock >= 5:
            self.state["dc"] = 1
        return self.read_state()

    def valid_action_indices(self, state):
        return list(range(len(ACTIONS)))

    def reached_goal(self, state):
        return state["x"] >= 24

    def _goal_distance(self, state):
        return abs(state["x"]-24)/32

    def _nearest_goal(self, state):
        return (1, 2)

    def navigation_view(self, state, size):
        return {"player_tile": [int(state["x"]//32), 2], "goal_tile": [1, 2],
                "cells": [[{"grids": [self.terrain, 0, 0, 0]} for _ in range(size)]
                          for _ in range(size)]}


class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.store = Store(self.path/"test.sqlite3", {"physics": "test"})
        self.args = SimpleNamespace(seed=1, minutes_per_map=1, stop_file=self.path/"STOP",
                                    map=Path("fixture.LMF"), cache_mb=1, horizon=12,
                                    max_steps=100, max_nodes=30, candidates=2, target_trials=2)
        self.env = FakeWorld()
        self.search = Search(self.env, self.store, self.args)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_memory_branch_and_cache_preserve_native_clock(self):
        a, route, reason = self.search.reach_prefix([2, 2])
        clock = self.env.clock
        self.search.step(1, a)
        b, _, why = self.search.reach_prefix([2, 2])
        self.assertEqual((a, reason), (b, why))
        self.assertEqual(clock, self.env.clock)
        self.assertEqual(self.search.cache_hits, 1)

    def test_goal_requires_clean_replay(self):
        self.env.state["x"] = 200
        self.assertFalse(self.search.accept_goal([0]))
        self.assertIsNone(self.store.get("best"))
        self.assertTrue(self.search.accept_goal([2]*6))
        self.assertEqual(len(unpack(self.store.get("best")["actions"])), 6)

    def test_context_distinguishes_geometry_facing_and_subcell(self):
        a = self.search.context(self.env.read_state(), [])
        self.env.terrain = 7
        b = self.search.context(self.env.read_state(), [])
        self.env.state["b0"] = 1
        c = self.search.context(self.env.read_state(), [])
        self.env.state["x"] = 1.
        d = self.search.context(self.env.read_state(), [])
        self.assertEqual(len({a, b, c, d}), 4)

    def test_chute_retries_native_deployment_then_keeps_direction(self):
        state, taken, _, reason = self.search.execute([("chute_LEFT", 8)], self.env.read_state(), 8)
        self.assertEqual(state["dc"], 1)
        self.assertEqual(ACTIONS[taken[-1]], ("LEFT",))
        self.assertLess(state["x"], 0)
        self.assertTrue(any("C" in keys for keys in self.env.sent[:4]))

    def test_damage_and_lava_are_not_blanket_banned(self):
        self.env.state["38"] = 17
        state, taken, _, reason = self.search.execute([(2, 6)], self.env.read_state(), 6)
        self.assertEqual(reason, "goal_region")
        self.assertEqual(len(taken), 6)

    def test_all_original_actions_and_compositions_present(self):
        pool = programs(random.Random(1), ACTIONS, 64)
        primitives = {phases[0][0] for name, phases in pool if name.startswith("primitive_")}
        self.assertEqual(primitives, set(range(len(ACTIONS))))
        self.assertTrue(any("turn_roll_chute" in name for name, _ in pool))
        self.assertTrue(any("weapon3_attack_jump" in name for name, _ in pool))

    def test_stop_and_time_budget(self):
        self.args.stop_file.touch()
        with self.assertRaises(InterruptedError):
            self.search.check()
        self.args.stop_file.unlink()
        self.search.deadline = time.monotonic()-1
        with self.assertRaises(TimeSliceComplete):
            self.search.check()

    def test_persistence_and_identity_guard(self):
        self.store.learn("context", "roll", 5)
        self.store.record("search", {"reason": "horizon", "actions": pack([2, 2, 0])})
        self.store.db.commit()
        other = Store(self.path/"test.sqlite3", {"physics": "test"})
        self.assertEqual(other.count(), 1)
        self.assertEqual(other.summary()["learned_context_skills"], 1)
        other.db.close()
        with self.assertRaises(ValueError):
            Store(self.path/"test.sqlite3", {"physics": "changed"})

    def test_trial_budget_never_overshoots(self):
        self.args.target_trials = 1
        self.store.add_node(self.env.read_state(), [], 1, 30)
        self.search.trial()
        self.assertEqual(self.store.count(), 1)

    def test_adaptive_budget_preserves_exploration_and_limits(self):
        self.assertEqual(adaptive_budget(dict(best=None, stale=2000),80),80)
        self.assertEqual(adaptive_budget(dict(best=40, stale=100),80),80)
        self.assertEqual(adaptive_budget(dict(best=40, stale=200),80),40)
        self.assertEqual(adaptive_budget(dict(best=40, stale=500),80),16)
        self.assertEqual(adaptive_budget(dict(best=40, stale=500),4),4)

    def test_stagnation_counts_only_search_trials(self):
        self.store.record('search', dict(reason='goal_region', improved=True))
        self.store.record('verification', dict(reason='goal_region'))
        self.store.record('search', dict(reason='horizon'))
        self.store.put('best',dict(actions=pack([2,2,0])))
        self.store.db.commit()
        self.assertEqual(learning_progress(self.path/'test.sqlite3'),dict(trials=2,best=3,stale=1))

    def test_session_deadline_is_enforced_inside_worker(self):
        self.args.session_end=time.time()-1
        search=Search(self.env,self.store,self.args)
        with self.assertRaises(TimeSliceComplete):
            search.check()


if __name__ == "__main__":
    unittest.main()
