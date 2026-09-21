"""Run a small read-only normal-Client input probe.

The probe only reads Client state and sends ordinary keyboard events. It is
intended for fixture parity checks after the native oracle has supplied a
candidate starting coordinate and input timing.
"""
from __future__ import annotations

import argparse
import ctypes as C
import json
import sys
import time
from pathlib import Path

from normal_trace_readonly import KEYEVENTF_KEYUP, focus_window, process_window, u
from live_state import Reader

VK = {"left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "c": 0x43}


def changed_sample(reader: Reader, rows: list, phase: str, last):
    state = reader.state()
    signature = (tuple(state["pos"]), state["motion58"],
                 tuple(sorted(state["state"].items())), tuple(state["player_header"]))
    if signature != last:
        rows.append({"phase": phase, "perf_ns": time.perf_counter_ns(), "state": state})
        return state, signature
    return state, last


def run(pid: int, output: Path, target_x: float, direction: str,
        jump: bool, jump_hold_ms: float, max_seconds: float,
        trigger_motion: float | None):
    reader = Reader(pid)
    hwnd = process_window(pid)
    prior = u.GetForegroundWindow()
    pressed: list[int] = []
    rows = []
    last = None
    hit = None

    def down(key: str):
        code = VK[key]
        u.keybd_event(code, 0, 0, 0)
        pressed.append(code)

    def up(key: str):
        code = VK[key]
        if code in pressed:
            u.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)
            pressed.remove(code)

    try:
        if not focus_window(hwnd):
            raise RuntimeError("Client foreground failed")
        time.sleep(0.08)
        state, last = changed_sample(reader, rows, "start", last)
        move_key = direction
        down(move_key)
        deadline = time.perf_counter() + 1.5
        while time.perf_counter() < deadline:
            state, last = changed_sample(reader, rows, "positioning", last)
            if ((direction == "left" and state["pos"][0] <= target_x) or
                    (direction == "right" and state["pos"][0] >= target_x)):
                break
        up(move_key)
        time.sleep(0.08)
        boundary, last = changed_sample(reader, rows, "boundary", last)

        down(direction)
        if jump:
            down("up")
            time.sleep(jump_hold_ms / 1000.0)
            up("up")

        deadline = time.perf_counter() + max_seconds
        while time.perf_counter() < deadline:
            state, last = changed_sample(reader, rows, "input", last)
            if trigger_motion is not None and state["motion58"] >= trigger_motion:
                hit = {"sample_index": len(rows) - 1, "state": state}
                break
        up(direction)
        time.sleep(0.08)
        final, last = changed_sample(reader, rows, "final", last)
        result = {
            "scope": "read-only normal Client microtest with ordinary keyboard input",
            "pid": pid,
            "target_x": target_x,
            "direction": direction,
            "jump": jump,
            "jump_hold_ms": jump_hold_ms,
            "boundary": boundary,
            "hit": hit,
            "final": final,
            "samples": rows,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"boundary_pos": boundary["pos"], "hit": bool(hit),
                          "hit_state": hit["state"] if hit else None,
                          "final_pos": final["pos"], "samples": len(rows),
                          "output": str(output)}, ensure_ascii=False, indent=2))
    finally:
        for code in reversed(pressed):
            u.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)
        if prior and u.GetForegroundWindow() == hwnd:
            u.SetForegroundWindow(prior)
        reader.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-x", type=float, required=True)
    parser.add_argument("--direction", choices=("left", "right"), default="right")
    parser.add_argument("--jump", action="store_true")
    parser.add_argument("--jump-hold-ms", type=float, default=55.0)
    parser.add_argument("--max-seconds", type=float, default=1.6)
    parser.add_argument("--trigger-motion", type=float)
    args = parser.parse_args()
    run(args.pid, args.output, args.target_x, args.direction, args.jump,
        args.jump_hold_ms, args.max_seconds, args.trigger_motion)


if __name__ == "__main__":
    main()
