"""test_bypass_verifier.py - Phase 3B Minimal Unit Test Suite.

Verifies:
1. Reference SUCCESS + Candidate SUCCESS -> KNOWN_BYPASS_FOUND
2. Reference SUCCESS + Candidate DEATH -> KNOWN_BYPASS_NOT_FOUND
3. Reference SUCCESS + Candidate TIMEOUT -> KNOWN_BYPASS_NOT_FOUND (Crucial: DEATH not required)
4. Reference DEATH -> REFERENCE_FAILED (Bypass not evaluated)
5. Reference TIMEOUT -> REFERENCE_FAILED (Bypass not evaluated)
6. Reference INVALID -> VERIFIER_ERROR
7. Candidate INVALID -> INCONCLUSIVE (Must not be treated as bypass failure)
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

from bypass_verifier import SingleBypassVerifier


class TestSingleBypassVerifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap_path = HARNESS_DIR / "private_snapshots" / "hun1_full.zip"
        cls.map_path = ROOT / "훈련용맵" / "physics_curriculum" / "stg1_01_gap2.LMF"
        cls.verifier = SingleBypassVerifier(cls.snap_path, cls.map_path)

        # Standard intended reference clear: jump at t=25 for 28 ticks
        cls.ref_clear_actions = []
        for t in range(175):
            if 25 <= t < 25 + 28:
                cls.ref_clear_actions.append(("RIGHT", "UP"))
            else:
                cls.ref_clear_actions.append(("RIGHT",))

        # Alternative successful bypass: jump slightly earlier at t=24 for 28 ticks (also clears)
        cls.alt_clear_actions = []
        for t in range(175):
            if 24 <= t < 24 + 28:
                cls.alt_clear_actions.append(("RIGHT", "UP"))
            else:
                cls.alt_clear_actions.append(("RIGHT",))

        # Suicide walk (falls into pit -> DEATH at t=68)
        cls.suicide_actions = [("RIGHT",) for _ in range(80)]

        # Short walk then idle (stands on safe ground -> TIMEOUT)
        cls.safe_idle_actions = [("RIGHT",) for _ in range(20)]

        # Idle actions
        cls.idle_actions = [() for _ in range(50)]

        # Invalid action sequence
        cls.invalid_actions = [("TELEPORT_HACK",)]

    def test_01_reference_success_and_bypass_success(self):
        """Case 1: Both reference and candidate clear -> KNOWN_BYPASS_FOUND."""
        res = self.verifier.evaluate(self.ref_clear_actions, self.alt_clear_actions, max_ticks=200)
        self.assertEqual(res["verdict"], "KNOWN_BYPASS_FOUND")
        self.assertEqual(res["reference_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["bypass_result"]["terminal_type"], "SUCCESS")
        self.assertIsNotNone(res["initial_snapshot_signature"])

    def test_02a_reference_success_and_bypass_death(self):
        """Case 2A: Reference clears, candidate dies -> KNOWN_BYPASS_NOT_FOUND."""
        res = self.verifier.evaluate(self.ref_clear_actions, self.suicide_actions, max_ticks=200)
        self.assertEqual(res["verdict"], "KNOWN_BYPASS_NOT_FOUND")
        self.assertEqual(res["reference_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["bypass_result"]["terminal_type"], "DEATH")
        self.assertEqual(res["bypass_result"]["terminal_tick"], 68)

    def test_02b_reference_success_and_bypass_timeout(self):
        """Case 2B: Reference clears, candidate stops short and timeouts -> KNOWN_BYPASS_NOT_FOUND."""
        # Crucial test: Death is NOT required; stopping short and timing out is a valid bypass failure.
        res = self.verifier.evaluate(self.ref_clear_actions, self.safe_idle_actions, max_ticks=200)
        self.assertEqual(res["verdict"], "KNOWN_BYPASS_NOT_FOUND")
        self.assertEqual(res["reference_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["bypass_result"]["terminal_type"], "TIMEOUT")

    def test_03a_reference_death_fails_map(self):
        """Case 3A: Reference fails with DEATH -> REFERENCE_FAILED (Bypass not evaluated)."""
        res = self.verifier.evaluate(self.suicide_actions, self.alt_clear_actions, max_ticks=100)
        self.assertEqual(res["verdict"], "REFERENCE_FAILED")
        self.assertEqual(res["reference_result"]["terminal_type"], "DEATH")
        self.assertIsNone(res["bypass_result"], "Bypass must not be evaluated if reference fails")

    def test_03b_reference_timeout_fails_map(self):
        """Case 3B: Reference fails with TIMEOUT -> REFERENCE_FAILED (Bypass not evaluated)."""
        res = self.verifier.evaluate(self.idle_actions, self.alt_clear_actions, max_ticks=50)
        self.assertEqual(res["verdict"], "REFERENCE_FAILED")
        self.assertEqual(res["reference_result"]["terminal_type"], "TIMEOUT")
        self.assertIsNone(res["bypass_result"], "Bypass must not be evaluated if reference fails")

    def test_04a_reference_invalid_yields_verifier_error(self):
        """Case 4A: Reference sequence contains invalid key -> VERIFIER_ERROR."""
        res = self.verifier.evaluate(self.invalid_actions, self.alt_clear_actions, max_ticks=50)
        self.assertEqual(res["verdict"], "VERIFIER_ERROR")
        self.assertEqual(res["reference_result"]["terminal_type"], "INVALID")
        self.assertIsNone(res["bypass_result"])

    def test_04b_candidate_invalid_yields_inconclusive(self):
        """Case 4B: Candidate contains invalid key -> INCONCLUSIVE (Not a bypass failure)."""
        res = self.verifier.evaluate(self.ref_clear_actions, self.invalid_actions, max_ticks=200)
        self.assertEqual(res["verdict"], "INCONCLUSIVE")
        self.assertEqual(res["reference_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["bypass_result"]["terminal_type"], "INVALID")


if __name__ == "__main__":
    unittest.main()
