"""test_phase3c_real_map_integration.py - Phase 3C Real Map Integration Test Suite.

End-to-End verification proving that Map -> Oracle -> Reference vs Candidate -> Verdict
accurately detects real map defects on actual LMF maps:

Test A: Positive Control (Bypassable map)
  - Reference: Jump + Weapon 1 dash -> SUCCESS
  - Candidate: Delayed backroll -> SUCCESS
  - Expected Verdict: KNOWN_BYPASS_FOUND

Test B: Negative Control (Corrected weapon1-required map)
  - Reference: Jump + Weapon 1 dash -> SUCCESS
  - Candidate: IDENTICAL delayed backroll candidate -> TIMEOUT / DEATH
  - Expected Verdict: KNOWN_BYPASS_NOT_FOUND

Test C: Non-evaluable Controls
  - Subcase C1: Reference fails (DEATH) -> REFERENCE_FAILED (Candidate skipped)
  - Subcase C2: Reference INVALID -> VERIFIER_ERROR (Candidate skipped)
  - Subcase C3: Candidate INVALID -> INCONCLUSIVE (Candidate fault not treated as bypass failure)

Strict Guarantees:
  - Bit-exact initial_snapshot_signature equality between trials checked by assertion.
  - Identical max_ticks and native x86 oracle terminal event semantics across all trials.
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

from bypass_verifier import SingleBypassVerifier


def build_lmf_file(width: int, height: int, records: list[tuple[int, int, int]], out_path: Path) -> Path:
    """Build a standard 32-byte header + 8-byte record LMF binary."""
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


class TestPhase3CRealMapIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures_dir = ROOT / "scratch" / "phase3c_fixtures"
        cls.fixtures_dir.mkdir(parents=True, exist_ok=True)
        cls.snap_path = HARNESS_DIR / "private_snapshots" / "hun6_live.zip"

        w, h, gy = 30, 20, 14
        cls.base_records = []
        for x in range(w):
            cls.base_records.append((49, x, 17)) # Bottom lethal hazard
        cls.base_records.append((100, 3, gy - 1)) # Spawn: tile (3, 13) -> x=96, y=416
        cls.base_records.append((140, 20, gy - 1)) # Flag: tile (20, 13) -> x=640, y=416
        for x in range(1, 6):
            cls.base_records.append((7, x, gy)) # Start platform: x=1..5, y=14 (ends at 191)
        for x in range(12, 26):
            cls.base_records.append((7, x, gy)) # Target platform: x=12..25, y=14 (starts at 384)

        # Fixture A: Open map (no ceiling) - Positive Control
        cls.lmf_a = cls.fixtures_dir / "fixture_a_open_knife_gap.LMF"
        build_lmf_file(w, h, cls.base_records, cls.lmf_a)

        # Fixture B: Fixed map (overhead ceiling at y=0..6, x=10..12) - Negative Control
        cls.lmf_b = cls.fixtures_dir / "fixture_b_ceiling_knife_gap.LMF"
        recs_b = list(cls.base_records)
        for y in range(0, 7):
            for x in range(10, 13):
                recs_b.append((7, x, y))
        build_lmf_file(w, h, recs_b, cls.lmf_b)

        # 1. Reference Sequence: Jump + Weapon 1 dash
        # Schedule:
        #   t=0:       ('1',) -> Equip Weapon 1 (knife)
        #   t=1..16:   ('RIGHT',) -> Run right to edge of platform (16 ticks)
        #   t=17..34:  ('RIGHT', 'UP') -> Shallow jump (18 ticks)
        #   t=35:      ('RIGHT', 'Z') -> Mid-air knife forward dash (+119px boost)
        #   t=36..135: ('RIGHT',) -> Coast and run to flag (100 ticks)
        cls.ref_actions = [("1",)]
        for _ in range(16): cls.ref_actions.append(("RIGHT",))
        for _ in range(18): cls.ref_actions.append(("RIGHT", "UP"))
        cls.ref_actions.append(("RIGHT", "Z"))
        for _ in range(100): cls.ref_actions.append(("RIGHT",))

        # 2. Candidate Sequence: Delayed Backroll (no weapon)
        # Schedule:
        #   t=0..15:   ('RIGHT',) -> Run right to edge (16 ticks)
        #   t=16..43:  ('RIGHT', 'UP') -> High jump (28 ticks)
        #   t=44:      ('LEFT',) -> Turn facing left (1 tick)
        #   t=45..49:  ('RIGHT', 'DOWN') -> Delayed backroll trigger (5 ticks)
        #   t=50..149: ('RIGHT',) -> Glide and run to flag (100 ticks)
        cls.cand_actions = []
        for _ in range(16): cls.cand_actions.append(("RIGHT",))
        for _ in range(28): cls.cand_actions.append(("RIGHT", "UP"))
        cls.cand_actions.append(("LEFT",))
        for _ in range(5): cls.cand_actions.append(("RIGHT", "DOWN"))
        for _ in range(100): cls.cand_actions.append(("RIGHT",))

    def test_A_bypassable_positive_control(self):
        """Test A: On open map, reference succeeds and candidate backroll also succeeds -> KNOWN_BYPASS_FOUND."""
        verifier = SingleBypassVerifier(self.snap_path, self.lmf_a)
        res = verifier.evaluate(self.ref_actions, self.cand_actions, max_ticks=200)

        # Verify exact baseline signature equality
        ref_sig = res["reference_result"]["initial_snapshot_signature"]
        cand_sig = res["bypass_result"]["initial_snapshot_signature"]
        self.assertEqual(ref_sig, cand_sig, "Initial snapshot signatures must match exactly.")

        # Reference must succeed
        self.assertEqual(res["reference_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["reference_result"]["terminal_tick"], 121)

        # Candidate must succeed (finding the bypass)
        self.assertEqual(res["bypass_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["bypass_result"]["terminal_tick"], 100)

        # Verdict must be KNOWN_BYPASS_FOUND
        self.assertEqual(res["verdict"], "KNOWN_BYPASS_FOUND")

    def test_B_corrected_negative_control(self):
        """Test B: On corrected ceiling map, reference succeeds and candidate backroll FAILS -> KNOWN_BYPASS_NOT_FOUND."""
        verifier = SingleBypassVerifier(self.snap_path, self.lmf_b)
        res = verifier.evaluate(self.ref_actions, self.cand_actions, max_ticks=200)

        # Verify exact baseline signature equality
        ref_sig = res["reference_result"]["initial_snapshot_signature"]
        cand_sig = res["bypass_result"]["initial_snapshot_signature"]
        self.assertEqual(ref_sig, cand_sig, "Initial snapshot signatures must match exactly.")

        # Reference must succeed under the ceiling
        self.assertEqual(res["reference_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["reference_result"]["terminal_tick"], 121)

        # Candidate must FAIL (TIMED OUT / stopped short by overhang obstacle)
        self.assertEqual(res["bypass_result"]["terminal_type"], "TIMEOUT")
        self.assertEqual(res["bypass_result"]["terminal_tick"], 200)
        self.assertEqual(res["bypass_result"]["final_position"], (594.0, 448.0)) # Stopped before flag at 656.0

        # Verdict must be KNOWN_BYPASS_NOT_FOUND
        self.assertEqual(res["verdict"], "KNOWN_BYPASS_NOT_FOUND")

    def test_C1_reference_failed_control(self):
        """Test C1: Reference dies in pit -> REFERENCE_FAILED, bypass evaluation skipped."""
        verifier = SingleBypassVerifier(self.snap_path, self.lmf_a)
        # Broken reference that walks off platform without jumping
        bad_ref = [("RIGHT",)] * 100
        res = verifier.evaluate(bad_ref, self.cand_actions, max_ticks=200)

        self.assertEqual(res["verdict"], "REFERENCE_FAILED")
        self.assertEqual(res["reference_result"]["terminal_type"], "DEATH")
        self.assertIsNone(res["bypass_result"], "Bypass must not be evaluated when reference fails.")

    def test_C2_reference_invalid_control(self):
        """Test C2: Reference has unregistered input key -> VERIFIER_ERROR, bypass evaluation skipped."""
        verifier = SingleBypassVerifier(self.snap_path, self.lmf_a)
        invalid_ref = [("INVALID_KEY",)] * 50
        res = verifier.evaluate(invalid_ref, self.cand_actions, max_ticks=200)

        self.assertEqual(res["verdict"], "VERIFIER_ERROR")
        self.assertEqual(res["reference_result"]["terminal_type"], "INVALID")
        self.assertIsNone(res["bypass_result"], "Bypass must not be evaluated when reference is invalid.")

    def test_C3_candidate_invalid_control(self):
        """Test C3: Reference succeeds, but candidate has invalid input key -> INCONCLUSIVE."""
        verifier = SingleBypassVerifier(self.snap_path, self.lmf_a)
        invalid_cand = [("CORRUPT_INPUT",)] * 50
        res = verifier.evaluate(self.ref_actions, invalid_cand, max_ticks=200)

        self.assertEqual(res["verdict"], "INCONCLUSIVE")
        self.assertEqual(res["reference_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["bypass_result"]["terminal_type"], "INVALID")


if __name__ == "__main__":
    unittest.main()
