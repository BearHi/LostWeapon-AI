"""Regression for jumping/back-rolling over a raw63 coin-block row.

The fixture was authored by the user specifically to separate a successful
timing window from a late failed attempt.  All transitions run original Client
x86 code through NativeTrainingAPI.
"""
from pathlib import Path
import json
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

SNAPSHOT = HARNESS / "private_snapshots" / "hun1_full.zip"
LMF = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\동전확인.LMF")
EVIDENCE = HARNESS / "evidence" / "coin_block_backroll_regression.json"


def run_attempt(api, baseline, trigger_tick):
    api.restore_state(baseline)
    trace = []
    for tick in range(45):
        if tick < trigger_tick:
            keys = ("UP",)
        elif tick < trigger_tick + 8:
            keys = ("LEFT", "DOWN")
        else:
            keys = ()
        state = api.step(1, keys)
        trace.append({"tick": tick, "keys": keys, **state})
    return {
        "trigger_tick": trigger_tick,
        "minimum_y": min(row["y"] for row in trace),
        "final": {key: trace[-1][key] for key in ("x", "y", "38", "c0")},
        "passed": trace[-1]["y"] == 416.0,
        "roll_start": next(({key: row[key] for key in
                             ("tick", "x", "y", "motion58", "38", "c0")}
                            for row in trace if row["38"] == 2 and row["c0"] == 4), None),
    }


api = NativeTrainingAPI(SNAPSHOT, LMF, track_dirty=True)
oracle = api.oracle
oracle.place_player_at_spawn((18, 18))
player = oracle.player_address
oracle.put(player, "dd", 592.0, 608.0)
oracle.put(player + 0xB0, "i", 0)  # face right; back-roll travels left
baseline = api.save_state()

early = run_attempt(api, baseline, 8)
late = run_attempt(api, baseline, 14)
assert early["passed"] and early["final"]["x"] == 388.0, early
assert not late["passed"], late

payload = {
    "fixture": str(LMF),
    "engine": "original Client x86",
    "start": {"x": 592.0, "y": 608.0, "facing": "right"},
    "normal_client_success_landing": {"x": 388.0, "y": 416.0},
    "early_native_attempt": early,
    "late_native_attempt": late,
    "verdict": "PASS",
}
EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))
