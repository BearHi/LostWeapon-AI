"""test_candidate_suite_verifier.py - Phase 3D CandidateSuiteVerifier Test Suite.

Verifies:
  1. Positive Control: Bypass in suite triggers KNOWN_BYPASS_FOUND with early termination and winner metadata.
  2. Negative Control: All clean failures trigger NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE.
  3. Reference Failed: Broken reference triggers REFERENCE_FAILED (0 candidates evaluated).
  4. Verifier Error: Corrupt reference triggers VERIFIER_ERROR (0 candidates evaluated).
  5. Suite Inconclusive: Invalid candidate input triggers SUITE_INCONCLUSIVE (no false negative).
  6. Expected Count Assertion: Mismatched count raises AssertionError.
  7. Metadata Preservation: All 8 required candidate fields are preserved and deterministic.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parent
HARNESS_DIR = ROOT / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from candidate_suite_verifier import CandidateSuiteVerifier


def build_lmf_file(width: int, height: int, records: list[tuple[int, int, int]], out_path: Path) -> Path:
    header = bytearray(32)
    header[:16] = b"NewLWMapFile_1.0"
    struct.pack_into("<HH", header, 16, width, height)
    header[20] = 0x12
    struct.pack_into("<I", header, 21, len(records))
    body = bytearray()
    for tile_id, x, y in records:
        body.extend(struct.pack("<Ihh", int(tile_id), int(x), int(y)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(header) + bytes(body))
    return out_path


class TestCandidateSuiteVerifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures_dir = ROOT / "scratch" / "phase3d_fixtures"
        cls.fixtures_dir.mkdir(parents=True, exist_ok=True)
        cls.snap_path = HARNESS_DIR / "private_snapshots" / "hun6_live.zip"

        w, h, gy = 30, 20, 14
        cls.base_records = []
        for x in range(w):
            cls.base_records.append((49, x, 17)) # Bottom lethal hazard
        cls.base_records.append((100, 3, gy - 1)) # Spawn: tile (3, 13) -> x=96, y=416
        cls.base_records.append((140, 20, 10)) # Flag: tile (20, 10) on target platform
        for x in range(1, 6):
            cls.base_records.append((7, x, gy)) # Start platform: x=1..5, y=14
        for x in range(10, 26):
            cls.base_records.append((7, x, 11)) # Target platform: x=10..25, y=11 (step-up 96px)

        # Map A: Open air (no ceiling) - Positive Control
        cls.lmf_a = cls.fixtures_dir / "suite_fixture_a_open.LMF"
        build_lmf_file(w, h, cls.base_records, cls.lmf_a)

        # Map B: Step-up with ceiling overhang (y=0..7, bottom Y=256) - Negative Control
        cls.lmf_b = cls.fixtures_dir / "suite_fixture_b_ceiling.LMF"
        recs_b = list(cls.base_records)
        for y in range(0, 8):
            for x in range(8, 26):
                recs_b.append((7, x, y))
        build_lmf_file(w, h, recs_b, cls.lmf_b)

        # Valid Reference: Shallow Jump + Weapon 1 dash
        cls.ref_actions = [("1",)]
        for _ in range(16): cls.ref_actions.append(("RIGHT",))
        for _ in range(14): cls.ref_actions.append(("RIGHT", "UP"))
        cls.ref_actions.append(("RIGHT", "Z"))
        for _ in range(100): cls.ref_actions.append(("RIGHT",))

    def _make_candidate(
        self,
        name: str,
        family: str,
        params: dict,
        actions: list[tuple[str, ...]],
    ) -> dict:
        return {
            "candidate_name": name,
            "family": family,
            "parameters": params,
            "action_sequence": actions,
        }

    def test_01_suite_known_bypass_found_with_early_termination(self):
        """Test 1: On open map, suite discovers backroll bypass, records winner, and early-terminates."""
        verifier = CandidateSuiteVerifier(self.snap_path, self.lmf_a)

        # Candidate 1: Plain walk (falls into gap -> DEATH)
        cand_walk = self._make_candidate(
            "walk_into_gap",
            "normal_jump_walk",
            {"mode": "walk"},
            [("RIGHT",)] * 80,
        )

        # Candidate 2: Running jump (falls short -> DEATH)
        jump_actions = [("RIGHT",)] * 16 + [("RIGHT", "UP")] * 16 + [("RIGHT",)] * 50
        cand_jump = self._make_candidate(
            "running_jump_16",
            "normal_jump_walk",
            {"jump_duration": 16},
            jump_actions,
        )

        # Candidate 3: High backroll (reaches target platform -> SUCCESS)
        backroll_actions = (
            [("RIGHT",)] * 16
            + [("RIGHT", "UP")] * 28
            + [("LEFT",)]
            + [("RIGHT", "DOWN")] * 5
            + [("RIGHT",)] * 120
        )
        cand_backroll = self._make_candidate(
            "delayed_backroll_j28_sw0_rd5",
            "delayed_backroll",
            {"jump_duration": 28, "switch_delay": 0, "roll_duration": 5},
            backroll_actions,
        )

        # Candidate 4: Extra candidate (should be skipped due to early exit!)
        cand_extra = self._make_candidate(
            "extra_candidate_should_skip",
            "weapon_free_movement",
            {"mode": "extra"},
            [("RIGHT",)] * 50,
        )

        manifest = [cand_walk, cand_jump, cand_backroll, cand_extra]
        res = verifier.evaluate_suite(
            self.ref_actions,
            manifest,
            expected_candidate_count=4,
            max_ticks=200,
        )

        self.assertEqual(res["verdict"], "KNOWN_BYPASS_FOUND")
        self.assertIsNotNone(res["winning_candidate"])
        self.assertEqual(res["winning_candidate"]["candidate_name"], "delayed_backroll_j28_sw0_rd5")
        self.assertEqual(res["winning_candidate"]["family"], "delayed_backroll")
        self.assertEqual(res["winning_candidate"]["parameters"]["jump_duration"], 28)
        self.assertEqual(res["winning_candidate"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["winning_candidate"]["terminal_tick"], 103)

        # Verify early termination: only 3 of 4 candidates were evaluated
        self.assertEqual(res["total_candidates_in_manifest"], 4)
        self.assertEqual(res["total_candidates_evaluated"], 3)
        self.assertEqual(len(res["evaluated_candidates"]), 3)

    def test_02_suite_no_known_bypass_found_in_tested_suite(self):
        """Test 2: On ceiling map, all candidates cleanly fail -> NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE."""
        verifier = CandidateSuiteVerifier(self.snap_path, self.lmf_b)

        manifest = [
            self._make_candidate(
                "cand_walk",
                "normal_jump_walk",
                {"type": "walk"},
                [("RIGHT",)] * 60,
            ),
            self._make_candidate(
                "cand_jump_shallow",
                "normal_jump_walk",
                {"jump_duration": 14},
                [("RIGHT",)] * 16 + [("RIGHT", "UP")] * 14 + [("RIGHT",)] * 50,
            ),
            self._make_candidate(
                "cand_backroll_j18",
                "delayed_backroll",
                {"jump_duration": 18, "switch_delay": 0, "roll_duration": 3},
                [("RIGHT",)] * 16 + [("RIGHT", "UP")] * 18 + [("LEFT",)] + [("RIGHT", "DOWN")] * 3 + [("RIGHT",)] * 100,
            ),
            self._make_candidate(
                "cand_backroll_j24",
                "delayed_backroll",
                {"jump_duration": 24, "switch_delay": 1, "roll_duration": 5},
                [("RIGHT",)] * 16 + [("RIGHT", "UP")] * 24 + [("RIGHT",)] + [("LEFT",)] + [("RIGHT", "DOWN")] * 5 + [("RIGHT",)] * 100,
            ),
            self._make_candidate(
                "cand_backroll_j28",
                "delayed_backroll",
                {"jump_duration": 28, "switch_delay": 0, "roll_duration": 5},
                [("RIGHT",)] * 16 + [("RIGHT", "UP")] * 28 + [("LEFT",)] + [("RIGHT", "DOWN")] * 5 + [("RIGHT",)] * 120,
            ),
            self._make_candidate(
                "cand_weapon_free_wait_jump",
                "weapon_free_movement",
                {"wait_ticks": 10, "jump_ticks": 16},
                [("RIGHT",)] * 10 + [()] * 10 + [("RIGHT", "UP")] * 16 + [("RIGHT",)] * 50,
            ),
        ]

        res = verifier.evaluate_suite(
            self.ref_actions,
            manifest,
            expected_candidate_count=6,
            max_ticks=200,
        )

        self.assertEqual(res["verdict"], "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE")
        self.assertIsNone(res["winning_candidate"])
        self.assertEqual(res["total_candidates_evaluated"], 6)

        # Verify all candidates failed cleanly with DEATH or TIMEOUT
        for c in res["evaluated_candidates"]:
            self.assertIn(c["terminal_type"], ("DEATH", "TIMEOUT"))
            self.assertEqual(c["initial_snapshot_signature"], verifier.baseline_signature)

    def test_03_suite_reference_failed_skips_suite(self):
        """Test 3: Reference failure immediately returns REFERENCE_FAILED with 0 candidate evaluations."""
        verifier = CandidateSuiteVerifier(self.snap_path, self.lmf_a)
        bad_ref = [("RIGHT",)] * 80 # Falls into pit -> DEATH

        manifest = [
            self._make_candidate("cand1", "normal_jump_walk", {}, [("RIGHT",)] * 50),
            self._make_candidate("cand2", "delayed_backroll", {}, [("RIGHT",)] * 50),
        ]

        res = verifier.evaluate_suite(bad_ref, manifest, expected_candidate_count=2, max_ticks=200)

        self.assertEqual(res["verdict"], "REFERENCE_FAILED")
        self.assertEqual(res["reference_result"]["terminal_type"], "DEATH")
        self.assertIsNone(res["winning_candidate"])
        self.assertEqual(res["total_candidates_evaluated"], 0)
        self.assertEqual(len(res["evaluated_candidates"]), 0)

    def test_04_suite_verifier_error_skips_suite(self):
        """Test 4: Invalid key in reference returns VERIFIER_ERROR with 0 candidate evaluations."""
        verifier = CandidateSuiteVerifier(self.snap_path, self.lmf_a)
        invalid_ref = [("UNREGISTERED_ACTION_KEY",)] * 10

        manifest = [
            self._make_candidate("cand1", "normal_jump_walk", {}, [("RIGHT",)] * 50),
        ]

        res = verifier.evaluate_suite(invalid_ref, manifest, expected_candidate_count=1, max_ticks=200)

        self.assertEqual(res["verdict"], "VERIFIER_ERROR")
        self.assertEqual(res["reference_result"]["terminal_type"], "INVALID")
        self.assertIsNone(res["winning_candidate"])
        self.assertEqual(res["total_candidates_evaluated"], 0)

    def test_05_suite_inconclusive_on_candidate_invalid(self):
        """Test 5: An invalid candidate prevents false security -> SUITE_INCONCLUSIVE."""
        verifier = CandidateSuiteVerifier(self.snap_path, self.lmf_b)

        manifest = [
            self._make_candidate("cand_walk", "normal_jump_walk", {}, [("RIGHT",)] * 50),
            self._make_candidate("cand_corrupt", "corrupt_family", {}, [("MALFORMED_KEY",)] * 20),
        ]

        res = verifier.evaluate_suite(self.ref_actions, manifest, expected_candidate_count=2, max_ticks=200)

        self.assertEqual(res["verdict"], "SUITE_INCONCLUSIVE")
        self.assertIsNone(res["winning_candidate"])
        self.assertEqual(res["total_candidates_evaluated"], 2)
        self.assertEqual(res["evaluated_candidates"][1]["terminal_type"], "INVALID")

    def test_06_expected_candidate_count_assertion(self):
        """Test 6: Manifest count mismatch raises AssertionError before running trials."""
        verifier = CandidateSuiteVerifier(self.snap_path, self.lmf_a)
        manifest = [
            self._make_candidate("cand1", "normal_jump_walk", {}, [("RIGHT",)] * 10),
        ]

        with self.assertRaises(AssertionError) as ctx:
            verifier.evaluate_suite(self.ref_actions, manifest, expected_candidate_count=3)
        self.assertIn("Candidate count mismatch", str(ctx.exception))

    def test_07_metadata_preservation_and_action_hashing(self):
        """Test 7: Verify all 8 audit fields are preserved and hashes are deterministic."""
        verifier = CandidateSuiteVerifier(self.snap_path, self.lmf_b)

        actions = [("RIGHT",)] * 20 + [("RIGHT", "UP")] * 10
        cand = self._make_candidate("test_meta", "normal_jump_walk", {"param_x": 42}, actions)

        res = verifier.evaluate_suite(self.ref_actions, [cand], expected_candidate_count=1)
        record = res["evaluated_candidates"][0]

        required_keys = [
            "candidate_name",
            "family",
            "parameters",
            "action_sequence_hash",
            "terminal_type",
            "terminal_tick",
            "evidence_source",
            "initial_snapshot_signature",
        ]
        for key in required_keys:
            self.assertIn(key, record, f"Missing required audit field: {key}")

        self.assertEqual(record["candidate_name"], "test_meta")
        self.assertEqual(record["family"], "normal_jump_walk")
        self.assertEqual(record["parameters"], {"param_x": 42})
        self.assertEqual(len(record["action_sequence_hash"]), 64) # Valid SHA-256 hex
        self.assertEqual(record["action_sequence_hash"], CandidateSuiteVerifier.compute_action_hash(actions))
        self.assertEqual(record["initial_snapshot_signature"], verifier.baseline_signature)


if __name__ == "__main__":
    unittest.main()
