"""Check whether tick count itself grows the native oracle process."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import sys
import time

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def memory_mb():
    counters = PROCESS_MEMORY_COUNTERS_EX()
    counters.cb = ctypes.sizeof(counters)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return {"working_set_mb": round(counters.WorkingSetSize / 1048576, 2),
            "private_mb": round(counters.PrivateUsage / 1048576, 2)}


api = NativeTrainingAPI(HARNESS / "private_snapshots" / "hun1_full.zip",
                        HARNESS.parent / "훈련용맵" / "훈1.LMF", track_dirty=False)
samples = []
started = time.perf_counter()
for tick in range(0, 20001):
    if tick % 1000 == 0:
        samples.append({"tick": tick, **memory_mb(),
                        "runtime_counts": list(api.oracle.get(0x25CA048, "ii")),
                        "player": api.read_state()})
    if tick < 20000:
        api.step(1, ())
elapsed = time.perf_counter() - started
result = {
    "ok": True,
    "scope": "훈1 original-x86 NOOP 20000-tick process stability",
    "pid": os.getpid(), "elapsed_seconds": round(elapsed, 3),
    "tick_rate": round(20000 / elapsed, 2), "samples": samples,
    "private_growth_mb": round(samples[-1]["private_mb"] - samples[0]["private_mb"], 2),
    "working_set_growth_mb": round(samples[-1]["working_set_mb"] - samples[0]["working_set_mb"], 2),
}
(HARNESS / "evidence" / "hun1_long_run_stability.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in result.items() if key != "samples"},
                 ensure_ascii=False, indent=2))
