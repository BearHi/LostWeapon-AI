"""Run one bounded, visible offline-native route-helper check on 훈1."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    lmf = root.parent / "훈련용맵" / "훈1.LMF"
    if not lmf.is_file():
        print(f"Map not found: {lmf}", flush=True)
        return 2
    print("훈1 route helper: one bounded native physics check.", flush=True)
    print("The long DQN/folder trainer is not started.", flush=True)
    return subprocess.run(
        [sys.executable, "-u", str(root / "run_physics_first.py"),
         str(lmf), "--max-steps", "65"], cwd=root, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
