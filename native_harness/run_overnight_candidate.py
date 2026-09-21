"""Resumeable, isolated native training over all playable training maps."""
from __future__ import annotations

import argparse
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from identify_live_map import parse_lmf
from snapshot_selector import snapshot_for_map

ROOT = Path(__file__).resolve().parent
DEFAULT_FOLDER = ROOT.parent / "훈련용맵"
DEFAULT_OUTPUT = ROOT / "checkpoints" / "overnight_candidate"
ACTIVE_OUTPUT = DEFAULT_OUTPUT


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path, payload):
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def result_from_log(path, byte_offset):
    with path.open("rb") as stream:
        stream.seek(byte_offset)
        lines = stream.read().decode("utf-8", errors="replace").splitlines()
    episode = None
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "episode" in row and "success" in row:
            episode = {"success": bool(row["success"]),
                       "steps": row.get("steps"), "reward": row.get("reward")}
    return episode, lines[-3:]


def family_key(path):
    match = re.search(r"(\d+(?:\.\d+)?)", path.stem)
    number = float(match.group(1)) if match else float("inf")
    return number, len(path.parts), str(path).lower()


def playable_maps(folder):
    maps, skipped = [], []
    for path in folder.rglob("*.LMF"):
        try:
            _width, _height, records, _runtime = parse_lmf(path)
            ids = {tile for tile, _x, _y in records}
            if 100 not in ids or 140 not in ids:
                skipped.append({"map": str(path), "reason": "no_spawn_or_goal"})
                continue
            maps.append((path, digest(path)))
        except (OSError, ValueError) as exc:
            skipped.append({"map": str(path), "reason": str(exc)})
    return sorted(maps, key=lambda item: family_key(item[0])), skipped


