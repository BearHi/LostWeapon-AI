"""Rotate flat and LMF combat episodes through one isolated combat checkpoint."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--maps", nargs="*", type=Path, default=[])
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--episodes-per-stage", type=int, default=1)
    parser.add_argument("--view-size", type=int, default=9)
    parser.add_argument("--max-steps", type=int, default=64)
    parser.add_argument("--no-flat", action="store_true", help="Retry maps without a flat stage")
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--checkpoint", type=Path,
                        default=ROOT / "checkpoints/combat_user_selected.pt")
    parser.add_argument("--log", type=Path,
                        default=ROOT / "checkpoints/combat_user_selected.jsonl")
    parser.add_argument("--status", type=Path,
                        default=ROOT / "checkpoints/combat_curriculum_status.json")
    args = parser.parse_args()
    if args.rounds < 1 or args.episodes_per_stage < 1:
        raise ValueError("rounds and episodes-per-stage must be positive")
    if args.no_flat and not args.maps:
        raise ValueError("--no-flat requires at least one selected map")
    for lmf in args.maps:
        if not lmf.is_file():
            raise FileNotFoundError(lmf)
    args.maps = [lmf.resolve() for lmf in args.maps]
    stages = [*args.maps] if args.no_flat else [None, *args.maps]
    total = args.rounds * len(stages)
    args.status.parent.mkdir(parents=True, exist_ok=True)

    def status(payload: dict) -> None:
        temporary = args.status.with_suffix(".tmp")
        temporary.write_text(json.dumps({**payload, "updated_at": time.time()},
                                        ensure_ascii=False), encoding="utf-8")
        temporary.replace(args.status)

    failures = []
    for index in range(total):
        if args.stop_file and args.stop_file.exists():
            status({"state": "stopped", "stage": index, "total_stages": total,
                    "failures": failures})
            return
        lmf = stages[index % len(stages)]
        name = str(lmf) if lmf else "flat_baseline"
        status({"state": "running", "stage": index + 1, "total_stages": total,
                "map": name, "failures": failures})
        command = [sys.executable, "-u", str(ROOT / "train_combat_selfplay.py"),
                   "--resume", "--episodes", str(args.episodes_per_stage),
                   "--max-steps", str(args.max_steps), "--view-size", str(args.view_size),
                   "--checkpoint", str(args.checkpoint), "--log", str(args.log)]
        if lmf:
            command += ["--lmf", str(lmf)]
        print(f"combat curriculum {index + 1}/{total}: {name}", flush=True)
        child = subprocess.Popen(command, cwd=ROOT)
        while child.poll() is None:
            if args.stop_file and args.stop_file.exists():
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                status({"state": "stopped", "stage": index + 1,
                        "total_stages": total, "map": name, "failures": failures})
                return
            time.sleep(0.5)
        code = child.returncode
        if code:
            failures.append({"map": name, "exit_code": code})
            print(f"stage failed: {name} ({code})", flush=True)
    status({"state": "complete" if not failures else "completed_with_failures",
            "stage": total, "total_stages": total, "failures": failures})
    print(json.dumps({"stages": total, "failures": failures}, ensure_ascii=False), flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
