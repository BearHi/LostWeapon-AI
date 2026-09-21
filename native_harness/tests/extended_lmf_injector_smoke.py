from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))

from api import SimpleTrainingAPI

maps = ("훈7.LMF", "훈7.5.LMF", "훈19.LMF")
OUT = ROOT / "evidence" / "extended_lmf_injector_smoke.json"
result = {
    "scope": "cross-capture object-template offline smoke; no normal-Client parity claim",
    "maps": {},
}
for name in maps:
    env = SimpleTrainingAPI(
        ROOT / "private_snapshots" / "hun1_full.zip",
        PROJECT / "훈련용맵" / name,
    )
    start = env.read_state()
    actions = ["UP"] if name.startswith("훈7") else ["LEFT"]
    first = env.step(12, actions)
    reset = env.reset()
    second = env.step(12, actions)
    result["maps"][name] = {
        "load": env.map,
        "start": start,
        "end": first,
        "reset_exact": start == reset,
        "replay_exact": first == second,
    }

OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
if not all(x["reset_exact"] and x["replay_exact"] for x in result["maps"].values()):
    raise SystemExit("extended injection replay mismatch")
