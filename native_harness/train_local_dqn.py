"""Train a local DQN against NativeTrainingAPI; no ChatGPT/API calls are used."""
from __future__ import annotations

import argparse
from collections import deque
import json
import os
from pathlib import Path
import random
import time

import numpy as np
import torch
from torch import nn

from native_env import LostWeaponEnv, ACTIONS
from training_archive import append_episode, physics_fingerprint, rle_actions, sha256_file
from physics_first_planner import fastest_horizontal_route
from route_library import load_library, save_route
from transition_library import extract_transitions, save_transitions
from transition_library import load_library as load_transition_library
from skill_navigator import chain_known_transitions
from mechanic_search import search_mechanic_route
from contextual_routes import try_air_traverse_route, try_ladder_route, try_water_route


class QNetwork(nn.Module):
    def __init__(self, inputs, actions):
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(inputs, 256), nn.ReLU(),
                                    nn.Linear(256, 256), nn.ReLU(),
                                    nn.Linear(256, actions))

    def forward(self, x):
        return self.layers(x)


def load_policy_compatible(network, saved_state, old_schema, new_schema):
    """Map feature columns and append-only action rows without renumbering."""
    current = network.state_dict()
    same_input = saved_state["layers.0.weight"].shape == current["layers.0.weight"].shape
    old_actions = saved_state["layers.4.bias"].shape[0]
    new_actions = current["layers.4.bias"].shape[0]
    if old_actions not in (new_actions, 19) or old_actions > new_actions:
        raise ValueError("unsupported checkpoint action schema")
    if same_input and old_actions == new_actions:
        network.load_state_dict(saved_state)
        return "exact"
    if not same_input and not old_schema:
        raise ValueError("older checkpoint has no observation schema; choose a new checkpoint")
    old_index = {name: index for index, name in enumerate(old_schema or [])}
    transferred = 0
    with torch.no_grad():
        for key, value in saved_state.items():
            if key == "layers.0.weight" and not same_input:
                for new_column, name in enumerate(new_schema):
                    old_column = old_index.get(name)
                    if old_column is not None and old_column < value.shape[1]:
                        current[key][:, new_column].copy_(value[:, old_column])
                        transferred += 1
            elif key in ("layers.4.weight", "layers.4.bias") and old_actions < new_actions:
                current[key][:old_actions].copy_(value)
            elif key in current and current[key].shape == value.shape:
                current[key].copy_(value)
        network.load_state_dict(current)
    parts = []
    if not same_input:
        parts.append(f"mapped_{transferred}_features")
    if old_actions < new_actions:
        parts.append(f"expanded_{old_actions}_to_{new_actions}_actions")
    return "+".join(parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("snapshot", type=Path)
    p.add_argument("lmf", type=Path)
    p.add_argument("--episodes", type=int, default=200)
    p.add_argument("--max-steps", type=int, default=1500)
    p.add_argument("--action-repeat", type=int, default=2)
    p.add_argument("--checkpoint", type=Path, default=Path("checkpoints/lostweapon_dqn.pt"))
    p.add_argument("--resume", action="store_true",
                   help="continue from --checkpoint when it exists")
    p.add_argument("--experience", type=Path,
                   help="append replayable action sequences here (default: beside checkpoint)")
    p.add_argument("--status", type=Path,
                   default=Path(__file__).resolve().parent / "checkpoints" / "map_runtime_status.json")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--skill-search", action="store_true",
                   help="try bounded native surface-skill chaining before DQN episodes")
    args = p.parse_args()
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    # The network is small and each sample arrives serially from Unicorn.
    # Avoid GPU transfer and CPU thread-pool overhead on every native step.
    torch.set_num_threads(1)
    device = torch.device("cpu")
    env = LostWeaponEnv(args.snapshot, args.lmf, action_repeat=args.action_repeat,
                        max_steps=args.max_steps)
    online = QNetwork(env.observation_size, env.action_size).to(device)
    target = QNetwork(env.observation_size, env.action_size).to(device)
    target.load_state_dict(online.state_dict())
    optimizer = torch.optim.Adam(online.parameters(), lr=2.5e-4)
    replay = deque(maxlen=100_000)
    demonstrations_by_map = {}
    # Native transitions are the scarce part. A 32-sample update every sixteen
    # decisions retains replay learning while avoiding four oversized matrix
    # updates over the same short interval.
    batch_size, gamma, updates = 32, 0.99, 0
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    experience_path = args.experience or args.checkpoint.with_suffix(".episodes.jsonl")
    fingerprint = physics_fingerprint(Path(__file__).resolve().parent)
    map_hash = sha256_file(args.lmf)
    topology = env.planner.topology_signature()
    map_scan = env.planner.summary()
    print(json.dumps({"planner": "native_map_scan",
                      "size": map_scan["size"],
                      "starts": map_scan["starts"],
                      "goals": map_scan["goals"],
                      "surfaces": [[row["y"], row["x0"], row["x1"]]
                                   for row in map_scan["surfaces"]],
                      "objects": map_scan["object_inventory"],
                      "mechanic": map_scan["mechanic_profile"]},
                     ensure_ascii=False), flush=True)
    route_library_path = args.checkpoint.parent / "map_route_library.json"
    transition_library_path = args.checkpoint.parent / "map_transition_library.json"
    snapshot_hash = sha256_file(args.snapshot)
    start_episode = 1
    if args.resume and args.checkpoint.exists():
        saved = torch.load(args.checkpoint, map_location=device, weights_only=False)
        if saved.get("observation_schema") == env.observation_schema:
            demonstrations_by_map = saved.get("demonstrations_by_map", {})
        if saved.get("action_size") not in (19, env.action_size):
            raise ValueError("checkpoint action size differs; choose a new checkpoint")
        transfer = load_policy_compatible(online, saved["model"],
                                          saved.get("observation_schema"),
                                          env.observation_schema)
        load_policy_compatible(target, saved["target"],
                               saved.get("observation_schema"),
                               env.observation_schema)
        # Corrected physics can reuse the policy while stale Adam moments are
        # discarded. Archived action sequences remain replayable in the new
        # oracle and do not assert that old next-state values are still true.
        same_physics = (saved.get("physics_fingerprint") == fingerprint and
                        saved.get("snapshot_sha256") == snapshot_hash)
        if same_physics and transfer == "exact":
            optimizer.load_state_dict(saved["optimizer"])
        else:
            print(json.dumps({"checkpoint_transfer": True,
                              "weights": transfer,
                              "reason": ("physics or capture fingerprint changed" if
                                         not same_physics
                                         else "observation or action schema changed"),
                              "optimizer_reset": True}, ensure_ascii=False), flush=True)
        start_episode = int(saved["episode"]) + 1

    # A checkpoint may be intentionally rebuilt after a physics/schema change.
    # Keep the monotonically increasing archive identity so new runs never
    # reuse episode numbers 1, 2, 3 and obscure older evidence.
    prior_map_attempts = 0
    if experience_path.exists():
        archived_episode_ids = []
        for line in experience_path.read_text(encoding="utf-8").splitlines():
            try:
                archived_row = json.loads(line)
                archived_episode_ids.append(int(archived_row.get("episode", 0)))
                if (archived_row.get("map_sha256") == map_hash and
                        archived_row.get("action_repeat") == args.action_repeat):
                    prior_map_attempts += 1
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        if archived_episode_ids:
            start_episode = max(start_episode, max(archived_episode_ids) + 1)

    # Solve only the certified trivial case before random exploration. The
    # candidate comes from whole-map topology; success is accepted only after
    # executing original Client physics and touching raw140.
    direct = env.planner.direct_candidate()
    verified = False
    demonstration = []
    guide_actions = []
    verified_states = []
    verified_source_episode = start_episode - 1
    physics_route = fastest_horizontal_route(env, max_steps=min(args.max_steps, 130))
    if physics_route["verified"]:
        verified = True
        demonstration = physics_route["demonstration"]
        guide_actions = physics_route["actions"]
        verified_states = physics_route["states"]
    print(json.dumps({"planner": "native_horizontal_speed_comparison",
                      "native_verified": verified,
                      "trials": physics_route["trials"]}, ensure_ascii=False), flush=True)
    if direct and not verified:
        obs, reset_info = env.reset()
        candidate_states = [reset_info["state"]]
        action = next(i for i, keys in enumerate(ACTIONS)
                      if tuple(keys) == tuple(direct["keys"]))
        verified = False
        for _ in range(min(args.max_steps, env.width * 8)):
            nxt, reward, done, truncated, _info = env.step(action)
            candidate_states.append(_info["state"])
            demonstration.append((obs.copy(), action))
            replay.append((obs, action, reward, nxt, done or truncated))
            obs = nxt
            if done:
                verified = True
                guide_actions = [action] * len(demonstration)
                verified_states = candidate_states
                break
            if truncated:
                break
        print(json.dumps({"planner": "same_surface_walk",
                          "candidate": direct, "native_verified": verified,
                          "probe_steps": env.steps}, ensure_ascii=False), flush=True)

    # Rebuild the shortest successful trajectory for this exact map from the
    # compact archive. Stored next-state values are never trusted: actions are
    # replayed through the current native physics and must reach raw140 again.
    archived = []
    if not verified and experience_path.exists():
        for line in experience_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (row.get("success") and row.get("map_sha256") == map_hash and
                    row.get("action_repeat") == args.action_repeat):
                archived.append(row)
    if archived:
        best = min(archived, key=lambda row: row.get("steps", 10**9))
        actions = [int(action) for action, count in best["actions_rle"]
                   for _ in range(int(count))]
        obs, reset_info = env.reset()
        candidate_states = [reset_info["state"]]
        candidate_demo = []
        for action in actions:
            nxt, reward, done, truncated, _info = env.step(action)
            candidate_states.append(_info["state"])
            candidate_demo.append((obs.copy(), action))
            replay.append((obs, action, reward, nxt, done or truncated))
            obs = nxt
            if done or truncated:
                break
        if done:
            verified = True
            demonstration = candidate_demo
            guide_actions = actions[:len(candidate_demo)]
            verified_source_episode = int(best["episode"])
            verified_states = candidate_states
        print(json.dumps({"planner": "archived_success_replay",
                          "source_episode": best["episode"],
                          "source_steps": best["steps"],
                          "native_verified": bool(done),
                          "replay_steps": len(candidate_demo)}, ensure_ascii=False), flush=True)

    # A different LMF may share the same surfaces and mechanics. Reuse its
    # ordered route only after replaying it in this current native world.
    if not verified:
        remembered = load_library(route_library_path)["routes"].get(topology)
        if remembered and remembered.get("action_repeat") == args.action_repeat:
            actions = [int(action) for action, count in remembered["actions_rle"]
                       for _ in range(int(count))]
            obs, reset_info = env.reset(); candidate_demo = []
            candidate_states = [reset_info["state"]]
            done = False
            for action in actions:
                nxt, reward, done, truncated, _info = env.step(action)
                candidate_states.append(_info["state"])
                candidate_demo.append((obs.copy(), action))
                replay.append((obs, action, reward, nxt, done or truncated))
                obs = nxt
                if done or truncated:
                    break
            if done:
                verified = True; demonstration = candidate_demo
                guide_actions = actions[:len(candidate_demo)]
                verified_states = candidate_states
            print(json.dumps({"planner": "topology_route_replay",
                              "source_episode": remembered["source_episode"],
                              "native_verified": bool(done),
                              "replay_steps": len(candidate_demo)}, ensure_ascii=False), flush=True)

    # A one-tile edit changes the topology hash even when the learned route is
    # still valid. Try a few shortest foreign routes, but accept one only when
    # the current native world actually reaches raw140. This makes small map
    # edits reusable without ever treating an old trajectory as physics truth.
    if not verified and not args.skill_search:
        foreign_routes = [row for key, row in load_library(route_library_path)["routes"].items()
                          if key != topology and row.get("action_repeat") == args.action_repeat]
        foreign_routes.sort(key=lambda row: int(row.get("steps", 10**9)))
        # Two short whole-route probes are enough before switching to local
        # skills; replaying every historical map route can waste many minutes.
        for remembered in foreign_routes[:2]:
            actions = [int(action) for action, count in remembered["actions_rle"]
                       for _ in range(int(count))]
            obs, reset_info = env.reset(); candidate_demo = []; done = False
            candidate_states = [reset_info["state"]]
            for action in actions:
                nxt, reward, done, truncated, _info = env.step(action)
                candidate_states.append(_info["state"])
                candidate_demo.append((obs.copy(), action))
                replay.append((obs, action, reward, nxt, done or truncated))
                obs = nxt
                if done or truncated:
                    break
            print(json.dumps({"planner": "native_route_transfer_probe",
                              "source_episode": remembered["source_episode"],
                              "native_verified": bool(done),
                              "replay_steps": len(candidate_demo)}, ensure_ascii=False), flush=True)
            if done:
                verified = True; demonstration = candidate_demo
                guide_actions = actions[:len(candidate_demo)]
                verified_source_episode = int(remembered["source_episode"])
                verified_states = candidate_states
                break

    # Map context can compose known primitives before undirected exploration.
    # Targets come from raw LMF geometry, while every movement and the final
    # clear are still checked by the original Client transition.
    if not verified and env.mechanic_profile["mode"] in ("ladder", "water", "air_traverse"):
        controllers = {"ladder": try_ladder_route, "water": try_water_route,
                       "air_traverse": try_air_traverse_route}
        contextual = controllers[env.mechanic_profile["mode"]](
            env, max_steps=args.max_steps)
        print(json.dumps({"planner": f"contextual_{env.mechanic_profile['mode']}_route",
                          "native_verified": contextual["native_verified"],
                          "steps": len(contextual["actions"]),
                          "stage": contextual.get("stage"),
                          "reason": contextual["reason"]},
                         ensure_ascii=False), flush=True)
        for index, (state_obs, action, next_obs, ended) in enumerate(
                contextual["transitions"]):
            terminal = contextual["native_verified"] and index + 1 == len(contextual["actions"])
            replay.append((state_obs, action, 100.0 if terminal else 0.0,
                           next_obs, ended or terminal))
        if contextual["native_verified"]:
            verified = True
            demonstration = contextual["demonstration"]
            guide_actions = contextual["actions"]
            verified_states = contextual["states"]

    # On an unfamiliar geometry, let the local machine try remembered surface
    # skills and bounded original-x86 search before falling back to DQN. This
    # stage makes no API calls and persists only native-confirmed landings.
    if not verified and args.skill_search:
        env.reset()
        skill_library = load_transition_library(transition_library_path)
        planner_started = time.time()
        def report_skill_progress(row):
            print(json.dumps({"planner": "native_local_skill_progress", **row},
                             ensure_ascii=False), flush=True)
            payload = {"state": "planning", "episode": start_episode,
                       "map": str(args.lmf.resolve()),
                       "phase": row.get("phase", "local_search"),
                       "native_checks": row.get("expanded", row.get("attempt", 0)),
                       "depth": row.get("depth", 0),
                       "target": row.get("target"),
                       "elapsed_seconds": round(time.time() - planner_started),
                       "updated_at": time.time()}
            try:
                args.status.parent.mkdir(parents=True, exist_ok=True)
                temporary = args.status.with_name(f"{args.status.stem}.{os.getpid()}.tmp")
                temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                os.replace(temporary, args.status)
            except OSError:
                pass
        skill_result = chain_known_transitions(
            env, skill_library, max_edges=32, explore_unknown=True,
            search_depth=5, beam_width=4,
            library_path=transition_library_path,
            source_map_sha256=map_hash,
            source_episode=start_episode - 1,
            progress=report_skill_progress)
        if skill_result["status"] == "needs_mechanic_search":
            mechanic = search_mechanic_route(
                env, skill_result["mechanic_profile"]["mode"],
                max_depth=4, beam_width=4, progress=report_skill_progress,
                commit=True)
            if mechanic["native_verified"]:
                skill_result = {"status": "goal_reached",
                                "actions": skill_result["actions"] + mechanic["actions"],
                                "edges": skill_result["edges"],
                                "mechanic": skill_result["mechanic_profile"],
                                "mechanic_steps": mechanic["steps"]}
        print(json.dumps({"planner": "native_surface_skill_search",
                          "status": skill_result["status"],
                          "actions": len(skill_result["actions"]),
                          "verified_edges": len(skill_result["edges"])},
                         ensure_ascii=False), flush=True)
        if skill_result["status"] == "goal_reached":
            obs, reset_info = env.reset(); candidate_states = [reset_info["state"]]
            candidate_demo = []; done = False
            for action in skill_result["actions"]:
                nxt, reward, done, truncated, info = env.step(action)
                candidate_states.append(info["state"])
                candidate_demo.append((obs.copy(), action))
                replay.append((obs, action, reward, nxt, done or truncated))
                obs = nxt
                if done or truncated:
                    break
            if done:
                verified = True; demonstration = candidate_demo
                guide_actions = skill_result["actions"][:len(candidate_demo)]
                verified_states = candidate_states

    if verified and guide_actions:
        save_route(route_library_path, topology,
                   actions_rle=rle_actions(guide_actions), steps=len(guide_actions),
                   action_repeat=args.action_repeat, source_map_sha256=map_hash,
                   source_episode=verified_source_episode)
        transitions = extract_transitions(env.planner, verified_states, guide_actions)
        saved_transitions = save_transitions(
            transition_library_path, transitions,
            action_repeat=args.action_repeat, source_map_sha256=map_hash,
            source_episode=verified_source_episode,
            verification="extracted_from_native_verified_clear")
        print(json.dumps({"planner": "transition_skill_extraction",
                          "transitions": len(transitions),
                          "new_or_shorter": saved_transitions}, ensure_ascii=False), flush=True)

    def retain_demonstration(rows):
        if not rows:
            return
        indices = np.linspace(0, len(rows) - 1, min(128, len(rows)), dtype=int)
        demonstrations_by_map[map_hash] = (
            np.stack([rows[i][0] for i in indices]).astype(np.float32),
            np.asarray([rows[i][1] for i in indices], dtype=np.int64))

    def rehearsal_loss(max_maps=None):
        entries = list(demonstrations_by_map.values())
        if max_maps is not None and len(entries) > max_maps:
            entries = random.sample(entries, max_maps)
        states, actions = [], []
        for state_array, action_array in entries:
            indices = np.random.choice(len(action_array), min(16, len(action_array)),
                                       replace=False)
            states.append(state_array[indices])
            actions.append(action_array[indices])
        if not states:
            return None
        features = torch.from_numpy(np.concatenate(states)).to(device)
        targets = torch.from_numpy(np.concatenate(actions)).to(device)
        return nn.functional.cross_entropy(online(features), targets)

    # A native-verified route is evidence, not a guessed answer. Teach that
    # short sequence directly instead of waiting thousands of random episodes
    # for sparse terminal reward to propagate back through every step.
    if verified and demonstration:
        retain_demonstration(demonstration)
        for _ in range(80):
            loss = rehearsal_loss()
            optimizer.zero_grad(); loss.backward()
            nn.utils.clip_grad_norm_(online.parameters(), 10.0); optimizer.step()
        target.load_state_dict(online.state_dict())

    # Once a 79-step native route exists, a 1500-step failure supplies mostly
    # repeated noise. Keep a generous 4x timing margin for exploration.
    episode_limit = (min(args.max_steps, max(256, len(demonstration) * 2))
                     if verified else args.max_steps)
    env.max_steps = episode_limit

    def write_status(payload):
        payload = {**payload, "updated_at": time.time(), "map": str(args.lmf.resolve())}
        args.status.parent.mkdir(parents=True, exist_ok=True)
        # Multiple launchers, antivirus and the UI reader can briefly hold a
        # Windows handle. Telemetry must never terminate an expensive episode.
        temporary = args.status.with_name(
            f"{args.status.stem}.{os.getpid()}.tmp")
        encoded = json.dumps(payload, ensure_ascii=False)
        for attempt in range(6):
            try:
                temporary.write_text(encoded, encoding="utf-8")
                os.replace(temporary, args.status)
                return True
            except (PermissionError, OSError):
                time.sleep(0.02 * (attempt + 1))
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False

    def save_checkpoint(episode):
        torch.save({"model": online.state_dict(), "target": target.state_dict(),
                    "optimizer": optimizer.state_dict(), "episode": episode,
                    "observation_size": env.observation_size,
                    "observation_schema": env.observation_schema,
                    "action_size": env.action_size, "args": vars(args),
                    "brain_task": "navigate",
                    "checkpoint_schema": 2,
                    "physics_fingerprint": fingerprint,
                    "snapshot_sha256": snapshot_hash,
                    "map_sha256": map_hash,
                    "demonstrations_by_map": demonstrations_by_map}, args.checkpoint)

    # Persist the repaired/imitation policy before exploratory RL can alter it.
    if verified:
        save_checkpoint(start_episode - 1)

    last_episode = start_episode - 1
    for local_episode, episode in enumerate(
            range(start_episode, start_episode + args.episodes), start=1):
        last_episode = episode
        obs, reset_info = env.reset(); total = 0.0; success = False
        episode_actions = []
        episode_transitions = []
        episode_states = [reset_info["state"]]
        # Resume keeps a per-map exploration schedule. Folder curricula launch
        # short subprocess batches; local_episode alone would reset every
        # unsolved map to epsilon 0.9 on each batch and bury learned behavior.
        map_attempt = prior_map_attempts + local_episode - 1
        epsilon = (max(0.002, 0.01 * (0.97 ** (local_episode - 1)))
                   if verified else max(0.10, 0.90 * (0.97 ** map_attempt)))
        episode_started = time.perf_counter()
        write_status({"state": "running", "episode": episode, "tick": 0,
                      "max_steps": episode_limit, "epsilon": round(epsilon, 3),
                      "reward": 0.0, "tps": 0.0})
        for step_index in range(episode_limit):
            valid_actions = env.valid_action_indices()
            if verified and step_index < len(guide_actions):
                # Follow the temporally ordered, native-verified plan while
                # occasionally perturbing one decision to measure robustness.
                action = (random.choice(valid_actions) if random.random() < epsilon
                          else (guide_actions[step_index]
                                if guide_actions[step_index] in valid_actions else 0))
            elif random.random() < epsilon:
                action = random.choice(valid_actions)
            else:
                with torch.no_grad():
                    values = online(torch.from_numpy(obs).to(device))
                    mask = torch.full_like(values, float("-inf"))
                    mask[list(valid_actions)] = 0
                    action = int((values + mask).argmax())
            nxt, reward, done, truncated, info = env.step(action)
            episode_actions.append(action)
            episode_transitions.append((obs.copy(), action))
            episode_states.append(info["state"])
            replay.append((obs, action, reward, nxt, done or truncated))
            obs, total = nxt, total + reward
            if (step_index + 1) % 16 == 0 or done or truncated:
                elapsed = max(0.001, time.perf_counter() - episode_started)
                write_status({"state": "running", "episode": episode,
                              "tick": step_index + 1, "max_steps": episode_limit,
                              "progress_percent": round((step_index + 1) * 100 / episode_limit, 1),
                              "epsilon": round(epsilon, 3), "reward": round(total, 3),
                              "tps": round((step_index + 1) / elapsed, 2),
                              "position": [round(info["state"]["x"], 2),
                                           round(info["state"]["y"], 2)]})
            if len(replay) >= batch_size and env.steps % 16 == 0:
                sample = random.sample(replay, batch_size)
                states = torch.from_numpy(np.stack([v[0] for v in sample])).to(device)
                actions = torch.tensor([v[1] for v in sample], device=device)
                rewards = torch.tensor([v[2] for v in sample], dtype=torch.float32, device=device)
                next_states = torch.from_numpy(np.stack([v[3] for v in sample])).to(device)
                ends = torch.tensor([v[4] for v in sample], dtype=torch.float32, device=device)
                q = online(states).gather(1, actions[:, None]).squeeze(1)
                with torch.no_grad():
                    next_q = target(next_states)
                    next_mask = torch.full_like(next_q, float("-inf"))
                    for row, transition in enumerate(sample):
                        allowed_next = env.valid_action_indices_from_observation(transition[3])
                        next_mask[row, list(allowed_next)] = 0
                    wanted = rewards + gamma * (1.0 - ends) * (next_q + next_mask).max(1).values
                loss = nn.functional.smooth_l1_loss(q, wanted)
                # Sparse-return Q updates must not erase a Client-verified
                # route. Rehearse a small random slice of the demonstration.
                if demonstrations_by_map:
                    loss = loss + rehearsal_loss(max_maps=4)
                optimizer.zero_grad(); loss.backward()
                nn.utils.clip_grad_norm_(online.parameters(), 10.0); optimizer.step()
                updates += 1
                if updates % 500 == 0:
                    target.load_state_dict(online.state_dict())
            if done or truncated:
                success = done
                break
        payload = {"episode": episode, "reward": round(total, 3),
                   "steps": env.steps, "success": success,
                   "epsilon": round(epsilon, 3), "device": str(device)}
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        write_status({**payload, "state": "episode_complete", "tick": env.steps,
                      "max_steps": episode_limit, "progress_percent": 100.0})
        append_episode(experience_path, {
            "schema": 1, "episode": episode, "map": str(args.lmf.resolve()),
            "map_sha256": map_hash, "physics_fingerprint": fingerprint,
            "topology_signature": topology,
            "snapshot_sha256": snapshot_hash,
            "action_repeat": args.action_repeat,
            "actions_rle": rle_actions(episode_actions),
            "reward": round(total, 6), "success": success,
                   "steps": env.steps, "final_state": info["state"],
        })
        # A failed full-map episode can still contain valid native landings.
        # Retain those short transitions so later episodes learn incrementally
        # instead of rediscovering every platform until the first full clear.
        partial_transitions = [transition for transition in extract_transitions(
            env.planner, episode_states, episode_actions)
            if transition["steps"] <= 64]
        partial_saved = save_transitions(
            transition_library_path, partial_transitions,
            action_repeat=args.action_repeat, source_map_sha256=map_hash,
            source_episode=episode,
            verification=("extracted_from_native_verified_clear" if success
                          else "observed_in_failed_native_episode"))
        if partial_saved:
            print(json.dumps({"planner": "partial_transition_learning",
                              "observed": len(partial_transitions),
                              "new_or_shorter": partial_saved,
                              "episode_success": success},
                             ensure_ascii=False), flush=True)
        if success:
            # Immediately consolidate this map-specific success instead of
            # waiting for terminal reward to crawl back through hundreds of
            # Q-learning updates.
            demonstration = episode_transitions
            verified = True
            if not guide_actions or len(episode_actions) < len(guide_actions):
                guide_actions = list(episode_actions)
            retain_demonstration(demonstration)
            for _ in range(32):
                loss = rehearsal_loss()
                optimizer.zero_grad(); loss.backward()
                nn.utils.clip_grad_norm_(online.parameters(), 10.0); optimizer.step()
            target.load_state_dict(online.state_dict())
            episode_limit = min(args.max_steps, max(256, len(demonstration) * 2))
            env.max_steps = episode_limit
            save_route(route_library_path, topology,
                       actions_rle=rle_actions(episode_actions), steps=env.steps,
                       action_repeat=args.action_repeat, source_map_sha256=map_hash,
                       source_episode=episode)
            save_transitions(
                transition_library_path,
                extract_transitions(env.planner, episode_states, episode_actions),
                action_repeat=args.action_repeat, source_map_sha256=map_hash,
                source_episode=episode,
                verification="extracted_from_native_verified_clear")
        # Native emulation may encounter a still-unmapped Client dependency.
        # Save every completed episode so a later crash loses at most one.
        save_checkpoint(episode)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        crash = Path(__file__).resolve().parent / "checkpoints" / "map_training_crash.log"
        crash.parent.mkdir(parents=True, exist_ok=True)
        crash.write_text(traceback.format_exc(), encoding="utf-8")
        status = crash.parent / "map_runtime_status.json"
        try:
            status.write_text(json.dumps({"state": "crashed",
                                          "error": f"{type(exc).__name__}: {exc}",
                                          "crash_log": str(crash),
                                          "updated_at": time.time()}, ensure_ascii=False),
                              encoding="utf-8")
        except OSError:
            pass
        raise
