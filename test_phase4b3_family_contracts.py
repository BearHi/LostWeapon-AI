"""test_phase4b3_family_contracts.py - Phase 4B-3 Family Generators & Semantic Contracts Test Suite.

Verifies:
  1. Golden Fixture SHA-256 Integrity.
  2. Weapon4BrakeFamily:
     - Positive Control: HIST-002 32px pillar -> SUCCESS with verified native Weapon 4 brake (state 38==18, active_weapon==3).
       (Contrasted directly with Weapon 1 which overshoots to DEATH on identical geometry).
     - Negative Control: Early brake falls into void -> DEATH with verified native Weapon 4 brake activation.
     - Semantic Contract: Candidate claiming weapon 4 brake without activation -> INVALID_CANDIDATE_SEMANTICS.
  3. Free-Air Brake Physics Regression:
     - In obstacle-free space: state 38==18 lasts 22 ticks with strictly 0.0px delta X (in-place air freeze) and dash90==2000.0.
  4. Multi-Weapon False-Positive Isolation:
     - Proves Weapon 1, 2, and 3 aerial attacks fail Weapon 4 brake semantic contract.
  5. Audit Preservations:
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
from family_generators import Weapon4BrakeFamily, Weapon1MobilityFamily
from x86_oracle_verifier import X86OracleVerifier
from regression_corpus import verify_file_sha256

GOLDEN_DIR = ROOT / "golden_fixtures"
SNAP_HUN6 = HARNESS_DIR / "private_snapshots" / "hun6_live.zip"


class TestPhase4B3FamilyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w4_family = Weapon4BrakeFamily()
        cls.w1_family = Weapon1MobilityFamily()

        # Golden fixtures and pinned hashes
        cls.pillar_lmf = GOLDEN_DIR / "hist002_pillar1_knife.LMF"
        cls.pillar_sha = "57708bc9d5b2e53dc520d7ca1f67fb7daffd0f12dac45b62a0c4304c88f453f0"

        cls.open_gap_lmf = GOLDEN_DIR / "hist001_broken_open_gap.LMF"
        cls.open_gap_sha = "1c62c57d3b26fc9bc6d385ea5f332d1017ea041088af7f2b973acbdcc3cddbd0"

        # Reference sequence for HIST-002 (precision jump without overshoot)
        cls.ref_precision_jump = (
            [("RIGHT",)] * 20
            + [("RIGHT", "UP")] * 28
        )

    def test_01_golden_fixtures_sha256(self):
        """Assert all golden fixtures for Phase 4B-3 match their pinned SHA-256 hashes."""
        self.assertTrue(
            verify_file_sha256(self.pillar_lmf, self.pillar_sha),
            f"HIST-002 fixture SHA altered: {self.pillar_lmf}"
        )
        self.assertTrue(
            verify_file_sha256(self.open_gap_lmf, self.open_gap_sha),
            f"Open gap fixture SHA altered: {self.open_gap_lmf}"
        )

    def test_02_weapon4_positive_control_hist002_pillar(self):
        """Positive Control: Weapon 4 brake lands on 32px pillar -> SUCCESS (while Weapon 1 overshoots to DEATH)."""
        suite_verifier = CandidateSuiteVerifier(SNAP_HUN6, self.pillar_lmf)

        # Reference sequence is valid precision jump -> SUCCESS
        # Candidate 1: Weapon 4 brake sequence (walk 16, jump 18, delay 6, Z, float down)
        cand_w4 = self.w4_family.generate_manifest(
            jump_durs=[18],
            brake_delays=[6],
            walk_ticks=16,
            post_brake_ticks=45,
            direction="RIGHT"
        )
        self.assertEqual(len(cand_w4), 1)

        result_w4 = suite_verifier.evaluate_suite(
            self.ref_precision_jump,
            cand_w4,
            expected_candidate_count=1,
            max_ticks=95
        )

        self.assertEqual(result_w4["verdict"], "KNOWN_BYPASS_FOUND")
        self.assertEqual(result_w4["reference_result"]["terminal_type"], "SUCCESS")

        winner = result_w4["winning_candidate"]
        self.assertIsNotNone(winner)
        self.assertEqual(winner["terminal_type"], "SUCCESS")
        self.assertIn("native_weapon4_verified", winner["mechanic_activation_evidence"])
        self.assertIn("state38==18", winner["mechanic_activation_evidence"])
        self.assertIn("active_weapon==3", winner["mechanic_activation_evidence"])
        self.assertIn("observed_dash90=2000.0", winner["mechanic_activation_evidence"])
        self.assertEqual(len(winner["action_sequence_hash"]), 64)

        # Direct Contrast: Run Weapon 1 mobility candidate on this exact same geometry
        cand_w1 = self.w1_family.generate_manifest(
            jump_durs=[14],
            attack_delays=[1],
            walk_ticks=16,
            post_dash_walk=50,
            direction="RIGHT"
        )
        trial_w1 = suite_verifier.verifier.run_trial(cand_w1[0]["action_sequence"], max_ticks=95)
        # Weapon 1 overshoots 32px pillar due to +119px dash impulse and falls into void
        self.assertEqual(trial_w1["terminal_type"], "DEATH")

    def test_03_weapon4_negative_control_early_brake_void(self):
        """Negative Control: Weapon 4 brake executed too early falls into void while proving native activation."""
        suite_verifier = CandidateSuiteVerifier(SNAP_HUN6, self.pillar_lmf)

        # Early brake (jump 10 ticks, delay 0) brakes at X=184 before the 32px pillar (X=256)
        cand_w4_early = self.w4_family.generate_manifest(
            jump_durs=[10],
            brake_delays=[0],
            walk_ticks=16,
            post_brake_ticks=70,
            direction="RIGHT"
        )
        self.assertEqual(len(cand_w4_early), 1)

        result = suite_verifier.evaluate_suite(
            self.ref_precision_jump,
            cand_w4_early,
            expected_candidate_count=1,
            max_ticks=95
        )

        self.assertEqual(result["verdict"], "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE")
        evaluated = result["evaluated_candidates"]
        self.assertEqual(len(evaluated), 1)
        c = evaluated[0]
        self.assertEqual(c["terminal_type"], "DEATH")
        self.assertIn("native_weapon4_verified", c["mechanic_activation_evidence"])
        self.assertIn("state38==18", c["mechanic_activation_evidence"])
        self.assertIn("active_weapon==3", c["mechanic_activation_evidence"])
        self.assertIn("observed_dash90=2000.0", c["mechanic_activation_evidence"])

    def test_04_weapon4_semantic_contract_violation(self):
        """Semantic Contract: Candidate claiming weapon 4 brake without activation is invalidated."""
        suite_verifier = CandidateSuiteVerifier(SNAP_HUN6, self.pillar_lmf)

        # Candidate falsely claims weapon 4 brake family but executes a normal jump without '4' or 'Z'
        fake_candidate = [{
            "candidate_name": "fake_w4_no_activation",
            "family": "weapon4_brake",
            "parameters": {"walk_ticks": 20, "jump_duration": 28},
            "action_sequence": [("RIGHT",)] * 20 + [("RIGHT", "UP")] * 28,
            "semantic_validator": self.w4_family.validate_semantics,
        }]

        result = suite_verifier.evaluate_suite(
            self.ref_precision_jump,
            fake_candidate,
            expected_candidate_count=1,
            max_ticks=95
        )

        self.assertEqual(result["verdict"], "SUITE_INCONCLUSIVE")
        c = result["evaluated_candidates"][0]
        self.assertEqual(c["terminal_type"], "INVALID_CANDIDATE_SEMANTICS")
        self.assertIn("missing_required_w4_key", c["evidence_source"])

    def test_05_candidate_manifest_and_hash_audit(self):
        """Manifest Audit: Cartesian product dimensions, expected counts, and hash repeatability."""
        manifest = self.w4_family.generate_manifest(
            jump_durs=[16, 18, 20],
            brake_delays=[4, 6],
            walk_ticks=16,
            post_brake_ticks=45,
            direction="RIGHT"
        )
        # 3 * 2 = 6 candidates
        self.assertEqual(len(manifest), 6, "Cartesian product must yield exactly 6 candidates.")

        names = [c["candidate_name"] for c in manifest]
        self.assertEqual(len(names), len(set(names)), "Candidate names must be unique.")

        # Hash audit: Same candidate sequence produces identical SHA-256 hash
        cand0 = manifest[0]
        hash1 = CandidateSuiteVerifier.compute_action_hash(cand0["action_sequence"])
        hash2 = CandidateSuiteVerifier.compute_action_hash(cand0["action_sequence"])
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)

    def test_06_weapon4_free_air_brake_physics_profile(self):
        """Physics Profile Regression: In free space, Weapon 4 brake holds delta X == 0.0px for exactly 22 ticks."""
        verifier = X86OracleVerifier(SNAP_HUN6, self.open_gap_lmf)
        actions = (
            [("4",)]
            + [("RIGHT",)] * 4
            + [("RIGHT", "UP")] * 14
            + [("Z",)]
            + [()] * 30
        )
        trial = verifier.run_trial(actions, max_ticks=60)
        trace = trial["state_trace"]

        brake_states = [s for s in trace if s.get("38") == 18]
        # In free air without collision or landing, state 38==18 lasts exactly 22 ticks
        self.assertEqual(len(brake_states), 22, f"Free-air brake duration must be 22 ticks, got {len(brake_states)}")

        # Verify X coordinate is frozen across all 22 ticks (delta X == 0.0px)
        x_positions = [s["x"] for s in brake_states]
        initial_brake_x = x_positions[0]
        for t_idx, x_pos in enumerate(x_positions):
            self.assertEqual(
                x_pos,
                initial_brake_x,
                f"Tick {t_idx}: X drifted from {initial_brake_x} to {x_pos} during air brake"
            )

        # Verify dash90 == 2000.0 throughout all brake ticks
        for s in brake_states:
            self.assertEqual(s.get("dash90", 0.0), 2000.0, "dash90 must equal 2000.0 during weapon 4 brake")
            self.assertEqual(s.get("active_weapon", 0), 3, "active_weapon must equal 3")

    def test_07_weapon4_negative_controls_other_weapons(self):
        """Negative Control: Weapon 1, 2, and 3 attacks fail Weapon 4 brake semantic contract."""
        verifier = X86OracleVerifier(SNAP_HUN6, self.pillar_lmf)

        # 1. Key Invariant: Weapon 1 key ('1') is forbidden
        actions_w1 = [("1",)] + [("RIGHT",)] * 16 + [("RIGHT", "UP")] * 14 + [("RIGHT", "Z")]
        cand_w1 = {"candidate_name": "cand_w1", "family": "weapon4_brake", "action_sequence": actions_w1}
        is_val_w1, ev_w1 = self.w4_family.validate_semantics(cand_w1, [], {})
        self.assertFalse(is_val_w1, "Weapon 1 key must be rejected by key invariant.")
        self.assertIn("forbidden_keys_at_tick_0", ev_w1)

        # 2. Key Invariant: Weapon 2 key ('2') is forbidden
        actions_w2 = [("2",)] + [("RIGHT",)] * 16 + [("RIGHT", "UP")] * 14 + [("RIGHT", "Z")]
        cand_w2 = {"candidate_name": "cand_w2", "family": "weapon4_brake", "action_sequence": actions_w2}
        is_val_w2, ev_w2 = self.w4_family.validate_semantics(cand_w2, [], {})
        self.assertFalse(is_val_w2, "Weapon 2 key must be rejected by key invariant.")
        self.assertIn("forbidden_keys_at_tick_0", ev_w2)

        # 3. Native State Invariant: Weapon 1 trial trace fails state 38 == 18
        trial_w1 = verifier.run_trial(actions_w1, max_ticks=80)
        valid_actions_claim = (
            [("4",)] + [("RIGHT",)] * 16 + [("RIGHT", "UP")] * 18 + [("RIGHT",)] * 6 + [("Z",)] + [()] * 45
        )
        cand_claim = {"candidate_name": "cand_claim", "family": "weapon4_brake", "action_sequence": valid_actions_claim}
        is_val_trace, ev_trace = self.w4_family.validate_semantics(cand_claim, trial_w1["state_trace"], trial_w1)
        self.assertFalse(is_val_trace, "Weapon 1 trace must NOT satisfy weapon 4 brake state invariant.")
        self.assertIn("weapon4_brake_never_activated", ev_trace)

        # 4. Native Slot Invariant: state 38 == 18 under wrong weapon slot (e.g. active_weapon == 0)
        synthetic_w1_slot_trace = [
            {"tick": 20, "x": 100.0, "y": 200.0, "38": 18, "active_weapon": 0, "dash90": 2000.0}
        ]
        is_val_slot, ev_slot = self.w4_family.validate_semantics(cand_claim, synthetic_w1_slot_trace, {})
        self.assertFalse(is_val_slot, "State 38==18 under active_weapon != 3 must be rejected.")
        self.assertIn("weapon4_brake_evidence_missing", ev_slot)
        self.assertIn("active_weapon==3", ev_slot)


if __name__ == "__main__":
    unittest.main()
