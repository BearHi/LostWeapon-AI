"""Capture a snapshot and normal RIGHT trace from the same suspended boundary.

The Client is read-only: no debugger and no process-memory write. RIGHT is held
through ordinary Windows keyboard input before the suspended process resumes.
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


def capture_boundary_trace(pid, snapshot_path, trace_path, distance=48.0):
    reader = Reader(pid)
    reader.close()
    reader.h = k.OpenProcess(0xC10, False, pid)
    if not reader.h:
        raise C.WinError(C.get_last_error())
    hwnd = process_window(pid)
    prior_foreground = u.GetForegroundWindow()
    regions = []
    samples = []
    suspended = False
    pressed = False
    meta = {
        "pid": pid,
        "regions": [],
        "modules": reader.modules,
        "client": reader.module,
        "teb32_candidates": [],
        "boundary": "process suspended immediately before ordinary RIGHT input and resume",
    }
    try:
        focus_window(hwnd)
        time.sleep(0.08)
        if u.GetForegroundWindow() != hwnd:
            raise RuntimeError("Client did not become foreground; no key sent")
        started = time.perf_counter()
        if nt.NtSuspendProcess(reader.h) < 0:
            raise RuntimeError("Could not suspend Client")
        suspended = True
        meta["state"] = reader.state()
        address = 0
        while address < 0x80000000:
            info = MBI()
            if not k.VirtualQueryEx(reader.h, address, C.byref(info), C.sizeof(info)):
                break
            base = info.BaseAddress or 0
            size = info.RegionSize
            if info.State == 0x1000 and not (info.Protect & 0x101) and info.Type in (0x20000, 0x1000000):
                raw = reader.read(base, size)
                regions.append((base, raw))
                meta["regions"].append({"base": base, "size": size, "protect": info.Protect, "type": info.Type})
                for offset in range(0, size - 0x34, 4096):
                    if struct.unpack_from("<I", raw, offset + 0x18)[0] == base + offset:
                        tls = struct.unpack_from("<I", raw, offset + 0x2C)[0]
                        if tls:
                            meta["teb32_candidates"].append({"teb": base + offset, "tls": tls})
            address = base + size
        meta["capture_pause_seconds"] = time.perf_counter() - started
        start = meta["state"]
        start_x = start["pos"][0]
        samples.append({"boundary": True, "perf_ns": time.perf_counter_ns(), "time_ms": winmm.timeGetTime(), "state": start})
        last = signature(start)
        u.keybd_event(VK_RIGHT, 0, 0, 0)
        pressed = True
        if nt.NtResumeProcess(reader.h) < 0:
            raise RuntimeError("Failed to resume Client")
        suspended = False
        deadline = time.perf_counter() + 1.0
        while time.perf_counter() < deadline:
            state = reader.state()
            sig = signature(state)
            if sig != last:
                samples.append({"boundary": False, "perf_ns": time.perf_counter_ns(), "time_ms": winmm.timeGetTime(), "state": state})
                last = sig
            if state["pos"][0] >= start_x + distance:
                break
    finally:
        if pressed:
            u.keybd_event(VK_RIGHT, 0, KEYEVENTF_KEYUP, 0)
        if suspended:
            nt.NtResumeProcess(reader.h)
        if prior_foreground and u.GetForegroundWindow() == hwnd:
            u.SetForegroundWindow(prior_foreground)
        reader.close()

    snapshot_path = Path(snapshot_path)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(snapshot_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for base, raw in regions:
            archive.writestr(f"{base:08x}.bin", raw)
        archive.writestr("metadata.json", json.dumps(meta))
    trace = {
        "scope": "same-boundary read-only normal Client snapshot and ordinary RIGHT trace",
        "snapshot": str(snapshot_path),
        "target_distance": distance,
        "samples": samples,
    }
    trace_path = Path(trace_path)
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "snapshot": str(snapshot_path),
        "trace": str(trace_path),
        "pause_seconds": meta["capture_pause_seconds"],
        "start": samples[0]["state"]["pos"],
        "end": samples[-1]["state"]["pos"],
        "samples": len(samples),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    capture_boundary_trace(int(sys.argv[1]), sys.argv[2], sys.argv[3])
