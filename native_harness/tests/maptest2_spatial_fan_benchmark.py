"""Benchmark dense raw51 spatial activation and compare player state."""
from pathlib import Path
import json
import sys
import time

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

SNAPSHOT = HARNESS / "private_snapshots" / "hun1_full.zip"
LMF = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\맵테스트2.LMF")
SCHEDULE = [(40, ()), (24, ("RIGHT", "UP")), (12, ("LEFT", "DOWN")),
            (40, ()), (24, ("LEFT", "UP")), (12, ("RIGHT", "DOWN")), (48, ())]


def run(spatial_ids):
    api = NativeTrainingAPI(SNAPSHOT, LMF, track_dirty=False,
                            spatial_field_ids=spatial_ids)
    initial_counts = list(api.oracle.get(0x25CA048, "ii"))
    rows = []
    started = time.perf_counter()
    for count, keys in SCHEDULE:
        for _ in range(count):
            rows.append(api.step(1, keys))
    elapsed = time.perf_counter() - started
    return {"ticks": len(rows), "seconds": elapsed,
            "tick_rate": len(rows) / elapsed, "initial_counts": initial_counts,
            "final_counts": list(api.oracle.get(0x25CA048, "ii")), "rows": rows}


baseline = run((49,))
optimized = run((49, 51))
result = {
    "ok": baseline["rows"] == optimized["rows"] and optimized["tick_rate"] >= 62.5,
    "scope": "맵테스트2 dense raw51 spatial activation; same original-x86 input schedule",
    "player_states_exact": baseline["rows"] == optimized["rows"],
    "baseline": {k: round(v, 3) if isinstance(v, float) else v
                 for k, v in baseline.items() if k != "rows"},
    "optimized": {k: round(v, 3) if isinstance(v, float) else v
                  for k, v in optimized.items() if k != "rows"},
}
(HARNESS / "evidence" / "maptest2_spatial_fan_benchmark.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
if not result["ok"]:
    raise SystemExit(1)
