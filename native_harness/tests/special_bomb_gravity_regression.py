"""Keep raw87/88/95/96 bound to their native type-60 moving objects."""
from pathlib import Path
import json
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

LMF = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\맵테스트2.LMF")
api = NativeTrainingAPI(HARNESS / "private_snapshots/hun1_full.zip", LMF,
                        track_dirty=False)
oracle = api.oracle
_width, _height, records = oracle.parse_lmf(LMF)
family = (87, 88, 95, 96)
expected = [i for i, (tile, _x, _y) in enumerate(records) if tile in family]
moved = []
for record_index in expected:
    special_index = oracle.special_index_by_record[record_index]
    tile, x, y = records[record_index]
    address = 0xA074460 + special_index * 0xF8
    assert oracle.get(address + 0xD0, "i")[0] == tile
    native = oracle.get(address + 0x10, "dd")
    source = (x * 32.0 + 16.0, y * 32.0 - 1.0)
    if native != source:
        moved.append({"record": record_index, "raw": tile,
                      "source": list(source), "native": list(native)})

result = {
    "ok": len(oracle.special_index_by_record) == len(expected) and bool(moved),
    "scope": "original x86 LMF builder type-60 special-object positions",
    "mapped": len(oracle.special_index_by_record),
    "expected": len(expected),
    "objects_moved_by_native_builder": len(moved),
    "examples": moved[:8],
}
(HARNESS / "evidence/special_bomb_gravity_regression.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
if not result["ok"]:
    raise SystemExit(1)
