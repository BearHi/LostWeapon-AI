"""Identify the currently loaded training LMF from a read-only Client sample.

The map loader keeps the runtime object records in the Client process.  This
tool reads only the already-known object count, object tile ids, and positions;
it never writes memory, suspends the process, or sends input.  A match is made
against the supplied LMF directory using the same tile-centre convention used
by the native builder.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_state import Reader  # noqa: E402

OBJECT_BASE = 0x27A5998
OBJECT_STRIDE = 0xF8
OBJECT_ID = 0xD0
OBJECT_POS = 0x10


def parse_lmf(path: Path):
    raw = path.read_bytes()
    if len(raw) < 32:
        raise ValueError(f"short LMF header: {path}")
    width, height = struct.unpack_from("<HH", raw, 16)
    count = struct.unpack_from("<I", raw, 21)[0]
    if len(raw) != 32 + 8 * count:
        raise ValueError(f"LMF length/count mismatch: {path}")
    records = [struct.unpack_from("<Ihh", raw, 32 + 8 * i) for i in range(count)]
    runtime = [(tile_id, x * 32.0 + 16.0, y * 32.0 + 16.0)
               for tile_id, x, y in records]
    return width, height, records, runtime


def read_runtime(reader: Reader):
    count = reader.get(0x25CA048, "i")[0]
    if not 0 <= count <= 100000:
        raise RuntimeError(f"invalid runtime object count: {count}")
    records = []
    for index in range(count):
        address = OBJECT_BASE + index * OBJECT_STRIDE
        tile_id = reader.get(address + OBJECT_ID, "I")[0]
        x, y = reader.get(address + OBJECT_POS, "dd")
        records.append((tile_id, x, y))
    return records


def key(record):
    tile_id, x, y = record
    return tile_id, round(x, 6), round(y, 6)


def identify(pid: int, lmf_dir: Path, output: Path | None):
    reader = Reader(pid)
    try:
        state = reader.state()
        live = read_runtime(reader)
        live_keys = Counter(key(record) for record in live)
        candidates = []
        for path in sorted(lmf_dir.glob("*.LMF")):
            width, height, records, runtime = parse_lmf(path)
            expected = Counter(key(record) for record in runtime)
            common = sum((live_keys & expected).values())
            exact = live_keys == expected and len(live) == len(runtime)
            candidates.append({
                "lmf": str(path.resolve()),
                "name": path.name,
                "size": [width, height],
                "records": len(records),
                "common_runtime_records": common,
                "missing_records": sum((expected - live_keys).values()),
                "extra_records": sum((live_keys - expected).values()),
                "exact_runtime_records": exact,
            })
        candidates.sort(key=lambda item: (item["exact_runtime_records"],
                                           item["common_runtime_records"]), reverse=True)
        result = {
            "scope": "read-only live Client map identification by runtime object records",
            "pid": pid,
            "client_state": state,
            "runtime_object_count": len(live),
            "runtime_tile_ids": sorted(Counter(item[0] for item in live)),
            "exact_matches": [item["name"] for item in candidates if item["exact_runtime_records"]],
            "candidates": candidates,
        }
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
        print(json.dumps({
            "exact_matches": result["exact_matches"],
            "runtime_object_count": len(live),
            "map_size": state.get("map_size"),
            "top_candidates": candidates[:3],
        }, ensure_ascii=False, indent=2))
        return result
    finally:
        reader.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--lmf-dir", type=Path, default=Path(__file__).resolve().parents[1] / "훈련용맵")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    identify(args.pid, args.lmf_dir, args.output)


if __name__ == "__main__":
    main()
