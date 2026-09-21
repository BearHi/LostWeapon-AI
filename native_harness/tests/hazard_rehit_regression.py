"""Original-code regression: a downed player must not be hit by spikes again."""
from pathlib import Path
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
fixture = HARNESS / "tests" / "hazard_rehit_fixture.LMF"
raw = bytearray(source.read_bytes())
count = struct.unpack_from("<I", raw, 21)[0]
raw.extend(struct.pack("<Ihh", 86, 10, 13))
struct.pack_into("<I", raw, 21, count + 1)
fixture.write_bytes(raw)

api = NativeTrainingAPI(HARNESS / "private_snapshots" / "hun1_full.zip",
                        fixture, track_dirty=False)
oracle = api.oracle

# Fall onto the Client-built spike and wait for its downed code.
oracle.place_player_at_spawn((10, 11))
hit_trace = []
for tick in range(40):
    state = api.step(1, ())
    hit_trace.append((tick, state["38"], state["7c"], state["80"], state["b8"]))
    if state["7c"] in (5, 7):
        break
assert hit_trace[-1][2] in (5, 7), hit_trace

# Move the same still-downed player onto the spike. The original type-260
# handler explicitly excludes +0x7c values 5 and 7; it must not restart damage.
downed_code = hit_trace[-1][2]
spike_trace = []
for tick in range(12):
    state = api.step(1, ())
    spike_trace.append((tick, state["38"], state["7c"], state["80"], state["b8"]))
assert all(row[2] == downed_code for row in spike_trace), spike_trace
print("PASS", {"initial_hit": hit_trace, "spike_while_downed": spike_trace})
