"""test_regression_corpus.py - Historical Defect Regression Corpus Test Suite.

Verifies that all 4 canonical past project defects are caught at their designated pipeline stage,
that stage short-circuiting strictly prevents unnecessary execution of downstream layers,
and that paired fixed controls pass cleanly.
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

from regression_corpus import HISTORICAL_REGRESSION_CORPUS
from regression_runner import RegressionRunner


class TestHistoricalDefectRegressionCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry_path = ROOT / "physics_registry.json"
        cls.snapshot_path = HARNESS_DIR / "private_snapshots" / "hun6_live.zip"
        cls.temp_dir = ROOT / "scratch" / "regression_corpus_fixtures"
        cls.runner = RegressionRunner(cls.registry_path, cls.snapshot_path, cls.temp_dir)

    def test_01_hist001_knife_backroll_bypass(self):
        """HIST-001: Knife required but delayed backroll bypass -> bypass_verifier stage."""
        res = self.runner.run_defect("HIST-001")
        self.assertTrue(res["passed"])
        self.assertEqual(res["stage_reached"], "bypass_verifier")
        self.assertEqual(res["broken_result"]["verdict"], "KNOWN_BYPASS_FOUND")
        self.assertEqual(res["fixed_result"]["verdict"], "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE")
        self.assertIsNotNone(res["broken_result"]["winning_candidate"])
        self.assertEqual(res["broken_result"]["winning_candidate"]["family"], "delayed_backroll")

    def test_02_hist002_pillar1_weapon1_overshoot(self):
        """HIST-002: 1-tile pillar overshoot fall -> x86_oracle stage, candidate suite blocked."""
        res = self.runner.run_defect("HIST-002")
        self.assertTrue(res["passed"])
        self.assertEqual(res["stage_reached"], "x86_oracle")
        self.assertEqual(res["broken_result"]["verdict"], "REFERENCE_FAILED")
        self.assertEqual(res["broken_result"]["total_candidates_evaluated"], 0)
        self.assertEqual(res["fixed_result"]["terminal_type"], "SUCCESS")
        # Assert candidate suite was NEVER reached
        self.assertNotIn("bypass_suite", res["executed_stages"])

    def test_03_hist003_impossible_parachute(self):
        """HIST-003: Impossible 576px parachute gap -> static_validator REJECT, x86 blocked."""
        res = self.runner.run_defect("HIST-003")
        self.assertTrue(res["passed"])
        self.assertEqual(res["stage_reached"], "static_validator")
        self.assertEqual(res["broken_result"]["verdict"], "REJECT")
        self.assertIn("exceeds verified pure chute envelope", res["broken_result"]["reason"])
        self.assertEqual(res["fixed_result"]["verdict"], "STATIC_OK")
        # Assert x86 oracle and bypass suite were NEVER invoked
        self.assertNotIn("x86_oracle", res["executed_stages"])
        self.assertNotIn("bypass_suite", res["executed_stages"])

    def test_04_hist004_collapse_hole_walk_mandated(self):
        """HIST-004: 32px hole before collapse platform -> static_validator REJECT, x86 blocked."""
        res = self.runner.run_defect("HIST-004")
        self.assertTrue(res["passed"])
        self.assertEqual(res["stage_reached"], "static_validator")
        self.assertEqual(res["broken_result"]["verdict"], "REJECT")
        self.assertIn("hole before collapse platform", res["broken_result"]["reason"])
        self.assertEqual(res["fixed_result"]["verdict"], "UNKNOWN")
        # Assert x86 oracle and bypass suite were NEVER invoked
        self.assertNotIn("x86_oracle", res["executed_stages"])
        self.assertNotIn("bypass_suite", res["executed_stages"])

    def test_05_corpus_runner_full_suite(self):
        """Verify all registered defects in HISTORICAL_REGRESSION_CORPUS execute and pass."""
        for defect_id in HISTORICAL_REGRESSION_CORPUS:
            with self.subTest(defect_id=defect_id):
                res = self.runner.run_defect(defect_id)
                self.assertTrue(res["passed"], f"Defect {defect_id} failed regression run.")


if __name__ == "__main__":
    unittest.main()
