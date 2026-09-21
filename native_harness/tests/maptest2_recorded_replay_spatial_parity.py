"""Replay the user's two jump/back-roll attempts across raw51 compaction."""
from pathlib import Path
import hashlib
import json
import sys
import time

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

SNAPSHOT = HARNESS / "private_snapshots" / "hun1_full.zip"
LMF = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\맵테스트2.LMF")
TRACE = HARNESS / "evidence" / "playground_recent_trace.jsonl"
LIMIT = 2000

records = [json.loads(line) for line in TRACE.read_text(encoding="utf-8").splitlines() if line]
keys_by_tick = {}
for row in records:
    if 1 <= row["tick"] <= LIMIT:
        keys_by_tick[row["tick"]] = tuple(row["input"])
schedule = [keys_by_tick.get(tick, ()) for tick in range(1, LIMIT + 1)]


def run(spatial_ids):
    api = NativeTrainingAPI(SNAPSHOT, LMF, track_dirty=False,
                            spatial_field_ids=spatial_ids)
    rows = []
    started = time.perf_counter()
    for keys in schedule:
        rows.append(api.step(1, keys))
    elapsed = time.perf_counter() - started
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return api, rows, elapsed, digest


baseline_api, baseline, baseline_seconds, baseline_hash = run((49,))
optimized_api, optimized, optimized_seconds, optimized_hash = run((49, 51))
first_mismatch = next((index + 1 for index, (a, b) in enumerate(zip(baseline, optimized))
                       if a != b), None)
result = {
    "ok": first_mismatch is None and 2000 / optimized_seconds >= 62.5,
    "scope": "user-recorded 맵테스트2 ticks 1..2000 including two jump/back-roll attempts",
    "ticks": LIMIT, "first_mismatch": first_mismatch,
    "player_states_exact": first_mismatch is None,
    "baseline": {"spatial_ids": [49], "seconds": round(baseline_seconds, 3),
                 "tick_rate": round(LIMIT / baseline_seconds, 2),
                 "final_runtime_counts": list(baseline_api.oracle.get(0x25CA048, "ii")),
                 "state_sha256": baseline_hash},
    "optimized": {"spatial_ids": [49, 51], "seconds": round(optimized_seconds, 3),
                  "tick_rate": round(LIMIT / optimized_seconds, 2),
                  "final_runtime_counts": list(optimized_api.oracle.get(0x25CA048, "ii")),
                  "state_sha256": optimized_hash},
    "final_player": optimized[-1],
}
(HARNESS / "evidence" / "maptest2_recorded_replay_spatial_parity.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
if not result["ok"]:
    raise SystemExit(1)
