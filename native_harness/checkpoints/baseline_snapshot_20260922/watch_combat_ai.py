"""Smooth visual replay of the latest native two-view combat policy."""
from pathlib import Path
import argparse
import copy
import queue
import struct
import sys
import threading
import time
import tkinter as tk

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
import torch
from combat_env import LostWeaponCombatEnv, COMBAT_ACTIONS
from train_combat_selfplay import network, load_combat_policy_compatible

parser = argparse.ArgumentParser()
parser.add_argument("--lmf", type=Path)
parser.add_argument("--combat-off", action="store_true",
                    help="Start with attack actions disabled; T toggles them")
parser.add_argument("--checkpoint", type=Path,
                    default=ROOT / "checkpoints" / "combat_shared_dqn.pt")
args = parser.parse_args()
checkpoint = args.checkpoint
if not checkpoint.exists():
    raise SystemExit("No valid checkpoint yet. Train at least 10 episodes first.")

env = LostWeaponCombatEnv(ROOT / "private_snapshots" / "team_p2p_combat_live.zip",
                          peer_snapshot=ROOT / "private_snapshots" / "team_slot1_live.zip",
                          lmf=args.lmf,
                          max_steps=512)
saved = torch.load(checkpoint, map_location="cpu", weights_only=False)
learned_actions = int(saved.get("action_size", saved["model"]["4.bias"].shape[0]))
model = network(env.observation_size, env.action_size)
load_combat_policy_compatible(model, saved["model"],
                              saved.get("observation_schema"), env.observation_schema)
model.eval()
observations, info = env.reset(spawn_distance=128)

root = tk.Tk(); root.title(f"LostWeapon combat AI - checkpoint episode {saved['episode']}")
canvas = tk.Canvas(root, width=1000, height=650, bg="#17202d", highlightthickness=0)
canvas.pack(fill="both", expand=True)

# Terrain is created once. Camera changes move this tag instead of rebuilding tiles.
camera = [240.0, 316.0]
grid = env.oracle.get(0x8952DEC, "I")[0]
for gy in range(env.height):
    for gx in range(env.width):
        value = struct.unpack("<H", env.oracle.u.mem_read(grid + 2 * (gy * env.width + gx), 2))[0]
        if value:
            x, y = gx * 32 - camera[0], gy * 32 - camera[1]
            canvas.create_rectangle(x, y, x + 32, y + 32, fill="#756044",
                                    outline="#a58b68", tags=("terrain",))

colors = ("#46d9ff", "#ff647c")
body = []; facing = []; label = []
for roster in (0, 1):
    body.append(canvas.create_rectangle(0, 0, 1, 1, fill=colors[roster], outline="white", width=2))
    facing.append(canvas.create_line(0, 0, 1, 1, fill="white", width=3))
    label.append(canvas.create_text(0, 0, fill="white", text=""))
status = canvas.create_text(12, 12, anchor="nw", fill="white", font=("Consolas", 13, "bold"))

samples = queue.Queue(maxsize=3)
stop_event = threading.Event(); pause_event = threading.Event(); reset_event = threading.Event()
combat_event = threading.Event()
if not args.combat_off:
    combat_event.set()
latest_info = copy.deepcopy(info); latest_actions = {0: 0, 1: 0}


def simulation_worker():
    global observations, info
    while not stop_event.is_set():
        if pause_event.is_set():
            time.sleep(.02); continue
        if reset_event.is_set():
            observations, info = env.reset(spawn_distance=128); reset_event.clear()
        with torch.no_grad():
            actions = {}
            for r in (0, 1):
                allowed = tuple(i for i in
                                env.valid_action_indices_from_observation(observations[r])
                                if i < learned_actions and
                                (combat_event.is_set() or "Z" not in COMBAT_ACTIONS[i]))
                q = model(torch.from_numpy(observations[r]))
                mask = torch.full_like(q, float("-inf"))
                mask[list(allowed)] = 0
                actions[r] = int((q + mask).argmax())
        observations, _, done, truncated, info = env.step(actions)
        if done or truncated:
            observations, info = env.reset(spawn_distance=128)
        sample = (time.perf_counter(), copy.deepcopy(info), dict(actions), env.steps)
        try: samples.put_nowait(sample)
        except queue.Full:
            try: samples.get_nowait()
            except queue.Empty: pass
            samples.put_nowait(sample)


threading.Thread(target=simulation_worker, daemon=True).start()
previous = copy.deepcopy(info); target = copy.deepcopy(info)
transition_start = time.perf_counter(); transition_duration = .10; target_tick = 0


def render():
    global previous, target, transition_start, transition_duration, target_tick, latest_actions
    now = time.perf_counter()
    newest = None
    while True:
        try: newest = samples.get_nowait()
        except queue.Empty: break
    if newest:
        stamp, new_info, latest_actions, target_tick = newest
        # Start the next interpolation from the currently displayed position.
        ratio = min(1.0, (now - transition_start) / max(.016, transition_duration))
        blended = copy.deepcopy(target)
        for r in (0, 1):
            for field in ("x", "y"):
                blended["players"][r][field] = (previous["players"][r][field] * (1-ratio) +
                                                   target["players"][r][field] * ratio)
        previous, target = blended, new_info
        transition_duration = max(.05, min(.30, stamp - transition_start))
        transition_start = now
    ratio = min(1.0, (now - transition_start) / max(.016, transition_duration))
    shown = {}
    for r in (0, 1):
        p0, p1 = previous["players"][r], target["players"][r]
        shown[r] = dict(p1)
        shown[r]["x"] = p0["x"] * (1-ratio) + p1["x"] * ratio
        shown[r]["y"] = p0["y"] * (1-ratio) + p1["y"] * ratio
    desired = [(shown[0]["x"] + shown[1]["x"]) / 2 - 500,
               (shown[0]["y"] + shown[1]["y"]) / 2 - 420]
    canvas.move("terrain", camera[0] - desired[0], camera[1] - desired[1])
    camera[:] = desired
    for r in (0, 1):
        p = shown[r]; x, y = p["x"] - camera[0], p["y"] - camera[1]
        canvas.coords(body[r], x-17, y-76, x+17, y)
        direction = 1 if p["b0"] == 0 else -1
        canvas.coords(facing[r], x, y-55, x + direction*25, y-55)
        canvas.coords(label[r], x, y-94)
        action = "+".join(COMBAT_ACTIONS[latest_actions[r]]) or "NOOP"
        canvas.itemconfigure(label[r], text=f"P{r} HP {p['hp']:.1f}  W{p['weapon']}  {action}")
    state = "PAUSED" if pause_event.is_set() else "PLAY"
    canvas.itemconfigure(status, text=(f"checkpoint {saved['episode']} | replay tick {target_tick} | "
                                      f"{state} | combat {'ON' if combat_event.is_set() else 'OFF'} | "
                                      "T toggle | Space pause | R reset"))
    root.after(16, render)


def key(event):
    if event.keysym == "space":
        pause_event.clear() if pause_event.is_set() else pause_event.set()
    elif event.keysym.lower() == "r": reset_event.set()
    elif event.keysym.lower() == "t":
        combat_event.clear() if combat_event.is_set() else combat_event.set()


def close():
    stop_event.set(); root.destroy()

root.bind("<KeyPress>", key); root.protocol("WM_DELETE_WINDOW", close)
root.after(16, render); root.mainloop()
