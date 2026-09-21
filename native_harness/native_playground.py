"""Interactive debug view backed by the original LostWeapon x86 gameplay code."""
from __future__ import annotations

import gc
import json
import multiprocessing as mp
import struct
import subprocess
import sys
import time
import tkinter as tk
import ctypes
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from api import NativeTrainingAPI


FIXTURES = ["훈1", "훈2", "훈3", "훈4", "훈5", "훈6", "훈6.5", "훈7", "훈7.5",
            "훈8", "훈8.5", "훈9", "훈10", "훈11", "훈12", "훈13", "훈14",
            "훈15", "훈16", "훈17", "훈18", "훈19", "훈20"]
SNAPSHOTS = {
    "훈1": "hun1_full.zip", "훈2": "hun2_live.zip", "훈5": "hun5_live.zip",
    "훈6": "hun6_live.zip", "훈7": "hun7_live.zip", "훈8.5": "hun85_live.zip",
    "훈10": "hun10_live.zip", "훈12": "hun12_live.zip", "훈13": "hun13_live.zip",
    "훈14": "hun14_live.zip", "훈15": "hun14_live.zip", "훈16": "hun16_live.zip",
    "훈17": "hun17_live.zip", "훈18": "hun18_live.zip", "훈19": "hun19_live.zip",
    "훈20": "hun20_live.zip",
}
KEY_NAMES = {"Left": "LEFT", "Right": "RIGHT", "Up": "UP", "Down": "DOWN",
             "space": "SPACE",
             "z": "Z", "x": "X", "c": "C", "Z": "Z", "X": "X", "C": "C",
             "1": "1", "2": "2", "3": "3", "4": "4",
             "KP_1": "1", "KP_2": "2", "KP_3": "3", "KP_4": "4"}

MICRO_INPUTS = (
    ("무입력", ()), ("←", ("LEFT",)), ("→", ("RIGHT",)),
    ("↑", ("UP",)), ("↓", ("DOWN",)),
    ("↖", ("LEFT", "UP")), ("↗", ("RIGHT", "UP")),
    ("↙", ("LEFT", "DOWN")), ("↘", ("RIGHT", "DOWN")),
    ("C", ("C",)), ("Z", ("Z",)), ("Space", ("SPACE",)),
)

# The normal Client advances its ground-walk boundary every ~16 ms (the
# read-only 훈2 trace measured 11 intervals in 175 ms).  Pacing the playground
# at an assumed 60.0 Hz made the same wall-clock key hold travel about 4%
# shorter even though every compared physics tick was exact.
CLIENT_TICKS_PER_SECOND = 62.5


def find_workspace():
    candidates = []
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve().parent
        candidates += [executable, executable.parent, executable.parent.parent]
    source = Path(__file__).resolve().parent
    candidates += [source, source.parent / "native_harness", Path.cwd() / "native_harness"]
    for harness in candidates:
        if (harness / "private_snapshots").is_dir() and (harness.parent / "훈련용맵").is_dir():
            return harness, harness.parent / "훈련용맵"
    raise FileNotFoundError("native_harness/private_snapshots와 훈련용맵 폴더를 찾지 못했습니다.")


