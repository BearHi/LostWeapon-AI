"""Run the original x86 world chain across a raw124 disappearing-block cycle."""
from pathlib import Path
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from lmf_injector import NativeLmfOracle

OBJECT_BASE = 0x27A5998
OBJECT_STRIDE = 0xF8
GRID1_POINTER = 0x8952DEC


def main():
    snapshot, output = map(Path, sys.argv[1:3])
    object_index = int(sys.argv[3])
    tile_x, tile_y = map(int, sys.argv[4:6])
    ticks = int(sys.argv[6])
    lmf = Path(sys.argv[7]) if len(sys.argv) > 7 else None
    oracle = NativeLmfOracle(snapshot) if lmf else CapturedOracle(snapshot)
    builder_info = oracle.load_lmf(lmf) if lmf else None
    width, height = oracle.get(0x8952DB0, "ii")
    rows = []

    def sample(tick):
        raw = bytes(oracle.u.mem_read(oracle.addr(OBJECT_BASE + object_index * OBJECT_STRIDE), OBJECT_STRIDE))
        grid1 = oracle.get(GRID1_POINTER, "I")[0]
        rows.append({"tick": tick, "state": oracle.read_player_state(),
                     "object_c8": struct.unpack_from("<i", raw, 0xC8)[0],
                     "collision_code": struct.unpack("<H", oracle.u.mem_read(grid1 + 2 * (tile_y * width + tile_x), 2))[0]})

    sample(0)
    for tick in range(1, ticks + 1):
        oracle.step_world_chain(())
        sample(tick)
    transitions = []
    prior = None
    for row in rows:
        key = (row["collision_code"], row["object_c8"] == 0, row["object_c8"] == 255)
        if key != prior:
            transitions.append({"tick": row["tick"], "y": row["state"]["y"],
                                "motion58": row["state"]["motion58"], "state38": row["state"]["38"],
                                "object_c8": row["object_c8"], "collision_code": row["collision_code"]})
            prior = key
    result = {"scope": "original-x86-built LMF raw124 disappearing-block cycle" if lmf else "captured original-x86 raw124 disappearing-block cycle",
              "snapshot": str(snapshot), "object_index": object_index, "tile": [tile_x, tile_y],
              "lmf": str(lmf) if lmf else None, "builder_info": builder_info,
              "ticks": ticks, "transitions": transitions, "samples": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "ticks": ticks,
                      "c8_range": [min(r["object_c8"] for r in rows), max(r["object_c8"] for r in rows)],
                      "collision_codes": sorted(set(r["collision_code"] for r in rows)),
                      "y_range": [min(r["state"]["y"] for r in rows), max(r["state"]["y"] for r in rows)],
                      "transitions": transitions}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
