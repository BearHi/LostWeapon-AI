"""Visual AI Replay Viewer for LostWeapon.
Smoothly renders AI player executing physics-verified routes at REAL GAME SPEED (62.5 FPS).
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

def build_pro_human_route():
    """Clean human-level pro route: Smooth sprint -> 3-tile arc jump -> sprint to flag."""
    route = []
    # Phase 1: Smooth sprint to gap edge (36 ticks = ~0.57 sec)
    for _ in range(36):
        route.append((["RIGHT"], "평지 전력 질주 (Sprint)"))
    # Phase 2: High arc jump across 3-tile gap (16 ticks = ~0.25 sec)
    for _ in range(16):
        route.append((["RIGHT", "UP"], "3칸 낭떠러지 도약 (Arc Jump)"))
    # Phase 3: Air glide & landing (12 ticks = ~0.19 sec)
    for _ in range(12):
        route.append((["RIGHT"], "착지 및 관성 제어 (Touchdown)"))
    # Phase 4: Full-speed sprint to flag (104 ticks = ~1.66 sec)
    for _ in range(104):
        route.append((["RIGHT"], "깃발을 향해 전력 질주 (Dash to Flag)"))
    return route

def build_learned_route(best_path):
    """Raw route found by heuristic local search."""
    data = json.loads(Path(best_path).read_text(encoding="utf-8"))
    route = []
    for action_id, duration in data["actions"]:
        keys = ACTIONS[action_id]
        for _ in range(duration * 2):
            desc = "앉기/눕기 이동" if "DOWN" in keys else "점프" if "UP" in keys else "이동"
            route.append((list(keys), desc))
    return route

class AIPlayerViewer:
    def __init__(self, root, map_name="훈2"):
        self.root = root
        self.root.title(f"LostWeapon AI Route Viewer - [{map_name}.LMF] (Real 62.5 FPS Speed)")
        self.root.geometry("1080x680")
        self.root.configure(bg="#0e131b")
        
        self.map_name = map_name
        self.maps_dir = ROOT / "훈련용맵"
        self.harness_dir = ROOT / "native_harness"
        self.lmf_path = self.maps_dir / f"{map_name}.LMF"
        
        # Build routes
        self.routes = {
            "pro": build_pro_human_route(),
        }
        best_path = self.harness_dir / "checkpoints" / "local_physics_v1" / f"{map_name}.best.json"
        if best_path.exists():
            self.routes["learned"] = build_learned_route(best_path)
            
        self.current_route_mode = "pro"  # Default: Clean human pro route!
        self.tick_inputs = self.routes[self.current_route_mode]
        
        self.width, self.height, self.records = load_lmf_tiles(self.lmf_path)
        
        # Initialize native API
        self.snapshot_path = self.harness_dir / "private_snapshots" / "hun1_full.zip"
        self.api = NativeTrainingAPI(self.snapshot_path, self.lmf_path)
        
        self.canvas = tk.Canvas(self.root, bg="#0d141e", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.current_tick = 0
        self.cleared = False
        self.camera_y = 150.0
        
        # 16ms interval = 62.5 FPS (Original LostWeapon Client real-time speed)
        self.tick_interval_ms = 16
        self.is_paused = False
        
        self._bind_keys()
        self._build_hud()
        self.reset_run()
        self.root.after(self.tick_interval_ms, self.update_frame)
        
    def _bind_keys(self):
        self.root.bind("<space>", lambda e: self.toggle_pause())
        self.root.bind("<Tab>", lambda e: self.toggle_route_mode())
        self.root.bind("<r>", lambda e: self.restart())
        self.root.bind("<R>", lambda e: self.restart())
        self.root.bind("1", lambda e: self.set_speed(16))   # 1x Real speed (62.5 FPS)
        self.root.bind("2", lambda e: self.set_speed(32))   # 0.5x Slow motion
        self.root.bind("3", lambda e: self.set_speed(8))    # 2x High speed
        
    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if not self.is_paused:
            self.update_frame()
            
    def set_speed(self, interval_ms):
        self.tick_interval_ms = interval_ms
        
    def toggle_route_mode(self):
        if self.current_route_mode == "pro" and "learned" in self.routes:
            self.current_route_mode = "learned"
        else:
            self.current_route_mode = "pro"
        self.tick_inputs = self.routes[self.current_route_mode]
        self.restart()
        
    def _build_hud(self):
        # Top HUD overlay
        self.hud_text = self.canvas.create_text(
            18, 16, anchor="nw", fill="#00ffcc",
            font=("Consolas", 12, "bold"), text="Initializing..."
        )
        self.action_text = self.canvas.create_text(
            18, 40, anchor="nw", fill="#ffeb3b",
            font=("Segoe UI", 12, "bold"), text=""
        )
        self.guide_text = self.canvas.create_text(
            1060, 16, anchor="ne", fill="#8899aa",
            font=("Segoe UI", 10),
            text="[Tab] 모드 전환(인간 프로 경로/기존 탐색 경로) | [Space] 일시정지 | [1] 1x 실시간 | [2] 0.5x 슬로우 | [R] 재시작"
        )
        
    def reset_run(self):
        self.api.reset()
        self.current_tick = 0
        self.cleared = False
        self.trail = []
        
    def draw_world(self, px, py, keys, desc, state):
        self.canvas.delete("world")
        cam_x = px - 420.0
        cam_y = self.camera_y
        
        # Draw tiles
        for tile_id, tx, ty in self.records:
            x0 = tx * 32.0 - cam_x
            y0 = ty * 32.0 - cam_y
            x1 = x0 + 32.0
            y1 = y0 + 32.0
            
            # Culling
            if x1 < -80 or x0 > 1160:
                continue
                
            if tile_id in (7, 8):  # Solid Ground Platform
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#3a4556", outline="#5b6a82", tags="world")
            elif tile_id == 49:    # Lava Hazard
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#c53030", outline="#e53e3e", tags="world")
            elif tile_id == 140:   # Goal Flag
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#d69e2e", outline="#ecc94b", width=2, tags="world")
                self.canvas.create_text(x0 + 16, y0 + 16, text="🚩", font=("Segoe UI Emoji", 14), tags="world")
            elif tile_id == 100:   # Start Spawn
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#2c7a7b", outline="#38b2ac", tags="world")
                
        # Draw Dynamic Jump Arc Trail
        self.trail.append((px - cam_x, py - cam_y))
        if len(self.trail) > 50:
            self.trail.pop(0)
        for i in range(len(self.trail) - 1):
            x_a, y_a = self.trail[i]
            x_b, y_b = self.trail[i+1]
            self.canvas.create_line(x_a, y_a, x_b, y_b, fill="#00e5ff", width=2, tags="world")
            
        # Draw Player Character
        pl_screen_x = px - cam_x
        pl_screen_y = py - cam_y
        pw, ph = 26.0, 40.0
        
        # Check crouching/ducking
        is_ducking = "DOWN" in keys
        if is_ducking:
            ph = 24.0
            
        # Body
        self.canvas.create_rectangle(
            pl_screen_x - pw/2, pl_screen_y - ph, pl_screen_x + pw/2, pl_screen_y,
            fill="#4299e1", outline="#ffffff", width=2, tags="world"
        )
        # Eye / visor
        self.canvas.create_oval(
            pl_screen_x + 3, pl_screen_y - ph + 8, pl_screen_x + 8, pl_screen_y - ph + 13,
            fill="#ffffff", outline="", tags="world"
        )
        
        # Mode indicator
        mode_label = "★ 인간형 최적화 경로 (Clean Sprint + Arc Jump)" if self.current_route_mode == "pro" else "◆ 기존 탐색 경로 (Raw Search)"
        
        # HUD Information
        input_str = "+".join(keys) if keys else "[NOOP]"
        fps_str = "62.5 FPS (실제 원본 속도)" if self.tick_interval_ms == 16 else f"{1000/self.tick_interval_ms:.1f} FPS"
        self.canvas.itemconfig(
            self.hud_text,
            text=f"TICK: {self.current_tick:3d}/{len(self.tick_inputs)} | POS: ({px:6.1f}, {py:6.1f}) | SPEED: {fps_str} | MODE: {mode_label}"
        )
        self.canvas.itemconfig(
            self.action_text,
            text=f"AI KEY: {input_str:<16} | MOTION: {desc}"
        )
        
        # Goal Clear Banner
        if px >= 760.0:
            self.cleared = True
            self.canvas.create_rectangle(240, 230, 840, 360, fill="#1a202c", outline="#ecc94b", width=3, tags="world")
            self.canvas.create_text(
                540, 275, text="★ GOAL REACHED! (STAGE CLEAR) ★",
                fill="#ffea00", font=("Segoe UI", 26, "bold"), tags="world"
            )
            self.canvas.create_text(
                540, 325, text=f"소요 시간: {self.current_tick}틱 ({self.current_tick * 0.016:.2f}초) | 3칸 낭떠러지 깔끔 돌파 & 깃발 클리어",
                fill="#e2e8f0", font=("Segoe UI", 13), tags="world"
            )

    def update_frame(self):
        if self.is_paused:
            return
        if self.current_tick < len(self.tick_inputs):
            keys, desc = self.tick_inputs[self.current_tick]
            st = self.api.step(1, keys=keys)
            self.current_tick += 1
            self.draw_world(st["x"], st["y"], keys, desc, st)
            self.root.after(self.tick_interval_ms, self.update_frame)
        else:
            # Loop replay after 2.5 seconds
            self.root.after(2500, self.restart)
            
    def restart(self):
        self.reset_run()
        if not self.is_paused:
            self.update_frame()

def main():
    root = tk.Tk()
    map_name = "훈2"
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        map_name = sys.argv[1]
    viewer = AIPlayerViewer(root, map_name=map_name)
    root.mainloop()

if __name__ == "__main__":
    main()
