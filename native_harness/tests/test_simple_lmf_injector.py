"""Validate the simple LMF injector against the original 훈1 capture."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))

from captured_oracle import CapturedOracle
from lmf_injector import SimpleLmfOracle

SNAPSHOT = ROOT / "private_snapshots" / "hun1_full.zip"
MAP_DIR = PROJECT / "훈련용맵"
OUT = ROOT / "evidence" / "simple_lmf_injector.json"


def trajectory(oracle, keys, ticks):
    return [oracle.step_world_chain(keys, call_limit=2_000_000) for _ in range(ticks)]


def main():
    sequences = {
        "noop": [()] * 12,
        "right": [("RIGHT",)] * 12,
        "jump": [("UP",)] + [()] * 11,
        "front_roll": [("RIGHT", "DOWN")] * 12,
        "back_roll": [("LEFT", "DOWN")] * 12,
        "jump_backroll": [("UP",)] + [()] * 8 + [("LEFT", "DOWN")] * 3,
        "backroll_chute": [("LEFT", "DOWN")] * 8 + [("RIGHT", "C")] + [()] * 3,
    }
    comparisons = {}
    meta = None
    for name, actions in sequences.items():
        baseline = CapturedOracle(SNAPSHOT)
        injected = SimpleLmfOracle(SNAPSHOT)
        meta = injected.load_lmf(MAP_DIR / "훈1.LMF")
        baseline_trace = [baseline.step_world_chain(keys, call_limit=2_000_000) for keys in actions]
        injected_trace = [injected.step_world_chain(keys, call_limit=2_000_000) for keys in actions]
        comparisons[name] = baseline_trace == injected_trace
    exact_hun1 = all(comparisons.values())

    smoke = {}
    for name in ("훈2.LMF", "훈3.LMF", "훈4.LMF", "훈5.LMF"):
        oracle = SimpleLmfOracle(SNAPSHOT)
        loaded = oracle.load_lmf(MAP_DIR / name)
        direction = "LEFT" if name == "훈4.LMF" else "RIGHT"
        states = trajectory(oracle, [direction], 12)
        smoke[name] = {"load": loaded, "start": states[0], "end": states[-1]}

    result = {
        "scope": "simple LMF runtime-state injection; original x86 world-chain execution",
        "supported_tile_ids": sorted(injected.supported_ids),
        "hun1_exact_7_scenario_replay": exact_hun1,
        "hun1_scenario_matches": comparisons,
        "hun1": meta,
        "smoke": smoke,
        "limitations": [
            "훈2~5 are offline smoke executions, not normal-Client parity fixtures",
            "only captured 훈1 object templates 7/49/100/140 are supported",
            "goal/lava outcome and clearability are not asserted by this test",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not exact_hun1:
        raise SystemExit("injected 훈1 diverged from captured 훈1")


if __name__ == "__main__":
    main()
