"""User-run offline x86 route trainer: deterministic rules with learned action values.

This trainer does not control a normal/online Client or train combat. It keeps
the existing native action mask and saves its own isolated JSON checkpoint.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import time

from discovered_map import DiscoveredMap
from native_env import ACTIONS, LostWeaponEnv
from snapshot_selector import snapshot_for_map
from training_archive import append_episode, physics_fingerprint, rle_actions, sha256_file
from transition_library import extract_transitions, save_transitions

ROOT = Path(__file__).resolve().parent
MOVEMENT = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)


def scan(env, memory, state, maximum=21):
    """Expand one tile of radius at a time only while the forward exit is unclear."""
    px, py = int(state["x"] // 32), int(state["y"] // 32)
    gx, gy = env._nearest_goal(state)
    direction = 1 if gx >= px else -1
    size = 5
    while True:
        view = env.navigation_view(state, size=size)
        memory.update(view)
        ahead = [memory.clearance(px + direction * n, py - 1)
                 for n in range(1, min(4, size // 2) + 1)]
        # A visible wall, unknown exit, or unsupported landing merits a wider look.
        edge = px + direction * (size // 2)
        support = memory.classify(edge, py + 1)
        if size >= maximum or ("unknown" not in ahead and
                               "blocked" not in ahead and support != "unknown"):
            return view
        size += 2


def context(env, memory, state):
    px, py = int(state["x"] // 32), int(state["y"] // 32)
    gx, gy = env._nearest_goal(state)
    direction = 1 if gx >= px else -1
    ahead = memory.clearance(px + direction, py - 1)
    landing = memory.classify(px + direction * 2, py + 1)
    vertical = "up" if gy < py - 1 else "down" if gy > py + 1 else "level"
    mode = "ladder" if state.get("74") == 1 else "water" if state.get("c0") == 21 else \
        "chute" if state.get("dc") else "normal"
    return ("R" if direction > 0 else "L", vertical, ahead, landing, mode)


def candidates(env, state):
    return [action for action in env.valid_action_indices(state)
            if action in MOVEMENT]


def rule_score(action, ctx):
    direction, vertical, ahead, landing, mode = ctx
    keys = ACTIONS[action]
    forward = direction == "R" and "RIGHT" in keys or direction == "L" and "LEFT" in keys
    backward = direction == "R" and "LEFT" in keys or direction == "L" and "RIGHT" in keys
    score = 0.0
    if forward:
        score += 2.0
    if backward:
        score -= 0.8
    if "DOWN" in keys and forward and ahead == "open" and landing == "blocked":
        score += 0.4  # Fast ground travel, subject to native verification.
    if ahead == "blocked" and "UP" in keys:
        score += 2.0
    if ahead == "blocked" and "DOWN" in keys:
        score -= 2.0
    if landing in ("open", "unknown") and "DOWN" in keys:
        score -= 1.5  # Uncertain landing, not a prohibition.
    if vertical == "up" and "UP" in keys:
        score += 1.0
    if vertical == "down" and "DOWN" in keys and mode in ("ladder", "water"):
        score += 1.0
    if mode == "chute" and "C" in keys:
        score += 0.4
    if not keys:
        score -= 1.0
    return score


def return_to_start(start, before, after, peak_distance):
    """Penalize lost progress, never a mere hazard touch or ordinary detour."""
    sx, sy = float(start["x"]), float(start["y"])
    old = math.hypot(float(before["x"]) - sx, float(before["y"]) - sy)
    new = math.hypot(float(after["x"]) - sx, float(after["y"]) - sy)
    jump = math.hypot(float(after["x"]) - float(before["x"]),
                      float(after["y"]) - float(before["y"]))
    return peak_distance >= 96 and old >= 96 and new <= 48 and jump >= 64


def near_lava(env, state):
    """Raw49 is the Client lava/reset object; proximity is only an event hint."""
    px, py = float(state["x"]) / 32, float(state["y"]) / 32
    return any(tile == 49 and abs(px - x) <= 1.5 and abs(py - y) <= 2.5
               for tile, x, y in env.records)


def save_checkpoint(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                         encoding="utf-8")
    temporary.replace(path)


def preserve_before_resume(checkpoint, archive):
    """Keep exact prior bytes before a resumed run updates its checkpoint."""
    checkpoint = Path(checkpoint)
    if not checkpoint.exists():
        return None
    folder = checkpoint.parent / "pre_resume_snapshots" / (
        checkpoint.stem + "_" + datetime.now().strftime("%Y%m%d_%H%M%S") +
        "_" + str(os.getpid()))
    folder.mkdir(parents=True, exist_ok=False)
    manifest = []
    for source in (checkpoint, archive):
        source = Path(source)
        if not source.exists():
            continue
        destination = folder / source.name
        shutil.copy2(source, destination)
        raw = destination.read_bytes()
        if raw != source.read_bytes():
            raise IOError(f"pre-resume copy differs: {source}")
        manifest.append({"name": source.name, "bytes": len(raw),
                         "sha256": hashlib.sha256(raw).hexdigest()})
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    return folder


def expand_actions(encoded):
    return [int(action) for action, count in encoded for _ in range(int(count))]


def best_recorded_route(path, map_hash):
    """Recover the fastest successful native trace, including older runs."""
    if not path.exists():
        return None
    best = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if (row.get("map_sha256") != map_hash or not row.get("done") or
                    row.get("interrupted") or int(row.get("return_to_start", 0))):
                continue
            actions = expand_actions(row["actions_rle"])
            if len(actions) != int(row["steps"]):
                continue
            candidate = {"episode": int(row["episode"]), "steps": len(actions),
                         "actions": actions, "return_to_start": int(row.get("return_to_start", 0))}
            if best is None or (candidate["steps"], candidate["return_to_start"]) < \
                    (best["steps"], best["return_to_start"]):
                best = candidate
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return best


def legacy_physics_seed(path, map_hash):
    """Use older x86 route work as a candidate, never as an assumed clear."""
    if not path.exists():
        return None
    try:
        rows = json.loads(path.read_text(encoding="utf-8")).get("routes", {}).values()
    except (OSError, json.JSONDecodeError):
        return None
    matches = []
    for row in rows:
        if row.get("source_map_sha256") == map_hash and row.get("action_repeat") == 2:
            actions = expand_actions(row.get("actions_rle", []))
            if actions and len(actions) == int(row.get("steps", -1)) and all(
                    0 <= action < len(ACTIONS) for action in actions):
                matches.append({"steps": len(actions), "actions": actions,
                                "source": "legacy_physics_route_requires_replay"})
    return min(matches, key=lambda row: row["steps"]) if matches else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", type=Path, nargs="?", default=ROOT.parent / "훈련용맵/훈1.LMF")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--max-steps", type=int, default=250)
    parser.add_argument("--checkpoint", type=Path,
                        default=ROOT / "checkpoints/route_rule_helper.json")
    parser.add_argument("--stop-file", type=Path,
                        default=ROOT / "checkpoints/route_rule_helper.stop")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--import-values", type=Path,
                        help="seed a new map checkpoint from another map's learned contexts")
    parser.add_argument("--combat", choices=("off", "priority"), default="off")
    args = parser.parse_args()
    if args.combat != "off":
        parser.error("combat priority needs a two-player native capture; this route trainer supports --combat off")
    if args.episodes < 1 or args.max_steps < 1:
        parser.error("episodes and max-steps must be positive")
    lmf = args.map.resolve()
    if not lmf.is_file():
        parser.error(f"map not found: {lmf}")
    snapshot = snapshot_for_map(ROOT, lmf)
    if not snapshot.is_file():
        parser.error(f"snapshot not found: {snapshot}")
    rng = random.Random(args.seed)
    env = LostWeaponEnv(snapshot, lmf, action_repeat=2, max_steps=args.max_steps)
    identity = {"map_sha256": sha256_file(lmf),
                "snapshot_sha256": sha256_file(snapshot),
                "physics_fingerprint": physics_fingerprint(ROOT),
                "action_schema": [list(a) for a in ACTIONS]}
    values = defaultdict(lambda: [0.0, 0])
    completed = 0
    archive = args.checkpoint.with_suffix(".episodes.jsonl")
    best = best_recorded_route(archive, identity["map_sha256"])
    legacy = legacy_physics_seed(ROOT / "checkpoints/physics_route_library.json",
                                 identity["map_sha256"])
    if args.checkpoint.exists():
        saved = json.loads(args.checkpoint.read_text(encoding="utf-8"))
        if any(saved.get(key) != value for key, value in identity.items()):
            parser.error("checkpoint map/snapshot/physics/action schema differs; choose another --checkpoint")
        completed = int(saved["completed_episodes"])
        saved_best = saved.get("best_route")
        if (saved_best and not int(saved_best.get("return_to_start", 0)) and
                (best is None or int(saved_best["steps"]) < best["steps"])):
            best = saved_best
        for key, value in saved["values"].items():
            values[key] = [float(value[0]), int(value[1])]
    elif args.import_values:
        source = json.loads(args.import_values.read_text(encoding="utf-8"))
        if (source.get("physics_fingerprint") != identity["physics_fingerprint"] or
                source.get("action_schema") != identity["action_schema"]):
            parser.error("imported values have a different physics/action schema")
        for key, value in source["values"].items():
            values[key] = [float(value[0]), int(value[1])]
    prior_backup = preserve_before_resume(args.checkpoint, archive)
    print(json.dumps({"phase": "start", "map": str(lmf), "resume_after": completed,
                      "new_episodes": args.episodes, "checkpoint": str(args.checkpoint),
                      "import_values": str(args.import_values) if args.import_values and not completed else None,
                      "recorded_best_steps": best["steps"] if best else None,
                      "legacy_seed_steps": legacy["steps"] if legacy else None,
                      "pre_resume_backup": str(prior_backup) if prior_backup else None,
                      "stop_file": str(args.stop_file), "combat": "off"},
                     ensure_ascii=False), flush=True)
    successes = 0
    for run in range(1, args.episodes + 1):
        if args.stop_file.exists():
            print(json.dumps({"phase": "stopped", "completed_episodes": completed},
                             ensure_ascii=False), flush=True)
            break
        _observation, info = env.reset()
        start = info["state"]
        state = start
        states = [start]
        memory = DiscoveredMap(env.width, env.height)
        visits = set()
        actions = []
        traces = []
        peak_distance = 0.0
        total_reward = 0.0
        done = False
        interrupted = False
        returned = 0
        lava_recent = 0
        view_sizes = []
        best_goal_distance = env._goal_distance(start)
        # A recorded clear becomes a physical route hypothesis. Verify it once
        # after resume, then explore short deviations and let the rule bot
        # replan from the resulting native state.
        seed = legacy if run == 1 and legacy and (best is None or legacy["steps"] < best["steps"]) else best
        if seed:
            mode = "replay_seed" if run == 1 else "mutate_best" if rng.random() < 0.7 else "free"
            pivot = rng.randrange(min(seed["steps"], args.max_steps)) if mode == "mutate_best" else 0
            mutation_steps = rng.randint(1, 4) if mode == "mutate_best" else 0
        else:
            mode, pivot, mutation_steps = "free", 0, 0
        for step in range(args.max_steps):
            if args.stop_file.exists():
                interrupted = True
                break
            view = scan(env, memory, state)
            view_sizes.append(view["size"])
            ctx = context(env, memory, state)
            allowed = candidates(env, state)
            if not allowed:
                break
            explore = max(0.05, 0.25 / math.sqrt(1 + completed / 20))
            if mode == "replay_seed" and step < seed["steps"] and seed["actions"][step] in allowed:
                action = seed["actions"][step]
            elif mode == "mutate_best" and step < pivot and seed["actions"][step] in allowed:
                action = seed["actions"][step]
            elif mode == "mutate_best" and pivot <= step < pivot + mutation_steps:
                original = seed["actions"][step] if step < seed["steps"] else None
                alternatives = [a for a in allowed if a != original]
                action = rng.choice(alternatives or allowed)
            elif rng.random() < explore:
                action = rng.choice(allowed)
            else:
                action = max(allowed, key=lambda a: rule_score(a, ctx) +
                             values[json.dumps([*ctx, a])][0])
            before = state
            _next_obs, _native_reward, done, truncated, info = env.step(action)
            state = info["state"]
            states.append(state)
            lava_recent = 12 if near_lava(env, before) or near_lava(env, state) else max(0, lava_recent - 1)
            actions.append(action)
            transition = memory.record_transition(before, action, state)
            tile = (int(state["x"] // 32), int(state["y"] // 32))
            reward = -0.05
            if tile not in visits:
                reward += 0.2
                visits.add(tile)
            goal_distance = env._goal_distance(state)
            # Only a new best with a currently clear forward corridor receives
            # small progress credit; walls cannot be farmed by moving in place.
            if goal_distance < best_goal_distance and ctx[2] == "open":
                reward += min(0.3, (best_goal_distance - goal_distance) * 0.1)
                best_goal_distance = goal_distance
            if transition["outcome"] == "failure":
                reward -= 0.2
            if lava_recent and return_to_start(start, before, state, peak_distance):
                reward -= 5.0
                returned += 1
                lava_recent = 0
            peak_distance = max(peak_distance, math.hypot(
                float(state["x"]) - float(start["x"]),
                float(state["y"]) - float(start["y"])))
            if done:
                reward += 100.0 + 100.0 * (args.max_steps - step - 1) / args.max_steps
                if returned == 0 and (best is None or len(actions) < best["steps"]):
                    reward += 10.0  # Explicit credit for a newly faster clear.
            traces.append((json.dumps([*ctx, action]), reward))
            total_reward += reward
            if done or truncated:
                break
        if interrupted:
            append_episode(archive, {"episode": completed + 1,
                                      "map_sha256": identity["map_sha256"],
                                      "interrupted": True, "steps": len(actions),
                                      "actions_rle": rle_actions(actions)})
            print(json.dumps({"phase": "stopped", "episode_not_counted": completed + 1,
                              "completed_episodes": completed}, ensure_ascii=False), flush=True)
            break
        # This is a compact, bounded Monte Carlo action-value correction.
        # Rule scores remain active even before any learning has occurred.
        future = 0.0
        for key, reward in reversed(traces):
            future = reward + 0.97 * future
            row = values[key]
            row[1] += 1
            row[0] += (max(-20.0, min(20.0, future / 10.0)) - row[0]) / row[1]
        completed += 1
        successes += int(done)
        new_best = bool(done and returned == 0 and
                        (best is None or len(actions) < best["steps"]))
        if new_best:
            best = {"episode": completed, "steps": len(actions), "actions": list(actions),
                    "return_to_start": returned}
        if done and returned == 0:
            segments = extract_transitions(env.planner, states, actions)
            save_transitions(ROOT / "checkpoints/route_curriculum/physics_transitions.json",
                             segments, action_repeat=env.action_repeat,
                             source_map_sha256=identity["map_sha256"],
                             source_episode=completed,
                             verification="native_goal_region_trace")
        payload = {**identity, "completed_episodes": completed,
                   "values": dict(values), "best_route": best,
                   "updated_at": time.time()}
        save_checkpoint(args.checkpoint, payload)
        append_episode(archive, {
            "episode": completed, "map_sha256": identity["map_sha256"],
            "done": bool(done), "steps": len(actions), "return_to_start": returned,
            "reward": round(total_reward, 3), "actions_rle": rle_actions(actions),
            "mode": mode, "new_best": new_best})
        print(json.dumps({"phase": "episode", "episode": completed,
                          "run": run, "steps": len(actions), "goal": bool(done),
                          "success_rate_this_run": round(successes / run, 3),
                          "reward": round(total_reward, 2),
                          "return_to_start": returned,
                          "known_tiles": len(memory.cells),
                          "view_max": max(view_sizes, default=0),
                          "mode": mode, "best_steps": best["steps"] if best else None,
                          "new_best": new_best,
                          "learned_context_actions": len(values)},
                         ensure_ascii=False), flush=True)
    print(json.dumps({"phase": "end", "completed_episodes": completed,
                      "checkpoint": str(args.checkpoint)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
