"""Read-only multi-player/team-base trace from a normal Client."""
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
    parser.add_argument("--seconds", type=float, default=180)
    parser.add_argument("--sample-ms", type=float, default=2)
    args = parser.parse_args()
    reader = Reader(args.pid)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.perf_counter() + args.seconds
    try:
        with args.output.open("w", encoding="utf-8", buffering=1) as stream:
            while time.perf_counter() < deadline:
                players = []
                for slot in range(8):
                    address = 0x3B12A00 + slot * 0xF8
                    header = reader.get(address - 16, "4i")
                    x, y = reader.get(address, "dd")
                    hp = reader.get(address + 0x60, "d")[0]
                    if any(header) or x or y or hp:
                        players.append({
                            "slot": slot, "header": header, "pos": [x, y], "hp": hp,
                            "weapon": reader.get(0x25F1AD8 + slot * 4, "i")[0] + 1,
                            "motion58": reader.get(address + 0x58, "d")[0],
                            "state": {hex(offset): reader.get(address + offset, "i")[0]
                                      for offset in (0x38, 0x3C, 0x68, 0x74, 0x7C, 0x80,
                                                     0x94, 0xB0, 0xC0, 0xC4, 0xD0, 0xDC)},
                            "bounds": reader.get(address + 0x18, "4i"),
                        })
                bases = []
                count = max(0, min(16, reader.get(0xA072AA4, "i")[0]))
                for index in range(count):
                    address = 0xA074460 + index * 0xF8
                    if reader.get(address, "i")[0] == 700:
                        bases.append({
                            "index": index,
                            "bounds": reader.get(address + 0x28, "4i"),
                            "fields": {hex(offset): reader.get(address + offset, "i")[0]
                                       for offset in range(0x38, 0xF8, 4)},
                        })
                roster = reader.get(0x2248AB4, "i")[0]
                room = reader.get(0xAA16538, "i")[0]
                local_slot = (reader.get(0x22C31C4 + roster * 0x130, "b")[0]
                              if 0 <= roster < 300 and room > 0 else roster)
                row = {"perf_ns": time.perf_counter_ns(),
                       "game_ms": reader.get(0x24DB7F0, "I")[0],
                       "local_slot": local_slot,
                       "keys": [name for name, vk in KEYS.items()
                                if user32.GetAsyncKeyState(vk) & 0x8000],
                       "players": players, "bases": bases}
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                time.sleep(args.sample_ms / 1000)
    finally:
        reader.close()


if __name__ == "__main__":
    main()
