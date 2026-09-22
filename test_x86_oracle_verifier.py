"""test_x86_oracle_verifier.py - Phase 3A Test Suite.

Verifies:
1. 10-Trial Snapshot Determinism:
   - Initial memory hash bit-exact restoration across all 10 trials.
   - Terminal type, terminal tick, coordinates, and state signature 100% invariant.
2. 3-Case Ground-Truth Regression:
   - Case 1 (Clear): Known sequence on stg1_01_gap2 -> SUCCESS (flag 0x8c == 1).
   - Case 2 (Death): Suicide walk into pit -> DEATH (player 7c == -1).
   - Case 3 (Timeout): Idle sequence -> TIMEOUT.
   - Case 4 (Invalid): Unknown action input -> INVALID.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
HARNESS_DIR = ROOT / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from snapshot_selector import snapshot_for_map
from x86_oracle_verifier import X86OracleVerifier


class TestX86OracleVerifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.map_path = ROOT / "훈련용맵" / "physics_curriculum" / "stg1_01_gap2.LMF"
        cls.snap_path = snapshot_for_map(HARNESS_DIR, cls.map_path)
        cls.verifier = X86OracleVerifier(cls.snap_path, cls.map_path)

        # Build clear sequence for stg1_01_gap2 (165 ticks total, jump across 2-tile gap)
        # Walk right, jump at t=25 for 28 ticks, then continue right
        cls.clear_actions = []
        for t in range(165):
            if 25 <= t < 25 + 28:
                cls.clear_actions.append(("RIGHT", "UP"))
            else:
                cls.clear_actions.append(("RIGHT",))

        # Suicide walk: walk right continuously into the 2-tile gap without jumping
        cls.suicide_actions = [("RIGHT",) for _ in range(100)]

        # Idle: do nothing
        cls.idle_actions = [() for _ in range(50)]

    def test_case_1_clear_success(self):
        """Case 1: Known clear sequence yields SUCCESS via native flag collision."""
        res = self.verifier.run_trial(self.clear_actions, max_ticks=200)
        self.assertEqual(res["terminal_type"], "SUCCESS")
        self.assertEqual(res["terminal_tick"], 158)
        self.assertIn("flag[rec_31].offset_0x8c==1", res["evidence_source"])
        self.assertEqual(res["final_position"], (748.0, 448.0))

    def test_case_2_suicide_death(self):
        """Case 2: Walking into pit yields DEATH via native player respawn flag (7c == -1)."""
        res = self.verifier.run_trial(self.suicide_actions, max_ticks=200)
        self.assertEqual(res["terminal_type"], "DEATH")
        self.assertEqual(res["terminal_tick"], 68)
        self.assertIn("offset_0x7c==-1", res["evidence_source"])
        # Coordinates at death tick reset to spawn
        self.assertEqual(res["final_position"], (112.0, 447.0))

    def test_case_3_idle_timeout(self):
        """Case 3: Idle inputs yield TIMEOUT."""
        res = self.verifier.run_trial(self.idle_actions, max_ticks=50)
        self.assertEqual(res["terminal_type"], "TIMEOUT")
        self.assertEqual(res["terminal_tick"], 50)
        self.assertIn("tick_limit_reached", res["evidence_source"])

    def test_case_4_invalid_action(self):
        """Case 4: Action containing invalid key yields INVALID."""
        invalid_seq = [("FLY_HACK",)]
        res = self.verifier.run_trial(invalid_seq, max_ticks=50)
        self.assertEqual(res["terminal_type"], "INVALID")
        self.assertEqual(res["terminal_tick"], 0)
        self.assertIn("unknown_keys_in_action", res["evidence_source"])

    def test_determinism_10_trials(self):
        """Determinism: 10 repeated trials produce 100% bit-exact results and memory hashes."""
        results = []
        for i in range(10):
            res = self.verifier.run_trial(self.clear_actions, max_ticks=200)
            results.append(res)

        first = results[0]
        self.assertEqual(first["terminal_type"], "SUCCESS")
        for i, r in enumerate(results[1:], start=2):
            self.assertEqual(
                r["terminal_type"], first["terminal_type"],
                f"Trial {i} terminal_type differs"
            )
            self.assertEqual(
                r["terminal_tick"], first["terminal_tick"],
                f"Trial {i} terminal_tick differs: {r['terminal_tick']} != {first['terminal_tick']}"
            )
            self.assertEqual(
                r["final_position"], first["final_position"],
                f"Trial {i} final_position differs: {r['final_position']} != {first['final_position']}"
            )
            self.assertEqual(
                r["final_motion_state"], first["final_motion_state"],
                f"Trial {i} final_motion_state differs"
            )
            self.assertEqual(
                r["initial_snapshot_signature"], first["initial_snapshot_signature"],
                f"Trial {i} initial memory hash differs"
            )
            self.assertEqual(
                r["final_state_signature"], first["final_state_signature"],
                f"Trial {i} final state hash differs"
            )


if __name__ == "__main__":
    unittest.main()
