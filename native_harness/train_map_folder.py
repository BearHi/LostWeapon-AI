"""Continuously train every unprocessed LMF in one folder, serially."""
from __future__ import annotations

import argparse
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from snapshot_selector import snapshot_for_map

ROOT = Path(__file__).resolve().parent


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def natural_key(path: Path):
    parts = re.split(r"(\d+(?:\.\d+)?)", path.stem)
    return [float(value) if re.fullmatch(r"\d+(?:\.\d+)?", value) else value.lower()
            for value in parts]


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--episodes", type=int, default=3)
    parser.add_argument("--min-number", type=float, default=None)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    args = parser.parse_args()
    lock_path = ROOT / "checkpoints" / "map_folder_training.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = lock_path.open("a+b")
    lock.seek(0); lock.write(b"1"); lock.flush(); lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("folder training is already running", flush=True)
        return
    ledger_path = ROOT / "checkpoints" / "map_folder_ledger.json"
    status_path = ROOT / "checkpoints" / "map_folder_status.json"
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        ledger = {"schema": 1, "completed": {}}

    while True:
        maps = sorted(args.folder.glob("*.LMF"), key=natural_key)
        pending = []
        for path in maps:
            match = re.search(r"(\d+(?:\.\d+)?)", path.stem)
            if args.min_number is not None and match and float(match.group(1)) < args.min_number:
                continue
            digest = file_hash(path)
            if ledger["completed"].get(digest, 0) < args.episodes:
                pending.append((path, digest))
        if not pending:
            write_json(status_path, {"state": "watching" if args.watch else "complete",
                                     "folder": str(args.folder.resolve()), "pending": 0,
                                     "updated_at": time.time()})
            if not args.watch:
                return
            time.sleep(args.poll_seconds)
            continue

        path, digest = pending[0]
        completed = int(ledger["completed"].get(digest, 0))
        remaining = args.episodes - completed
        write_json(status_path, {"state": "running", "map": str(path.resolve()),
                                 "completed": completed, "target": args.episodes,
                                 "queue_remaining": len(pending), "updated_at": time.time()})
        command = [sys.executable, str(ROOT / "train_local_dqn.py"),
                   str(snapshot_for_map(ROOT, path)), str(path),
                   "--episodes", str(remaining), "--max-steps", "1500",
                   "--action-repeat", "2", "--checkpoint",
                   str(ROOT / "checkpoints" / "map_clear_shared_dqn.pt"),
                   "--resume", "--skill-search"]
        started = time.time()
        child = subprocess.Popen(command, cwd=ROOT)
        while child.poll() is None:
            write_json(status_path, {"state": "running", "map": str(path.resolve()),
                                     "completed": completed, "target": args.episodes,
                                     "queue_remaining": len(pending),
                                     "elapsed_seconds": round(time.time() - started),
                                     "updated_at": time.time()})
            time.sleep(5)
        result_code = child.returncode
        if result_code == 0:
            ledger["completed"][digest] = args.episodes
            write_json(ledger_path, ledger)
        else:
            write_json(status_path, {"state": "map_failed", "map": str(path.resolve()),
                                     "exit_code": result_code,
                                     "updated_at": time.time()})
            # Do not loop forever on one broken map in watch mode.
            ledger["completed"][digest] = args.episodes
            ledger.setdefault("failed", {})[digest] = str(path.resolve())
            write_json(ledger_path, ledger)


if __name__ == "__main__":
    main()
