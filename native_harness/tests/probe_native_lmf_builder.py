"""Probe original Client function 0x41e510 as an LMF record materializer."""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))

from lmf_injector import SimpleLmfOracle

SNAPSHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "private_snapshots" / "hun1_full.zip"
LMF = Path(sys.argv[2]) if len(sys.argv) > 2 else PROJECT / "훈련용맵" / "훈1.LMF"
OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "evidence" / "native_lmf_builder_probe.json"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    oracle = SimpleLmfOracle(SNAPSHOT)
    width, height, records = oracle.parse_lmf(LMF)
    cells = width * height
    object_base = oracle.addr(oracle.OBJECT_BASE)
    expected_objects = bytes(oracle.u.mem_read(object_base, len(records) * oracle.OBJECT_STRIDE))
    expected_grids = []
    for address in oracle.GRID_POINTERS:
        pointer = oracle.get(address, "I")[0]
        expected_grids.append(bytes(oracle.u.mem_read(pointer, cells * 2)))

    initial = [bytearray(cells * 2) for _ in range(4)]
    initial[2][:] = b"\x01" * (cells * 2)
    initial[3][:] = b"\xff" * (cells * 2)
    for index, (address, raw) in enumerate(zip(oracle.GRID_POINTERS, initial)):
        pointer = oracle.INJECT_MEMORY + index * 0x4000
        oracle.u.mem_write(pointer, bytes(raw))
        oracle.put(address, "I", pointer)
    oracle.put(0x8952DB0, "II", width, height)
    oracle.put(0xA073150, "I" * height, *[y * width for y in range(height)])
    room = oracle.get(0xAA16538, "i")[0]
    oracle.put(0xAA0411E + room * 0x124, "hh", width, height)
    oracle.put(0x25CA048, "ii", 0, 0)
    oracle.u.mem_write(object_base, bytes(len(records) * oracle.OBJECT_STRIDE))

    calls = []
    for tile_id, x, y in records:
        try:
            oracle.call(0x41E510, struct.pack("<iii", tile_id, x, y), limit=2_000_000)
            calls.append({"record": [tile_id, x, y], "status": "PASS"})
        except Exception as exc:
            calls.append({"record": [tile_id, x, y], "status": "BLOCKED", "error": str(exc), "fault": oracle.fault})
            break

    actual_count = oracle.get(0x25CA048, "i")[0]
    actual_objects = bytes(oracle.u.mem_read(object_base, len(records) * oracle.OBJECT_STRIDE))
    actual_grids = []
    for address in oracle.GRID_POINTERS:
        pointer = oracle.get(address, "I")[0]
        actual_grids.append(bytes(oracle.u.mem_read(pointer, cells * 2)))
    result = {
        "scope": "original x86 0x41e510 LMF-record materializer probe",
        "map": str(LMF),
        "records": len(records),
        "calls_completed": sum(x["status"] == "PASS" for x in calls),
        "first_failure": next((x for x in calls if x["status"] != "PASS"), None),
        "object_count": actual_count,
        "objects_exact": actual_objects == expected_objects,
        "object_hash_expected": digest(expected_objects),
        "object_hash_actual": digest(actual_objects),
        "grids_exact": [a == b for a, b in zip(actual_grids, expected_grids)],
        "grid_hash_expected": list(map(digest, expected_grids)),
        "grid_hash_actual": list(map(digest, actual_grids)),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
