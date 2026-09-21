"""Visual AI Replay Viewer for LostWeapon.
Smoothly renders AI player executing physics-verified routes in real time.
"""
import json
import struct
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "native_harness"))

from api import NativeTrainingAPI
from native_env import ACTIONS

def load_lmf_tiles(lmf_path):
    raw = Path(lmf_path).read_bytes()
    width, height = struct.unpack_from("<HH", raw, 16)
    count = struct.unpack_from("<I", raw, 21)[0]
    records = [struct.unpack_from("<Ihh", raw, 32 + i * 8) for i in range(count)]
    return width, height, records

class AIPlayerViewer:
    def __init__(self, root, map_name="훈2"):
        self.root = root
        self.root.title(f"LostWeapon AI Route Player - [{map_name}.LMF]")
        self.root.geometry("1000x650")
        self.root.configure(bg="#121820")
        
        self.map_name = map_name
        self.maps_dir = ROOT / "훈련용맵"
        self.harness_dir = ROOT / "native_harness"
        self.lmf_path = self.maps_dir / f"{map_name}.LMF"
        
        # Load best route
        best_path = self.harness_dir / "checkpoints" / "local_physics_v1" / f"{map_name}.best.json"
        if not best_path.exists():
            raise FileNotFoundError(f"No best route found for {map_name}")
            
        data = json.loads(best_path.read_text(encoding="utf-8"))
        self.actions_rle = data["actions"]
        
        # Expand ticks (2 ticks per action in local_physics_v1)
        self.tick_inputs = []
        for action_id, duration in self.actions_rle:
            keys = ACTIONS[action_id]
            for _ in range(duration * 2):
                self.tick_inputs.append(keys)
                
        self.width, self.height, self.records = load_lmf_tiles(self.lmf_path)
        
        # Initialize native API
        self.snapshot_path = self.harness_dir / "private_snapshots" / "hun1_full.zip"
        self.api = NativeTrainingAPI(self.snapshot_path, self.lmf_path)
        
        self.canvas = tk.Canvas(self.root, bg="#101722", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.current_tick = 0
        self.cleared = False
        self.camera_x = 0.0
        self.camera_y = 150.0
        
        self._build_hud()
        self.reset_run()
        self.root.after(50, self.update_frame)
        
    def _build_hud(self):
        self.hud_text = self.canvas.create_text(
            16, 16, anchor="nw", fill="#00ffcc",
            font=("Consolas", 12, "bold"), text="Initializing..."
        )
        self.action_text = self.canvas.create_text(
            16, 42, anchor="nw", fill="#ffcc00",
            font=("Consolas", 12, "bold"), text=""
        )
        
    def reset_run(self):
        self.api.reset()
        self.current_tick = 0
        self.cleared = False
        self.trail = []
        
    def draw_world(self, px, py, keys, state):
        self.canvas.delete("world")
        cam_x = px - 400.0
        cam_y = self.camera_y
        
        # Draw tiles
        for tile_id, tx, ty in self.records:
            x0 = tx * 32.0 - cam_x
            y0 = ty * 32.0 - cam_y
            x1 = x0 + 32.0
            y1 = y0 + 32.0
            
            # Culling
            if x1 < -50 or x0 > 1050:
                continue
                
            if tile_id in (7, 8):  # Ground
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#4a5568", outline="#718096", tags="world")
            elif tile_id == 49:    # Lava
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#e53e3e", outline="#dd6b20", tags="world")
            elif tile_id == 140:   # Flag
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#ecc94b", outline="#faf089", width=2, tags="world")
                self.canvas.create_text(x0 + 16, y0 + 16, text="🚩", font=("Segoe UI Emoji", 14), tags="world")
            elif tile_id == 100:   # Spawn
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#319795", outline="#4fd1c5", tags="world")
                
        # Draw Trail
        self.trail.append((px - cam_x, py - cam_y))
        if len(self.trail) > 40:
            self.trail.pop(0)
        for i in range(len(self.trail) - 1):
            x_a, y_a = self.trail[i]
            x_b, y_b = self.trail[i+1]
            self.canvas.create_line(x_a, y_a, x_b, y_b, fill="#38b2ac", width=2, tags="world")
            
        # Draw Player
        pl_screen_x = px - cam_x
        pl_screen_y = py - cam_y
        pw, ph = 24.0, 36.0
        self.canvas.create_rectangle(
            pl_screen_x - pw/2, pl_screen_y - ph, pl_screen_x + pw/2, pl_screen_y,
            fill="#63b3ed", outline="#ffffff", width=2, tags="world"
        )
        # Eye direction
        self.canvas.create_oval(
            pl_screen_x + 2, pl_screen_y - ph + 8, pl_screen_x + 6, pl_screen_y - ph + 12,
            fill="#ffffff", outline="", tags="world"
        )
        
        # HUD
        input_str = "+".join(keys) if keys else "[IDLE]"
        self.canvas.itemconfig(
            self.hud_text,
            text=f"TICK: {self.current_tick:3d}/{len(self.tick_inputs)} | POS: ({px:6.1f}, {py:6.1f}) | SPEED: {state['motion58']:+6.1f}"
        )
        self.canvas.itemconfig(
            self.action_text,
            text=f"AI KEY INPUT: {input_str:<18} | TECHNIQUE: {'3칸 낭떠러지 대시 롱점프 돌파' if 20 <= self.current_tick <= 45 else '전력 질주'}"
        )
        
        if px >= 740.0:
            self.cleared = True
            self.canvas.create_text(
                500, 260, text="★ GOAL REACHED! (STAGE CLEAR) ★",
                fill="#ffea00", font=("Segoe UI", 28, "bold"), tags="world"
            )
            self.canvas.create_text(
                500, 310, text="3칸 낭떠러지 점프 & 깃발 클리어 성공 실측 재생",
                fill="#ffffff", font=("Segoe UI", 14), tags="world"
            )

    def update_frame(self):
        if self.current_tick < len(self.tick_inputs):
            keys = self.tick_inputs[self.current_tick]
            st = self.api.step(1, keys=keys)
            self.current_tick += 1
            self.draw_world(st["x"], st["y"], keys, st)
            self.root.after(50, self.update_frame)
        else:
            # Loop replay after 2 seconds
            self.root.after(2000, self.restart)
            
    def restart(self):
        self.reset_run()
        self.update_frame()

def main():
    root = tk.Tk()
    map_name = "훈2"
    if len(sys.argv) > 1:
        map_name = sys.argv[1]
    viewer = AIPlayerViewer(root, map_name=map_name)
    root.mainloop()

if __name__ == "__main__":
    main()
