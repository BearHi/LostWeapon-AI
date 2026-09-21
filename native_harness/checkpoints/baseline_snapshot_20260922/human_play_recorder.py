"""Read-only, opt-in recording of a foreground normal Client.exe session.

Keyboard samples are observations, not exact game ticks or training labels.
Only the named game keys are sampled; pause with F9 during in-game chat.
Input from other foreground applications is omitted.
"""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import signal
import struct
import time

from live_state import Reader
from identify_live_map import key as object_key, parse_lmf, read_runtime

u = C.WinDLL("user32", use_last_error=True)
u.GetForegroundWindow.restype = W.HWND
u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
u.GetWindowThreadProcessId.restype = W.DWORD
u.GetAsyncKeyState.argtypes = [C.c_int]
u.GetAsyncKeyState.restype = C.c_short
KEYS = {"LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
        "SPACE": 0x20, "C": 0x43, "Z": 0x5A, "X": 0x58,
        "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34}
running = True


def terrain_snapshot(reader, state, size=9):
    """Read four real native grids. Absolute grid pointers are not relocated twice."""
    width,height=state['map_size']
    if not (0<width<=8192 and 0<height<=8192):raise ValueError('invalid map dimensions')
    px,py=(int(v//32) for v in state['pos'])
    pointers=[reader.get(a,'I')[0] for a in (0x8952DCC,0x8952DEC,0x8952E2C,0x8952E4C)]
    layers=[]
    for pointer in pointers:
        rows=[]
        for y in range(py-size//2,py+size//2+1):
            x0=px-size//2;lo=max(0,x0);hi=min(width,x0+size)
            values=struct.unpack('<'+'H'*(hi-lo),reader.read(pointer+2*(y*width+lo),2*(hi-lo))) if 0<=y<height and hi>lo else ()
            rows.append([values[x-lo] if 0<=y<height and lo<=x<hi else None for x in range(x0,x0+size)])
        layers.append(rows)
    return {'origin':[px-size//2,py-size//2],'size':size,'grids':layers}


def stop(_signum, _frame):
    global running
    running = False


def foreground_pid():
    hwnd = u.GetForegroundWindow()
    pid = W.DWORD()
    if hwnd:
        u.GetWindowThreadProcessId(hwnd, C.byref(pid))
    return pid.value


def write(stream, row):
    stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    stream.flush()


def publish_status(path, **status):
    if path is None:
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def load_map_catalog(folder):
    catalog = []
    if folder is None:
        return catalog
    for path in folder.rglob("*.LMF"):
        try:
            _, _, records, runtime = parse_lmf(path)
        except (OSError, ValueError):
            continue
        catalog.append((path, Counter(map(object_key, runtime)),
                        [(x, y) for tile, x, y in records if tile == 100],
                        [(x, y) for tile, x, y in records if tile == 140]))
    return catalog


def match_loaded_map(reader, catalog):
    live = Counter(map(object_key, read_runtime(reader)))
    matches = [entry for entry in catalog if entry[1] == live]
    return matches[0] if len(matches) == 1 else None


class AttemptTracker:
    def __init__(self):
        self.map_entry = None
        self.attempt = 0
        self.previous_pos = None
        self.goal_seen = False

    def set_map(self, entry):
        if entry == self.map_entry:
            return []
        self.map_entry = entry
        self.attempt = 1 if entry else 0
        self.previous_pos = None
        self.goal_seen = False
        return [{"event": "map_identified", "map": str(entry[0]),
                 "attempt": self.attempt}] if entry else [{"event": "map_unidentified"}]

    def observe(self, state):
        if not self.map_entry:
            return []
        pos = state.get("pos")
        if not pos or len(pos) != 2:
            return []
        x, y = pos
        _, _, starts, goals = self.map_entry
        events = []
        if self.previous_pos and starts:
            old_x, old_y = self.previous_pos
            near_start = any(abs(x - (sx * 32 + 16)) <= 40 and
                             abs(y - (sy * 32 + 16)) <= 64 for sx, sy in starts)
            was_far = all(abs(old_x - (sx * 32 + 16)) > 80 or
                          abs(old_y - (sy * 32 + 16)) > 80 for sx, sy in starts)
            if near_start and was_far and abs(old_x - x) + abs(old_y - y) > 80:
                self.attempt += 1
                self.goal_seen = False
                events.append({"event": "restart_candidate", "attempt": self.attempt,
                               "from_pos": self.previous_pos, "to_pos": pos})
        if not self.goal_seen and any(gx * 32 - 24 <= x <= gx * 32 + 32 and
                                      gy * 32 <= y <= gy * 32 + 64 for gx, gy in goals):
            self.goal_seen = True
            events.append({"event": "goal_contact_candidate", "attempt": self.attempt,
                           "pos": pos})
        self.previous_pos = pos
        return events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--wait-seconds", type=float, default=30)
    parser.add_argument("--sample-ms", type=float, default=10)
    parser.add_argument("--stop-file", type=Path)
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--lmf-dir", type=Path)
    parser.add_argument("--terrain-ms", type=float, default=0,
                        help="optional local native grids, sampled separately from keys")
    parser.add_argument("--max-minutes", type=float, default=30)
    parser.add_argument("--max-mb", type=float, default=256)
    args = parser.parse_args()
    if args.sample_ms<=0 or args.terrain_ms<0 or min(args.max_minutes,args.max_mb)<=0:
        parser.error('sampling intervals/budgets must be positive')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    reader = None
    target_pid = None
    rejected_pids = set()
    samples = 0
    last_status = 0.0
    latest_state = None
    started = time.time()
    catalog = load_map_catalog(args.lmf_dir)
    tracker = AttemptTracker()
    last_map_check = 0.0
    last_terrain=last_objects=0.0
    controls={0x75:False,0x76:False,0x78:False}  # F6 success, F7 mistake, F9 pause
    manually_paused=False
    deadline = time.monotonic() + args.wait_seconds
    with args.output.open("x", encoding="utf-8", buffering=1) as stream:
        write(stream, {"event": "waiting_for_foreground_client", "wall_time": time.time()})
        publish_status(args.status_file, phase="waiting", samples=0,
                       output=str(args.output), started_at=started)
        try:
            while running and not (args.stop_file and args.stop_file.exists()):
                if time.time()-started>=args.max_minutes*60 or stream.tell()>=args.max_mb*1024*1024:
                    write(stream,{'event':'recording_budget_reached','wall_time':time.time()})
                    break
                pid = foreground_pid()
                if reader is None and pid and pid not in rejected_pids and time.monotonic() < deadline:
                    try:
                        reader = Reader(pid)  # Rejects processes without Client.exe module.
                        target_pid = pid
                        write(stream, {"event": "recording_started", "pid": pid,
                                       "wall_time": time.time(), "sample_ms_requested": args.sample_ms})
                    except (OSError, StopIteration, RuntimeError):
                        reader = None
                        rejected_pids.add(pid)
                if reader is None:
                    if time.monotonic() >= deadline:
                        write(stream, {"event": "no_client_selected", "wall_time": time.time()})
                        publish_status(args.status_file, phase="no_client", samples=0,
                                       output=str(args.output), started_at=started)
                        break
                    time.sleep(0.1)
                    continue
                if pid != target_pid:
                    if time.monotonic() - last_status >= 1:
                        publish_status(args.status_file, phase="paused_other_window",
                                       samples=samples, output=str(args.output),
                                       started_at=started, last_player=latest_state)
                        last_status = time.monotonic()
                    time.sleep(0.05)  # Never record input from another foreground app.
                    continue
                for key in controls:
                    pressed=bool(u.GetAsyncKeyState(key)&0x8000)
                    if pressed and not controls[key]:
                        if key==0x78:
                            manually_paused=not manually_paused
                            write(stream,{'event':'manual_pause','paused':manually_paused,'wall_time':time.time()})
                        elif not manually_paused:
                            write(stream,{'event':'human_marker','label':'good_segment' if key==0x75 else 'mistake',
                                          'wall_time':time.time(),'label_source':'user_hint_not_native_goal'})
                    controls[key]=pressed
                if manually_paused:
                    time.sleep(.02)
                    continue
                try:
                    state = reader.state()
                    if state.get("slot") is None or not state.get('pos') or not state.get('map_size'):
                        time.sleep(0.05)
                        continue
                    if catalog and time.monotonic() - last_map_check >= 5:
                        last_map_check = time.monotonic()
                        try:
                            matched = match_loaded_map(reader, catalog)
                            for event in tracker.set_map(matched):
                                write(stream, {**event, "wall_time": time.time()})
                        except (OSError, RuntimeError):
                            pass  # A map may be partway through loading.
                    row = {"event": "sample", "sample_perf_ns": time.perf_counter_ns(),
                           "wall_time": time.time(),
                           "keys": [name for name, vk in KEYS.items()
                                    if u.GetAsyncKeyState(vk) & 0x8000],
                           "player": state}
                    if args.terrain_ms and time.monotonic()-last_terrain>=args.terrain_ms/1000:
                        began=time.perf_counter_ns()
                        try:
                            terrain=terrain_snapshot(reader,state)
                            write(stream,{'event':'terrain','wall_time':row['wall_time'],
                                          'read_start_ns':began,'read_end_ns':time.perf_counter_ns(),**terrain})
                        except (OSError,RuntimeError,ValueError) as exc:
                            write(stream,{'event':'terrain_unavailable','wall_time':row['wall_time'],'reason':str(exc)[:120]})
                        last_terrain=time.monotonic()
                    if args.terrain_ms and time.monotonic()-last_objects>=10:
                        try:
                            write(stream,{'event':'objects_snapshot','wall_time':row['wall_time'],
                                          'records':read_runtime(reader)})
                        except (OSError,RuntimeError):pass
                        last_objects=time.monotonic()
                except (OSError, RuntimeError):
                    write(stream, {"event": "client_read_ended", "wall_time": time.time()})
                    break
                write(stream, row)
                for event in tracker.observe(state):
                    write(stream, {**event, "map": str(tracker.map_entry[0]),
                                   "wall_time": row["wall_time"]})
                samples += 1
                latest_state = {key: state.get(key) for key in ("room", "pos", "hp", "map_size")}
                if time.monotonic() - last_status >= 1:
                    publish_status(args.status_file, phase="recording", samples=samples,
                                   output=str(args.output), started_at=started,
                                   last_player=latest_state,
                                   map_name=tracker.map_entry[0].name if tracker.map_entry else None,
                                   attempt=tracker.attempt)
                    last_status = time.monotonic()
                time.sleep(max(0.001, args.sample_ms / 1000))
        finally:
            if reader is not None:
                reader.close()
            write(stream, {"event": "recording_ended", "wall_time": time.time(),
                           "samples": samples, "pid": target_pid})
            publish_status(args.status_file, phase="ended" if target_pid else "no_client", samples=samples,
                           output=str(args.output), started_at=started,
                           last_player=latest_state,
                           map_name=tracker.map_entry[0].name if tracker.map_entry else None,
                           attempt=tracker.attempt)


if __name__ == "__main__":
    main()
