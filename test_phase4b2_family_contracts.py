"""test_phase4b2_family_contracts.py - Phase 4B-2 Family Generators & Semantic Contracts Test Suite.

Verifies:
  1. Golden Fixture SHA-256 Integrity for Parachute and Weapon 1 fixtures.
  2. Weapon1MobilityFamily:
     - Positive Control: Open step-up gap -> SUCCESS with verified native knife dash (state 38==15).
     - Negative Control: 1-tile narrow pillar -> DEATH (overshoot into void) with verified knife dash.
     - Semantic Contract: Candidate claiming knife dash without knife slash -> INVALID_CANDIDATE_SEMANTICS.
  3. ParachuteFamily:
     - Positive Control: 448px gap + vertical drop -> SUCCESS with verified parachute glide (state 38==3, dc==1).
     - Negative Control: 704px long gap -> DEATH (falls into lava) with verified parachute glide.
     - Semantic Contract: Candidate claiming parachute that never deploys -> INVALID_CANDIDATE_SEMANTICS.
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
from family_generators import ParachuteFamily, Weapon1MobilityFamily
from regression_corpus import verify_file_sha256

GOLDEN_DIR = ROOT / "golden_fixtures"
SNAP_HUN6 = HARNESS_DIR / "private_snapshots" / "hun6_live.zip"
SNAP_HUN5 = HARNESS_DIR / "private_snapshots" / "hun5_parachute_fast_boundary.zip"


class TestPhase4B2FamilyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w1_family = Weapon1MobilityFamily()
        cls.chute_family = ParachuteFamily()

        # Golden fixtures and pinned hashes
        cls.w1_pos_lmf = GOLDEN_DIR / "hist001_broken_open_gap.LMF"
        cls.w1_pos_sha = "1c62c57d3b26fc9bc6d385ea5f332d1017ea041088af7f2b973acbdcc3cddbd0"

        cls.w1_neg_lmf = GOLDEN_DIR / "hist002_pillar1_knife.LMF"
        cls.w1_neg_sha = "57708bc9d5b2e53dc520d7ca1f67fb7daffd0f12dac45b62a0c4304c88f453f0"

        cls.chute_pos_lmf = GOLDEN_DIR / "chute_positive_glide.LMF"
        cls.chute_pos_sha = "e798a42a66c94241993c53bee7f88e71b84b1dc81f1fe548dffbdf588908acdb"

        cls.chute_neg_lmf = GOLDEN_DIR / "chute_negative_long_gap.LMF"
        cls.chute_neg_sha = "6a1705525a1e92d61fdbc93d8723c30cd416c2fb95a3de20f771b5e5ebddf809"

        # Reference sequences
        cls.ref_backroll = (
            [("RIGHT",)] * 16
            + [("RIGHT", "UP")] * 28
            + [("LEFT",)]
            + [("RIGHT", "DOWN")] * 5
            + [("RIGHT",)] * 120
        )

        cls.ref_precision_jump = (
            [("RIGHT",)] * 20
            + [("RIGHT", "UP")] * 28
        )

        cls.ref_chute = (
            [("RIGHT",)] * 16
            + [("RIGHT", "UP")] * 20
            + [("RIGHT",)] * 12
            + [("RIGHT", "C")]
            + [("RIGHT",)] * 120
        )

        cls.ref_backroll_chute = (
            [("RIGHT",)] * 16
            + [("RIGHT", "UP")] * 28
            + [("LEFT",)]
            + [("RIGHT", "DOWN")] * 5
            + [("RIGHT",)] * 10
            + [("RIGHT", "C")]
            + [("RIGHT",)] * 150
        )

    def test_01_golden_fixtures_sha256(self):
        """Assert all golden fixtures for Phase 4B-2 match their pinned SHA-256 hashes."""
        self.assertTrue(verify_file_sha256(self.w1_pos_lmf, self.w1_pos_sha))
        self.assertTrue(verify_file_sha256(self.w1_neg_lmf, self.w1_neg_sha))
        self.assertTrue(verify_file_sha256(self.chute_pos_lmf, self.chute_pos_sha))
        self.assertTrue(verify_file_sha256(self.chute_neg_lmf, self.chute_neg_sha))

    def test_02_weapon1_positive_control(self):
        """Positive Control: Weapon 1 knife dash clears open gap and proves native state 38==15."""
        verifier = CandidateSuiteVerifier(SNAP_HUN6, self.w1_pos_lmf)
        manifest = self.w1_family.generate_manifest(
            jump_durs=[14],
            attack_delays=[1],
            walk_ticks=16,
            post_dash_walk=100,
        )
        self.assertEqual(len(manifest), 1, "Expected exactly 1 candidate in manifest.")

        res = verifier.evaluate_suite(
            self.ref_backroll,
            manifest,
            expected_candidate_count=1,
            max_ticks=150,
        )

        self.assertEqual(res["verdict"], "KNOWN_BYPASS_FOUND")
        winner = res["winning_candidate"]
        self.assertIsNotNone(winner)
        self.assertEqual(winner["family"], "weapon1_mobility")
        self.assertEqual(winner["terminal_type"], "SUCCESS")
        self.assertIn("native_weapon1_verified", winner["mechanic_activation_evidence"])
        self.assertIn("state38==15", winner["mechanic_activation_evidence"])
        self.assertEqual(len(winner["action_sequence_hash"]), 64)

    def test_03_weapon1_negative_control(self):
        """Negative Control: Weapon 1 knife dash overshoots 32px pillar into void while proving native activation."""
        verifier = CandidateSuiteVerifier(SNAP_HUN6, self.w1_neg_lmf)
        manifest = self.w1_family.generate_manifest(
            jump_durs=[14, 18],
            attack_delays=[1],
            walk_ticks=16,
            post_dash_walk=50,
        )
        self.assertEqual(len(manifest), 2, "Expected exactly 2 candidates in manifest.")

        res = verifier.evaluate_suite(
            self.ref_precision_jump,
            manifest,
            expected_candidate_count=2,
            max_ticks=100,
        )

        self.assertEqual(res["verdict"], "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE")
        self.assertIsNone(res["winning_candidate"])
        self.assertEqual(res["total_candidates_evaluated"], 2)

        for c in res["evaluated_candidates"]:
            self.assertEqual(c["terminal_type"], "DEATH")
            self.assertIn("native_weapon1_verified", c["mechanic_activation_evidence"])
            self.assertIn("state38==15", c["mechanic_activation_evidence"])

    def test_04_weapon1_semantic_contract_violation(self):
        """Semantic Contract: Candidate claiming weapon 1 mobility without knife activation is invalidated."""
        verifier = CandidateSuiteVerifier(SNAP_HUN6, self.w1_pos_lmf)
        # Fake candidate: presses 'Z' in air without equipping weapon 1 ('1') -> produces 38==16, never 15
        fake_w1 = {
            "candidate_name": "fake_w1_no_equip",
            "family": "weapon1_mobility",
            "parameters": {"fake": True},
            "action_sequence": (
                [("RIGHT",)] * 16
                + [("RIGHT", "UP")] * 14
                + [("RIGHT", "Z")]
                + [("RIGHT",)] * 100
            ),
            "semantic_validator": self.w1_family.validate_semantics,
        }

        res = verifier.evaluate_suite(
            self.ref_backroll,
            [fake_w1],
            expected_candidate_count=1,
            max_ticks=150,
        )

        self.assertEqual(res["verdict"], "SUITE_INCONCLUSIVE")
        cand_record = res["evaluated_candidates"][0]
        self.assertEqual(cand_record["terminal_type"], "INVALID_CANDIDATE_SEMANTICS")
        self.assertIn("weapon1_dash_never_activated", cand_record["evidence_source"])

    def test_05_parachute_positive_control(self):
        """Positive Control: Parachute glide clears 448px gap and proves native state 38==3, dc==1."""
        verifier = CandidateSuiteVerifier(SNAP_HUN5, self.chute_pos_lmf)
        manifest = self.chute_family.generate_manifest(
            jump_ticks_list=[20],
            descent_delays=[12],
            walk_ticks=16,
            post_glide_walk=120,
        )
        self.assertEqual(len(manifest), 1, "Expected exactly 1 candidate in manifest.")

        res = verifier.evaluate_suite(
            self.ref_chute,
            manifest,
            expected_candidate_count=1,
            max_ticks=200,
        )

        self.assertEqual(res["verdict"], "KNOWN_BYPASS_FOUND")
        winner = res["winning_candidate"]
        self.assertIsNotNone(winner)
        self.assertEqual(winner["family"], "parachute")
        self.assertEqual(winner["terminal_type"], "SUCCESS")
        self.assertIn("native_parachute_verified", winner["mechanic_activation_evidence"])
        self.assertIn("state38==3", winner["mechanic_activation_evidence"])
        self.assertIn("dc==1", winner["mechanic_activation_evidence"])
        self.assertEqual(len(winner["action_sequence_hash"]), 64)

    def test_06_parachute_negative_control(self):
        """Negative Control: Pure parachute fails 704px long gap while proving native activation."""
        verifier = CandidateSuiteVerifier(SNAP_HUN5, self.chute_neg_lmf)
        manifest = self.chute_family.generate_manifest(
            jump_ticks_list=[20, 24],
            descent_delays=[12],
            walk_ticks=16,
            post_glide_walk=150,
        )
        self.assertEqual(len(manifest), 2, "Expected exactly 2 candidates in manifest.")

        res = verifier.evaluate_suite(
            self.ref_backroll_chute,
            manifest,
            expected_candidate_count=2,
            max_ticks=250,
        )

        self.assertEqual(res["verdict"], "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE")
        self.assertIsNone(res["winning_candidate"])
        self.assertEqual(res["total_candidates_evaluated"], 2)

        for c in res["evaluated_candidates"]:
            self.assertEqual(c["terminal_type"], "DEATH")
            self.assertIn("native_parachute_verified", c["mechanic_activation_evidence"])
            self.assertIn("state38==3", c["mechanic_activation_evidence"])
            self.assertIn("dc==1", c["mechanic_activation_evidence"])

    def test_07_parachute_semantic_contract_violation(self):
        """Semantic Contract: Candidate claiming parachute that never deploys parachute is invalidated."""
        verifier = CandidateSuiteVerifier(SNAP_HUN5, self.chute_pos_lmf)
        # Fake candidate: normal jump without 'C' key
        fake_chute = {
            "candidate_name": "fake_chute_no_c_key",
            "family": "parachute",
            "parameters": {"fake": True},
            "action_sequence": (
                [("RIGHT",)] * 16
                + [("RIGHT", "UP")] * 20
                + [("RIGHT",)] * 100
            ),
            "semantic_validator": self.chute_family.validate_semantics,
        }

        res = verifier.evaluate_suite(
            self.ref_chute,
            [fake_chute],
            expected_candidate_count=1,
            max_ticks=200,
        )

        self.assertEqual(res["verdict"], "SUITE_INCONCLUSIVE")
        cand_record = res["evaluated_candidates"][0]
        self.assertEqual(cand_record["terminal_type"], "INVALID_CANDIDATE_SEMANTICS")
        self.assertIn("parachute_never_activated", cand_record["evidence_source"])

    def test_08_candidate_manifest_and_hash_audit(self):
        """Manifest Audit: Cartesian product dimensions, expected counts, and hash repeatability."""
        m_w1 = self.w1_family.generate_manifest(jump_durs=[14, 18, 22], attack_delays=[1, 2])
        self.assertEqual(len(m_w1), 3 * 2)

        m_chute = self.chute_family.generate_manifest(jump_ticks_list=[16, 20, 24], descent_delays=[10, 12])
        self.assertEqual(len(m_chute), 3 * 2)

        # Hash determinism
        hash1 = CandidateSuiteVerifier.compute_action_hash(m_w1[0]["action_sequence"])
        hash2 = CandidateSuiteVerifier.compute_action_hash(m_w1[0]["action_sequence"])
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)


if __name__ == "__main__":
    unittest.main()
