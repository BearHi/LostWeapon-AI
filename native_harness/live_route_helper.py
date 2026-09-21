"""Opt-in foreground Client helper. F8 run/pause, F7 combat, Shift manual, F9 exit.

Reads normal Client state; sends ordinary keyboard events only while armed and
the selected Client is foreground. No process memory is written.
"""
from __future__ import annotations

import argparse
import ctypes as C
from ctypes import wintypes as W
from collections import deque
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import time

from combat_live_advisor import ENVELOPES, load_envelope
from discovered_map import DiscoveredMap
from human_play_recorder import KEYS, foreground_pid, load_map_catalog, match_loaded_map
from identify_live_map import key as object_key, parse_lmf, read_runtime
from live_state import Reader
from native_env import ACTIONS, LostWeaponEnv
from restriction_fields import RestrictionFields
from train_rule_helper import MOVEMENT, rule_score
from training_archive import sha256_file

ROOT = Path(__file__).resolve().parent
u = C.WinDLL("user32", use_last_error=True)
u.GetAsyncKeyState.argtypes = [C.c_int]
u.GetAsyncKeyState.restype = C.c_short
u.keybd_event.argtypes = [W.BYTE, W.BYTE, W.DWORD, C.c_size_t]
u.keybd_event.restype = None
F7, F8, F9, SHIFT = 0x76, 0x77, 0x78, 0x10
KEYUP = 0x0002
GAME_KEYS = {key: KEYS[key] for key in ("LEFT", "RIGHT", "UP", "DOWN", "C", "Z", "1", "2", "3", "4")}


def down(vk):
    return bool(u.GetAsyncKeyState(vk) & 0x8000)


class KeyOutput:
    def __init__(self):
        self.held = set()

    def set(self, keys):
        wanted = set(keys)
        for key in self.held - wanted:
            u.keybd_event(GAME_KEYS[key], 0, KEYUP, 0)
        for key in wanted - self.held:
            u.keybd_event(GAME_KEYS[key], 0, 0, 0)
        self.held = wanted

    def release(self):
        self.set(())


