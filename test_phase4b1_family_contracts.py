"""test_phase4b1_family_contracts.py - Phase 4B-1 Family Generators & Semantic Contracts Test Suite.

Verifies:
  1. Golden Fixture SHA-256 Integrity.
  2. NormalJumpWalkFamily:
     - Positive Control: 64px gap -> SUCCESS with clean semantic validation.
     - Negative Control: 128px step-up gap -> DEATH with clean semantic validation.
     - Semantic Contract: Forbidden keys/state -> INVALID_CANDIDATE_SEMANTICS.
  3. DelayedBackrollFamily:
     - Positive Control: Open step-up gap -> SUCCESS with verified native backroll (state 38==2, motion58==760).
     - Negative Control: Ceiling step-up gap -> DEATH with verified native backroll.
     - Semantic Contract: Unactivated backroll -> INVALID_CANDIDATE_SEMANTICS.
  4. Audit Preservations:
     - Expected count == actual count assertion.
     - Action sequence SHA-256 preservation.
     - Native terminal evidence & mechanic activation evidence.
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

from candidate_suite_verifier import CandidateSuiteVerifier
from family_generators import DelayedBackrollFamily, NormalJumpWalkFamily
from regression_corpus import verify_file_sha256

GOLDEN_DIR = ROOT / "golden_fixtures"
SNAP_PATH = HARNESS_DIR / "private_snapshots" / "hun6_live.zip"


class TestPhase4B1FamilyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.njw_family = NormalJumpWalkFamily()
        cls.backroll_family = DelayedBackrollFamily()

        # Golden fixture paths and hashes
        cls.njw_pos_lmf = GOLDEN_DIR / "njw_positive_flat_gap2.LMF"
        cls.njw_pos_sha = "ed024af77d0fc3fd13253ec47ebf2403b8671a3aa026ad8b613ffcb560017bd5"

        cls.hist001_broken_lmf = GOLDEN_DIR / "hist001_broken_open_gap.LMF"
        cls.hist001_broken_sha = "1c62c57d3b26fc9bc6d385ea5f332d1017ea041088af7f2b973acbdcc3cddbd0"

        cls.hist001_fixed_lmf = GOLDEN_DIR / "hist001_fixed_ceiling_gap.LMF"
        cls.hist001_fixed_sha = "b25b51728db804cae371ddf5363fe164dc4c99fc780452700b73aa98e9237b62"

        # Standard References
        cls.ref_njw = [("RIGHT",)] * 16 + [("RIGHT", "UP")] * 20 + [("RIGHT",)] * 40
        cls.ref_knife = (
            [("1",)]
            + [("RIGHT",)] * 16
            + [("RIGHT", "UP")] * 14
            + [("RIGHT", "Z")]
            + [("RIGHT",)] * 100
        )

    def test_01_golden_fixtures_sha256(self):
        """Assert all golden fixtures for Phase 4B-1 match their pinned SHA-256 hashes."""
        self.assertTrue(verify_file_sha256(self.njw_pos_lmf, self.njw_pos_sha))
        self.assertTrue(verify_file_sha256(self.hist001_broken_lmf, self.hist001_broken_sha))
        self.assertTrue(verify_file_sha256(self.hist001_fixed_lmf, self.hist001_fixed_sha))

    def test_02_normal_jump_walk_positive_control(self):
        """Positive Control: Normal jump walk clears 64px gap and validates clean semantics."""
        verifier = CandidateSuiteVerifier(SNAP_PATH, self.njw_pos_lmf)
        manifest = self.njw_family.generate_manifest(
            walk_ticks_list=[16],
            jump_ticks_list=[20],
            post_walk_ticks=40,
        )
        self.assertEqual(len(manifest), 1, "Expected exactly 1 candidate in manifest.")

        res = verifier.evaluate_suite(
            self.ref_njw,
            manifest,
            expected_candidate_count=1,
            max_ticks=100,
        )

        self.assertEqual(res["verdict"], "KNOWN_BYPASS_FOUND")
        winner = res["winning_candidate"]
        self.assertIsNotNone(winner)
        self.assertEqual(winner["family"], "normal_jump_walk")
        self.assertEqual(winner["terminal_type"], "SUCCESS")
        self.assertIn("normal_jump_walk_verified", winner["mechanic_activation_evidence"])
        self.assertEqual(len(winner["action_sequence_hash"]), 64)

    def test_03_normal_jump_walk_negative_control(self):
        """Negative Control: Normal jump walk fails 128px step-up gap while maintaining clean semantics."""
        verifier = CandidateSuiteVerifier(SNAP_PATH, self.hist001_fixed_lmf)
        manifest = self.njw_family.generate_manifest(
            walk_ticks_list=[16],
            jump_ticks_list=[14, 20, 28],
            post_walk_ticks=50,
        )
        self.assertEqual(len(manifest), 3, "Expected exactly 3 candidates in manifest.")

        res = verifier.evaluate_suite(
            self.ref_knife,
            manifest,
            expected_candidate_count=3,
            max_ticks=150,
        )

        self.assertEqual(res["verdict"], "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE")
        self.assertIsNone(res["winning_candidate"])
        self.assertEqual(res["total_candidates_evaluated"], 3)

        for c in res["evaluated_candidates"]:
            self.assertEqual(c["terminal_type"], "DEATH")
            self.assertIn("normal_jump_walk_verified", c["mechanic_activation_evidence"])

    def test_04_normal_jump_walk_semantic_contract_violation(self):
        """Semantic Contract: Candidate with forbidden key is invalidated to prevent false attribution."""
        verifier = CandidateSuiteVerifier(SNAP_PATH, self.njw_pos_lmf)
        corrupt_cand = {
            "candidate_name": "njw_with_illegal_down",
            "family": "normal_jump_walk",
            "parameters": {"illegal": True},
            "action_sequence": [("RIGHT",)] * 16 + [("DOWN",)] * 5 + [("RIGHT",)] * 20,
            "semantic_validator": self.njw_family.validate_semantics,
        }

        res = verifier.evaluate_suite(
            self.ref_njw,
            [corrupt_cand],
            expected_candidate_count=1,
            max_ticks=100,
        )

        self.assertEqual(res["verdict"], "SUITE_INCONCLUSIVE")
        cand_record = res["evaluated_candidates"][0]
        self.assertEqual(cand_record["terminal_type"], "INVALID_CANDIDATE_SEMANTICS")
        self.assertIn("forbidden_keys", cand_record["evidence_source"])

    def test_05_delayed_backroll_positive_control(self):
        """Positive Control: Delayed backroll clears open step-up gap and proves native activation."""
        verifier = CandidateSuiteVerifier(SNAP_PATH, self.hist001_broken_lmf)
        manifest = self.backroll_family.generate_manifest(
            jump_durs=[28],
            switch_delays=[0],
            roll_durs=[5],
            walk_ticks=16,
            post_roll_walk=120,
        )
        self.assertEqual(len(manifest), 1, "Expected exactly 1 candidate in manifest.")

        res = verifier.evaluate_suite(
            self.ref_knife,
            manifest,
            expected_candidate_count=1,
            max_ticks=150,
        )

        self.assertEqual(res["verdict"], "KNOWN_BYPASS_FOUND")
        winner = res["winning_candidate"]
        self.assertIsNotNone(winner)
        self.assertEqual(winner["family"], "delayed_backroll")
        self.assertEqual(winner["terminal_type"], "SUCCESS")
        # Assert native mechanic activation evidence
        self.assertIn("native_backroll_verified", winner["mechanic_activation_evidence"])
        self.assertIn("state38==2", winner["mechanic_activation_evidence"])
        self.assertIn("motion58_reload==760.0", winner["mechanic_activation_evidence"])

    def test_06_delayed_backroll_negative_control(self):
        """Negative Control: Backroll fails ceiling step-up gap while proving native activation."""
        verifier = CandidateSuiteVerifier(SNAP_PATH, self.hist001_fixed_lmf)
        manifest = self.backroll_family.generate_manifest(
            jump_durs=[20, 28],
            switch_delays=[0],
            roll_durs=[5],
            walk_ticks=16,
            post_roll_walk=100,
        )
        self.assertEqual(len(manifest), 2, "Expected exactly 2 candidates in manifest.")

        res = verifier.evaluate_suite(
            self.ref_knife,
            manifest,
            expected_candidate_count=2,
            max_ticks=150,
        )

        self.assertEqual(res["verdict"], "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE")
        self.assertIsNone(res["winning_candidate"])
        self.assertEqual(res["total_candidates_evaluated"], 2)

        for c in res["evaluated_candidates"]:
            self.assertEqual(c["terminal_type"], "DEATH")
            self.assertIn("native_backroll_verified", c["mechanic_activation_evidence"])

    def test_07_delayed_backroll_semantic_contract_violation(self):
        """Semantic Contract: Candidate claiming backroll that never activates roll is invalidated."""
        verifier = CandidateSuiteVerifier(SNAP_PATH, self.hist001_broken_lmf)
        # Sequence that never activates backroll (just jumps right without roll trigger)
        fake_backroll = {
            "candidate_name": "fake_backroll_no_activation",
            "family": "delayed_backroll",
            "parameters": {"fake": True},
            "action_sequence": [("RIGHT",)] * 16 + [("RIGHT", "UP")] * 20 + [("RIGHT",)] * 50,
            "semantic_validator": self.backroll_family.validate_semantics,
        }

        res = verifier.evaluate_suite(
            self.ref_knife,
            [fake_backroll],
            expected_candidate_count=1,
            max_ticks=150,
        )

        self.assertEqual(res["verdict"], "SUITE_INCONCLUSIVE")
        cand_record = res["evaluated_candidates"][0]
        self.assertEqual(cand_record["terminal_type"], "INVALID_CANDIDATE_SEMANTICS")
        self.assertIn("backroll_never_activated", cand_record["evidence_source"])


if __name__ == "__main__":
    unittest.main()
