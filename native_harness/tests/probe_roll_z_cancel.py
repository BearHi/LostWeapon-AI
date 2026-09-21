"""Inspect Z pressed after a roll begins during its rising phase."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api import NativeTrainingAPI

api = NativeTrainingAPI(ROOT / "private_snapshots" / "hun1_live.zip",
                        ROOT.parent / "훈련용맵" / "훈1.LMF", track_dirty=True)
baseline = api.save_state()
initial_y = api.read_state()["y"]
for roll_ticks in (1, 2, 3, 4):
    rows = {}
    for followup in (("Z",), ("RIGHT", "DOWN"), ()):
        api.restore_state(baseline)
        for _ in range(roll_ticks):
            start = api.step(1, ("RIGHT", "DOWN"))
        after = api.step(1, followup)
        rows[followup] = (start, after)
    start, cancelled = rows[("Z",)]
    _, continued = rows[("RIGHT", "DOWN")]
    assert start["y"] < initial_y and start["motion58"] > 0
    assert cancelled["38"] == 15 and cancelled["c0"] == 0
    assert continued["38"] == 1 and continued["c0"] == 3
    assert cancelled["x"] > continued["x"]
print("PASS: Z cancels rising roll at ticks 1..4 in captured original x86")
