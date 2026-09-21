"""Compare aligned captured and original-built raw124 world cycles."""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from lmf_injector import NativeLmfOracle

OBJECT_BASE = 0x27A5998
OBJECT_STRIDE = 0xF8
FIELDS = ("x", "y", "motion58", "38", "68", "74", "b0", "c0", "c4", "d0", "dc")


def boundary(oracle, object_index, tile_x, tile_y):
    state = oracle.read_player_state()
    width = oracle.get(0x8952DB0, "i")[0]
    raw = bytes(oracle.u.mem_read(oracle.addr(OBJECT_BASE + object_index * OBJECT_STRIDE), OBJECT_STRIDE))
    grid1 = oracle.get(0x8952DEC, "I")[0]
    return {**{field: state[field] for field in FIELDS},
            "object_c8": struct.unpack_from("<i", raw, 0xC8)[0],
            "collision_code": struct.unpack("<H", oracle.u.mem_read(grid1 + 2 * (tile_y * width + tile_x), 2))[0]}


def main():
    snapshot, lmf, output = map(Path, sys.argv[1:4])
    captured = CapturedOracle(snapshot)
    built = NativeLmfOracle(snapshot)
    builder_info = built.load_lmf(lmf)
    for _ in range(65):
        captured.step_world_chain(())
    for _ in range(143):
        built.step_world_chain(())

    count = builder_info["records"]
    size = count * OBJECT_STRIDE
    expected_objects = bytes(captured.u.mem_read(captured.addr(OBJECT_BASE), size))
    actual_objects = bytes(built.u.mem_read(built.addr(OBJECT_BASE), size))
    object_differences = [index for index in range(count) if
                          expected_objects[index * OBJECT_STRIDE:(index + 1) * OBJECT_STRIDE] !=
                          actual_objects[index * OBJECT_STRIDE:(index + 1) * OBJECT_STRIDE]]
    width, height = builder_info["size"]
    grid_size = width * height * 2
    grids = []
    for index, pointer_global in enumerate(built.GRID_POINTERS):
        expected_pointer = captured.get(pointer_global, "I")[0]
        actual_pointer = built.get(pointer_global, "I")[0]
        expected = bytes(captured.u.mem_read(expected_pointer, grid_size))
        actual = bytes(built.u.mem_read(actual_pointer, grid_size))
        grids.append({"grid": index, "captured_sha256": hashlib.sha256(expected).hexdigest(),
                      "built_sha256": hashlib.sha256(actual).hexdigest(), "byte_exact": expected == actual})

    differences = []
    for cycle_tick in range(143):
        expected, actual = boundary(captured, 29, 6, 14), boundary(built, 29, 6, 14)
        if expected != actual:
            differences.append({"cycle_tick": cycle_tick, "captured": expected, "built": actual})
        captured.step_world_chain(())
        built.step_world_chain(())
    result = {
        "scope": "captured 훈20 world versus original-0x41e510-built raw124 full-cycle parity after phase alignment",
        "snapshot": str(snapshot), "lmf": str(lmf), "builder_info": builder_info,
        "phase_alignment": {"captured_noop_ticks": 65, "built_noop_ticks": 143},
        "cycle_ticks": 143, "compared_fields": list(FIELDS) + ["object_c8", "collision_code"],
        "state_differences": len(differences), "state_parity": not differences,
        "differences": differences, "object_count": count,
        "byte_exact_object_records_at_aligned_boundary": not object_differences,
        "object_record_differences": object_differences,
        "collision_grids": grids, "all_collision_grids_byte_exact": all(grid["byte_exact"] for grid in grids),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "phase_alignment", "cycle_ticks", "state_differences", "state_parity", "object_count",
        "byte_exact_object_records_at_aligned_boundary", "all_collision_grids_byte_exact")}, ensure_ascii=False, indent=2))
    if differences or object_differences or not result["all_collision_grids_byte_exact"]:
        raise SystemExit("captured/native-built raw124 cycle mismatch")


if __name__ == "__main__":
    main()
