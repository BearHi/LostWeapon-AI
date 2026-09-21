from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))

from api import SimpleTrainingAPI

env = SimpleTrainingAPI(
    ROOT / "private_snapshots" / "hun1_full.zip",
    PROJECT / "훈련용맵" / "훈2.LMF",
)
start = env.read_state()
first = env.step(12, ["RIGHT"])
reset = env.reset()
second = env.step(12, ["RIGHT"])
result = {
    "map": env.map,
    "start": start,
    "first": first,
    "reset": reset,
    "second": second,
    "reset_exact": start == reset,
    "replay_exact": first == second,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
if not result["reset_exact"] or not result["replay_exact"]:
    raise SystemExit("simple training API reset/replay mismatch")
