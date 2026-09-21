"""Persistent offline native search. No API calls, neural model, or live key output.

Learn an archive of reachable states, reusable action candidates and their results.
Archive bins guide exploration; they NEVER certify two native worlds equivalent.
Every branch is restored in native memory and every saved best route is replayed.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
DEFAULT_OUT = ROOT / "checkpoints/local_physics_v1"
VERSION = 1


class TimeSliceComplete(Exception):
    pass


def learning_progress(path):
    """Read committed data, not a potentially stale summary file."""
    if not path.exists():
        return {"trials": 0, "best": None, "stale": 0}
    db = sqlite3.connect(path.resolve().as_uri()+"?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT result FROM trials WHERE mode='search' ORDER BY id DESC").fetchall()
        stale = 0
        for (raw,) in rows:
            if json.loads(raw).get("improved"):
                break
            stale += 1
        raw = db.execute("SELECT value FROM meta WHERE key='best'").fetchone()
        best = sum(n for a, n in json.loads(raw[0])["actions"]) if raw else None
        return {"trials": len(rows), "best": best, "stale": stale}
    finally:
        db.close()


def adaptive_budget(stats, normal):
    if stats["best"] is None or stats["stale"] < 160:
        return normal
    if stats["stale"] < 400:
        return min(normal, max(8, normal//2))
    return min(normal, max(8, normal//5))


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def pack(actions):
    out = []
    for a in actions:
        if out and out[-1][0] == a:
            out[-1][1] += 1
        else:
            out.append([a, 1])
    return out


def unpack(rows):
    return [int(a) for a, n in rows for _ in range(int(n))]


def emit(**row):
    print(encode(row), flush=True)


class Store:
    def __init__(self, path, identity):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS nodes(
                key TEXT PRIMARY KEY, route TEXT, state TEXT, steps INTEGER,
                distance REAL, attempts INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS contexts(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS skills(
                context TEXT, family TEXT, n INTEGER, value REAL,
                PRIMARY KEY(context, family));
            CREATE TABLE IF NOT EXISTS trials(
                id INTEGER PRIMARY KEY, time REAL, mode TEXT, reason TEXT,
                result TEXT);
        """)
        old = self.get("identity")
        if old is not None and old != identity:
            self.db.close()
            raise ValueError("Map/physics/action schema changed. Use a new --out folder; old data retained.")
        self.put("identity", identity)
        self.db.commit()

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, encode(value)))

    def count(self):
        return self.db.execute("SELECT count(*) FROM trials WHERE mode='search'").fetchone()[0]

    def record(self, mode, result):
        self.db.execute("INSERT INTO trials(time,mode,reason,result) VALUES (?,?,?,?)",
                        (time.time(), mode, result["reason"], encode(result)))

    def add_node(self, state, actions, distance, max_nodes):
        # Diversity buckets, not a Markov state or a lookup-based controller.
        key = encode([int(state["x"] // 16), int(state["y"] // 16),
                      *[state.get(k) for k in ("38", "3c", "68", "74", "b0", "c0", "dc")]])
        old = self.db.execute("SELECT steps FROM nodes WHERE key=?", (key,)).fetchone()
        if old and old[0] <= len(actions):
            return False
        if not old and self.db.execute("SELECT count(*) FROM nodes").fetchone()[0] >= max_nodes:
            return False
        self.db.execute("""INSERT INTO nodes(key,route,state,steps,distance) VALUES (?,?,?,?,?)
            ON CONFLICT(key) DO UPDATE SET route=excluded.route,state=excluded.state,
                steps=excluded.steps,distance=excluded.distance""",
                        (key, encode(pack(actions)), encode(state), len(actions), distance))
        return old is None

    def choose_node(self, rng):
        # Distance is only one scheduling mode. Detours remain explorable.
        if rng.random() < .25:
            rows = self.db.execute("SELECT key,route FROM nodes ORDER BY distance,attempts LIMIT 64").fetchall()
        else:
            rows = self.db.execute("SELECT key,route FROM nodes ORDER BY attempts,steps LIMIT 256").fetchall()
        key, route = rng.choice(rows)
        self.db.execute("UPDATE nodes SET attempts=attempts+1 WHERE key=?", (key,))
        return key, unpack(json.loads(route))

    def learn(self, context, family, value):
        self.db.execute("""INSERT INTO skills VALUES (?,?,1,?)
            ON CONFLICT(context,family) DO UPDATE SET
            value=(skills.value*skills.n+excluded.value)/(skills.n+1),n=skills.n+1""",
                        (context, family, value))

    def summary(self):
        best = self.get("best")
        return {"search_trials": self.count(),
                "archive_states": self.db.execute("SELECT count(*) FROM nodes").fetchone()[0],
                "learned_context_skills": self.db.execute("SELECT count(*) FROM skills").fetchone()[0],
                "best_decisions": len(unpack(best["actions"])) if best else None,
                "failure_counts": dict(self.db.execute(
                    "SELECT reason,count(*) FROM trials WHERE mode='search' GROUP BY reason")),
                "goal_evidence": "offline_x86_goal_region_not_client_event",
                "reset_detection": "position_discontinuity_heuristic"}


def programs(rng, actions, horizon):
    """A vocabulary of inputs and compositions, never terrain->mandatory key rules."""
    idx = {tuple(keys): i for i, keys in enumerate(actions)}
    result = []
    def add(name, phases):
        result.append((name, phases))
    for i in range(len(actions)):
        add("primitive_" + str(i), [(i, min(horizon, rng.choice((4, 8, 16, 24))))])
    for direction, other in (("LEFT", "RIGHT"), ("RIGHT", "LEFT")):
        walk = idx[(direction,)]
        jump = idx[(direction, "UP")]
        roll = idx[(direction, "DOWN")]
        launch = rng.choice((1, 2, 4, 6, 8))
        duration = rng.choice((8, 12, 16, 24))
        add(direction + "_jump_roll", [(jump, launch), (0, 1), (roll, duration), (walk, 8)])
        add(direction + "_turn_roll", [(idx[(other,)], 1), (0, 1), (roll, duration)])
        add(direction + "_roll_chute", [(roll, launch), ("chute_" + direction, 24)])
        add(direction + "_jump_roll_chute", [(jump, launch), (0, 1), (roll, launch),
                                              ("chute_" + direction, 24)])
        add(direction + "_turn_roll_chute", [(idx[(other,)], 1), (0, 1),
                                              (roll, launch), ("chute_" + direction, 24)])
        for weapon in ("1", "2", "3", "4"):
            # Three Z presses separated by releases; vary spacing across trials.
            gap = rng.choice((2, 4, 8, 12))
            add(direction + "_weapon" + weapon + "_attack_jump",
                [(idx[(weapon,)], 1), (walk, 1), (idx[("Z",)], gap), (0, 1),
                 (idx[("Z",)], gap), (0, 1), (idx[("Z",)], gap), (jump, 8),
                 ("chute_" + direction, 12)])
    # Open-ended composition keeps candidates beyond the named templates reachable.
    for i in range(8):
        add("compose_" + str(i), [(rng.randrange(len(actions)), rng.choice((1, 2, 4, 8, 16)))
                                  for _ in range(rng.randint(2, 6))])
    return result


class Search:
    def __init__(self, env, store, args):
        from native_env import ACTIONS
        self.env, self.store, self.args, self.actions = env, store, args, ACTIONS
        self.rng = random.Random(args.seed + store.count())
        self.start = env.api.read_state()
        self.initial = env.api.save_state()
        self.last_heartbeat = 0.0
        self.ticks = 0
        self.deadline = time.monotonic() + args.minutes_per_map * 60
        session_end = getattr(args, "session_end", 0)
        if session_end:
            self.deadline = min(self.deadline, time.monotonic()+max(0, session_end-time.time()))
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.cache_hits = 0
        self.guide = None
        guide_path = getattr(args, "guide_model", None)
        if guide_path and guide_path.exists():
            from shared_physics_model import CandidateGuide
            self.guide = CandidateGuide(guide_path)
            emit(phase="shared_guide_loaded", map=args.map.stem, model=str(guide_path))

    def check(self):
        if self.args.stop_file.exists():
            raise InterruptedError("stop marker")
        if time.monotonic() >= self.deadline:
            raise TimeSliceComplete()
        now = time.monotonic()
        if now - self.last_heartbeat >= 10:
            emit(phase="working", map=self.args.map.stem, search_trials=self.store.count(),
                 native_ticks=self.ticks)
            self.last_heartbeat = now

    def restore(self, snapshot):
        self.env.api.restore_state(snapshot)
        # Every tick below passes explicit keys; no Python input latch leaks branches.

    def remember(self, route, state):
        if not route:
            return
        key = tuple(route)
        if key in self.cache:
            self.cache.move_to_end(key)
            return
        snapshot = self.env.api.save_state()
        size = sum(len(page) for page in snapshot.get("pages", {}).values())
        limit = self.args.cache_mb * 1024 * 1024
        if size > limit:
            return
        while self.cache and (self.cache_bytes + size > limit or len(self.cache) >= 64):
            _, (_, _, old_size) = self.cache.popitem(last=False)
            self.cache_bytes -= old_size
        self.cache[key] = (snapshot, state, size)
        self.cache_bytes += size

    def reach_prefix(self, route):
        self.check()
        cached = self.cache.get(tuple(route))
        if cached:
            self.cache_hits += 1
            self.cache.move_to_end(tuple(route))
            self.restore(cached[0])
            return cached[1], route, "ok"
        ancestors = [key for key in self.cache if len(key) < len(route)
                     and tuple(route[:len(key)]) == key]
        if ancestors:
            key = max(ancestors, key=len)
            snapshot, state, _ = self.cache[key]
            self.cache.move_to_end(key)
            self.restore(snapshot)
            self.cache_hits += 1
            actual = list(key)
            for a in route[len(key):]:
                if a not in self.env.valid_action_indices(state):
                    return state, actual, "masked_replay"
                state, reason = self.step(a, state)
                actual.append(a)
                if reason != "ok":
                    return state, actual, reason
            self.remember(actual, state)
            return state, actual, "ok"
        state, actual, reason = self.replay(route)
        if reason == "ok":
            self.remember(actual, state)
        return state, actual, reason

    def step(self, action, previous):
        self.check()
        state = previous
        for _ in range(2):
            state = self.env.api.step(1, self.actions[action])
            self.ticks += 1
            if not all(math.isfinite(float(state[k])) for k in ("x", "y", "motion58")):
                return state, "invalid_state"
            jump = math.hypot(state["x"] - previous["x"], state["y"] - previous["y"])
            before = math.hypot(previous["x"] - self.start["x"], previous["y"] - self.start["y"])
            after = math.hypot(state["x"] - self.start["x"], state["y"] - self.start["y"])
            if jump >= 64 and before >= 64 and after <= 48:
                return state, "reset_suspected"
            if not (-64 <= state["x"] <= self.env.width * 32 + 64 and
                    -256 <= state["y"] <= self.env.height * 32 + 128):
                return state, "out_of_bounds"
            previous = state
        return state, "goal_region" if self.env.reached_goal(state) else "ok"

    def replay(self, route, collect=False):
        self.restore(self.initial)
        state = self.env.api.read_state()
        done = []
        for a in route:
            if a not in self.env.valid_action_indices(state):
                return state, done, "masked_replay"
            state, reason = self.step(a, state)
            done.append(a)
            if collect and reason in ("ok", "goal_region") and len(done) % 8 == 0:
                self.store.add_node(state, done, self.env._goal_distance(state), self.args.max_nodes)
                if reason == "ok":
                    self.remember(done, state)
            if reason != "ok":
                return state, done, reason
        return state, done, "ok"

    def context(self, state, route):
        view = self.env.navigation_view(state, size=9)
        px, py = view["player_tile"]
        # Preserve individual IDs rather than native_env's OR-packed object identity.
        objects = sorted((t, x-px, y-py) for t, x, y in self.env.records
                         if abs(x-px) <= 4 and abs(y-py) <= 4)
        feature = {"player": {k: v for k, v in state.items() if k not in ("x", "y")},
                   "subcell": [round(state["x"] % 32, 1), round(state["y"] % 32, 1)],
                   "held": self.actions[route[-1]] if route else (),
                   "grid": [[c["grids"] for c in row] for row in view["cells"]],
                   "objects": objects,
                   "goal_delta": [view["goal_tile"][0]-px, view["goal_tile"][1]-py]}
        key = digest(feature)
        self.store.db.execute("INSERT OR IGNORE INTO contexts VALUES (?,?)", (key, encode(feature)))
        return key

    def execute(self, phases, state, budget):
        taken, samples = [], []
        reason = "ok"
        stalled = 0
        observations = []
        self.last_observations = observations
        for spec, duration in phases:
            for phase_tick in range(duration):
                if len(taken) >= budget:
                    return state, taken, samples, "horizon"
                allowed = self.env.valid_action_indices(state)
                if isinstance(spec, str):
                    direction = spec.split("_", 1)[1]
                    walk = self.actions.index((direction,))
                    chute = self.actions.index((direction, "C"))
                    # Pulse deploy attempts only while closed; native state/mask decides.
                    a = chute if not state.get("dc") and phase_tick % 2 == 0 else walk
                else:
                    a = spec
                a = a if a in allowed else 0
                previous = state
                state, reason = self.step(a, previous)
                taken.append(a)
                samples.append(state)
                if len(taken) % 8 == 0 and reason not in ("invalid_state", "out_of_bounds"):
                    # Read local native grids throughout the trajectory, not just at launch.
                    observations.append({"offset": len(taken),
                        "context": self.context(state, taken),
                        "displacement_per_tick": [(state["x"]-previous["x"])/2,
                                                   (state["y"]-previous["y"])/2]})
                stalled = stalled + 1 if state == previous else 0
                if reason != "ok":
                    return state, taken, samples, reason
                if stalled >= 16:
                    return state, taken, samples, "stalled"
        return state, taken, samples, "horizon"

    def accept_goal(self, route):
        best = self.store.get("best")
        if best and len(route) >= len(unpack(best["actions"])):
            return False
        state, actual, reason = self.replay(route)
        result = {"reason": reason, "decisions": len(actual), "source": "clean_reset_replay"}
        self.store.record("verification", result)
        if reason != "goal_region":
            return False
        self.store.put("best", {"actions": pack(actual), "state": state,
                                "evidence": "offline_x86_goal_region", "updated": time.time()})
        emit(phase="new_best", map=self.args.map.stem, decisions=len(actual),
             evidence="offline_x86_goal_region")
        return True

    def seed(self):
        from train_rule_helper import best_recorded_route, legacy_physics_seed
        from training_archive import sha256_file
        if self.store.get("seed_import_done"):
            return
        sha = sha256_file(self.args.map)
        paths = [ROOT / "checkpoints/route_curriculum" / (self.args.map.stem + ".episodes.jsonl")]
        if self.args.map.stem == "훈1":
            paths.append(ROOT / "checkpoints/route_rule_helper.episodes.jsonl")
        routes = [best_recorded_route(p, sha) for p in paths]
        routes.append(legacy_physics_seed(ROOT / "checkpoints/physics_route_library.json", sha))
        imported = set(self.store.get("imported_seeds", []))
        for seed in sorted((r for r in routes if r), key=lambda r: r["steps"]):
            if len(seed["actions"]) > self.args.max_steps:
                continue
            signature = digest(seed["actions"])
            if signature in imported:
                continue
            state, taken, reason = self.replay(seed["actions"], collect=True)
            self.store.record("seed", {"reason": reason, "decisions": len(taken)})
            if reason == "goal_region":
                self.accept_goal(taken)
            imported.add(signature)
            self.store.put("imported_seeds", sorted(imported))
            self.store.db.commit()
        self.store.put("seed_import_done", True)
        self.store.db.commit()

    def trial(self):
        best = self.store.get("best")
        # Improve existing routes while leaving most trials for independent exploration.
        full = None
        if best and self.rng.random() < (.65 if getattr(self.args, "adaptive", False) else .35):
            full = unpack(best["actions"])
            prefix = full[:self.rng.randrange(len(full))]
            source = "best_prefix"
        else:
            source, prefix = self.store.choose_node(self.rng)
        state, prefix, reason = self.reach_prefix(prefix)
        if reason != "ok":
            if reason == "goal_region":
                self.accept_goal(prefix)
            else:
                self.store.db.execute("DELETE FROM nodes WHERE key=?", (source,))
            self.store.record("search", {"reason": reason, "source": "prefix_replay"})
            self.store.db.commit()
            return
        root_state = state
        snapshot = self.env.api.save_state()
        context = self.context(state, prefix)
        vocabulary = programs(self.rng, self.actions, self.args.horizon)
        learned = dict((f, (n, v)) for f, n, v in self.store.db.execute(
            "SELECT family,n,value FROM skills WHERE context=?", (context,)))
        self.rng.shuffle(vocabulary)
        total = sum(n for n, _ in learned.values()) + 1
        guide_scores = {}
        if self.guide:
            raw = self.store.db.execute("SELECT value FROM contexts WHERE key=?", (context,)).fetchone()[0]
            predicted = self.guide.scores(json.loads(raw), vocabulary,
                                          min(self.args.horizon, self.args.max_steps-len(prefix)))
            guide_scores = {family: score for (family, _), score in zip(vocabulary, predicted)
                            if score is not None}
        def priority(item):
            n, value = learned.get(item[0], (0, 0.0))
            direction = "RIGHT" if self.env._nearest_goal(state)[0]*32 >= state["x"] else "LEFT"
            # A small prior only orders trials; opposite-direction detours remain sampled.
            if item[0] in guide_scores:
                return guide_scores[item[0]] + .25*(direction in item[0])
            if self.guide:
                return .25*(direction in item[0]) + .1/(n+1)
            return value + 5 * math.sqrt(math.log(total + 1) / (n + 1)) + .25*(direction in item[0])
        # Half random candidates prevents a learned prior from removing techniques.
        count = self.args.candidates
        selected = sorted(vocabulary, key=priority, reverse=True)[:max(1, count//2)]
        remaining = [p for p in vocabulary if p not in selected]
        selected += self.rng.sample(remaining, min(count-len(selected), len(remaining)))
        if full:
            # Route shortening is an explicit experiment, always replay-verified.
            skip = self.rng.randint(1, min(12, len(full)-len(prefix)))
            selected[-1] = ("shortcut_existing_route", [(a, 1) for a in full[len(prefix)+skip:]])
            if getattr(self.args, "adaptive", False) and len(selected) >= 2:
                # Replace a short segment, then retain the successful continuation.
                replacement = self.rng.choice(self.env.valid_action_indices(root_state))
                duration = self.rng.randint(1, min(4, skip))
                selected[-2] = ("repair_existing_route", [(replacement, duration)] +
                                [(a, 1) for a in full[len(prefix)+skip:]])
        for family, phases in selected:
            if self.store.count() >= self.args.target_trials:
                break
            self.restore(snapshot)
            budget = min(self.args.horizon, self.args.max_steps-len(prefix))
            if family in ("shortcut_existing_route", "repair_existing_route"):
                budget = self.args.max_steps-len(prefix)
            end, suffix, samples, reason = self.execute(phases, root_state, budget)
            route = prefix + suffix
            if suffix and reason in ("horizon", "stalled"):
                self.remember(route, end)
            novel = 0
            # Unsafe tail isn't archived; earlier native-safe prefixes remain useful.
            for i, s in enumerate(samples):
                if i == len(samples)-1 and reason not in ("horizon", "stalled", "goal_region"):
                    continue
                if (i+1) % 8 == 0 or i == len(samples)-1:
                    if len(prefix)+i+1 < self.args.max_steps and not self.env.reached_goal(s):
                        novel += self.store.add_node(s, prefix+suffix[:i+1],
                                                     self.env._goal_distance(s), self.args.max_nodes)
            improvement = self.accept_goal(route) if reason == "goal_region" else False
            reward = min(5, novel) - .02*len(suffix)
            if reason == "goal_region":
                reward += 100 + (20 if improvement else 0)
            if reason in ("reset_suspected", "out_of_bounds", "invalid_state"):
                reward -= 100
            self.store.learn(context, family, reward)
            self.store.record("search", {"reason": reason, "family": family,
                "context": context, "prefix": pack(prefix), "actions": pack(suffix),
                "before": root_state, "after": end, "new_states": novel,
                "observations": self.last_observations,
                "planned_phases": phases, "plan_budget": budget,
                "guide_score": guide_scores.get(family),
                "reward": reward, "improved": improvement})
            self.store.db.commit()
            emit(phase="candidate", map=self.args.map.stem, trial=self.store.count(),
                 family=family, result=reason, new_states=novel,
                 best=self.store.summary()["best_decisions"])


def atomic_json(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def worker(args):
    from native_env import LostWeaponEnv, ACTIONS
    from snapshot_selector import snapshot_for_map
    from training_archive import physics_fingerprint, sha256_file
    identity = {"version": VERSION, "map": sha256_file(args.map),
                "physics": physics_fingerprint(ROOT), "actions": ACTIONS,
                "environment": sha256_file(ROOT / "native_env.py"), "ticks_per_decision": 2}
    identity = json.loads(encode(identity))
    store = Store(args.out / (args.map.stem + ".sqlite3"), identity)
    search = None
    state = "running"
    try:
        if store.count() >= args.target_trials and not args.preflight:
            state = "budget_complete"
            return
        emit(phase="loading", map=args.map.stem)
        env = LostWeaponEnv(snapshot_for_map(ROOT, args.map), args.map, max_steps=args.max_steps)
        search = Search(env, store, args)
        store.add_node(search.start, [], env._goal_distance(search.start), args.max_nodes)
        store.db.commit()
        # Verify branch isolation at a non-initial state, including a distracting branch.
        allowed = env.valid_action_indices(search.start)
        a = 2 if 2 in allowed else 0
        middle, _ = search.step(a, search.start)
        branch = env.api.save_state()
        expected, why = search.step(0, middle)
        search.step(a, expected)
        search.restore(branch)
        observed, why2 = search.step(0, middle)
        if expected != observed or why != why2:
            raise RuntimeError("Native branch restore mismatch; training refused")
        search.restore(search.initial)
        if args.preflight:
            store.put("branch_check", "player_state_replay_equal")
            emit(phase="preflight_pass", map=args.map.stem,
                 check="load_native_map_and_branch_replay")
            state = "preflight_pass"
            return
        search.seed()
        initial_count = store.count()
        while store.count() < args.target_trials:
            search.check()
            search.trial()
        state = "budget_complete" if store.count() >= args.target_trials else "time_slice_complete"
        emit(phase="map_end", map=args.map.stem, new_trials=store.count()-initial_count,
             **store.summary())
    except TimeSliceComplete:
        store.db.rollback()
        state = "time_slice_complete"
    except (KeyboardInterrupt, InterruptedError):
        store.db.rollback()
        state = "stopped"
    except Exception as exc:
        store.db.rollback()
        state = "error"
        store.put("last_error", repr(exc))
        raise
    finally:
        store.put("state", state)
        store.db.commit()
        report = {"map": args.map.stem, "state": state, **store.summary()}
        if search:
            report.update(native_ticks_this_session=search.ticks,
                          snapshot_cache_hits=search.cache_hits,
                          snapshot_cache_bytes=search.cache_bytes)
        atomic_json(args.out / (args.map.stem + ".summary.json"), report)
        best = store.get("best")
        if best:
            atomic_json(args.out / (args.map.stem + ".best.json"), best)
        store.db.close()


def report(out):
    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(out.glob("*.summary.json"))]
    text = ["# 로컬 물리 탐색 결과", "", "오프라인 원본 x86의 목표 영역 도달 기록입니다. 실제 Client 클리어/새 맵 일반화 성적이 아닙니다.",
            "", "|맵|상태|누적 후보 시험|도달 상태|최선 결정 수|", "|---|---|---:|---:|---:|"]
    for row in rows:
        text.append(f"|{row['map']}|{row['state']}|{row['search_trials']}|{row['archive_states']}|{row['best_decisions']}|")
    text += ["", "## 실패/종료 사유", ""]
    for row in rows:
        text.append(f"- {row['map']}: {encode(row['failure_counts'])}")
    (out / "SUMMARY.md").write_text("\n".join(text)+"\n", encoding="utf-8")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--trials-per-map", type=int, default=80)
    parser.add_argument("--minutes-per-map", type=float, default=20)
    parser.add_argument("--max-steps", type=int, default=1200)
    parser.add_argument("--horizon", type=int, default=64)
    parser.add_argument("--candidates", type=int, default=8)
    parser.add_argument("--max-nodes", type=int, default=4000)
    parser.add_argument("--cache-mb", type=int, default=96)
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument("--adaptive", action="store_true",
                        help="focus on route repair and reduce budgets for stagnant maps")
    parser.add_argument("--hours", type=float, default=4,
                        help="session wall-clock limit; default 4 hours")
    parser.add_argument("--patience-rounds", type=int, default=2,
                        help="adaptive mode stops after this many full passes with no best improvement")
    parser.add_argument("--session-end", type=float, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--guide-model", type=Path,
                        help="validated shared outcome model; only orders native-tested candidates")
    parser.add_argument("--maps", nargs="*", help="Optional exact map stems, e.g. 훈1 훈2")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--preflight", action="store_true",
                        help="load each map and check native branch replay; no search")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--map", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--target-trials", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.rounds, args.trials_per_map, args.minutes_per_map, args.max_steps,
           args.horizon, args.candidates, args.max_nodes, args.cache_mb,
           args.hours, args.patience_rounds) <= 0:
        parser.error("budgets must be positive")
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    args.stop_file = args.out / "STOP"
    if args.stop:
        args.stop_file.touch()
        emit(phase="stop_requested", path=str(args.stop_file))
        return
    if args.report:
        emit(maps=report(args.out), report=str(args.out / "SUMMARY.md"))
        return
    if args.worker:
        worker(args)
        return
    from train_route_curriculum import maps_for
    maps = maps_for("hun")
    if args.maps:
        unknown = set(args.maps) - {p.stem for p in maps}
        if unknown:
            parser.error("unknown maps: " + ",".join(sorted(unknown)))
        maps = [p for p in maps if p.stem in args.maps]
    if not maps:
        parser.error("no training maps found")
    if args.list:
        emit(maps=[p.name for p in maps], count=len(maps))
        return
    # Exclusive file lock is automatically released on process exit (even a crash).
    import msvcrt
    with (args.out / "RUN.lock").open("a+b") as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b"0"); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            parser.error("another local training coordinator is already running")
        if args.resume:
            args.stop_file.unlink(missing_ok=True)
        if args.stop_file.exists():
            parser.error("stopped: use --resume (existing records are preserved)")
        progress_path = args.out / "curriculum.json"
        progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {}
        completed = int(progress.get("completed_rounds", 0))
        deadline = time.time()+args.hours*3600
        stagnant_rounds = 0
        # --rounds is an additional budget for this invocation; partial round resumes.
        end_round = completed + (1 if args.preflight else args.rounds)
        finished = set(progress.get("finished_maps", []))
        try:
            for round_id in range(completed+1, end_round+1):
                baseline = {p.stem: learning_progress(args.out/(p.stem+".sqlite3"))["best"] for p in maps}
                resumed_partial_round = bool(finished)
                for path in maps:
                    if path.stem in finished:
                        continue
                    if args.stop_file.exists():
                        return
                    if time.time() >= deadline:
                        progress["state"] = "session_time_limit"
                        return
                    summary = args.out / (path.stem + ".summary.json")
                    old = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
                    # Persist target before launching, so interrupted slices don't reset budget.
                    targets = progress.setdefault("targets", {})
                    stats = learning_progress(args.out/(path.stem+".sqlite3"))
                    budget = adaptive_budget(stats, args.trials_per_map) if args.adaptive else args.trials_per_map
                    proposed = stats["trials"]+budget
                    # A pre-upgrade pending target may be larger than its new adaptive slice.
                    target = min(targets.get(path.stem, proposed), proposed) if args.adaptive else targets.get(path.stem, proposed)
                    targets[path.stem] = target
                    progress.update(completed_rounds=round_id-1, finished_maps=sorted(finished), state="running")
                    atomic_json(progress_path, progress)
                    emit(phase="map", round=round_id, map=path.stem, target_trials=target,
                         stale_trials=stats["stale"], allocated_trials=max(0,target-stats["trials"]))
                    command = [sys.executable, "-u", str(Path(__file__).resolve()), "--worker",
                               "--map", str(path), "--out", str(args.out), "--target-trials", str(target)]
                    for name in ("minutes_per_map", "max_steps", "horizon", "candidates", "max_nodes", "cache_mb", "seed"):
                        command += ["--"+name.replace("_", "-"), str(getattr(args, name))]
                    if args.preflight:
                        command += ["--preflight"]
                    if args.adaptive:
                        command += ["--adaptive"]
                    if args.guide_model:
                        command += ["--guide-model", str(args.guide_model.resolve())]
                    command += ["--session-end", str(deadline)]
                    code = subprocess.run(command, cwd=ROOT, check=False).returncode
                    report(args.out)
                    if code:
                        progress.update(state="error", failed_map=path.stem)
                        atomic_json(progress_path, progress)
                        raise SystemExit(code)
                    if args.stop_file.exists():
                        return
                    if time.time() >= deadline:
                        progress["state"] = "session_time_limit"
                        return
                    finished.add(path.stem)
                    progress["finished_maps"] = sorted(finished)
                    atomic_json(progress_path, progress)
                completed = round_id
                finished = set()
                after = {p.stem: learning_progress(args.out/(p.stem+".sqlite3"))["best"] for p in maps}
                improved = sum(after[k] is not None and (baseline[k] is None or after[k] < baseline[k]) for k in baseline)
                # Do not count an incomplete resumed pass as a full stagnation window.
                if improved:
                    stagnant_rounds = 0
                elif not resumed_partial_round:
                    stagnant_rounds += 1
                progress = {"completed_rounds": completed, "finished_maps": [], "targets": {}, "state": "round_complete"}
                progress.update(improved_maps_last_round=improved, stagnant_rounds=stagnant_rounds)
                atomic_json(progress_path, progress)
                emit(phase="round_end", round=round_id, improved_maps=improved, stagnant_rounds=stagnant_rounds)
                if args.adaptive and not args.preflight and stagnant_rounds >= args.patience_rounds:
                    progress["state"] = "diminishing_returns"
                    return
        except KeyboardInterrupt:
            args.stop_file.touch()
        finally:
            progress["state"] = "stopped" if args.stop_file.exists() else progress.get("state", "finished")
            atomic_json(progress_path, progress)
            report(args.out)
            emit(phase="session_end", state=progress["state"], completed_rounds=progress.get("completed_rounds",0))


if __name__ == "__main__":
    main()
