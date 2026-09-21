"""Retry zero-clear maps in bounded batches, stopping after repeated clears."""
from __future__ import annotations

import argparse
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time
from snapshot_selector import snapshot_for_map

ROOT = Path(__file__).resolve().parent


def episodes(path: Path, minimum_episode: int):
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if int(row.get("episode", 0)) >= minimum_episode:
                    rows.append(row)
            except json.JSONDecodeError:
                pass
    except OSError:
        pass
    return rows


def write_status(path: Path, value):
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimum-episode", type=int, default=180)
    parser.add_argument("--required-successes", type=int, default=2)
    parser.add_argument("--max-attempts", type=int, default=12)
    parser.add_argument("--batch", type=int, default=3)
    parser.add_argument("--map-stems", nargs="*",
                        help="optional exact LMF stems to retry")
    args = parser.parse_args()
    checkpoint_dir = ROOT / "checkpoints"
    archive = checkpoint_dir / "map_clear_shared_dqn.episodes.jsonl"
    status = checkpoint_dir / "map_folder_status.json"
    lock_path = checkpoint_dir / "map_folder_training.lock"
    lock = lock_path.open("a+b"); lock.seek(0); lock.write(b"1"); lock.flush(); lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise SystemExit("folder training is already running")

    initial = episodes(archive, args.minimum_episode)
    by_map = {}
    for row in initial:
        by_map.setdefault(str(Path(row["map"]).resolve()), []).append(row)
    targets = [Path(path) for path, rows in by_map.items()
               if rows and not any(row.get("success") for row in rows)
               and (not args.map_stems or Path(path).stem in args.map_stems)]
    summary = {}
    for index, map_path in enumerate(targets):
        attempts = successes = 0
        while attempts < args.max_attempts and successes < args.required_successes:
            count = min(args.batch, args.max_attempts - attempts)
            started = time.time()
            command = [sys.executable, str(ROOT / "train_local_dqn.py"),
                       str(snapshot_for_map(ROOT, map_path)), str(map_path),
                       "--episodes", str(count), "--max-steps", "1500", "--action-repeat", "2",
                       "--checkpoint", str(checkpoint_dir / "map_clear_shared_dqn.pt"),
                       "--resume", "--skill-search"]
            child = subprocess.Popen(command, cwd=ROOT)
            while child.poll() is None:
                write_status(status, {"state": "retrying", "map": str(map_path),
                                      "attempts": attempts, "max_attempts": args.max_attempts,
                                      "successes": successes,
                                      "required_successes": args.required_successes,
                                      "remaining_maps": len(targets) - index,
                                      "elapsed_seconds": round(time.time() - started),
                                      "updated_at": time.time()})
                time.sleep(5)
            if child.returncode != 0:
                summary[str(map_path)] = {"status": "process_error", "attempts": attempts}
                break
            recent = episodes(archive, args.minimum_episode)
            new_rows = [row for row in recent if str(Path(row["map"]).resolve()) == str(map_path.resolve())]
            retries = new_rows[len(by_map[str(map_path.resolve())]):]
            attempts = len(retries)
            successes = sum(bool(row.get("success")) for row in retries)
        summary[str(map_path)] = {"status": "learned" if successes >= args.required_successes else "limit",
                                  "attempts": attempts, "successes": successes}
    write_status(status, {"state": "retry_complete", "summary": summary,
                          "updated_at": time.time()})


if __name__ == "__main__":
    main()
