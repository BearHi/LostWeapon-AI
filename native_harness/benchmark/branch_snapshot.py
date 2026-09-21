"""Measure the lightweight planner branch snapshot used by NativeTrainingAPI."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api import NativeTrainingAPI  # noqa: E402


def main():
    snapshot = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "private_snapshots" / "hun1_full.zip"
    lmf = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT.parent / "훈련용맵" / "훈2.LMF"
    output = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "evidence" / "branch_snapshot_benchmark.json"
    env = NativeTrainingAPI(snapshot, lmf)
    env.step(12, ["RIGHT"])
    expected = env.read_state()
    save_times = []
    restore_times = []
    page_counts = []
    byte_counts = []
    for _ in range(3):
        started = time.perf_counter()
        state = env.save_state()
        save_times.append(time.perf_counter() - started)
        page_counts.append(len(state["dirty"]))
        byte_counts.append(sum(len(data) for data in state["pages"].values()))
        env.step(12, ["UP"])
        started = time.perf_counter()
        env.restore_state(state)
        restore_times.append(time.perf_counter() - started)
        assert env.read_state() == expected
    result = {
        "scope": "NativeTrainingAPI process-local dirty branch snapshot benchmark",
        "snapshot": str(snapshot),
        "lmf": str(lmf),
        "repetitions": 3,
        "save_seconds": save_times,
        "restore_seconds": restore_times,
        "dirty_pages": page_counts,
        "saved_bytes": byte_counts,
        "replay_exact": True,
        "full_capture_bytes": sum(item["size"] for item in env.oracle.meta["regions"]),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "replay_exact": True,
        "median_save_ms": sorted(save_times)[1] * 1000,
        "median_restore_ms": sorted(restore_times)[1] * 1000,
        "dirty_pages": page_counts,
        "saved_bytes": byte_counts,
        "full_capture_bytes": result["full_capture_bytes"],
        "output": str(output),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
