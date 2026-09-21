"""Regression checks for the first interactive-playground user feedback."""
from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api import NativeTrainingAPI


api = NativeTrainingAPI(ROOT / "private_snapshots/hun1_full.zip",
                        ROOT.parent / "훈련용맵/훈1.LMF")
captured = json.loads((ROOT / "evidence/captured_tests.json").read_text())

api.reset()
# The playground now begins at the ID-100 marker and visibly falls onto the
# floor, while the older captured trace begins after that spawn fall. Verify
# the jump as an exact branch replay from the new start boundary.
for _ in range(20):
    api.step(1, ())
jump_start = api.save_state()
jump = [api.step(1, keys) for keys in ([("UP",)] + [()] * 80)]
api.restore_state(jump_start)
jump_replay = [api.step(1, keys) for keys in ([("UP",)] + [()] * 80)]
jump_exact = jump == jump_replay

api.reset()
for _ in range(4):
    api.step(1, ("LEFT",))
api.step(2, ())
left_idle = api.read_state()
right_first = api.step(1, ("RIGHT",))

api.reset()
for _ in range(4):
    api.step(1, ("LEFT",))
api.step(2, ())
backroll = [api.step(1, ("RIGHT", "DOWN")) for _ in range(42)]
backroll_facing_preserved = all(state["b0"] == 1 for state in backroll)
backroll_motion_right = backroll[0]["x"] > 96.0

fast_api = NativeTrainingAPI(ROOT / "private_snapshots/hun1_full.zip",
                             ROOT.parent / "훈련용맵/훈1.LMF", track_dirty=False)
started = time.perf_counter()
for _ in range(120):
    fast_api.step(1, ())
elapsed = time.perf_counter() - started
tps = 120 / elapsed

goal_api = NativeTrainingAPI(ROOT / "private_snapshots/hun1_full.zip",
                             ROOT.parent / "훈련용맵/훈1.LMF", track_dirty=False)
goal_state = None
for _ in range(200):
    goal_state = goal_api.step(1, ("RIGHT",))
goal_completion_path_runs = goal_state["x"] >= 748.0

result = {
    "ok": jump_exact and left_idle["b0"] == 1 and right_first["b0"] == 0
          and backroll_facing_preserved and backroll_motion_right and tps >= 60
          and goal_completion_path_runs,
    "jump_81_tick_branch_replay_exact": jump_exact,
    "left_idle_body_facing_b0": left_idle["b0"],
    "right_first_tick_body_facing_b0": right_first["b0"],
    "backroll_rightward_while_body_stays_left": backroll_facing_preserved and backroll_motion_right,
    "hun1_native_ticks_per_second": round(tps, 2),
    "goal_completion_path_runs_without_unsupported_avx": goal_completion_path_runs,
}
(ROOT / "evidence/playground_feedback_regression.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
if not result["ok"]:
    raise SystemExit(1)