def main():
    global ACTIVE_OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--episodes-per-map", type=int, default=1)
    parser.add_argument("--stop-on-clear", action="store_true",
                        help="move to the next map after a native flag clear")
    parser.add_argument("--max-steps", type=int, default=750)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    ACTIVE_OUTPUT = args.output
    if args.episodes_per_map < 1 or args.max_steps < 1:
        raise ValueError("episodes-per-map and max-steps must be positive")
    maps, skipped = playable_maps(args.folder)
    if args.dry_run:
        print(json.dumps({"playable": len(maps), "skipped": skipped,
                          "candidate": str(args.output)}, ensure_ascii=False))
        return
    if not maps:
        raise SystemExit("no playable LMF maps found")
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output / "training.lock").open("a+b")
    lock.seek(0)
    lock.write(b"1")
    lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise SystemExit("overnight candidate training is already running")
    baseline = ROOT / "checkpoints" / "map_clear_shared_dqn.pt"
    checkpoint = args.output / "brain.pt"
    if not checkpoint.exists():
        shutil.copy2(baseline, checkpoint)
        for name in ("map_route_library.json", "map_transition_library.json"):
            source = baseline.parent / name
            if source.exists():
                shutil.copy2(source, args.output / name)
        write_json(args.output / "source.json", {
            "baseline": str(baseline), "baseline_sha256": digest(baseline),
            "created_at": time.time(), "promotion": "manual_policy_only_gate_required"})
    ledger_path = args.output / "ledger.json"
    status_path = args.output / "status.json"
    log_path = args.output / "training.log"
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        ledger = {"schema": 1, "completed": {}, "failed": {}}
    ledger.setdefault("results", {})
    started = time.time()
    print(f"Visible local training: {len(maps)} playable maps, {len(skipped)} skipped."
          f" Candidate: {checkpoint}", flush=True)
    while True:
        if (args.output / "stop.requested").exists():
            write_json(status_path, {"state": "stopped", "playable": len(maps),
                                     "elapsed_seconds": round(time.time() - started),
                                     "updated_at": time.time()})
            return
        pending = [(path, key) for path, key in maps
                   if ledger["completed"].get(key, 0) < args.episodes_per_map
                   and not (args.stop_on_clear and any(
                       row.get("success") for row in ledger["results"].get(key, [])))]
        success_maps = sum(any(row.get("success") for row in rows)
                           for rows in ledger["results"].values())
        if not pending:
            write_json(status_path, {"state": "complete", "playable": len(maps),
                                     "skipped": skipped, "failed": ledger["failed"],
                                     "success_maps": success_maps,
                                     "elapsed_seconds": round(time.time() - started),
                                     "updated_at": time.time()})
            print(f"Done: {success_maps}/{len(maps)} maps reached the goal area."
                  f" Report: {status_path}", flush=True)
            return
        # One episode on each map before a second pass prevents long single-map runs.
        path, key = min(pending, key=lambda item: (ledger["completed"].get(item[1], 0),
                                                   family_key(item[0])))
        completed = ledger["completed"].get(key, 0)
        print(f"[{maps.index((path, key)) + 1}/{len(maps)}] {path.name} "
              f"pass {completed + 1}/{args.episodes_per_map}", flush=True)
        command = [sys.executable, str(ROOT / "train_local_dqn.py"),
                   str(snapshot_for_map(ROOT, path)), str(path),
                   "--episodes", "1", "--max-steps", str(args.max_steps),
                   "--action-repeat", "2", "--checkpoint", str(checkpoint),
                   "--status", str(args.output / "map_runtime_status.json"),
                   "--resume", "--skill-search"]
        with log_path.open("a", encoding="utf-8") as log:
            log_offset = log_path.stat().st_size
            log.write(f"\n=== {path} pass {completed + 1}/{args.episodes_per_map} ===\n")
            log.flush()
            child = subprocess.Popen(command, cwd=ROOT, stdout=log,
                                     stderr=subprocess.STDOUT)
            last_console = 0.0
            stop_now = False
            while child.poll() is None:
                if (args.output / "stop.requested").exists():
                    child.terminate()
                    try:
                        child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                    stop_now = True
                    break
                write_json(status_path, {"state": "running", "map": str(path),
                                         "pass": completed + 1,
                                         "target_passes": args.episodes_per_map,
                                         "pending": len(pending), "playable": len(maps),
                                         "completed_maps": len(maps) - len(pending),
                                         "success_maps": success_maps,
                                         "skipped": len(skipped),
                                         "elapsed_seconds": round(time.time() - started),
                                         "updated_at": time.time()})
                now = time.monotonic()
                if now - last_console >= 15:
                    last_console = now
                    try:
                        detail = json.loads((args.output / "map_runtime_status.json")
                                            .read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        detail = {}
                    if detail.get("map") == str(path.resolve()):
                        if detail.get("state") == "running":
                            print(f"  tick {detail.get('tick', 0)}/"
                                  f"{detail.get('max_steps', args.max_steps)} "
                                  f"reward {detail.get('reward', 0)}", flush=True)
                        else:
                            print(f"  {detail.get('phase', 'planning')} "
                                  f"checks {detail.get('native_checks', 0)}", flush=True)
                    else:
                        print("  native map scan / route planning...", flush=True)
                time.sleep(5)
            result = child.returncode
        if stop_now:
            write_json(status_path, {"state": "stopped", "map": str(path),
                                     "playable": len(maps),
                                     "success_maps": success_maps,
                                     "updated_at": time.time()})
            print("Stopped by user. Current unfinished map will retry next run.",
                  flush=True)
            return
        episode, recent_lines = result_from_log(log_path, log_offset)
        ledger["completed"][key] = completed + 1 if result == 0 else args.episodes_per_map
        if result != 0:
            ledger["failed"][key] = {"map": str(path), "exit_code": result}
            print(f"  ERROR exit={result}; see {log_path}", flush=True)
            for line in recent_lines:
                print(f"  {line[:240]}", flush=True)
        elif episode is not None:
            ledger["results"].setdefault(key, []).append(episode)
            print(f"  goal_area={'YES' if episode['success'] else 'NO'} "
                  f"steps={episode['steps']} reward={episode['reward']}", flush=True)
        else:
            print(f"  no episode result; see {log_path}", flush=True)
        write_json(ledger_path, ledger)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        output = ACTIVE_OUTPUT
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "status.json", {"state": "crashed", "error": repr(exc),
                                             "updated_at": time.time()})
        raise
