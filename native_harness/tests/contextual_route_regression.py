from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))

from contextual_routes import try_air_traverse_route, try_ladder_route, try_water_route
from native_env import LostWeaponEnv


cases = (
    ("ladder", "hun7_live.zip", "훈7.LMF", try_ladder_route),
    ("water", "hun12_live.zip", "훈12.LMF", try_water_route),
    ("air_traverse", "hun5_live.zip", "훈5.LMF", try_air_traverse_route),
    ("air_traverse_chain", "hun1_full.zip", "혼련용/혼2.LMF",
     try_air_traverse_route),
)
for mode, snapshot, lmf, controller in cases:
    if len(sys.argv) > 1 and mode not in sys.argv[1:]:
        continue
    env = LostWeaponEnv(ROOT / "private_snapshots" / snapshot,
                        PROJECT / "훈련용맵" / lmf,
                        action_repeat=2, max_steps=1500)
    result = controller(env, max_steps=1500)
    print(mode, {key: result.get(key) for key in
                 ("native_verified", "reason", "stage")},
          len(result["actions"]), result.get("state"), flush=True)
    assert result["native_verified"], {
        "reason": result.get("reason"), "stage": result.get("stage"),
        "steps": len(result["actions"]), "state": result.get("state")}
