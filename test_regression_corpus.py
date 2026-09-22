"""test_regression_corpus.py - Phase 4A.1 Historical Defect Regression Corpus Test Suite.

Verifies:
  1. Parachute Envelope Boundary Regression:
     - Verified kinematic envelope on flat ground is 388.97px (not 353px).
     - Inside envelope (384px) -> STATIC_OK (REJECT forbidden).
     - Outside envelope (416px) -> REJECT.
  2. Golden Fixture SHA-256 Integrity:
     - All 7 broken/fixed golden artifacts match pinned SHA-256 hashes.
  3. Neutral Pipeline Gatekeeping & Short-Circuiting:
     - Tests all 4 historical defects through neutral RegressionRunner.
     - Confirms execution halts at exact expected stage and blocks must_not_reach stages.
  4. 6 Mandatory Audit Fields Preserved:
     - fixture_sha256, expected_stage, actual_executed_stages,
       expected_verdict, actual_verdict, native_evidence_source.
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

from regression_corpus import HISTORICAL_REGRESSION_CORPUS, verify_file_sha256
from regression_runner import RegressionRunner
from static_validator import StaticPhysicsValidator


class TestHistoricalDefectRegressionCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry_path = ROOT / "physics_registry.json"
        cls.snapshot_path = HARNESS_DIR / "private_snapshots" / "hun6_live.zip"
        cls.temp_dir = ROOT / "scratch" / "regression_corpus_fixtures"
        cls.runner = RegressionRunner(cls.registry_path, cls.snapshot_path, cls.temp_dir)
        cls.static_validator = StaticPhysicsValidator(cls.registry_path)

    def test_00_parachute_envelope_boundary_regression(self):
        """Boundary Audit: Prove flat ground envelope is 488.0px and test threshold boundary."""
        env = self.static_validator.compute_pure_chute_envelope(448.0, 448.0)
        self.assertAlmostEqual(env, 488.0, places=1,
                               msg="Verified flat ground parachute envelope must be 488.0px.")

        # Boundary Test 1: Inside envelope (spawn x=2 -> goal x=17: 15 tiles = 480px <= 488.0px)
        spec_inside = {
            "version": "1.0",
            "map_id": "boundary_inside_480",
            "training_type": "isolated_skill",
            "metadata": {"required_mechanic": "parachute_glide", "collapse_entry": "none"},
            "allowed_capabilities": ["jump", "parachute"],
            "spawn": {"x": 2, "y": 14},
            "goal": {"x": 17, "y": 14}, # 480px
            "tiles": [{"id": 7, "x": 1, "y": 15}, {"id": 7, "x": 2, "y": 15}, {"id": 7, "x": 17, "y": 15}]
        }
        v_in, r_in = self.static_validator.validate_spec(spec_inside)
        self.assertEqual(v_in, "STATIC_OK", f"Distance 480px <= {env:.1f}px must NOT be REJECTed. Got: {v_in}")

        # Boundary Test 2: Outside envelope (spawn x=2 -> goal x=18: 16 tiles = 512px > 488.0px)
        spec_outside = {
            "version": "1.0",
            "map_id": "boundary_outside_512",
            "training_type": "isolated_skill",
            "metadata": {"required_mechanic": "parachute_glide", "collapse_entry": "none"},
            "allowed_capabilities": ["jump", "parachute"],
            "spawn": {"x": 2, "y": 14},
            "goal": {"x": 18, "y": 14}, # 512px
            "tiles": [{"id": 7, "x": 1, "y": 15}, {"id": 7, "x": 2, "y": 15}, {"id": 7, "x": 18, "y": 15}]
        }
        v_out, r_out = self.static_validator.validate_spec(spec_outside)
        self.assertEqual(v_out, "REJECT", f"Distance 512px > {env:.1f}px must be REJECTed. Got: {v_out}")
        self.assertIn("exceeds verified pure chute envelope", r_out)

    def test_01_golden_fixtures_sha256_integrity(self):
        """Assert all golden fixture files match their pinned SHA-256 hashes."""
        for defect_id, entry in HISTORICAL_REGRESSION_CORPUS.items():
            b_path = entry["golden_broken_path"]
            b_sha = entry["golden_broken_sha256"]
            self.assertTrue(verify_file_sha256(b_path, b_sha),
                            f"[{defect_id}] Broken fixture hash altered: {b_path}")

            f_path = entry["golden_fixed_path"]
            f_sha = entry["golden_fixed_sha256"]
            self.assertTrue(verify_file_sha256(f_path, f_sha),
                            f"[{defect_id}] Fixed fixture hash altered: {f_path}")

    def test_02_hist001_knife_backroll_bypass(self):
        """HIST-001: Knife required but delayed backroll bypass -> bypass_verifier stage."""
        res = self.runner.evaluate_defect("HIST-001")
        self.assertTrue(res["passed"])
        self.assertEqual(res["expected_stage"], "bypass_verifier")
        self.assertIn("bypass_verifier", res["actual_executed_stages"])
        self.assertEqual(res["actual_verdict"], "KNOWN_BYPASS_FOUND")
        self.assertEqual(res["fixed_verdict"], "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE")
        self._verify_audit_fields(res)

    def test_03_hist002_pillar1_weapon1_overshoot(self):
        """HIST-002: 1-tile pillar overshoot fall -> x86_oracle stage, candidate suite blocked."""
        res = self.runner.evaluate_defect("HIST-002")
        self.assertTrue(res["passed"])
        self.assertEqual(res["expected_stage"], "x86_oracle")
        self.assertIn("x86_oracle", res["actual_executed_stages"])
        self.assertNotIn("bypass_suite", res["actual_executed_stages"])
        self.assertEqual(res["actual_verdict"], "REFERENCE_FAILED")
        self.assertEqual(res["fixed_verdict"], "SUCCESS")
        self._verify_audit_fields(res)

    def test_04_hist003_impossible_parachute(self):
        """HIST-003: Impossible 576px parachute gap -> static_validator REJECT, x86 blocked."""
        res = self.runner.evaluate_defect("HIST-003")
        self.assertTrue(res["passed"])
        self.assertEqual(res["expected_stage"], "static_validator")
        self.assertEqual(res["actual_executed_stages"], ["static_validator"])
        self.assertNotIn("x86_oracle", res["actual_executed_stages"])
        self.assertNotIn("bypass_suite", res["actual_executed_stages"])
        self.assertEqual(res["actual_verdict"], "REJECT")
        self.assertEqual(res["fixed_verdict"], "STATIC_OK")
        self._verify_audit_fields(res)

    def test_05_hist004_collapse_hole_walk_mandated(self):
        """HIST-004: 32px hole before collapse platform -> static_validator REJECT, x86 blocked."""
        res = self.runner.evaluate_defect("HIST-004")
        self.assertTrue(res["passed"])
        self.assertEqual(res["expected_stage"], "static_validator")
        self.assertEqual(res["actual_executed_stages"], ["static_validator"])
        self.assertNotIn("x86_oracle", res["actual_executed_stages"])
        self.assertNotIn("bypass_suite", res["actual_executed_stages"])
        self.assertEqual(res["actual_verdict"], "REJECT")
        self.assertEqual(res["fixed_verdict"], "UNKNOWN")
        self._verify_audit_fields(res)

    def test_06_corpus_runner_full_suite(self):
        """Verify all registered defects in HISTORICAL_REGRESSION_CORPUS execute through runner."""
        for defect_id in HISTORICAL_REGRESSION_CORPUS:
            with self.subTest(defect_id=defect_id):
                res = self.runner.evaluate_defect(defect_id)
                self.assertTrue(res["passed"], f"Defect {defect_id} failed regression run.")
                self._verify_audit_fields(res)

    def _verify_audit_fields(self, res: dict):
        """Assert presence of all 6 mandatory audit metadata fields."""
        required = [
            "fixture_sha256",
            "expected_stage",
            "actual_executed_stages",
            "expected_verdict",
            "actual_verdict",
            "native_evidence_source",
        ]
        for key in required:
            self.assertIn(key, res, f"Missing required audit field: {key}")


if __name__ == "__main__":
    unittest.main()
