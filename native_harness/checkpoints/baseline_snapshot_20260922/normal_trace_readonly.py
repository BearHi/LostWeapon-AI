"""Capture a short normal-Client state trace using ordinary keyboard input.

No Client memory is written and no debugger is attached. The target window must
successfully become foreground before any key is sent. Key-up and prior focus
restoration are guaranteed in finally.
"""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import json
import sys
import time

from live_state import Reader

u = C.WinDLL("user32", use_last_error=True)
winmm = C.WinDLL("winmm")
winmm.timeGetTime.restype = W.DWORD
WNDENUMPROC = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
u.EnumWindows.argtypes = [WNDENUMPROC, W.LPARAM]
u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
u.GetForegroundWindow.restype = W.HWND
u.SetForegroundWindow.argtypes = [W.HWND]
u.SetForegroundWindow.restype = W.BOOL
u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
u.GetWindowThreadProcessId.restype = W.DWORD
u.AttachThreadInput.argtypes = [W.DWORD, W.DWORD, W.BOOL]
u.AttachThreadInput.restype = W.BOOL
u.ShowWindow.argtypes = [W.HWND, C.c_int]
u.BringWindowToTop.argtypes = [W.HWND]
u.IsWindowVisible.argtypes = [W.HWND]
u.keybd_event.argtypes = [W.BYTE, W.BYTE, W.DWORD, W.LPARAM]
u.SwitchToThisWindow.argtypes = [W.HWND, W.BOOL]
u.SwitchToThisWindow.restype = None

VK_RIGHT = 0x27
KEYEVENTF_KEYUP = 0x0002


def process_window(pid):
    found = []

    @WNDENUMPROC
    def callback(hwnd, _):
        owner = W.DWORD()
        u.GetWindowThreadProcessId(hwnd, C.byref(owner))
        if owner.value == pid and u.IsWindowVisible(hwnd):
            found.append(hwnd)
            return False
        return True

    u.EnumWindows(callback, 0)
    if not found:
        raise RuntimeError("No visible Client window")
    return found[0]


def focus_window(hwnd):
    """Bring a normal Client window to the foreground without sending input.

    Windows can reject SetForegroundWindow when the sampler is launched from
    another foreground process. Temporarily joining the target and foreground
    GUI threads makes the same operation reliable while leaving input untouched.
    """
    foreground = u.GetForegroundWindow()
    foreground_pid = W.DWORD()
    foreground_tid = u.GetWindowThreadProcessId(foreground, C.byref(foreground_pid)) if foreground else 0
    target_pid = W.DWORD()
    target_tid = u.GetWindowThreadProcessId(hwnd, C.byref(target_pid))
    u.ShowWindow(hwnd, 9)
    u.BringWindowToTop(hwnd)
    attached = bool(foreground_tid and target_tid and foreground_tid != target_tid and
                    u.AttachThreadInput(target_tid, foreground_tid, True))
    try:
        ok = bool(u.SetForegroundWindow(hwnd))
    finally:
        if attached:
            u.AttachThreadInput(target_tid, foreground_tid, False)
    if ok and u.GetForegroundWindow() == hwnd:
        return True

    # SetForegroundWindow is commonly refused when this helper was launched by
    # an automation host. SwitchToThisWindow performs the same visible window
    # activation without injecting a click or touching Client memory.
    u.SwitchToThisWindow(hwnd, True)
    return u.GetForegroundWindow() == hwnd


def signature(state):
    return [state["pos"], state["motion58"], state["state"], state["player_header"]]


def trace_right(pid, output, distance=48.0):
    reader = Reader(pid)
    hwnd = process_window(pid)
    previous_foreground = u.GetForegroundWindow()
    pressed = False
    samples = []
    try:
        focus_window(hwnd)
        time.sleep(0.08)
        if u.GetForegroundWindow() != hwnd:
            raise RuntimeError("Client did not become foreground; no key sent")
        start = reader.state()
        start_x = start["pos"][0]
        last = None
        u.keybd_event(VK_RIGHT, 0, 0, 0)
        pressed = True
        deadline = time.perf_counter() + 1.0
        while time.perf_counter() < deadline:
            state = reader.state()
            sig = signature(state)
            if sig != last:
                samples.append({"perf_ns": time.perf_counter_ns(), "time_ms": winmm.timeGetTime(), "state": state})
                last = sig
            if state["pos"][0] >= start_x + distance:
                break
        u.keybd_event(VK_RIGHT, 0, KEYEVENTF_KEYUP, 0)
        pressed = False
        release = reader.state()
        time.sleep(0.08)
        final = reader.state()
        result = {
            "scope": "read-only normal Client sampling with ordinary RIGHT key input",
            "pid": pid,
            "target_distance": distance,
            "start": start,
            "release": release,
            "final": final,
            "changed_samples": samples,
        }
        output = Path(output)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "output": str(output),
            "start": start["pos"],
            "release": release["pos"],
            "final": final["pos"],
            "changed_samples": len(samples),
        }, ensure_ascii=False, indent=2))
    finally:
        if pressed:
            u.keybd_event(VK_RIGHT, 0, KEYEVENTF_KEYUP, 0)
        if previous_foreground and u.GetForegroundWindow() == hwnd:
            u.SetForegroundWindow(previous_foreground)
        reader.close()


if __name__ == "__main__":
    trace_right(int(sys.argv[1]), sys.argv[2])
