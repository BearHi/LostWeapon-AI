"""Load every supplied training LMF through original Client x86 map builder."""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))

from lmf_injector import NativeLmfOracle

SNAPSHOT = ROOT / "private_snapshots" / "hun1_full.zip"
MAP_DIR = PROJECT / "훈련용맵"
OUT = ROOT / "evidence" / "native_lmf_all_training_maps.json"


def key(path):
    return float(re.fullmatch(r"훈(\d+(?:\.\d+)?)", path.stem).group(1))


def main():
    result = {
        "scope": "original x86 0x41e510 map build plus one full-world tick; normal-Client parity remains separate",
        "maps": {},
    }
    for path in sorted(MAP_DIR.glob("훈*.LMF"), key=key):
        try:
            oracle = NativeLmfOracle(SNAPSHOT)
            loaded = oracle.load_lmf(path)
            start = oracle.read_player_state()
            end = oracle.step_world_chain((), call_limit=2_000_000)
            result["maps"][path.name] = {
                "status": "PASS",
                "load": loaded,
                "start": start,
                "end": end,
            }
        except Exception as exc:
            result["maps"][path.name] = {"status": "BLOCKED", "error": str(exc)}
        print(path.name, result["maps"][path.name]["status"], flush=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "pass": sum(x["status"] == "PASS" for x in result["maps"].values()),
        "blocked": [name for name, x in result["maps"].items() if x["status"] != "PASS"],
        "output": str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
