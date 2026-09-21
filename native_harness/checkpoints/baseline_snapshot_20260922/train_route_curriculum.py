"""Visible, resumable 훈1~20 curriculum; optionally unlock 혼1~20 afterward."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
MAP_ROOT = ROOT.parent / "훈련용맵"
OUT = ROOT / "checkpoints/route_curriculum"
STOP = ROOT / "checkpoints/route_rule_helper.stop"
NAME = re.compile(r"^(훈|혼)(\d+(?:\.\d+)?)$")


def maps_for(stage):
    folder = MAP_ROOT if stage == "hun" else MAP_ROOT / "혼련용"
    prefix = "훈" if stage == "hun" else "혼"
    found = []
    for path in folder.glob("*.LMF"):
        match = NAME.fullmatch(path.stem)
        if match and match.group(1) == prefix and 1 <= float(match.group(2)) <= 20:
            found.append((float(match.group(2)), path))
    return [path for _, path in sorted(found)]


def checkpoint(path):
    if path.stem == "훈1":
        previous = ROOT / "checkpoints/route_rule_helper.json"
        if previous.exists() and not (OUT / "훈1.json").exists():
            return previous
    return OUT / f"{path.stem}.json"


def rows_for(path):
    archive = path.with_suffix(".episodes.jsonl")
    if not archive.exists():
        return []
    return [row for line in archive.read_text(encoding="utf-8").splitlines()
            if line.strip() for row in [json.loads(line)] if not row.get("interrupted")]


def score(path, window):
    rows = rows_for(checkpoint(path))
    recent = rows[-window:]
    return {"map": path.stem, "episodes": len(rows),
            "recent_success": sum(bool(row.get("done")) for row in recent),
            "recent_count": len(recent),
            "recent_rate": round(sum(bool(row.get("done")) for row in recent) /
                                 len(recent), 3) if recent else 0.0}


def save_status(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({**payload, "updated_at": time.time()},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("hun", "hon"), default="hun")
    parser.add_argument("--episodes-per-map", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--gate-window", type=int, default=5)
    parser.add_argument("--min-success", type=float, default=0.8)
    parser.add_argument("--retry-failed", action="store_true",
                        help="add one bounded block on maps below the success gate")
    parser.add_argument("--list", action="store_true", help="show maps without training")
    args = parser.parse_args()
    if args.episodes_per_map < 1 or args.max_steps < 1 or args.gate_window < 1:
        parser.error("episodes-per-map, max-steps, and gate-window must be positive")
    if not 0 <= args.min_success <= 1:
        parser.error("min-success must be between 0 and 1")
    hun = maps_for("hun")
    maps = maps_for(args.stage)
    if not hun or not maps:
        parser.error(f"no maps found for {args.stage}")
    if args.list:
        print(json.dumps({"stage": args.stage, "maps": [path.name for path in maps],
                          "count": len(maps)}, ensure_ascii=False, indent=2))
        return
    if args.stage == "hon":
        not_ready = [score(path, args.gate_window) for path in hun
                     if score(path, args.gate_window)["recent_count"] < args.gate_window or
                     score(path, args.gate_window)["recent_rate"] < args.min_success]
        if not_ready:
            parser.error("훈 stage has not passed the recent-success gate; "
                         f"see {OUT / 'hun_status.json'}")
    if STOP.exists():
        parser.error(f"stop marker exists: {STOP}; remove it with 깃발헬퍼_재개.bat")
    OUT.mkdir(parents=True, exist_ok=True)
    status_path = OUT / f"{args.stage}_status.json"
    source = checkpoint(hun[-1]) if args.stage == "hon" else None
    failures = []
    for index, path in enumerate(maps, 1):
        target = checkpoint(path)
        existing = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
        completed = int(existing.get("completed_episodes", 0))
        remaining = max(0, args.episodes_per_map - completed)
        current_score = score(path, args.gate_window)
        if args.retry_failed and remaining == 0 and (current_score["recent_count"] < args.gate_window or
                                                     current_score["recent_rate"] < args.min_success):
            remaining = args.episodes_per_map
        print(json.dumps({"phase": "map", "stage": args.stage,
                          "index": index, "total": len(maps), "map": path.name,
                          "existing_episodes": completed, "new_episodes": remaining,
                          "source": str(source) if source and not target.exists() else None},
                         ensure_ascii=False), flush=True)
        if remaining:
            command = [sys.executable, "-u", str(ROOT / "train_rule_helper.py"),
                       str(path), "--episodes", str(remaining),
                       "--max-steps", str(args.max_steps),
                       "--checkpoint", str(target), "--stop-file", str(STOP)]
            if source and source.exists() and not target.exists():
                command += ["--import-values", str(source)]
            code = subprocess.run(command, cwd=ROOT, check=False).returncode
            if code:
                failures.append({"map": path.name, "exit_code": code})
                print(json.dumps({"phase": "error", "map": path.name,
                                  "exit_code": code}, ensure_ascii=False), flush=True)
                break
        source = target if target.exists() else source
        report = [score(item, args.gate_window) for item in maps[:index]]
        save_status(status_path, {"state": "stopped" if STOP.exists() else "running",
                                  "stage": args.stage, "map_index": index,
                                  "total_maps": len(maps), "maps": report,
                                  "failures": failures})
        if STOP.exists():
            break
    report = [score(path, args.gate_window) for path in maps]
    passed = all(row["recent_count"] >= args.gate_window and
                 row["recent_rate"] >= args.min_success for row in report)
    state = "stopped" if STOP.exists() else "failed" if failures else \
        "ready" if passed else "needs_work"
    save_status(status_path, {"state": state, "stage": args.stage,
                              "total_maps": len(maps), "maps": report,
                              "failures": failures,
                              "gate": {"window": args.gate_window,
                                       "min_success": args.min_success}})
    print(json.dumps({"phase": "end", "stage": args.stage, "state": state,
                      "passed_maps": sum(row["recent_count"] >= args.gate_window and
                                         row["recent_rate"] >= args.min_success for row in report),
                      "total_maps": len(maps), "status": str(status_path)},
                     ensure_ascii=False), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
