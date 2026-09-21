"""Read-only Client state and global keyboard timeline for parity diagnosis."""
from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
import time

from live_state import Reader

KEYS = {"LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
        "SPACE": 0x20, "C": 0x43, "Z": 0x5A, "X": 0x58,
        "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34}
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=600.0)
    parser.add_argument("--sample-ms", type=float, default=2.0)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    reader = Reader(args.pid)
    deadline = time.perf_counter() + args.seconds
    try:
        with args.output.open("w", encoding="utf-8", buffering=1) as stream:
            while time.perf_counter() < deadline:
                perf_ns = time.perf_counter_ns()
                try:
                    state = reader.state()
                    slot = state.get("slot")
                    if slot is None:
                        break
                    player = 0x3B12A00 + slot * 0xF8
                    row = {
                        "sample_perf_ns": perf_ns,
                        "keys": [name for name, vk in KEYS.items()
                                 if user32.GetAsyncKeyState(vk) & 0x8000],
                        "player": state,
                        "field_d8": reader.get(player + 0xD8, "i")[0],
                        "acc": reader.get(0x25CA528 + slot * 4, "i")[0],
                        "inertia_direction": reader.get(0x25CA078 + slot * 4, "i")[0],
                    }
                except OSError:
                    break
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                time.sleep(args.sample_ms / 1000.0)
    finally:
        reader.close()


if __name__ == "__main__":
    main()
