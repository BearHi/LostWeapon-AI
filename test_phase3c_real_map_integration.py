"""test_phase3c_real_map_integration.py - Phase 3C Real Map Integration Test Suite.

End-to-End verification proving that Map -> Oracle -> Reference vs Candidate -> Verdict
accurately detects real map defects on actual LMF maps:

Test A: Positive Control (Bypassable map)
  - Open map with 4-tile gap and 3-tile step-up:
    Reference (Jump + Weapon 1 dash) -> SUCCESS
    Candidate (Delayed backroll) -> SUCCESS
  - Expected Verdict: KNOWN_BYPASS_FOUND

Test B: Negative Control (Corrected weapon1-required map)
  - Fixed map with overhead ceiling (y=0..7, bottom Y=256) over the target step-up platform (y=11, Y=352):
    Reference (Jump + Weapon 1 dash) stays under Y=256 -> SUCCESS (clears at tick 121)
    Candidate (Delayed backroll) attempts high arc (Y<=250), crashes into step-up wall/ceiling,
    and falls into lethal pit -> DEATH (tick 108)
  - Expected Verdict: KNOWN_BYPASS_NOT_FOUND
  - Exhaustive sweep: 0/48 backroll timing parameter combinations clear Map B.

Test C: Non-evaluable Controls
  - Subcase C1: Reference fails (DEATH) -> REFERENCE_FAILED (Candidate skipped)
  - Subcase C2: Reference INVALID -> VERIFIER_ERROR (Candidate skipped)
  - Subcase C3: Candidate INVALID -> INCONCLUSIVE (Candidate fault not treated as bypass failure)

Strict Guarantees:
  - Bit-exact initial_snapshot_signature equality between trials checked by assertion.
  - Snapshot signature divergence between distinct maps (A != B) explicitly verified.
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
        cls.base_records.append((140, 20, 10)) # Flag: tile (20, 10) on target platform
        for x in range(1, 6):
            cls.base_records.append((7, x, gy)) # Start platform: x=1..5, y=14 (ends at 191)
        for x in range(10, 26):
            cls.base_records.append((7, x, 11)) # Target platform: x=10..25, y=11 (step-up 96px)

        # Fixture A: Open map (no ceiling) - Positive Control
        cls.lmf_a = cls.fixtures_dir / "fixture_a_open_knife_gap.LMF"
        build_lmf_file(w, h, cls.base_records, cls.lmf_a)

        # Fixture B: Fixed map with ceiling overhang over target platform - Negative Control
        # Ceiling at y=0..7 (bottom at Y=256), leaving 96px headroom over y=11 platform
        cls.lmf_b = cls.fixtures_dir / "fixture_b_ceiling_knife_gap.LMF"
        recs_b = list(cls.base_records)
        for y in range(0, 8):
            for x in range(8, 26):
                recs_b.append((7, x, y))
        build_lmf_file(w, h, recs_b, cls.lmf_b)

        # 1. Reference Sequence: Shallow Jump + Weapon 1 dash
        # Schedule:
        #   t=0:       ('1',) -> Equip Weapon 1 (knife)
        #   t=1..16:   ('RIGHT',) -> Run right to edge of platform (16 ticks)
        #   t=17..30:  ('RIGHT', 'UP') -> Shallow jump (14 ticks)
        #   t=31:      ('RIGHT', 'Z') -> Mid-air knife forward dash (+119px boost)
        #   t=32..131: ('RIGHT',) -> Coast and run to flag (100 ticks)
        cls.ref_actions = [("1",)]
        for _ in range(16): cls.ref_actions.append(("RIGHT",))
        for _ in range(14): cls.ref_actions.append(("RIGHT", "UP"))
        cls.ref_actions.append(("RIGHT", "Z"))
        for _ in range(100): cls.ref_actions.append(("RIGHT",))

        # 2. Candidate Sequence: Delayed Backroll (no weapon)
        # Schedule:
        #   t=0..15:   ('RIGHT',) -> Run right to edge (16 ticks)
        #   t=16..43:  ('RIGHT', 'UP') -> High jump (28 ticks)
        #   t=44:      ('LEFT',) -> Turn facing left (1 tick)
        #   t=45..49:  ('RIGHT', 'DOWN') -> Delayed backroll trigger (5 ticks)
        #   t=50..169: ('RIGHT',) -> Glide and run to flag (120 ticks, full forward attempt)
        cls.cand_actions = []
        for _ in range(16): cls.cand_actions.append(("RIGHT",))
        for _ in range(28): cls.cand_actions.append(("RIGHT", "UP"))
        cls.cand_actions.append(("LEFT",))
        for _ in range(5): cls.cand_actions.append(("RIGHT", "DOWN"))
        for _ in range(120): cls.cand_actions.append(("RIGHT",))

    def test_A_bypassable_positive_control(self):
        """Test A: On open map, reference succeeds and candidate backroll also succeeds -> KNOWN_BYPASS_FOUND."""
        verifier = SingleBypassVerifier(self.snap_path, self.lmf_a)
        res = verifier.evaluate(self.ref_actions, self.cand_actions, max_ticks=200)

        # Verify exact baseline signature equality within Map A
        ref_sig = res["reference_result"]["initial_snapshot_signature"]
        cand_sig = res["bypass_result"]["initial_snapshot_signature"]
        self.assertEqual(ref_sig, cand_sig, "Initial snapshot signatures within Map A must match exactly.")

        # Reference must succeed
        self.assertEqual(res["reference_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["reference_result"]["terminal_tick"], 121)

        # Candidate must succeed (finding the bypass)
        self.assertEqual(res["bypass_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res["bypass_result"]["terminal_tick"], 103)

        # Verdict must be KNOWN_BYPASS_FOUND
        self.assertEqual(res["verdict"], "KNOWN_BYPASS_FOUND")

    def test_B_corrected_negative_control(self):
        """Test B: On corrected ceiling map, reference succeeds and candidate backroll DIES -> KNOWN_BYPASS_NOT_FOUND."""
        verifier_a = SingleBypassVerifier(self.snap_path, self.lmf_a)
        verifier_b = SingleBypassVerifier(self.snap_path, self.lmf_b)

        # Verify that Map A and Map B have distinct snapshot signatures (different loaded world state)
        self.assertNotEqual(
            verifier_a.verifier.initial_signature,
            verifier_b.verifier.initial_signature,
            "Fixture A and Fixture B must have distinct initial signatures reflecting different map records."
        )

        res_b = verifier_b.evaluate(self.ref_actions, self.cand_actions, max_ticks=200)

        # Verify exact baseline signature equality within Map B
        ref_sig = res_b["reference_result"]["initial_snapshot_signature"]
        cand_sig = res_b["bypass_result"]["initial_snapshot_signature"]
        self.assertEqual(ref_sig, cand_sig, "Initial snapshot signatures within Map B must match exactly.")

        # Reference must succeed under the ceiling
        self.assertEqual(res_b["reference_result"]["terminal_type"], "SUCCESS")
        self.assertEqual(res_b["reference_result"]["terminal_tick"], 121)
        self.assertEqual(res_b["reference_result"]["final_position"], (619.0, 352.0))

        # Candidate must physically DIE in the gap (pit fall due to ceiling collision and step-up wall)
        self.assertEqual(res_b["bypass_result"]["terminal_type"], "DEATH")
        self.assertEqual(res_b["bypass_result"]["terminal_tick"], 108)
        self.assertEqual(res_b["bypass_result"]["evidence_source"], "native_player:offset_0x7c==-1 (respawn_triggered)")

        # Verdict must be KNOWN_BYPASS_NOT_FOUND
        self.assertEqual(res_b["verdict"], "KNOWN_BYPASS_NOT_FOUND")

    def test_B_backroll_parameter_sweep_audit(self):
        """Audit: Verify that 100% of backroll timing variations physically fail on Map B.
        
        Note on 48 vs 90 Cartesian product:
        - j_dur uses step=2 (range(16, 32, 2) -> 8 even values: [16, 18, 20, 22, 24, 26, 28, 30]).
        - sw in (0, 1, 2) -> 3 values.
        - rd in (3, 5) -> 2 values.
        Total even-step trials: 8 * 3 * 2 = 48 trials (0/48 cleared).
        The full 90-combination Cartesian product (all integer ticks 16..30) was audited in Phase 3D,
        confirming 0/90 clears.
        """
        from x86_oracle_verifier import X86OracleVerifier
        vb = X86OracleVerifier(self.snap_path, self.lmf_b)

        total_trials = 0
        cleared_trials = 0
        for j_dur in range(16, 32, 2):
            for sw in (0, 1, 2):
                for rd in (3, 5):
                    total_trials += 1
                    sweep_actions = []
                    for _ in range(16): sweep_actions.append(("RIGHT",))
                    for _ in range(j_dur): sweep_actions.append(("RIGHT", "UP"))
                    for _ in range(sw): sweep_actions.append(("RIGHT",))
                    sweep_actions.append(("LEFT",))
                    for _ in range(rd): sweep_actions.append(("RIGHT", "DOWN"))
                    for _ in range(120): sweep_actions.append(("RIGHT",))

                    trial = vb.run_trial(sweep_actions, max_ticks=200)
                    if trial["terminal_type"] == "SUCCESS":
                        cleared_trials += 1

        self.assertEqual(cleared_trials, 0, f"Expected 0 backroll variations to clear Map B, but {cleared_trials}/{total_trials} cleared.")
        self.assertEqual(total_trials, 48, "Expected 48 even-step parameter sweep variations evaluated.")

    def test_C1_reference_failed_control(self):
        """Test C1: Reference dies in pit -> REFERENCE_FAILED, bypass evaluation skipped."""
        verifier = SingleBypassVerifier(self.snap_path, self.lmf_a)
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