def parse_lmf(path):
    raw = path.read_bytes()
    width, height = struct.unpack_from("<HH", raw, 16)
    count = struct.unpack_from("<I", raw, 21)[0]
    records = [struct.unpack_from("<Ihh", raw, 32 + index * 8) for index in range(count)]
    return width, height, records


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_self_test(output_path):
    """Exercise load, original x86 stepping, save, and exact restore from the frozen app."""
    started = time.perf_counter()
    try:
        harness, maps_dir = find_workspace()
        api = NativeTrainingAPI(harness / "private_snapshots" / "hun1_full.zip",
                                maps_dir / "훈1.LMF")
        initial = api.read_state()
        saved = api.save_state()
        first = [api.step(1, ("RIGHT",)) for _ in range(12)]
        api.restore_state(saved)
        second = [api.step(1, ("RIGHT",)) for _ in range(12)]
        if first != second:
            raise AssertionError("save/restore 뒤 12틱 상태열이 달라졌습니다")
        result = {
            "ok": True,
            "engine": "original Client x86 via Unicorn",
            "fixture": "훈1.LMF",
            "ticks": 12,
            "initial": initial,
            "final": second[-1],
            "deterministic_replay": True,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        write_json(output_path, result)
        return 0
    except Exception as exc:
        write_json(output_path, {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        })
        return 1


def worker_gameplay_status(api, dynamic_indices):
    oracle = api.oracle
    slot = oracle.meta["state"]["slot"]
    selected = oracle.get(0x25F1AD8, "i")[0]
    weapon = f"무기 {selected + 1}" if 0 <= selected <= 3 else "무기 -"
    state = api.read_state()
    player = 0x3B12A00 + slot * 0xF8
    attack_bounds = list(oracle.get(player + 0x18, "4i"))
    if state["38"] == 5 or state["7c"] not in (0, -1):
        action = "피격/누움"
    elif state["dc"]:
        action = "낙하산 펼침"
    elif state["c0"] == 1 or state["38"] == 6:
        action = "앉기"
    elif state["c0"] == 4:
        action = "앞굴"
    elif state["c0"] == 3:
        action = "뒷굴"
    elif 15 <= state["38"] <= 18 or state["68"]:
        action = "공격"
    elif state["38"] == 21 or state["c0"] == 21:
        action = "물속"
    elif state["38"] == 9:
        action = "공중"
    else:
        action = "보통"
    ice_acc = oracle.get(0x25CA528 + slot * 4, "i")[0]
    field_d8 = oracle.get(player + 0xD8, "i")[0]
    inertia_direction = oracle.get(0x25CA078 + slot * 4, "i")[0]
    dynamic = {}
    for record_index in dynamic_indices:
        runtime_index = oracle.runtime_index_by_record.get(record_index)
        if runtime_index is not None:
            address = 0x27A5998 + runtime_index * 0xF8
            dynamic[record_index] = {
                "c8": oracle.get(address + 0xC8, "i")[0],
                "animation": oracle.get(address + 0x08, "i")[0],
                "frame": oracle.get(address + 0x4C, "i")[0],
            }
        else:
            special_index = getattr(oracle, "special_index_by_record", {}).get(record_index)
            if special_index is not None:
                address = 0xA074460 + special_index * 0xF8
                x, y = oracle.get(address + 0x10, "dd")
                dynamic[record_index] = {
                    "special": True, "x": x, "y": y,
                    "c8": oracle.get(address + 0xC8, "i")[0],
                    "animation": oracle.get(address + 0x08, "i")[0],
                    "frame": oracle.get(address + 0x4C, "i")[0],
                }
    return (state, weapon, action, ice_acc, dynamic, attack_bounds,
            field_d8, inertia_direction)


def physics_worker(connection):
    """Own Unicorn and run it on a dedicated process at game-clock rate."""
    api = None
    generation = 0
    tick = 0
    running = False
    keys = ()
    multiplier = 1
    dynamic_indices = []
    goals = []
    saved = None
    next_tick = time.perf_counter()
    rate_started = next_tick
    rate_tick = 0
    actual_tps = 0.0
    last_applied_keys = None
    input_ticks = 0

    def publish(phase="running"):
        if api is None:
            return
        (state, weapon, action, ice_acc, dynamic, attack_bounds,
         field_d8, inertia_direction) = worker_gameplay_status(api, dynamic_indices)
        connection.send({"kind": "state", "generation": generation, "phase": phase,
                         "tick": tick, "actual_tps": actual_tps, "state": state,
                         "weapon": weapon, "action": action, "ice_acc": ice_acc,
                         "field_d8": field_d8,
                         "inertia_direction": inertia_direction,
                         "sample_perf_ns": time.perf_counter_ns(),
                         "dynamic": dynamic, "attack_bounds": attack_bounds,
                         "input": list(keys), "input_ticks": input_ticks})

    while True:
        while connection.poll():
            command = connection.recv()
            kind = command[0]
            if kind == "close":
                return
            if kind == "load":
                _, generation, snapshot, lmf, dynamic_indices, goals = command
                try:
                    # Release the previous ~550 MB captured process before
                    # constructing the next one. Keeping both alive during a
                    # map switch caused heavy paging and multi-second stalls.
                    api = None
                    gc.collect()
                    api = NativeTrainingAPI(Path(snapshot), Path(lmf), track_dirty=False)
                    tick = 0
                    keys = ()
                    saved = None
                    running = True
                    next_tick = rate_started = time.perf_counter()
                    rate_tick = 0
                    actual_tps = 0.0
                    last_applied_keys = None
                    input_ticks = 0
                    connection.send({"kind": "loaded", "generation": generation,
                                     "map": api.map})
                    publish("loaded")
                except Exception as exc:
                    api = None
                    running = False
                    connection.send({"kind": "error", "generation": generation,
                                     "error": f"{type(exc).__name__}: {exc}"})
            elif kind == "input":
                keys = tuple(command[1])
            elif kind == "unload":
                api = None
                running = False
                tick = 0
                gc.collect()
            elif kind == "running":
                running = bool(command[1])
                next_tick = time.perf_counter()
                publish("running" if running else "paused")
            elif kind == "speed":
                multiplier = max(1, int(command[1]))
                next_tick = time.perf_counter()
            elif kind == "step" and api is not None:
                running = False
                step_keys = tuple(command[1])
                if step_keys == last_applied_keys:
                    input_ticks += 1
                else:
                    last_applied_keys, input_ticks = step_keys, 1
                api.step(1, step_keys)
                tick += 1
                publish("paused")
            elif kind == "save" and api is not None:
                saved = (api.save_state(), tick)
                connection.send({"kind": "saved", "generation": generation, "tick": tick})
            elif kind == "restore" and api is not None and saved is not None:
                api.restore_state(saved[0])
                tick = saved[1]
                keys = ()
                running = False
                publish("paused")

        if api is None or not running:
            time.sleep(0.002)
            continue
        now = time.perf_counter()
        interval = 1.0 / (CLIENT_TICKS_PER_SECOND * multiplier)
        if now < next_tick:
            time.sleep(min(next_tick - now, 0.001))
            continue
        if keys == last_applied_keys:
            input_ticks += 1
        else:
            last_applied_keys, input_ticks = keys, 1
        api.step(1, keys)
        tick += 1
        next_tick += interval
        if now - next_tick > 0.25:
            next_tick = now
        state = api.read_state()
        if any(gx * 32 - 24 <= state["x"] <= gx * 32 + 32 and
               gy * 32 <= state["y"] <= gy * 32 + 64 for gx, gy in goals):
            running = False
            keys = ()
            phase = "cleared"
        else:
            phase = "running"
        elapsed = now - rate_started
        if elapsed >= 0.5:
            actual_tps = (tick - rate_tick) / elapsed
            rate_started = now
            rate_tick = tick
        # At 1x publish every original Client tick so the tester sees the same
        # cadence. At accelerated speeds send only the newest display-rate
        # boundary; flooding the pipe with hundreds of stale frames made input
        # and drawing lag behind the physics worker.
        if phase != "running" or multiplier == 1 or tick % multiplier == 0:
            publish(phase)


class Playground:
    COLORS = {
        7: ("#5d6470", "#858e9d"), 49: ("#d63b28", "#ff7a38"),
        3: ("#ad7a42", "#e2b56f"), 4: ("#35b96f", "#9ef0b7"),
        5: ("#35b96f", "#9ef0b7"), 6: ("#35b96f", "#9ef0b7"),
        27: ("#77d9ff", "#d7f6ff"), 37: ("#77d9ff", "#d7f6ff"),
        51: ("#56c6d8", "#b4f6ff"), 52: ("#a56af4", "#dfc7ff"),
        53: ("#a56af4", "#dfc7ff"), 54: ("#a56af4", "#dfc7ff"),
        55: ("#a56af4", "#dfc7ff"), 123: ("#247ec7", "#65c8ff"),
        124: ("#d6b13b", "#fff09a"), 136: ("#cc5d96", "#ffafd5"),
        138: ("#9a6138", "#d39a6a"), 140: ("#ffd84c", "#fff2a0"),
        100: ("#4fd56d", "#b8ffc5"),
    }

    def __init__(self, root, initial_lmf=None, start_paused=False):
        self.root = root
        self.root.title("LostWeapon Native Physics Playground")
        self.root.geometry("1120x780")
        self.root.minsize(820, 580)
        self.harness, self.maps_dir = find_workspace()
        registry_path = self.harness.parent / "analysis" / "system_model" / "tile_registry.json"
        self.tile_registry = (json.loads(registry_path.read_text(encoding="utf-8"))
                              if registry_path.exists() else {})
        self.sprite_cache = {}
        self.api = None  # True once the worker owns a loaded API.
        self.start_paused = bool(start_paused)
        self.latest_state = None
        self.latest_weapon = "무기 -"
        self.latest_action = "보통"
        self.latest_ice_acc = 0
        self.latest_dynamic = {}
        self.latest_attack_bounds = None
        self.latest_input_ticks = 0
        self.state_changed = False
        worker_side, child_side = mp.Pipe()
        self.worker_connection = worker_side
        self.worker_process = mp.Process(target=physics_worker, args=(child_side,), daemon=True)
        self.worker_process.start()
        self.records = []
        self.dynamic_records = []
        self.map_size = (1, 1)
        self.object_index = {}
        self.goal_tiles = []
        self.cleared = False
        self.custom_lmf = None
        self.tick = 0
        self.running = False
        self.loading = False
        self.held = set()
        self.saved = None
        self.generation = 0
        self.last_frame = time.perf_counter()
        self.last_draw = self.last_frame
        self.tick_accumulator = 0.0
        self.rate_started = self.last_frame
        self.rate_started_tick = 0
        self.actual_tps = 0.0
        self.last_worker_speed = 1
        self.last_status_tick = -1
        self.loaded_lmf = None
        self.snapshot_name = None
        self.world_cache_key = None
        self.world_origin = (0.0, 0.0)
        self.world_image = None
        self.step_seconds = 0.0
        self.step_samples = 0
        self.draw_seconds = 0.0
        self.draw_samples = 0
        self.runtime_status_path = self.harness / "evidence" / "playground_runtime_status.json"
        self.recent_trace_path = self.harness / "evidence" / "playground_recent_trace.jsonl"
        self.trace_buffer = []
        self.last_trace_flush_tick = 0
        self.ai_process = None
        self.last_ai_status_time = 0.0
        self.status_var = tk.StringVar(value="맵을 불러오는 중...")
        self.fixture_var = tk.StringVar(value="훈1")
        self.speed_var = tk.StringVar(value="1x")
        if initial_lmf is not None:
            self.custom_lmf = Path(initial_lmf).resolve()
            self.fixture_var.set(self.custom_lmf.stem)
        self._build_ui()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.load_fixture()
        self.root.after(16, self.loop)

    def _build_ui(self):
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill="x")
        ttk.Label(bar, text="맵").pack(side="left")
        self.fixture_box = ttk.Combobox(bar, textvariable=self.fixture_var, values=FIXTURES,
                                        width=8, state="readonly")
        self.fixture_box.pack(side="left", padx=(5, 8))
        self.fixture_box.bind("<<ComboboxSelected>>", self.select_fixture)
        ttk.Button(bar, text="불러오기", command=self.load_fixture).pack(side="left")
        ttk.Button(bar, text="LMF 열기...", command=self.open_lmf).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="초기화", command=self.reset).pack(side="left", padx=(8, 0))
        self.run_button = ttk.Button(bar, text="일시정지", command=self.toggle_run)
        self.run_button.pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="1틱", command=self.single_step).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="상태 저장", command=self.save).pack(side="left", padx=(18, 0))
        ttk.Button(bar, text="복원", command=self.restore).pack(side="left", padx=(6, 0))
        ttk.Label(bar, text="속도").pack(side="left", padx=(18, 4))
        ttk.Combobox(bar, textvariable=self.speed_var, values=("1x", "2x", "4x", "8x"),
                     width=4, state="readonly").pack(side="left")

        micro = ttk.Frame(self.root, padding=(8, 0, 8, 6))
        micro.pack(fill="x")
        ttk.Label(micro, text="미세 1틱").pack(side="left", padx=(0, 5))
        for label, keys in MICRO_INPUTS:
            ttk.Button(micro, text=label, width=5,
                       command=lambda value=keys: self.step_with(value)).pack(side="left", padx=1)
        ttk.Label(micro, text="(자동 일시정지)", foreground="#596574").pack(side="left", padx=(6, 0))
        ttk.Button(micro, text="이 맵 칼전 학습", command=self.train_combat_map).pack(side="left", padx=(18, 2))
        ttk.Button(micro, text="이 맵 깃발 학습", command=self.train_clear_map).pack(side="left", padx=2)
        ttk.Button(micro, text="학습 AI 보기", command=self.watch_combat_map).pack(side="left", padx=2)

        self.canvas = tk.Canvas(self.root, bg="#141821", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        bottom = ttk.Frame(self.root, padding=(10, 2, 10, 8))
        bottom.pack(fill="x")
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left")
        ttk.Label(bottom, text="방향키 이동/점프/구르기 · C 낙하산 · 1~4 칼 · Z 공격 · Space 기지 (F5 재생/정지)",
                  foreground="#596574").pack(side="right")
        self.canvas.bind("<Button-1>", lambda event: self.canvas.focus_set())
        self.canvas.bind("<Configure>", lambda event: self.draw())

    def _bind_keys(self):
        self.root.bind_all("<KeyPress>", self.key_down)
        self.root.bind_all("<KeyRelease>", self.key_up)

    def key_down(self, event):
        key = KEY_NAMES.get(event.keysym)
        if key and not self.loading:
            self.held.add(key)
            if self.api:
                self.worker_connection.send(("input", tuple(sorted(self.held))))
            return "break"
        if event.keysym == "F5":
            self.toggle_run()
            return "break"

    def key_up(self, event):
        key = KEY_NAMES.get(event.keysym)
        if key:
            self.held.discard(key)
            if self.api:
                self.worker_connection.send(("input", tuple(sorted(self.held))))
            return "break"

    def select_fixture(self, _event=None):
        self.custom_lmf = None

    def open_lmf(self):
        selected = filedialog.askopenfilename(
            title="LostWeapon LMF 열기",
            initialdir=str(self.maps_dir.parent),
            filetypes=(("LostWeapon Map", "*.LMF"), ("모든 파일", "*.*")),
        )
        if not selected:
            return
        self.custom_lmf = Path(selected)
        self.fixture_var.set(self.custom_lmf.stem)
        self.load_fixture()

    def train_combat_map(self):
        if not self.loaded_lmf or self.loading:
            messagebox.showerror("맵 없음", "먼저 LMF를 불러오세요.")
            return
        if self.ai_process and self.ai_process.poll() is None:
            messagebox.showinfo("학습 중", "현재 맵 학습이 이미 실행 중입니다.")
            return
        episodes = simpledialog.askinteger("현재 맵 칼전 학습", "추가 episode 수",
                                           initialvalue=20, minvalue=1, maxvalue=10000)
        if not episodes:
            return
        # Release the single-player physics capture. The dual-view trainer
        # will load this same LMF and reset its tick to zero every episode.
        self.running = False
        self.worker_connection.send(("unload",))
        self.api = None
        self.tick = 0
        self.run_button.configure(text="재생")
        command = [sys.executable, str(self.harness / "train_combat_selfplay.py"),
                   "--resume", "--episodes", str(episodes), "--max-steps", "256",
                   "--lmf", str(self.loaded_lmf)]
        self.ai_process = subprocess.Popen(command, cwd=self.harness,
                                           creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.status_var.set(f"{self.loaded_lmf.stem} 칼전 학습 준비 중 · episode마다 tick 0~256")

    def train_clear_map(self):
        if not self.loaded_lmf or self.loading:
            messagebox.showerror("맵 없음", "먼저 LMF를 불러오세요.")
            return
        if not any(tile_id == 140 for tile_id, _x, _y in self.records):
            messagebox.showerror("깃발 없음", "이 맵에는 raw140 깃발이 없습니다.")
            return
        if self.ai_process and self.ai_process.poll() is None:
            messagebox.showinfo("학습 중", "현재 학습이 이미 실행 중입니다.")
            return
        episodes = simpledialog.askinteger("현재 맵 깃발 학습", "추가 episode 수",
                                           initialvalue=50, minvalue=1, maxvalue=1000000)
        if not episodes:
            return
        self.running = False
        self.worker_connection.send(("unload",))
        self.api = None
        self.tick = 0
        self.run_button.configure(text="재생")
        checkpoint = self.harness / "checkpoints" / "map_clear_shared_dqn.pt"
        command = [sys.executable, str(self.harness / "train_local_dqn.py"),
                   str(self.harness / "private_snapshots" / "hun1_full.zip"),
                   str(self.loaded_lmf), "--episodes", str(episodes),
                   "--max-steps", "1500", "--action-repeat", "2",
                   "--checkpoint", str(checkpoint), "--resume"]
        self.ai_process = subprocess.Popen(command, cwd=self.harness,
                                           creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.status_var.set(f"{self.loaded_lmf.stem} 깃발 학습 중 · 공통 맵 두뇌에 누적")

    def watch_combat_map(self):
        if not self.loaded_lmf or self.loading:
            messagebox.showerror("맵 없음", "먼저 LMF를 불러오세요.")
            return
        checkpoint = self.harness / "checkpoints" / "combat_shared_dqn.pt"
        if not checkpoint.exists():
            messagebox.showerror("체크포인트 없음", "먼저 칼전 학습을 실행하세요.")
            return
        self.running = False
        self.worker_connection.send(("unload",))
        self.api = None
        subprocess.Popen([sys.executable.replace("python.exe", "pythonw.exe"),
                          str(self.harness / "watch_combat_ai.py"),
                          "--lmf", str(self.loaded_lmf)], cwd=self.harness,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        self.status_var.set(f"{self.loaded_lmf.stem} 학습 AI 보기 실행 중")

    def load_fixture(self):
        if self.loading:
            return
        fixture = self.fixture_var.get()
        lmf = (self.custom_lmf if self.custom_lmf and self.custom_lmf.stem == fixture
               else self.maps_dir / f"{fixture}.LMF")
        snapshot_name = ("hun1_full.zip" if self.custom_lmf
                         else SNAPSHOTS.get(fixture, "hun12_live.zip"))
        snapshot = self.harness / "private_snapshots" / snapshot_name
        if not lmf.exists() or not snapshot.exists():
            messagebox.showerror("파일 없음", f"{lmf}\n{snapshot}")
            return
        self.loading = True
        self.api = None
        self.latest_state = None
        self.running = False
        self.held.clear()
        self.saved = None
        self.generation += 1
        generation = self.generation
        self.status_var.set(f"{fixture} 원본 x86 환경 로딩 중... (수 초 걸림)")
        self.run_button.configure(text="재생")

        try:
            width, height, records = parse_lmf(lmf)
        except Exception as exc:
            self.loading = False
            self.status_var.set(f"로드 실패: {exc}")
            messagebox.showerror("로드 실패", str(exc))
            return
        self.pending_load = (generation, fixture, snapshot_name, lmf, width, height, records)
        dynamic_indices = [index for index, record in enumerate(records)
                           if record[0] in (87, 88, 95, 96, 119, 124)]
        goals = [(x, y) for tile_id, x, y in records if tile_id == 140]
        self.worker_connection.send(("load", generation, str(snapshot), str(lmf),
                                     dynamic_indices, goals))

    def finish_load(self, generation, fixture, snapshot_name, width, height, records):
        if generation != self.generation:
            return
        self.loading = False
        self.api = True
        self.loaded_lmf = (self.custom_lmf.resolve() if self.custom_lmf
                           else (self.maps_dir / f"{fixture}.LMF").resolve())
        self.snapshot_name = snapshot_name
        self.map_size = (width, height)
        self.records = records
        self.dynamic_records = [
            (index, tile_id, x, y)
            for index, (tile_id, x, y) in enumerate(records)
            if tile_id in (87, 88, 95, 96, 119, 124)
        ]
        self.world_cache_key = None
        self.object_index = {(tile_id, x, y): index for index, (tile_id, x, y) in enumerate(records)}
        self.goal_tiles = [(x, y) for tile_id, x, y in records if tile_id == 140]
        self.cleared = False
        self.tick = 0
        self.step_seconds = 0.0
        self.step_samples = 0
        self.draw_seconds = 0.0
        self.draw_samples = 0
        self.trace_buffer = []
        self.last_trace_flush_tick = 0
        self.recent_trace_path.write_text("", encoding="utf-8")
        self.running = not self.start_paused
        self.reset_clock()
        self.worker_connection.send(("running", self.running))
        self.run_button.configure(text="일시정지" if self.running else "재생")
        self.status_var.set(
            f"{fixture} · {width}x{height} · 오브젝트 {len(records):,} · 원본 x86 world-chain 실행"
        )
        self.write_runtime_status("loaded")
        self.canvas.focus_set()
        self.draw()

    def toggle_run(self):
        if not self.api or self.loading:
            return
        self.running = not self.running
        self.reset_clock()
        self.worker_connection.send(("running", self.running))
        self.run_button.configure(text="일시정지" if self.running else "재생")
        self.write_runtime_status("running" if self.running else "paused")

    def reset(self):
        if self.api and not self.loading:
            self.load_fixture()

    def single_step(self):
        if self.api and not self.loading:
            self.step_with(tuple(sorted(self.held)))

    def step_with(self, keys):
        """Run one exact Client tick with an explicit input set."""
        if not self.api or self.loading:
            return
        self.running = False
        self.run_button.configure(text="재생")
        self.worker_connection.send(("step", tuple(keys)))
        self.reset_clock()
        shown = "+".join(keys) or "NOOP"
        self.status_var.set(f"미세입력 {shown} 실행 중...")

    def save(self):
        if self.api and not self.loading:
            self.worker_connection.send(("save",))
            self.status_var.set(f"tick {self.tick} 상태 저장 중...")

    def restore(self):
        if self.api and not self.loading:
            self.worker_connection.send(("restore",))
            self.held.clear()
            self.reset_clock()

    def loop(self):
        try:
            now = time.perf_counter()
            self.poll_worker()
            if self.ai_process is not None and now - self.last_ai_status_time >= 2:
                self.last_ai_status_time = now
                status_path = self.harness / "checkpoints" / "combat_runtime_status.json"
                if status_path.exists():
                    try:
                        live = json.loads(status_path.read_text(encoding="utf-8"))
                        if time.time() - live.get("updated_at", 0) < 10:
                            self.status_var.set(
                                f"{Path(live.get('map','')).stem} 칼전 학습 · episode {live['episode']} · "
                                f"tick {live['tick']}/{live['max_steps']} · {live.get('progress_percent',0)}% · "
                                f"{live.get('tps',0)} tick/s · HP {live.get('hp')}"
                            )
                    except (OSError, json.JSONDecodeError, KeyError):
                        pass
                if self.ai_process.poll() is not None:
                    self.status_var.set(f"{self.loaded_lmf.stem} 칼전 학습 종료 · 불러오기로 직접 조작 재개")
                    self.ai_process = None
            if self.api and not self.loading:
                multiplier = int(self.speed_var.get().rstrip("x"))
                if multiplier != self.last_worker_speed:
                    self.last_worker_speed = multiplier
                    self.worker_connection.send(("speed", multiplier))
                # One worker event is one visible Client tick at 1x. Drawing it
                # immediately removes the former 30 FPS judder. Accelerated
                # modes are already coalesced by the worker to display rate.
                if self.state_changed:
                    self.last_draw = now
                    self.state_changed = False
                    self.draw()
                if self.tick // 60 != self.last_status_tick // 60:
                    self.last_status_tick = self.tick
                    self.write_runtime_status("running" if self.running else "paused")
                if self.tick - self.last_trace_flush_tick >= 60:
                    self.flush_recent_trace()
        except Exception as exc:
            self.running = False
            self.run_button.configure(text="재생")
            self.status_var.set(f"실행 중단: {exc}")
            messagebox.showerror("원본 x86 실행 오류", str(exc))
        self.root.after(8, self.loop)

    def poll_worker(self):
        while self.worker_connection.poll():
            event = self.worker_connection.recv()
            if event.get("generation") != self.generation:
                continue
            kind = event["kind"]
            if kind == "loaded":
                generation, fixture, snapshot_name, _lmf, width, height, records = self.pending_load
                self.finish_load(generation, fixture, snapshot_name, width, height, records)
            elif kind == "error":
                self.loading = False
                self.running = False
                self.api = None
                self.status_var.set(f"로드 실패: {event['error']}")
                messagebox.showerror("로드 실패", event["error"])
            elif kind == "saved":
                self.saved = True
                self.status_var.set(f"tick {event['tick']} 상태 저장됨")
            elif kind == "state":
                self.latest_state = event["state"]
                self.latest_weapon = event["weapon"]
                self.latest_action = event["action"]
                self.latest_ice_acc = event["ice_acc"]
                self.latest_dynamic = event["dynamic"]
                self.latest_attack_bounds = event.get("attack_bounds")
                self.latest_input_ticks = event.get("input_ticks", 0)
                self.tick = event["tick"]
                self.actual_tps = event["actual_tps"]
                phase = event["phase"]
                self.running = phase == "running"
                self.cleared = phase == "cleared"
                if self.cleared:
                    self.held.clear()
                    self.run_button.configure(text="재생")
                    self.status_var.set(f"{self.fixture_var.get()} CLEAR · tick {self.tick}")
                self.state_changed = True
                self.trace_buffer.append({
                    "tick": self.tick,
                    "sample_perf_ns": event.get("sample_perf_ns"),
                    "input": event.get("input", []),
                    "player": self.latest_state,
                    "ice_acceleration": self.latest_ice_acc,
                    "field_d8": event.get("field_d8"),
                    "inertia_direction": event.get("inertia_direction"),
                    "action": self.latest_action,
                })

    def flush_recent_trace(self):
        if not self.trace_buffer:
            return
        rows, self.trace_buffer = self.trace_buffer, []
        with self.recent_trace_path.open("a", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.last_trace_flush_tick = self.tick

    def reset_clock(self):
        now = time.perf_counter()
        self.last_frame = now
        self.last_draw = now
        self.tick_accumulator = 0.0
        self.rate_started = now
        self.rate_started_tick = self.tick
        self.actual_tps = 0.0

    def update_actual_tps(self, now):
        elapsed = now - self.rate_started
        if elapsed >= 0.5:
            self.actual_tps = (self.tick - self.rate_started_tick) / elapsed
            self.rate_started = now
            self.rate_started_tick = self.tick

    def write_runtime_status(self, phase):
        if not self.api or self.latest_state is None:
            return
        state = self.latest_state
        weapon, action, ice_acc = self.gameplay_status(state)
        write_json(self.runtime_status_path, {
            "ok": True,
            "phase": phase,
            "fixture": self.fixture_var.get(),
            "lmf_path": str(self.loaded_lmf) if self.loaded_lmf else None,
            "map_size": list(self.map_size),
            "record_count": len(self.records),
            "snapshot": self.snapshot_name,
            "tick": self.tick,
            "actual_tick_rate": round(self.actual_tps, 2),
            "average_native_step_ms": round(
                self.step_seconds * 1000 / self.step_samples, 3
            ) if self.step_samples else 0.0,
            "average_draw_ms": round(
                self.draw_seconds * 1000 / self.draw_samples, 3
            ) if self.draw_samples else 0.0,
            "input": sorted(self.held),
            "player": state,
            "weapon": weapon,
            "action": action,
            "ice_acceleration": ice_acc,
            "engine": "original Client x86 via Unicorn",
            "updated_unix": time.time(),
        })

    def reached_goal(self, state):
        px, py = state["x"], state["y"]
        return any(gx * 32 - 24 <= px <= gx * 32 + 32
                   and gy * 32 <= py <= gy * 32 + 64
                   for gx, gy in self.goal_tiles)

    def dynamic_c8(self, index):
        if not self.api:
            return 0
        return self.latest_dynamic.get(index, {}).get("c8", 255)

    def gameplay_status(self, state):
        return self.latest_weapon, self.latest_action, self.latest_ice_acc

    def close(self):
        try:
            self.flush_recent_trace()
            self.worker_connection.send(("close",))
            self.worker_process.join(timeout=1.0)
            if self.worker_process.is_alive():
                self.worker_process.terminate()
        finally:
            self.root.destroy()

    def draw_tile(self, tile_id, x, y, left, top, scale, index):
        x0, y0 = left + x * scale, top + y * scale
        x1, y1 = x0 + scale, y0 + scale
        fill, outline = self.COLORS.get(tile_id, ("#424b5b", "#69778c"))
        if tile_id == 49:
            self.canvas.create_rectangle(x0, y0 + scale * .32, x1, y1, fill=fill, outline=outline)
            for dx in (.2, .5, .8):
                self.canvas.create_oval(x0 + scale * (dx - .08), y0 + scale * .18,
                                        x0 + scale * (dx + .08), y0 + scale * .45, fill=outline, outline="")
        elif tile_id in (27, 37):
            points = (x0, y1, x1, y1, x1, y0) if tile_id == 27 else (x0, y0, x0, y1, x1, y1)
            self.canvas.create_polygon(*points, fill=fill, outline=outline)
        elif tile_id == 3:
            self.canvas.create_line(x0 + scale * .3, y0, x0 + scale * .3, y1, fill=outline, width=3)
            self.canvas.create_line(x0 + scale * .7, y0, x0 + scale * .7, y1, fill=outline, width=3)
            for fraction in (.2, .5, .8):
                self.canvas.create_line(x0 + scale * .3, y0 + scale * fraction,
                                        x0 + scale * .7, y0 + scale * fraction, fill=fill, width=3)
        elif tile_id == 123:
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="")
            self.canvas.create_arc(x0, y0 - scale * .15, x1, y0 + scale * .35,
                                   start=0, extent=180, style="arc", outline=outline, width=2)
        elif tile_id == 124:
            c8 = self.dynamic_c8(index)
            if c8 < 255:
                shade = "#d6b13b" if c8 < 128 else "#806d38"
                self.canvas.create_rectangle(x0, y0, x1, y1, fill=shade, outline=outline, width=2)
                self.canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=str(c8), fill="#171717",
                                        font=("Segoe UI", max(7, int(scale * .25)), "bold"))
        elif tile_id == 119:
            info = self.latest_dynamic.get(index, {})
            extended = info.get("animation") == 17
            if extended:
                self.canvas.create_rectangle(x0, y0, x1, y1, fill="#8f1722",
                                             outline="#ff6b78", width=2)
                for fraction in (.2, .5, .8):
                    cx = x0 + scale * fraction
                    self.canvas.create_polygon(cx - scale * .12, y1, cx, y0,
                                               cx + scale * .12, y1,
                                               fill="#eceff4", outline="#ff6b78")
            else:
                self.canvas.create_rectangle(x0, y1 - max(3, scale * .12), x1, y1,
                                             fill="#56606f", outline="#8994a4")
        elif tile_id in (100, 140):
            label = "S" if tile_id == 100 else "G"
            self.canvas.create_oval(x0 + scale * .18, y0 + scale * .18, x1 - scale * .18,
                                    y1 - scale * .18, fill=fill, outline=outline, width=2)
            self.canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=label, fill="#142018",
                                    font=("Segoe UI", max(8, int(scale * .34)), "bold"))
        else:
            self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline)
            if tile_id not in (7,):
                labels = {4: "↑", 5: "↗", 6: "↖", 51: "F", 52: "↓M", 53: "↑M", 54: "M→", 55: "←M"}
                self.canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                                        text=labels.get(tile_id, str(tile_id)), fill="#111923",
                                        font=("Segoe UI", max(7, int(scale * .28)), "bold"))

    def build_map_image(self, width, height, scale):
        """Rasterize immutable LMF records into one Tk image.

        Thousands of individual Canvas items make Tk repaint the entire item
        tree even when Python only changes the player overlay. A binary PPM is
        fast to build, needs no external image package, and paints as one item.
        """
        pixel_scale = int(scale)
        image_w, image_h = width * pixel_scale, height * pixel_scale
        background = bytes.fromhex("202634")
        pixels = bytearray(background * (image_w * image_h))

        def rgb(hex_color):
            return bytes.fromhex(hex_color.lstrip("#"))

        def fill_span(y, x0, x1, color):
            if not (0 <= y < image_h):
                return
            x0, x1 = max(0, x0), min(image_w, x1)
            if x0 >= x1:
                return
            start = (y * image_w + x0) * 3
            pixels[start:start + (x1 - x0) * 3] = color * (x1 - x0)

        def sprite(tile_id):
            cache_key = (tile_id, pixel_scale)
            if cache_key in self.sprite_cache:
                return self.sprite_cache[cache_key]
            entry = self.tile_registry.get(str(tile_id))
            if not entry:
                self.sprite_cache[cache_key] = None
                return None
            path = self.harness.parent / "analysis" / f"bitmap_{entry['bitmap_resource_id']}.bmp"
            if not path.exists():
                self.sprite_cache[cache_key] = None
                return None
            raw = path.read_bytes()
            offset = struct.unpack_from("<I", raw, 10)[0]
            source_w, source_h = struct.unpack_from("<ii", raw, 18)
            bpp = struct.unpack_from("<H", raw, 28)[0]
            compression = struct.unpack_from("<I", raw, 30)[0]
            if bpp != 24 or compression != 0 or source_w <= 0 or source_h == 0:
                self.sprite_cache[cache_key] = None
                return None
            flipped = source_h > 0
            source_h = abs(source_h)
            stride = (source_w * 3 + 3) & ~3
            result = []
            for dy in range(pixel_scale):
                sy = min(source_h - 1, dy * source_h // pixel_scale)
                file_y = source_h - 1 - sy if flipped else sy
                row = offset + file_y * stride
                output_row = []
                for dx in range(pixel_scale):
                    sx = min(source_w - 1, dx * source_w // pixel_scale)
                    blue, green, red = raw[row + sx * 3:row + sx * 3 + 3]
                    # Editor bitmaps use magenta as their transparent key.
                    output_row.append(None if red > 240 and blue > 240 and green < 32
                                      else bytes((red, green, blue)))
                result.append(output_row)
            self.sprite_cache[cache_key] = result
            return result

        for tile_id, x, y in self.records:
            if tile_id in (87, 88, 95, 96, 119, 124):  # live native overlays
                continue
            tile_sprite = sprite(tile_id)
            if tile_sprite is not None:
                x0, y0 = x * pixel_scale, y * pixel_scale
                for row, colors in enumerate(tile_sprite):
                    target_y = y0 + row
                    if not (0 <= target_y < image_h):
                        continue
                    for column, color in enumerate(colors):
                        target_x = x0 + column
                        if color is None or not (0 <= target_x < image_w):
                            continue
                        start = (target_y * image_w + target_x) * 3
                        pixels[start:start + 3] = color
                continue
            fill, outline = self.COLORS.get(tile_id, ("#424b5b", "#69778c"))
            fill_color, outline_color = rgb(fill), rgb(outline)
            x0, y0 = x * pixel_scale, y * pixel_scale
            for row in range(pixel_scale):
                if tile_id == 27:
                    begin = x0 + pixel_scale - row - 1
                elif tile_id == 37:
                    begin = x0
                else:
                    begin = x0
                end = x0 + (row + 1 if tile_id == 37 else pixel_scale)
                color = outline_color if row in (0, pixel_scale - 1) else fill_color
                fill_span(y0 + row, begin, end, color)
        ppm = f"P6\n{image_w} {image_h}\n255\n".encode("ascii") + pixels
        return tk.PhotoImage(data=ppm, format="PPM")

    def draw(self):
        draw_started = time.perf_counter()
        if not self.api:
            self.canvas.delete("all")
            self.canvas.create_text(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2,
                                    text="원본 Client 상태를 불러오는 중...", fill="#dce6f2",
                                    font=("Segoe UI", 18, "bold"))
            return
        width, height = self.map_size
        state = self.latest_state
        if state is None:
            return
        weapon, action, ice_acc = self.gameplay_status(state)
        canvas_w, canvas_h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        fit_scale = min((canvas_w - 50) / width, (canvas_h - 70) / height)
        if fit_scale >= 10:
            scale = fit_scale
        else:
            # Large custom maps use a player-following camera instead of
            # shrinking every tile to an unreadable dot.
            scale = 16.0
        # Keep the cached raster bounded even for very tall user maps. Integer
        # scale also prevents image filtering and keeps tile edges exact.
        max_pixels = 12_000_000
        if width * height * scale * scale > max_pixels:
            scale = max(4.0, (max_pixels / (width * height)) ** 0.5)
        scale = float(max(4, int(scale)))
        if fit_scale >= 10:
            left = (canvas_w - width * scale) / 2
            top = (canvas_h - height * scale) / 2 + 15
        else:
            left = canvas_w / 2 - state["x"] / 32.0 * scale
            top = canvas_h / 2 - state["y"] / 32.0 * scale
            left = min(20.0, max(canvas_w - width * scale - 20.0, left))
            top = min(35.0, max(canvas_h - height * scale - 20.0, top))
        min_x, max_x = (-left / scale - 1, (canvas_w - left) / scale + 1)
        min_y, max_y = (-top / scale - 1, (canvas_h - top) / scale + 1)
        # Static map geometry used to be deleted and recreated on every frame.
        # A 1,784-record map then spent far more time in thousands of Tk calls
        # than in the native physics. Build it once and move the canvas group as
        # the camera follows the player. Tile 124 remains an overlay because its
        # visibility depends on live Client state.
        world_key = (id(self.records), width, height, round(scale, 5))
        if world_key != self.world_cache_key:
            self.canvas.delete("all")
            self.world_image = self.build_map_image(width, height, scale)
            self.canvas.create_image(left, top, image=self.world_image, anchor="nw",
                                     tags=("world",))
            self.world_cache_key = world_key
            self.world_origin = (left, top)
        else:
            dx, dy = left - self.world_origin[0], top - self.world_origin[1]
            if dx or dy:
                self.canvas.move("world", dx, dy)
                self.world_origin = (left, top)

        self.canvas.delete("overlay")
        for index, tile_id, x, y in self.dynamic_records:
            info = self.latest_dynamic.get(index, {})
            if info.get("special"):
                x = (info["x"] - 16.0) / 32.0
                y = (info["y"] + 1.0) / 32.0
            if min_x <= x <= max_x and min_y <= y <= max_y:
                before = set(self.canvas.find_all())
                self.draw_tile(tile_id, x, y, left, top, scale, index)
                for item in set(self.canvas.find_all()) - before:
                    self.canvas.addtag_withtag("overlay", item)
        px = left + state["x"] / 32.0 * scale
        py = top + state["y"] / 32.0 * scale
        half_w = scale * .5
        crouching = state["c0"] == 1 or state["38"] == 6
        player_h = scale * (49 if crouching else 60) / 32
        self.canvas.create_rectangle(px - half_w, py - player_h, px + half_w, py,
                                     fill="#f5f7fb", outline="#22d3ee", width=3,
                                     tags=("overlay",))
        if action == "공격" and self.latest_attack_bounds:
            x0, y0, x1, y1 = self.latest_attack_bounds
            ax0, ax1 = sorted((left + x0 / 32.0 * scale, left + x1 / 32.0 * scale))
            ay0, ay1 = sorted((top + y0 / 32.0 * scale, top + y1 / 32.0 * scale))
            self.canvas.create_rectangle(ax0, ay0, ax1, ay1, outline="#ff9f43",
                                         width=3, dash=(6, 3), tags=("overlay",))
            self.canvas.create_text(ax0, ay0 - 3, anchor="sw", text="공격 프레임 범위",
                                    fill="#ffbd73", font=("Segoe UI", 9, "bold"),
                                    tags=("overlay",))
        # b0 is the persistent body-facing flag. 0x74 is the current movement/
        # input direction and deliberately points opposite during a back roll.
        facing_right = state["b0"] == 0
        eye_x = px + (half_w * .45 if facing_right else -half_w * .45)
        self.canvas.create_oval(eye_x - 2, py - player_h * .72 - 2, eye_x + 2,
                                py - player_h * .72 + 2, fill="#10202b", outline="",
                                tags=("overlay",))
        keys = "+".join(sorted(self.held)) or "NOOP"
        held_ticks = f" ({self.latest_input_ticks}틱)" if self.held else ""
        self.canvas.create_text(12, 10, anchor="nw", fill="#dce6f2",
                                text=(f"tick {self.tick}   {self.actual_tps:.1f} tick/s   input {keys}{held_ticks}   "
                                      f"x {state['x']:.3f}  y {state['y']:.3f}  motion {state['motion58']:.0f}  "
                                      f"state {state['38']}  facing {'>' if facing_right else '<'}"),
                                font=("Consolas", 11, "bold"), tags=("overlay",))
        self.canvas.create_text(12, 32, anchor="nw", fill="#78e6d0",
                                text=f"{weapon}   {action}   얼음 관성 {ice_acc}",
                                font=("Segoe UI", 11, "bold"), tags=("overlay",))
        if self.cleared:
            self.canvas.create_text(canvas_w / 2, 55, text="CLEAR", fill="#fff37a",
                                    font=("Segoe UI", 34, "bold"), tags=("overlay",))
        self.draw_seconds += time.perf_counter() - draw_started
        self.draw_samples += 1


def main():
    mp.freeze_support()
    if "--self-test" in sys.argv:
        index = sys.argv.index("--self-test")
        output = (Path(sys.argv[index + 1]) if index + 1 < len(sys.argv)
                  else Path.cwd() / "native_playground_self_test.json")
        raise SystemExit(run_self_test(output))
    timer_period_set = False
    if sys.platform == "win32":
        timer_period_set = ctypes.windll.winmm.timeBeginPeriod(1) == 0
    try:
        initial_lmf = None
        if "--map" in sys.argv:
            index = sys.argv.index("--map")
            if index + 1 < len(sys.argv):
                initial_lmf = sys.argv[index + 1]
        root = tk.Tk()
        Playground(root, initial_lmf=initial_lmf, start_paused="--paused" in sys.argv)
        root.mainloop()
    finally:
        if timer_period_set:
            ctypes.windll.winmm.timeEndPeriod(1)


if __name__ == "__main__":
    main()
