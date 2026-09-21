"""Replay the latest playground path and expose the raw53 activation boundary."""
from pathlib import Path
import json
import struct
import sys
import time

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

SNAPSHOT = HARNESS / "private_snapshots" / "hun1_full.zip"
LMF = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\맵테스트2.LMF")
TRACE = HARNESS / "evidence" / "playground_recent_trace.jsonl"
OUTPUT = HARNESS / "evidence" / "maptest2_latest_magnet_diagnosis.json"
LIMIT = 11720

source = [json.loads(line) for line in TRACE.read_text(encoding="utf-8").splitlines() if line]
keys = {row["tick"]: tuple(row["input"]) for row in source if 1 <= row["tick"] <= LIMIT}
api = NativeTrainingAPI(SNAPSHOT, LMF, track_dirty=False, spatial_field_ids=(49, 51))
slot = api.oracle.meta["state"]["slot"]
player = api.oracle.player_address
rows = []
started = time.perf_counter()
for tick in range(1, LIMIT + 1):
    state = api.step(1, keys.get(tick, ()))
    if 11460 <= tick <= LIMIT:
        rows.append({
            "tick": tick,
            "input": list(keys.get(tick, ())),
            "x": state["x"], "y": state["y"], "motion58": state["motion58"],
            "state38": state["38"], "dc": state["dc"],
            "field_d8": struct.unpack("<i", api.oracle.u.mem_read(player + 0xD8, 4))[0],
            "acc": api.oracle.get(0x25CA528 + slot * 4, "i")[0],
            "direction": api.oracle.get(0x25CA078 + slot * 4, "i")[0],
        })
elapsed = time.perf_counter() - started
activations = [r for r in rows if r["field_d8"]]
result = {
    "scope": "latest user-recorded maptest2 path around raw53 at (720,11472)",
    "ticks": LIMIT,
    "seconds": elapsed,
    "tick_rate": LIMIT / elapsed,
    "first_field_activation": activations[0] if activations else None,
    "last_field_activation": activations[-1] if activations else None,
    "rows": rows,
}
OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2))
