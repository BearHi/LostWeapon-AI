"""Compare native-built 훈1 with the captured 훈1 across seven action traces."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))

from captured_oracle import CapturedOracle
from lmf_injector import NativeLmfOracle

SNAPSHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "private_snapshots" / "hun1_full.zip"
LMF = Path(sys.argv[2]) if len(sys.argv) > 2 else PROJECT / "훈련용맵" / "훈1.LMF"
OUT = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "evidence" / "native_lmf_hun1_parity.json"
SEQUENCES = {
    "noop": [()] * 12,
    "right": [("RIGHT",)] * 12,
    "jump": [("UP",)] + [()] * 11,
    "front_roll": [("RIGHT", "DOWN")] * 12,
    "back_roll": [("LEFT", "DOWN")] * 12,
    "jump_backroll": [("UP",)] + [()] * 8 + [("LEFT", "DOWN")] * 3,
    "backroll_chute": [("LEFT", "DOWN")] * 8 + [("RIGHT", "C")] + [()] * 3,
}


def run(oracle, actions):
    return [oracle.step_world_chain(keys, call_limit=2_000_000) for keys in actions]


def main():
    tests = {}
    for name, actions in SEQUENCES.items():
        captured = CapturedOracle(SNAPSHOT)
        built = NativeLmfOracle(SNAPSHOT)
        built.load_lmf(LMF)
        expected = run(captured, actions)
        actual = run(built, actions)
        tests[name] = {
            "status": "PASS" if expected == actual else "MISMATCH",
            "expected_end": expected[-1],
            "actual_end": actual[-1],
        }
        print(name, tests[name]["status"], flush=True)
    result = {
        "scope": "captured 훈1 versus original-x86-built 훈1 tick-state parity",
        "map": str(LMF),
        "tests": tests,
        "all_pass": all(x["status"] == "PASS" for x in tests.values()),
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"all_pass": result["all_pass"], "output": str(OUT)}, ensure_ascii=False, indent=2))
    if not result["all_pass"]:
        raise SystemExit("native-built 훈1 parity mismatch")


if __name__ == "__main__":
    main()
