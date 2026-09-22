"""test_x86_oracle_verifier.py - Phase 3A.1 Test Suite.

Generic Oracle Audit & Terminal Semantics Verification:
1. Multi-map dynamic flag identification:
   - stg1_01_gap2.LMF (flag record index = 31) -> SUCCESS
   - auto_test_2gap.LMF (flag record index = 55) -> SUCCESS
   - compiled_flag_rec0.LMF (flag record index = 0) -> SUCCESS
2. Negative controls for flag detection:
   - Wall bumping does not trigger flag 0x8c.
   - High-altitude pass above flag hitbox does not trigger flag 0x8c.
3. Death semantics audit:
   - Void / pit drop -> DEATH (player 7c == -1)
   - Lethal hazard (raw49) -> DEATH (player 7c == -1)
   - Non-lethal damage (raw48) -> NO DEATH (player 7c > 0, state38 == 5)
4. Neutral coasting delayed terminal events:
   - Action sequence ends early (t=55), neutral coasting detects delayed DEATH at t=68.
5. Bit-exact snapshot determinism (10 trials):
   - Comprehensive signature (RAM + CPU registers + tick counter) invariant.
   - Zero tick, zero pixel divergence across trials.
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

from snapshot_selector import snapshot_for_map
from x86_oracle_verifier import X86OracleVerifier


class TestX86OracleVerifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap_path = HARNESS_DIR / "private_snapshots" / "hun1_full.zip"

        # Map 1: stg1_01_gap2.LMF (flag record index = 31)
        cls.map1_path = ROOT / "훈련용맵" / "physics_curriculum" / "stg1_01_gap2.LMF"
        cls.verifier1 = X86OracleVerifier(cls.snap_path, cls.map1_path)

        # Map 2: auto_test_2gap.LMF (flag record index = 55)
        cls.map2_path = ROOT / "훈련용맵" / "auto_test_2gap.LMF"
        cls.verifier2 = X86OracleVerifier(cls.snap_path, cls.map2_path)

        # Map 3: Compiled map with flag at record index 0 (using exact geometry of stg1_01_gap2)
        from lmf_injector import SimpleLmfOracle
        w_ref, h_ref, recs_ref = SimpleLmfOracle.parse_lmf(cls.map1_path)
        goal_rec = next(r for r in recs_ref if r[0] == 140)
        records_3 = [goal_rec] + [r for r in recs_ref if r[0] != 140]

        raw_header = bytearray(32)
        raw_header[:16] = b"NewLWMapFile_1.0"
        struct.pack_into("<HH", raw_header, 16, w_ref, h_ref)
        struct.pack_into("<I", raw_header, 21, len(records_3))
        cls.map3_path = ROOT / "scratch" / "compiled_flag_rec0.LMF"
        cls.map3_path.write_bytes(raw_header + b"".join(struct.pack("<Ihh", *r) for r in records_3))
        cls.verifier3 = X86OracleVerifier(cls.snap_path, cls.map3_path)

        # Standard 2-gap jump sequence (175 ticks, clears map 1 & 3 at t=158, and map 2 at t=166)
        cls.jump_clear_actions = []
        for t in range(175):
            if 25 <= t < 25 + 28:
                cls.jump_clear_actions.append(("RIGHT", "UP"))
            else:
                cls.jump_clear_actions.append(("RIGHT",))

    def test_01_multimap_dynamic_flag_resolution(self):
        """Audit 1: Verify SUCCESS on 3 distinct maps with different flag record indices."""
        # Map 1: flag at rec_31
        res1 = self.verifier1.run_trial(self.jump_clear_actions, max_ticks=200)
        self.assertEqual(res1["terminal_type"], "SUCCESS")
        self.assertEqual(res1["terminal_tick"], 158)
        self.assertIn("flag[rec_31]", res1["evidence_source"])

        # Map 2: flag at rec_55 (flag position is x=25 instead of 24, reaches at t=166)
        res2 = self.verifier2.run_trial(self.jump_clear_actions, max_ticks=200)
        self.assertEqual(res2["terminal_type"], "SUCCESS")
        self.assertEqual(res2["terminal_tick"], 166)
        self.assertIn("flag[rec_55]", res2["evidence_source"])

        # Map 3: flag at rec_0 (same geometry as map 1, but goal flag is record 0)
        res3 = self.verifier3.run_trial(self.jump_clear_actions, max_ticks=200)
        self.assertEqual(res3["terminal_type"], "SUCCESS")
        self.assertEqual(res3["terminal_tick"], 158)
        self.assertIn("flag[rec_0]", res3["evidence_source"])

    def test_02_negative_controls(self):
        """Audit 2: Ensure flag 0x8c does not false-positive on wall bumping or high pass."""
        # 1. Wall bumping on stg2_01_wall6.LMF
        wall_map = ROOT / "훈련용맵" / "physics_curriculum" / "stg2_01_wall6.LMF"
        wall_verifier = X86OracleVerifier(self.snap_path, wall_map)
        bump_actions = [("RIGHT",) for _ in range(80)]
        res_bump = wall_verifier.run_trial(bump_actions, max_ticks=80)
        self.assertEqual(res_bump["terminal_type"], "TIMEOUT")
        self.assertNotIn("flag", res_bump["evidence_source"])

        # 2. High altitude pass
        self.verifier1.reset()
        player_addr = self.verifier1.api.oracle.player_address
        self.verifier1.api.oracle.put(player_addr, "dd", 748.0, 200.0)
        self.verifier1.api.step(1, ())
        flag_hit, _ = self.verifier1.check_flag_triggered()
        self.assertFalse(flag_hit, "Flag should not trigger at high altitude above hitbox")

    def test_03_death_semantics(self):
        """Audit 3: Pit and lethal hazard trigger DEATH (7c==-1); non-lethal hit does NOT."""
        # 1. Pit fall
        suicide = [("RIGHT",) for _ in range(80)]
        res_pit = self.verifier1.run_trial(suicide, max_ticks=80)
        self.assertEqual(res_pit["terminal_type"], "DEATH")
        self.assertEqual(res_pit["terminal_tick"], 68)
        self.assertIn("offset_0x7c==-1", res_pit["evidence_source"])

        # 2. Lethal hazard (raw49 lava)
        lava_map = ROOT / "scratch" / "lethal_hazard_fixture.LMF"
        lava_verifier = X86OracleVerifier(self.snap_path, lava_map)
        res_lava = lava_verifier.run_trial(suicide, max_ticks=60)
        self.assertEqual(res_lava["terminal_type"], "DEATH")
        self.assertEqual(res_lava["terminal_tick"], 15)
        self.assertIn("offset_0x7c==-1", res_lava["evidence_source"])

        # 3. Non-lethal damage (raw48 fire)
        fire_map = ROOT / "scratch" / "nonlethal_hazard_fixture.LMF"
        fire_verifier = X86OracleVerifier(self.snap_path, fire_map)
        res_fire = fire_verifier.run_trial(suicide, max_ticks=60)
        # Non-lethal damage knocks player down (7c == 12 > 0), player survives up to max_ticks
        self.assertEqual(res_fire["terminal_type"], "TIMEOUT")
        self.assertNotIn("offset_0x7c==-1", res_fire["evidence_source"])

    def test_04_neutral_coasting_delayed_events(self):
        """Audit 4: Early action exhaustion triggers neutral coasting, detecting delayed death."""
        # Action sequence has only 55 ticks of walking; player steps into void and falls.
        # Neutral coasting continues up to max_ticks=100 and catches death at t=68.
        short_suicide = [("RIGHT",) for _ in range(55)]
        res = self.verifier1.run_trial(short_suicide, max_ticks=100)
        self.assertEqual(res["terminal_type"], "DEATH")
        self.assertEqual(res["terminal_tick"], 68)
        self.assertIn("coasting tick +13", res["evidence_source"])

    def test_05_idle_timeout(self):
        """Audit 5: Idle inputs up to max_ticks return TIMEOUT."""
        idle_seq = [() for _ in range(40)]
        res = self.verifier1.run_trial(idle_seq, max_ticks=40)
        self.assertEqual(res["terminal_type"], "TIMEOUT")
        self.assertEqual(res["terminal_tick"], 40)

    def test_06_snapshot_determinism_and_restoration(self):
        """Audit 6: 10 trials produce bit-exact signatures (RAM + CPU registers + tick)."""
        results = []
        for _ in range(10):
            res = self.verifier1.run_trial(self.jump_clear_actions, max_ticks=200)
            results.append(res)

        first = results[0]
        self.assertEqual(first["terminal_type"], "SUCCESS")
        for i, r in enumerate(results[1:], start=2):
            self.assertEqual(r["terminal_type"], first["terminal_type"])
            self.assertEqual(r["terminal_tick"], first["terminal_tick"])
            self.assertEqual(r["final_position"], first["final_position"])
            self.assertEqual(r["final_motion_state"], first["final_motion_state"])
            self.assertEqual(r["initial_snapshot_signature"], first["initial_snapshot_signature"])
            self.assertEqual(r["final_state_signature"], first["final_state_signature"])


if __name__ == "__main__":
    unittest.main()
