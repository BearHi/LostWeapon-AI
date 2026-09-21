"""Compare a captured stable ice map with an original-x86-built LMF world."""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from lmf_injector import NativeLmfOracle

ACC = 0x25CA528
DIRECTION = 0x25CA078
FIELDS = ("x", "y", "motion58", "38", "68", "74", "b0", "c0", "c4", "d0", "dc", "acc", "dir")


def state(oracle):
    value = oracle.read_player_state()
    slot = oracle.meta["state"]["slot"]
    value["acc"] = oracle.get(ACC + slot * 4, "i")[0]
    value["dir"] = oracle.get(DIRECTION + slot * 4, "i")[0]
    return {field: value[field] for field in FIELDS}


def main():
    snapshot, lmf, output = map(Path, sys.argv[1:4])
    direction = sys.argv[4].upper()
    settle = int(sys.argv[5])
    held = int(sys.argv[6])
    released = int(sys.argv[7])

    captured = CapturedOracle(snapshot)
    built = NativeLmfOracle(snapshot)
    builder_info = built.load_lmf(lmf)
    count = builder_info["records"]
    object_size = count * built.OBJECT_STRIDE
    captured_objects = bytes(captured.u.mem_read(captured.addr(built.OBJECT_BASE), object_size))
    built_objects = bytes(built.u.mem_read(built.addr(built.OBJECT_BASE), object_size))
    object_differences = []
    for index in range(count):
        start = index * built.OBJECT_STRIDE
        if captured_objects[start:start + built.OBJECT_STRIDE] != built_objects[start:start + built.OBJECT_STRIDE]:
            object_differences.append(index)

    width, height = builder_info["size"]
    grid_size = width * height * 2
    grid_results = []
    for index, global_address in enumerate(built.GRID_POINTERS):
        captured_pointer = captured.get(global_address, "I")[0]
        built_pointer = built.get(global_address, "I")[0]
        expected_grid = bytes(captured.u.mem_read(captured_pointer, grid_size))
        actual_grid = bytes(built.u.mem_read(built_pointer, grid_size))
        differing_cells = []
        for cell in range(width * height):
            expected_code = struct.unpack_from("<H", expected_grid, cell * 2)[0]
            actual_code = struct.unpack_from("<H", actual_grid, cell * 2)[0]
            if expected_code != actual_code:
                differing_cells.append(cell)
        grid_results.append({
            "grid": index,
            "captured_sha256": hashlib.sha256(expected_grid).hexdigest(),
            "built_sha256": hashlib.sha256(actual_grid).hexdigest(),
            "differing_cells": differing_cells,
        })

    for _ in range(settle):
        built.step_world_chain(())

    differences = []
    boundary = 0
    if state(captured) != state(built):
        differences.append({"boundary": boundary, "captured": state(captured), "built": state(built)})
    actions = [(direction, "DOWN")] * held + [()] * released
    for keys in actions:
        boundary += 1
        captured.step_world_chain(keys)
        built.step_world_chain(keys)
        expected, actual = state(captured), state(built)
        if expected != actual:
            differences.append({"boundary": boundary, "captured": expected, "built": actual})

    result = {
        "scope": "captured stable ice world versus original-0x41e510-built and settled ice route parity",
        "snapshot": str(snapshot), "lmf": str(lmf), "builder_info": builder_info,
        "settle_ticks": settle, "schedule": {f"{direction}_DOWN_ticks": held, "NOOP_ticks": released},
        "compared_fields": list(FIELDS), "animation_phase_excluded": True,
        "state_boundaries": boundary + 1, "state_differences": len(differences),
        "state_parity": not differences, "differences": differences,
        "object_count": {"captured": count, "built": count},
        "byte_exact_object_records_before_step": not object_differences,
        "object_record_differences": object_differences,
        "all_collision_grids_byte_exact": all(not grid["differing_cells"] for grid in grid_results),
        "collision_grids": grid_results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "settle_ticks", "state_boundaries", "state_differences", "state_parity",
        "object_count", "byte_exact_object_records_before_step", "all_collision_grids_byte_exact")}, ensure_ascii=False, indent=2))
    if differences or object_differences or any(grid["differing_cells"] for grid in grid_results):
        raise SystemExit("captured/native-built ice parity mismatch")


if __name__ == "__main__":
    main()
