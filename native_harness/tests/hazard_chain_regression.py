"""Original-code regression for lava knockdown followed by spike contact."""
from pathlib import Path
import json
import struct
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI


def move_player(oracle, x, y):
    slot = oracle.meta["state"]["slot"]
    player = 0x3B12A00 + slot * 0xF8
    old_x, old_y = oracle.get(player, "dd")
    oracle.put(player, "dd", float(x), float(y))
    dx, dy = int(x - old_x), int(y - old_y)
    for offset, delta in ((0x18, dx), (0x1C, dy), (0x20, dx), (0x24, dy)):
        oracle.put(player + offset, "i", oracle.get(player + offset, "i")[0] + delta)


source = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\훈1.LMF")
fixture = HARNESS / "tests" / "hazard_chain_fixture.LMF"
raw = bytearray(source.read_bytes())
count = struct.unpack_from("<I", raw, 21)[0]
# raw48 is the Client fire damage object. raw49 is the separate lava/reset
# object, which intentionally writes the reset sentinel +0x7c=-1.
raw.extend(struct.pack("<Ihh", 48, 10, 13))
raw.extend(struct.pack("<Ihh", 86, 11, 13))
struct.pack_into("<I", raw, 21, count + 2)
fixture.write_bytes(raw)

api = NativeTrainingAPI(HARNESS / "private_snapshots" / "hun1_full.zip",
                        fixture, track_dirty=False)
oracle = api.oracle
oracle.place_player_at_spawn((10, 11))

lava_trace = []
for tick in range(60):
    state = api.step(1, ())
    lava_trace.append({"tick": tick, **state})
    if state["38"] == 5 and state["7c"] != 0:
        break
assert lava_trace[-1]["38"] == 5 and lava_trace[-1]["7c"] != 0, lava_trace

# Simulate the knockback path carrying the still-downed body onto the adjacent
# spike. Only position/bounds change; the Client's hit/recovery state is kept.
downed = lava_trace[-1]
move_player(oracle, 11 * 32 + 16, downed["y"])
spike_trace = []
for tick in range(16):
    state = api.step(1, ())
    spike_trace.append({"tick": tick, **state})

assert all(row["7c"] == downed["7c"] for row in spike_trace), spike_trace
result = {
    "ok": True,
    "scope": "original x86 lava knockdown followed by spike contact",
    "lava_hit": lava_trace[-1],
    "spike_while_downed": spike_trace,
}
(HARNESS / "evidence" / "hazard_chain_regression.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("PASS", {"lava_hit_tick": lava_trace[-1]["tick"],
               "downed_code": downed["7c"], "spike_ticks": len(spike_trace)})
