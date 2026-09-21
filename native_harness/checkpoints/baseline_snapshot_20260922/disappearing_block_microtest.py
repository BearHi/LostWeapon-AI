"""Read-only normal Client trace for a disappearing block and its collision cell."""
from __future__ import annotations
import argparse
import json
import struct
import time
from pathlib import Path

from live_state import Reader

OBJECT_BASE = 0x27A5998
OBJECT_STRIDE = 0xF8
GRID1_POINTER = 0x8952DEC


def run(pid: int, output: Path, object_index: int, tile_x: int, tile_y: int, seconds: float):
    reader = Reader(pid)
    samples = []
    first_object = None
    last_signature = None
    changed_offsets = set()
    try:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            state = reader.state()
            width, height = state["map_size"]
            raw = reader.get(OBJECT_BASE + object_index * OBJECT_STRIDE, f"{OBJECT_STRIDE}s")[0]
            if first_object is None:
                first_object = raw
            changed_offsets.update(i for i, (a, b) in enumerate(zip(first_object, raw)) if a != b)
            grid1 = reader.get(GRID1_POINTER, "I")[0]
            cell = struct.unpack("<H", reader.read(grid1 + 2 * (tile_y * width + tile_x), 2))[0]
            signature = (state["pos"], state["motion58"], tuple(state["state"].items()),
                         state["player_header"], raw, cell)
            if signature != last_signature:
                samples.append({"perf_ns": time.perf_counter_ns(), "state": state,
                                "object_hex": raw.hex(), "collision_code": cell})
                last_signature = signature
        result = {
            "scope": "read-only normal Client disappearing-block state, object record, and collision-cell trace",
            "pid": pid, "object_index": object_index, "tile": [tile_x, tile_y],
            "seconds": seconds, "changed_object_offsets_from_first": sorted(changed_offsets),
            "samples": samples,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "output": str(output), "samples": len(samples),
            "y_range": [min(s["state"]["pos"][1] for s in samples), max(s["state"]["pos"][1] for s in samples)],
            "states38": sorted(set(s["state"]["state"]["0x38"] for s in samples)),
            "collision_codes": sorted(set(s["collision_code"] for s in samples)),
            "changed_object_offsets": sorted(changed_offsets),
        }, ensure_ascii=False, indent=2))
    finally:
        reader.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("output", type=Path)
    parser.add_argument("--object-index", type=int, required=True)
    parser.add_argument("--tile-x", type=int, required=True)
    parser.add_argument("--tile-y", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=3.0)
    args = parser.parse_args()
    run(args.pid, args.output, args.object_index, args.tile_x, args.tile_y, args.seconds)
