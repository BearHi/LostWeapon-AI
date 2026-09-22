"""Regression Test: MapSpec Compiler Roundtrip and Semantic Parity.

Verifies that:
1. MapSpec correctly defines stg1_01_gap2.
2. MapCompiler builds an LMF identical in semantic content (records, dimensions, objects)
   to the verified reference LMF.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "native_harness"))

from map_compiler import MapSpec, MapCompiler
from lmf_injector import NativeLmfOracle


def test_compiler_semantic_parity():
    # 1. Existing verified reference map
    ref_lmf_path = ROOT / "훈련용맵" / "physics_curriculum" / "stg1_01_gap2.LMF"
    assert ref_lmf_path.exists(), f"Reference map missing: {ref_lmf_path}"

    w_ref, h_ref, recs_ref = NativeLmfOracle.parse_lmf(ref_lmf_path)
    ref_records_set = set(recs_ref)

    # 2. Extract spawn, goal, and non-spawn/goal tiles from reference
    spawn_rec = next(r for r in recs_ref if r[0] == 100)
    goal_rec = next(r for r in recs_ref if r[0] == 140)
    other_tiles = [{"id": r[0], "x": r[1], "y": r[2]} for r in recs_ref if r[0] not in (100, 140)]

    # 3. Create MapSpec
    spec = MapSpec.from_dict({
        "map_id": "stg1_01_gap2_roundtrip",
        "width": w_ref,
        "height": h_ref,
        "training_type": "isolated_skill",
        "spawn": {"x": spawn_rec[1], "y": spawn_rec[2]},
        "goal": {"x": goal_rec[1], "y": goal_rec[2]},
        "tiles": other_tiles,
        "metadata": {
            "required_mechanic": "basic_jump",
            "gap_tiles": 2
        }
    })

    # 4. Compile into temporary LMF
    out_compiled_path = ROOT / "scratch" / "compiled_stg1_01_gap2.LMF"
    MapCompiler.compile(spec, out_compiled_path)

    # 5. Parse compiled LMF and verify exact semantic parity
    w_out, h_out, recs_out = NativeLmfOracle.parse_lmf(out_compiled_path)
    out_records_set = set(recs_out)

    assert w_out == w_ref, f"Width mismatch: {w_out} != {w_ref}"
    assert h_out == h_ref, f"Height mismatch: {h_out} != {h_ref}"
    assert len(recs_out) == len(recs_ref), f"Record count mismatch: {len(recs_out)} != {len(recs_ref)}"
    assert out_records_set == ref_records_set, "Record content mismatch between reference and compiled LMF!"

    print("======================================================================")
    print(" [ROUNDTRIP PASS] MapSpec -> MapCompiler -> LMF Semantic Parity Verified!")
    print(f"  - Dimensions: {w_out}x{h_out}")
    print(f"  - Records: {len(recs_out)} identical tile records matched 100%")
    print("======================================================================")


if __name__ == "__main__":
    test_compiler_semantic_parity()
