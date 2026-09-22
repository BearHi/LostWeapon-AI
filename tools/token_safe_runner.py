#!/usr/bin/env python3
"""
Token-Safe Subprocess Runner
Redirects all child process stdout and stderr directly to disk (runlogs/<run_id>.log).
Guarantees parent console output budget is strictly < 4KB.
Separates raw telemetry (.log / .jsonl) from structured summary (.summary.json).
"""

import sys
import os
import time
import argparse
import subprocess
import json
from pathlib import Path
from datetime import datetime

MAX_CONSOLE_BUDGET_BYTES = 4096

def run_token_safe():
    parser = argparse.ArgumentParser(
        description="Token-Safe Subprocess Runner for heavy x86 / sweep jobs.",
        usage="token_safe_runner.py [--run-id ID] [--summary-only] -- command [args...]"
    )
    parser.add_argument("--run-id", dest="run_id", default=None, help="Explicit run identifier")
    parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to execute")
    args = parser.parse_args()

    # Filter out leading '--' if passed
    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    if not cmd:
        sys.stderr.write("Error: No command provided to token_safe_runner.\n")
        sys.exit(2)

    root_dir = Path(__file__).resolve().parent.parent
    runlogs_dir = root_dir / "runlogs"
    runlogs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = args.run_id or f"run_{timestamp}_{os.getpid()}"

    log_path = runlogs_dir / f"{run_id}.log"
    summary_path = runlogs_dir / f"{run_id}.summary.json"
    jsonl_path = runlogs_dir / f"{run_id}.jsonl"
    progress_path = runlogs_dir / f"{run_id}.progress.json"

    # Child environment with runlog hints
    child_env = os.environ.copy()
    child_env["TOKEN_SAFE_RUN_ID"] = run_id
    child_env["TOKEN_SAFE_RUNLOGS_DIR"] = str(runlogs_dir)
    child_env["TOKEN_SAFE_LOG_PATH"] = str(log_path)
    child_env["TOKEN_SAFE_SUMMARY_PATH"] = str(summary_path)
    child_env["TOKEN_SAFE_JSONL_PATH"] = str(jsonl_path)
    child_env["TOKEN_SAFE_PROGRESS_PATH"] = str(progress_path)
    child_env["PYTHONUNBUFFERED"] = "1"

    # Initial progress file
    try:
        with open(progress_path, "w", encoding="utf-8") as pf:
            json.dump({
                "status": "running",
                "completed": 0,
                "total": None,
                "success": 0,
                "elapsed_sec": 0.0
            }, pf, indent=2)
    except Exception:
        pass

    # Exactly 1 line on start
    sys.stdout.write(f"=== TOKEN-SAFE RUN STARTED: {run_id} ===\n")
    sys.stdout.flush()

    start_time = time.time()
    
    with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=child_env,
            cwd=str(root_dir)
        )
        proc.wait()

    duration = round(time.time() - start_time, 3)
    exit_code = proc.returncode
    status = "SUCCESS" if exit_code == 0 else "FAILED"

    # Final progress file update
    try:
        if progress_path.exists():
            with open(progress_path, "r", encoding="utf-8") as pf:
                prog = json.load(pf)
            prog["status"] = "completed"
            prog["elapsed_sec"] = duration
            with open(progress_path, "w", encoding="utf-8") as pf:
                json.dump(prog, pf, indent=2)
    except Exception:
        pass

    # Analyze log file metrics
    log_size = log_path.stat().st_size if log_path.exists() else 0
    line_count = 0
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for _ in f:
                line_count += 1

    # Load or generate structured summary
    custom_metrics = {}
    if summary_path.exists():
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                custom_summary = json.load(f)
                custom_metrics = {k: v for k, v in custom_summary.items() if k not in ["run_id", "command"]}
        except Exception:
            pass
    else:
        # Create default summary
        default_summary = {
            "run_id": run_id,
            "command": cmd,
            "exit_code": exit_code,
            "duration_sec": duration,
            "status": status,
            "log_bytes": log_size,
            "log_lines": line_count
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(default_summary, f, indent=2)

    # Format strictly compact parent output (< 4KB budget)
    lines = [
        "=== TOKEN-SAFE RUN COMPLETED ===",
        f"RUN_ID:       {run_id}",
        f"EXIT_CODE:    {exit_code}",
        f"DURATION_SEC: {duration}",
        f"STATUS:       {status}",
        f"SUMMARY_PATH: {summary_path.relative_to(root_dir)}",
        f"LOG_PATH:     {log_path.relative_to(root_dir)} ({log_size} bytes, {line_count} lines)"
    ]

    if custom_metrics:
        # Compact 1-line display of key metrics if present
        key_items = [f"{k}={v}" for k, v in list(custom_metrics.items())[:8] if not isinstance(v, (dict, list))]
        if key_items:
            lines.append(f"METRICS:      {', '.join(key_items)}")

    output_str = "\n".join(lines) + "\n"
    output_bytes = output_str.encode("utf-8")

    if len(output_bytes) > MAX_CONSOLE_BUDGET_BYTES:
        output_str = output_str[:MAX_CONSOLE_BUDGET_BYTES - 64] + "\n[OUTPUT TRUNCATED TO ENFORCE <4KB BUDGET]\n"

    sys.stdout.write(output_str)
    sys.stdout.flush()

    sys.exit(exit_code)

if __name__ == "__main__":
    run_token_safe()
