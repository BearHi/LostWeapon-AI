"""Small interactive window for the confirmed native-oracle fixtures.

This is a debug harness, not the original Client renderer. It draws LMF tiles
and the native-oracle player state, while keyboard input is fed to the same
NativeTrainingAPI used by the headless tests.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tkinter as tk

from api import NativeTrainingAPI
from lmf_injector import NativeLmfOracle

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
FIXTURES = {
    "hun2": (ROOT / "private_snapshots" / "hun2_live.zip", PROJECT / "훈련용맵" / "훈2.LMF"),
    "hun5": (ROOT / "private_snapshots" / "hun5_live.zip", PROJECT / "훈련용맵" / "훈5.LMF"),
    "hun6": (ROOT / "private_snapshots" / "hun6_live.zip", PROJECT / "훈련용맵" / "훈6.LMF"),
    "hun7": (ROOT / "private_snapshots" / "hun7_live.zip", PROJECT / "훈련용맵" / "훈7.LMF"),
    "hun12": (ROOT / "private_snapshots" / "hun12_live.zip", PROJECT / "훈련용맵" / "훈12.LMF"),
}
KEYS = {"Left": "LEFT", "Right": "RIGHT", "Up": "UP", "Down": "DOWN",
        "space": "SPACE", "c": "C", "C": "C", "z": "Z", "Z": "Z"}
TILE_COLORS = {7: "#4b5563", 3: "#f59e0b", 100: "#60a5fa", 140: "#34d399"}


class DebugWindow:
    def __init__(self, fixture: str):
        snapshot, lmf = FIXTURES[fixture]
        self.fixture = fixture
        self.api = NativeTrainingAPI(snapshot, lmf)
        self.width, self.height, records = self.api.oracle.parse_lmf(lmf)
        self.records = records
        self.root = tk.Tk()
        self.root.title(f"LostWeapon Native Oracle — {fixture}")
        self.root.configure(bg="#111827")
        self.scale = 32
        self.canvas = tk.Canvas(self.root, width=self.width * self.scale, height=self.height * self.scale,
                                bg="#0b1220", highlightthickness=0)
        self.canvas.pack(padx=8, pady=8)
        self.info = tk.StringVar()
        tk.Label(self.root, textvariable=self.info, anchor="w", justify="left",
                 bg="#111827", fg="#e5e7eb", font=("Consolas", 10)).pack(fill="x", padx=8)
        buttons = tk.Frame(self.root, bg="#111827")
        buttons.pack(fill="x", padx=8, pady=(4, 8))
        tk.Button(buttons, text="Reset", command=self.reset).pack(side="left")
        tk.Button(buttons, text="Save branch", command=self.save_branch).pack(side="left", padx=4)
        tk.Button(buttons, text="Restore branch", command=self.restore_branch).pack(side="left")
        tk.Label(buttons, text="  Arrows / C / Z", bg="#111827", fg="#9ca3af").pack(side="right")
        self.held: set[str] = set()
        self.saved = None
        self.root.bind("<KeyPress>", self.key_down)
        self.root.bind("<KeyRelease>", self.key_up)
        self.root.focus_force()
        self.draw()
        # Keep the UI cadence close to the Client's 60 Hz gameplay tick.  The
        # native closure remains authoritative; if an emulation step takes
        # longer, Tkinter naturally queues the next tick instead of dropping
        # or inventing a physics update.
        self.root.after(16, self.tick)

    def key_down(self, event):
        if event.keysym in KEYS:
            self.held.add(KEYS[event.keysym])

    def key_up(self, event):
        if event.keysym in KEYS:
            self.held.discard(KEYS[event.keysym])

    def tick(self):
        try:
            self.api.step(1, sorted(self.held))
            self.draw()
        finally:
            self.root.after(16, self.tick)

    def reset(self):
        self.api.reset()
        self.draw()

    def save_branch(self):
        self.saved = self.api.save_state()

    def restore_branch(self):
        if self.saved is not None:
            self.api.restore_state(self.saved)
            self.draw()

    def draw(self):
        self.canvas.delete("all")
        s = self.api.read_state()
        for tile_id, x, y in self.records:
            color = TILE_COLORS.get(tile_id, "#8b5cf6")
            self.canvas.create_rectangle(x * self.scale, y * self.scale,
                                         (x + 1) * self.scale, (y + 1) * self.scale,
                                         fill=color, outline="#263244")
        px, py = s["x"], s["y"]
        self.canvas.create_oval(px - 8, py - 8, px + 8, py + 8, fill="#fb7185", outline="white", width=2)
        self.info.set(f"{self.fixture}   x={px:.1f} y={py:.1f} motion58={s['motion58']:.1f} "
                      f"state38={s['38']} C0={s['c0']} action74={s['74']} keys={sorted(self.held)}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    fixture = sys.argv[1] if len(sys.argv) > 1 else "hun7"
    if fixture not in FIXTURES:
        raise SystemExit(f"fixture must be one of: {', '.join(FIXTURES)}")
    DebugWindow(fixture).run()
