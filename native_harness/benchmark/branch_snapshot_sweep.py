"""Regression sweep for process-local dirty branch save/restore."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))
from api import NativeTrainingAPI  # noqa: E402

FIXTURES = {
    "hun2": ("hun2_live.zip", "훈2.LMF", ["RIGHT"]),
    "hun5": ("hun5_live.zip", "훈5.LMF", ["RIGHT", "C"]),
    "hun6": ("hun6_live.zip", "훈6.LMF", ["RIGHT", "UP"]),
    "hun7": ("hun7_live.zip", "훈7.LMF", ["RIGHT"]),
    "hun12": ("hun12_live.zip", "훈12.LMF", []),
}


def main():
    rows = {}
    for name, (snapshot_name, lmf_name, keys) in FIXTURES.items():
        started = time.perf_counter()
        env = NativeTrainingAPI(ROOT / "private_snapshots" / snapshot_name,
                                PROJECT / "훈련용맵" / lmf_name)
        env.step(12, keys)
        expected = env.read_state()
        save_start = time.perf_counter()
        branch = env.save_state()
        save_seconds = time.perf_counter() - save_start
        env.step(12, ["UP"] if name != "hun12" else [])
        restore_start = time.perf_counter()
        env.restore_state(branch)
        restore_seconds = time.perf_counter() - restore_start
        actual = env.read_state()
        row = {
            "status": "PASS" if actual == expected else "MISMATCH",
            "dirty_pages": len(branch["dirty"]),
            "saved_bytes": sum(len(data) for data in branch["pages"].values()),
            "save_seconds": save_seconds,
            "restore_seconds": restore_seconds,
            "elapsed_seconds": time.perf_counter() - started,
            "expected": expected,
            "actual": actual,
        }
        rows[name] = row
        print(name, row["status"], row["dirty_pages"], row["saved_bytes"], flush=True)
    result = {
        "scope": "NativeTrainingAPI process-local dirty branch save/restore sweep",
        "fixtures": rows,
        "all_pass": all(row["status"] == "PASS" for row in rows.values()),
    }
    output = ROOT / "evidence" / "branch_snapshot_sweep.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"all_pass": result["all_pass"], "output": str(output)}, ensure_ascii=False, indent=2))
    if not result["all_pass"]:
        raise SystemExit("branch snapshot sweep mismatch")


if __name__ == "__main__":
    main()
