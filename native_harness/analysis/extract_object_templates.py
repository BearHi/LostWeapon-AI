"""Extract small relocatable map-object templates from private Client captures."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle

SOURCES = [
    ROOT / "private_snapshots" / "hun1_full.zip",
    ROOT / "private_snapshots" / "current_live.zip",
]
OUTPUT = ROOT / "evidence" / "object_templates.json"
BASE = 0x27A5998
STRIDE = 0xF8


def main():
    templates = {}
    sources = []
    for snapshot in SOURCES:
        oracle = CapturedOracle(snapshot)
        count = oracle.get(0x25CA048, "i")[0]
        base = oracle.addr(BASE)
        found = []
        for index in range(count):
            raw = bytes(oracle.u.mem_read(base + index * STRIDE, STRIDE))
            tile_id = int.from_bytes(raw[0xD0:0xD4], "little")
            key = str(tile_id)
            if key not in templates:
                templates[key] = {
                    "source": snapshot.name,
                    "object_index": index,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes_hex": raw.hex(),
                }
                found.append(tile_id)
        sources.append({"snapshot": snapshot.name, "object_count": count, "new_ids": sorted(found)})
    result = {
        "scope": "248-byte captured Client runtime object templates; no behavior claim",
        "object_base": hex(BASE),
        "object_stride": STRIDE,
        "sources": sources,
        "templates": templates,
    }
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "ids": sorted(map(int, templates))}, indent=2))


if __name__ == "__main__":
    main()