def live_view(reader, state, size):
    width, height = state["map_size"]
    px, py = int(state["pos"][0] // 32), int(state["pos"][1] // 32)
    pointer = reader.get(0x8952DEC, "I")[0]
    rows = []
    for y in range(py - size // 2, py + size // 2 + 1):
        row = []
        x0 = px - size // 2
        lo, hi = max(0, x0), min(width, x0 + size)
        raw = reader.read(pointer + 2 * (y * width + lo), 2 * (hi - lo)) if 0 <= y < height and lo < hi else b""
        for x in range(x0, x0 + size):
            solid = not (0 <= x < width and 0 <= y < height)
            if not solid:
                offset = 2 * (x - lo)
                solid = int.from_bytes(raw[offset:offset + 2], "little") != 0
            row.append({"x": x, "y": y, "solid": solid,
                        "grids": (0, int(solid), 0, 0), "object_id": 0})
        rows.append(row)
    return {"cells": rows, "size": size, "player_tile": (px, py)}


def scan_live(reader, state, memory, goal, *, maximum=21):
    px, py = int(state["pos"][0] // 32), int(state["pos"][1] // 32)
    direction = 1 if goal[0] >= px else -1
    size = 9
    while True:
        view = live_view(reader, state, size)
        memory.update(view)
        ahead = [memory.clearance(px + direction * n, py - 1)
                 for n in range(1, min(4, size // 2) + 1)]
        edge = px + direction * (size // 2)
        support = memory.classify(edge, py + 1)
        if size >= maximum or ("unknown" not in ahead and support != "unknown"):
            return size
        size += 2


def select_goal(goals, pos):
    return min(goals, key=lambda g: (g[0] * 32 - pos[0]) ** 2 + (g[1] * 32 - pos[1]) ** 2)


def live_context(memory, state, goal):
    px, py = int(state["pos"][0] // 32), int(state["pos"][1] // 32)
    direction = 1 if goal[0] >= px else -1
    vertical = "up" if goal[1] < py - 1 else "down" if goal[1] > py + 1 else "level"
    fields = state["state"]
    mode = "ladder" if fields["0x74"] == 1 else "water" if fields["0xc0"] == 21 else \
        "chute" if fields["0xdc"] else "normal"
    return ("R" if direction > 0 else "L", vertical,
            memory.clearance(px + direction, py - 1),
            memory.classify(px + 2 * direction, py + 1), mode)


def safe_roll(memory, state, direction):
    px, py = int(state["pos"][0] // 32), int(state["pos"][1] // 32)
    for step in range(1, 4):
        x = px + direction * step
        if memory.clearance(x, py - 1) != "open":
            return False
        if memory.classify(x, py + 1) != "blocked":
            return False
    return True


def terrain_case(memory, state, direction):
    """Compress nearby geometry into a few decisions, not tile permutations."""
    px, py = (int(v // 32) for v in state["pos"])
    body = [memory.clearance(px + direction * step, py - 1) for step in range(1, 5)]
    support = [memory.classify(px + direction * step, py + 1) for step in range(1, 5)]
    if "unknown" in body or "unknown" in support:
        return "unknown"
    if "blocked" in body:
        return "wall"
    if any(tile != "blocked" for tile in support):
        return "gap"
    return "flat"


def opponent_state(reader, slot):
    address = 0x3B12A00 + int(slot) * 0xF8
    header = reader.get(address - 16, "4i")
    if not any(header):
        return None
    x, y = reader.get(address, "dd")
    hp = reader.get(address + 0x60, "d")[0]
    motion = reader.get(address + 0x38, "i")[0]
    return {"pos": (x, y), "hp": hp, "motion": motion}


def attack_action(own, opponent, weapon, envelope, corridor_clear):
    """Conservative flat hit envelope; roll toward target then reconsider."""
    if opponent is None or opponent["hp"] <= 0 or own["hp"] <= 0:
        return None
    dx = opponent["pos"][0] - own["pos"][0]
    dy = opponent["pos"][1] - own["pos"][1]
    if abs(dy) > 40 or abs(dx) > 180:
        return None
    toward = "RIGHT" if dx > 0 else "LEFT"
    facing = own["state"]["0xb0"] == 0
    if (dx > 0) != facing:
        return (toward,)
    if own["state"]["0x38"] in range(15, 21):
        return None
    hit = (envelope.get(weapon) or {}).get("observed_hit_start_dx")
    if hit is None:
        return None
    if abs(dx) <= max(0, hit - 12):
        return ("Z",)
    if corridor_clear and abs(dx) <= hit + 64:
        return (toward, "DOWN")
    return None


def route_action(state, goal, memory, restrictions, values):
    ctx = live_context(memory, state, goal)
    direction = 1 if ctx[0] == "R" else -1
    native_state = {key: state["state"]["0x" + key] for key in ("38", "74", "c0", "dc")}
    active = restrictions.active_at(*state["pos"])
    allowed = [a for a in LostWeaponEnv._valid_actions_for(native_state, active) if a in MOVEMENT]
    if not allowed:
        return (), ctx
    case = terrain_case(memory, state, direction)
    toward = "RIGHT" if direction > 0 else "LEFT"
    airborne = state["state"]["0x38"] == 9
    # A grounded roll needs a supported lane. After a jump, a clear air lane
    # can admit a native air roll even when the ground below is absent.
    air_lane = all(memory.clearance(int(state["pos"][0] // 32) + direction * n,
                                    int(state["pos"][1] // 32) - 1) == "open"
                   for n in range(1, 4))
    if not safe_roll(memory, state, direction) and not (airborne and air_lane):
        allowed = [a for a in allowed if not (toward in ACTIONS[a] and "DOWN" in ACTIONS[a])]
    if case in ("gap", "unknown") and not airborne:
        allowed = [a for a in allowed if not (toward in ACTIONS[a] and "DOWN" in ACTIONS[a])]
    if not allowed:
        return (), ctx
    def priority(a):
        keys = ACTIONS[a]
        score = rule_score(a, ctx) + values.get(json.dumps([*ctx, a]), [0])[0]
        forward = toward in keys
        if case == "flat" and forward and "DOWN" in keys:
            score += 3.0  # front/back roll follows current facing automatically
        elif case in ("gap", "wall"):
            if not airborne and "UP" in keys:
                score += 5.0  # jump first
            if airborne and forward and "DOWN" in keys and air_lane:
                score += 4.0  # choose air roll only after launch
            if forward and "DOWN" in keys and not airborne:
                score -= 6.0
        elif case == "unknown" and forward and "DOWN" in keys:
            score -= 5.0
        return score
    selected = max(allowed, key=priority)
    return ACTIONS[selected], ctx


def load_values(lmf):
    candidates = [ROOT / "checkpoints/route_curriculum" / (lmf.stem + ".json")]
    if lmf.stem == "훈1":
        candidates.append(ROOT / "checkpoints/route_rule_helper.json")
    for path in candidates:
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("map_sha256") == sha256_file(lmf) and saved.get("action_schema") == [list(a) for a in ACTIONS]:
                return saved.get("values", {}), path
    return {}, None


def acquire_reader(pid, wait_seconds):
    deadline = time.perf_counter() + wait_seconds
    while time.perf_counter() < deadline:
        target = pid or foreground_pid()
        if target:
            try:
                return target, Reader(target)
            except (OSError, StopIteration, RuntimeError):
                if pid:
                    raise
        time.sleep(0.1)
    raise TimeoutError("Client.exe was not selected before timeout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--lmf", type=Path)
    parser.add_argument("--act", action="store_true", help="allow ordinary keyboard output after F8")
    parser.add_argument("--combat", choices=("off", "priority"), default="off")
    parser.add_argument("--opponent-slot", type=int, choices=range(8))
    parser.add_argument("--wait-seconds", type=float, default=30)
    parser.add_argument("--decision-ms", type=float, default=50)
    args = parser.parse_args()
    if args.combat == "priority" and args.opponent_slot is None:
        parser.error("combat priority requires an explicitly identified --opponent-slot")
    if not 10 <= args.decision_ms <= 100:
        parser.error("decision-ms must be between 10 and 100")
    pid, reader = acquire_reader(args.pid, args.wait_seconds)
    output = KeyOutput()
    enabled = False
    combat = args.combat == "priority"
    key_edges = {F7: False, F8: False, F9: False}
    try:
        if args.lmf:
            lmf = args.lmf.resolve()
        else:
            catalog = load_map_catalog(ROOT.parent / "훈련용맵")
            entry = match_loaded_map(reader, catalog)
            if entry is None:
                raise RuntimeError("loaded map is not uniquely identified; pass --lmf")
            lmf = entry[0]
        width, height, records, expected_runtime = parse_lmf(lmf)
        actual_runtime = read_runtime(reader)
        if Counter(map(object_key, actual_runtime)) != Counter(map(object_key, expected_runtime)):
            raise RuntimeError("selected LMF does not match the live Client object records")
        goals = [(x, y) for tile, x, y in records if tile == 140]
        if not goals:
            raise RuntimeError("selected LMF has no flag")
        initial = reader.state()
        if "pos" not in initial or not 0 <= initial["slot"] < 8:
            raise RuntimeError("Client is not in a supported active player slot")
        if tuple(initial["map_size"]) != (width, height):
            raise RuntimeError("selected LMF size differs from the live room")
        initial_room = initial["room"]
        memory = DiscoveredMap(width, height)
        restrictions = RestrictionFields(records)
        values, checkpoint = load_values(lmf)
        envelope = load_envelope(ENVELOPES)
        timings = deque(maxlen=100)
        last_report = 0.0
        print(json.dumps({"phase": "ready", "pid": pid, "map": str(lmf),
                          "checkpoint": str(checkpoint) if checkpoint else None,
                          "combat": combat, "act": args.act,
                          "controls": "F8 run/pause, F7 combat, hold Shift manual, F9 exit"},
                         ensure_ascii=False), flush=True)
        while True:
            started = time.perf_counter()
            pressed = {vk: down(vk) for vk in key_edges}
            toggled = {vk: pressed[vk] and not key_edges[vk] for vk in key_edges}
            key_edges = pressed
            if toggled[F9]:
                break
            if toggled[F8]:
                enabled = not enabled
                output.release()
            if toggled[F7] and args.opponent_slot is not None:
                combat = not combat
                output.release()
            if foreground_pid() != pid:
                enabled = False
                output.release()
                phase, desired, size = "other_window", (), 0
            elif down(SHIFT):
                output.release()
                phase, desired, size = "manual", (), 0
            elif any(down(vk) for key, vk in GAME_KEYS.items() if key not in output.held):
                output.release()
                phase, desired, size = "manual_keys", (), 0
            else:
                state = reader.state()
                if state.get("room") != initial_room or tuple(state.get("map_size", ())) != (width, height):
                    output.release()
                    raise RuntimeError("room/map changed; restart after identifying the new map")
                goal = select_goal(goals, state["pos"])
                size = scan_live(reader, state, memory, goal)
                desired, ctx = route_action(state, goal, memory, restrictions, values)
                phase = "route"
                if combat and args.opponent_slot is not None and args.opponent_slot != state["slot"]:
                    opponent = opponent_state(reader, args.opponent_slot)
                    own_weapon = reader.get(0x25F1AD8 + state["slot"] * 4, "i")[0] + 1
                    direction = 1 if opponent and opponent["pos"][0] > state["pos"][0] else -1
                    attack = attack_action(state, opponent, own_weapon, envelope,
                                           safe_roll(memory, state, direction))
                    active = restrictions.active_at(*state["pos"])
                    native = {key: state["state"]["0x" + key] for key in ("38", "74", "c0", "dc")}
                    allowed = {ACTIONS[a] for a in LostWeaponEnv._valid_actions_for(native, active)}
                    if attack and attack in allowed:
                        desired, phase = attack, "combat"
                if args.act and enabled:
                    output.set(desired)
                else:
                    output.release()
                    phase = "paused" if not enabled else "observe"
            elapsed_ms = (time.perf_counter() - started) * 1000
            timings.append(elapsed_ms)
            if time.perf_counter() - last_report >= 1:
                last_report = time.perf_counter()
                p95 = sorted(timings)[int((len(timings) - 1) * 0.95)] if timings else 0
                print(json.dumps({"phase": phase, "armed": bool(args.act and enabled),
                                  "combat": combat, "keys": list(desired),
                                  "view": size, "decision_ms": round(elapsed_ms, 2),
                                  "p95_ms": round(p95, 2), "known_tiles": len(memory.cells)},
                                 ensure_ascii=False), flush=True)
            time.sleep(max(0.0, args.decision_ms / 1000 - (time.perf_counter() - started)))
    finally:
        output.release()
        reader.close()


if __name__ == "__main__":
    main()
