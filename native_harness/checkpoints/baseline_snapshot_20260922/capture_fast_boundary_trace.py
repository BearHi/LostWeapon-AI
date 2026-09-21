"""Capture a normal-Client input boundary with a sub-frame suspend window.

Most memory is copied while the Client keeps running.  Once suspended, only
the pages observed by the offline gameplay closure are refreshed.  The Client
is read-only throughout; input is an ordinary Windows key event.
"""
from pathlib import Path
import ctypes as C
import json
import struct
import sys
import time
import zipfile

from capture import MBI, Reader, k, nt
from normal_trace_readonly import KEYEVENTF_KEYUP, VK_RIGHT, focus_window, process_window, signature, u, winmm

VK_UP = 0x26
VK_LEFT = 0x25
VK_C = 0x43
ACTION_KEYS = {
    "NOOP": (),
    "RIGHT": (VK_RIGHT,), "RIGHT_UP": (VK_RIGHT, VK_UP),
    "LEFT": (VK_LEFT,), "LEFT_UP": (VK_LEFT, VK_UP),
    "RIGHT_PARACHUTE": (VK_RIGHT,),
    "RIGHT_LADDER": (VK_RIGHT,),
}


def selected_pages(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pages = set()
    for scenario in data["scenarios"].values():
        for field in ("read_ranges", "write_ranges", "exec_ranges"):
            pages.update(int(value, 16) for value in scenario.get(field, ()))
    # These ranges belong to the emulator itself and do not exist in Client.
    return sorted(page for page in pages if not (
        0x60000000 <= page < 0x60010000 or
        0x61000000 <= page < 0x61100000 or
        0x62000000 <= page < 0x62001000
    ))


def capture(pid, snapshot_path, trace_path, footprint_path, action="RIGHT", distance=48.0, settle=False):
    reader = Reader(pid)
    reader.close()
    reader.h = k.OpenProcess(0xC10, False, pid)
    if not reader.h:
        raise C.WinError(C.get_last_error())
    hwnd = process_window(pid)
    prior_foreground = u.GetForegroundWindow()
    regions = []
    region_meta = []
    teb_candidates = []
    samples = []
    events = []
    suspended = False
    pressed = []
    key_codes = ACTION_KEYS[action]
    pages = selected_pages(footprint_path)
    try:
        focus_window(hwnd)
        time.sleep(0.08)
        if u.GetForegroundWindow() != hwnd:
            raise RuntimeError("Client did not become foreground; no key sent")

        # Rolling base copy: consistency is supplied below for every page the
        # validated gameplay closure actually reads, writes, or executes.
        address = 0
        while address < 0x80000000:
            info = MBI()
            if not k.VirtualQueryEx(reader.h, address, C.byref(info), C.sizeof(info)):
                break
            base = info.BaseAddress or 0
            size = info.RegionSize
            if info.State == 0x1000 and not (info.Protect & 0x101) and info.Type in (0x20000, 0x1000000):
                raw = bytearray(reader.read(base, size))
                regions.append((base, raw))
                region_meta.append({"base": base, "size": size, "protect": info.Protect, "type": info.Type})
                for offset in range(0, size - 0x34, 4096):
                    if struct.unpack_from("<I", raw, offset + 0x18)[0] == base + offset:
                        tls = struct.unpack_from("<I", raw, offset + 0x2C)[0]
                        if tls:
                            teb_candidates.append({"teb": base + offset, "tls": tls})
            address = base + size

        started = time.perf_counter()
        if nt.NtSuspendProcess(reader.h) < 0:
            raise RuntimeError("Could not suspend Client")
        suspended = True
        boundary_state = reader.state()
        refreshed = 0
        missing = []
        for page in pages:
            owner = next(((base, raw) for base, raw in regions if base <= page < base + len(raw)), None)
            if owner is None:
                missing.append(page)
                continue
            base, raw = owner
            raw[page - base:page - base + 0x1000] = reader.read(page, 0x1000)
            refreshed += 1
        pause_seconds = time.perf_counter() - started
        if missing:
            raise RuntimeError(f"{len(missing)} footprint pages absent from live process")

        samples.append({"boundary": True, "phase": "held", "perf_ns": time.perf_counter_ns(),
                        "time_ms": winmm.timeGetTime(), "state": boundary_state})
        last = signature(boundary_state)
        start_x = boundary_state["pos"][0]
        for key_code in key_codes:
            u.keybd_event(key_code, 0, 0, 0)
            pressed.append(key_code)
        if nt.NtResumeProcess(reader.h) < 0:
            raise RuntimeError("Failed to resume Client")
        suspended = False
        direction = -1 if action.startswith("LEFT") else 1
        deadline = time.perf_counter() + 1.0
        while time.perf_counter() < deadline:
            state = reader.state()
            sig = signature(state)
            if sig != last:
                samples.append({"boundary": False, "phase": "held", "perf_ns": time.perf_counter_ns(),
                                "time_ms": winmm.timeGetTime(), "state": state})
                last = sig
            if action == "RIGHT_LADDER" and VK_RIGHT in pressed and state["pos"][0] >= start_x + 256:
                u.keybd_event(VK_RIGHT, 0, KEYEVENTF_KEYUP, 0)
                pressed.remove(VK_RIGHT)
                events.append({"event": "RIGHT_UP", "state": state})
                u.keybd_event(VK_UP, 0, 0, 0)
                pressed.append(VK_UP)
                events.append({"event": "UP_DOWN", "state": state})
            elif action == "RIGHT_PARACHUTE" and VK_C not in pressed and not any(e["event"] == "C_UP" for e in events):
                if state["state"]["0x38"] == 9 and state["pos"][0] >= start_x + 140:
                    u.keybd_event(VK_C, 0, 0, 0)
                    pressed.append(VK_C)
                    events.append({"event": "C_DOWN", "state": state})
            elif action == "RIGHT_PARACHUTE" and VK_C in pressed and state["state"]["0xdc"] == 1:
                u.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
                pressed.remove(VK_C)
                events.append({"event": "C_UP", "state": state})
            if action == "RIGHT_LADDER" and state["pos"][1] <= 384:
                break
            if action == "NOOP" and len(samples) >= 160:
                break
            if action not in ("RIGHT_LADDER", "NOOP") and direction * (state["pos"][0] - start_x) >= distance:
                break
        if settle:
            for key_code in reversed(pressed):
                u.keybd_event(key_code, 0, KEYEVENTF_KEYUP, 0)
            pressed.clear()
            airborne = state["state"]["0x38"] != 7
            deadline = time.perf_counter() + 2.0
            landed_at = None
            while time.perf_counter() < deadline:
                state = reader.state()
                sig = signature(state)
                if sig != last:
                    samples.append({"boundary": False, "phase": "released", "perf_ns": time.perf_counter_ns(),
                                    "time_ms": winmm.timeGetTime(), "state": state})
                    last = sig
                airborne = airborne or state["state"]["0x38"] != 7
                if airborne and state["state"]["0x38"] == 7:
                    landed_at = landed_at or time.perf_counter()
                    if time.perf_counter() - landed_at >= 0.15:
                        break
    finally:
        for key_code in reversed(pressed):
            u.keybd_event(key_code, 0, KEYEVENTF_KEYUP, 0)
        if suspended:
            nt.NtResumeProcess(reader.h)
        if prior_foreground and u.GetForegroundWindow() == hwnd:
            u.SetForegroundWindow(prior_foreground)
        reader.close()

    meta = {
        "pid": pid,
        "regions": region_meta,
        "modules": reader.modules,
        "client": reader.module,
        "teb32_candidates": teb_candidates,
        "boundary": f"rolling full copy plus suspended gameplay-footprint refresh immediately before {action}",
        "state": boundary_state,
        "capture_pause_seconds": pause_seconds,
        "refreshed_pages": refreshed,
        "footprint": str(footprint_path),
    }
    snapshot_path = Path(snapshot_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(snapshot_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for base, raw in regions:
            archive.writestr(f"{base:08x}.bin", raw)
        archive.writestr("metadata.json", json.dumps(meta))
    result = {
        "scope": f"fast-boundary read-only normal Client snapshot and ordinary {action} trace",
        "snapshot": str(snapshot_path),
        "target_distance": distance,
        "settle_after_release": settle,
        "input_events": events,
        "samples": samples,
    }
    Path(trace_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"snapshot": str(snapshot_path), "trace": str(trace_path),
                      "pause_seconds": pause_seconds, "refreshed_pages": refreshed,
                      "start": samples[0]["state"]["pos"], "end": samples[-1]["state"]["pos"],
                      "samples": len(samples)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    action = sys.argv[5] if len(sys.argv) > 5 else "RIGHT"
    distance = float(sys.argv[6]) if len(sys.argv) > 6 else 48.0
    settle = len(sys.argv) > 7 and sys.argv[7].lower() in ("1", "true", "yes", "settle")
    capture(int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], action, distance, settle)
