"""Local shared-policy DQN for two-player native Client sword combat."""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import random
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
import torch
from torch import nn

from combat_env import LostWeaponCombatEnv, COMBAT_ACTIONS


def network(inputs: int, outputs: int):
    return nn.Sequential(nn.Linear(inputs, 384), nn.ReLU(),
                         nn.Linear(384, 256), nn.ReLU(),
                         nn.Linear(256, outputs))


def load_combat_policy_compatible(model, saved_state, old_schema, new_schema):
    """Preserve named input features and append-only combat action Q rows."""
    current = model.state_dict()
    old_actions = saved_state["4.bias"].shape[0]
    new_actions = current["4.bias"].shape[0]
    if old_actions not in (new_actions, 21) or old_actions > new_actions:
        raise ValueError("unsupported combat action schema")
    if not old_schema or len(old_schema) != saved_state["0.weight"].shape[1]:
        raise ValueError("combat checkpoint has no compatible observation schema")
    if old_schema == new_schema and old_actions == new_actions:
        model.load_state_dict(saved_state)
        return "exact"
    old_index = {name: index for index, name in enumerate(old_schema)}
    with torch.no_grad():
        for key, value in saved_state.items():
            if key == "0.weight":
                for column, name in enumerate(new_schema):
                    if name in old_index:
                        current[key][:, column].copy_(value[:, old_index[name]])
            elif key in ("4.weight", "4.bias") and old_actions < new_actions:
                current[key][:old_actions].copy_(value)
            elif key in current and current[key].shape == value.shape:
                current[key].copy_(value)
        model.load_state_dict(current)
    return f"mapped_features_expanded_{old_actions}_to_{new_actions}_actions"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path,
                        default=ROOT / "private_snapshots" / "team_p2p_combat_live.zip")
    parser.add_argument("--peer-snapshot", type=Path,
                        default=ROOT / "private_snapshots" / "team_slot1_live.zip")
    parser.add_argument("--lmf", type=Path)
    parser.add_argument("--checkpoint", type=Path,
                        default=ROOT / "checkpoints" / "combat_shared_dqn.pt")
    parser.add_argument("--log", type=Path,
                        default=ROOT / "checkpoints" / "combat_training.jsonl")
    parser.add_argument("--status", type=Path,
                        default=ROOT / "checkpoints" / "combat_runtime_status.json")
    parser.add_argument("--episodes", type=int, default=1000)
    parser.add_argument("--view-size", type=int, default=9,
                        help="Odd local terrain width in tiles, e.g. 9, 11, or 13")
    parser.add_argument("--max-steps", type=int, default=256,
                        help="Keep <=256 until the 15-second inactivity phase is calibrated")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--seed", type=int, default=20260915)
    args = parser.parse_args()
    if args.view_size < 5 or args.view_size > 21 or args.view_size % 2 == 0:
        raise ValueError("--view-size must be odd and between 5 and 21")
    if args.max_steps > 256:
        raise ValueError("long combat episodes are locked until inactivity-timer parity is calibrated")

    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    # Tiny MLP updates are slower when PyTorch fans them across all laptop
    # cores on every game tick. One worker avoids thread-pool overhead and
    # leaves CPU time for the two Unicorn Client views.
    torch.set_num_threads(1)
    env = LostWeaponCombatEnv(args.snapshot, peer_snapshot=args.peer_snapshot,
                              lmf=args.lmf, crop=args.view_size, max_steps=args.max_steps)
    print(json.dumps({"episode_baseline": "clean",
                      "preflight_ticks": env.capture_settle_ticks,
                      "preflight_damage": env.capture_settle_damage},
                     ensure_ascii=False), flush=True)
    device = torch.device("cpu")
    online = network(env.observation_size, env.action_size).to(device)
    target = network(env.observation_size, env.action_size).to(device)
    target.load_state_dict(online.state_dict())
    optimizer = torch.optim.Adam(online.parameters(), lr=2e-4)
    replay = deque(maxlen=100_000)
    start_episode = 1; updates = 0
    if args.resume and args.checkpoint.exists():
        saved = torch.load(args.checkpoint, map_location=device, weights_only=False)
        transfer = load_combat_policy_compatible(online, saved["model"],
                                                 saved.get("observation_schema"),
                                                 env.observation_schema)
        load_combat_policy_compatible(target, saved["target"],
                                      saved.get("observation_schema"),
                                      env.observation_schema)
        if transfer == "exact":
            optimizer.load_state_dict(saved["optimizer"])
        else:
            print(json.dumps({"checkpoint_transfer": transfer,
                              "optimizer_reset": True}), flush=True)
        start_episode = int(saved["episode"]) + 1

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    def write_status(payload):
        payload = {**payload, "updated_at": time.time()}
        args.status.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.status.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(args.status)

    for episode in range(start_episode, start_episode + args.episodes):
        # Position curriculum changes only the reset distribution. Movement,
        # collision, attacks and damage remain original Client x86 behavior.
        maximum_gap = min(384, 96 + episode // 4)
        gap = random.randrange(64, maximum_gap + 1, 16)
        observations, _ = env.reset(spawn_distance=gap); totals = {0: 0.0, 1: 0.0}
        spawn_dx = abs(env.oracle.read_combatant(1)["x"] - env.oracle.read_combatant(0)["x"])
        spawn_dy = abs(env.oracle.read_combatant(1)["y"] - env.oracle.read_combatant(0)["y"])
        epsilon = max(0.08, 1.0 - episode / 800.0)
        episode_started = time.perf_counter()
        write_status({"state": "running", "episode": episode, "tick": 0,
                      "max_steps": args.max_steps, "epsilon": round(epsilon, 3),
                      "spawn_gap": spawn_dx, "spawn_dy": spawn_dy,
                      "map": str(args.lmf) if args.lmf else "flat_baseline",
                      "hp": [100.0, 100.0], "tps": 0.0})
        for step_index in range(args.max_steps):
            actions = {}
            for roster in (0, 1):
                allowed = env.valid_action_indices_from_observation(observations[roster])
                if random.random() < epsilon:
                    actions[roster] = random.choice(allowed)
                else:
                    with torch.no_grad():
                        q = online(torch.from_numpy(observations[roster]))
                        mask = torch.full_like(q, float("-inf"))
                        mask[list(allowed)] = 0
                        actions[roster] = int((q + mask).argmax())
            nxt, rewards, done, truncated, info = env.step(actions)
            terminal = done or truncated
            for roster in (0, 1):
                replay.append((observations[roster], actions[roster], rewards[roster],
                               nxt[roster], terminal))
                totals[roster] += rewards[roster]
            observations = nxt
            if (step_index + 1) % 8 == 0 or terminal:
                elapsed = max(0.001, time.perf_counter() - episode_started)
                write_status({"state": "running", "episode": episode,
                              "tick": step_index + 1, "max_steps": args.max_steps,
                              "progress_percent": round((step_index + 1) * 100 / args.max_steps, 1),
                              "epsilon": round(epsilon, 3), "spawn_gap": gap,
                              "map": str(args.lmf) if args.lmf else "flat_baseline",
                              "hp": [info["players"][r]["hp"] for r in (0, 1)],
                              "actions": ["+".join(COMBAT_ACTIONS[actions[r]]) or "NOOP"
                                          for r in (0, 1)],
                              "tps": round((step_index + 1) / elapsed, 2)})
            # One gradient update per four native ticks is sufficient for the
            # replay ratio and avoids spending most wall time inside PyTorch.
            if len(replay) >= 64 and (step_index + 1) % 4 == 0:
                batch = random.sample(replay, 64)
                states = torch.from_numpy(np.stack([x[0] for x in batch]))
                acts = torch.tensor([x[1] for x in batch])
                rewards_t = torch.tensor([x[2] for x in batch], dtype=torch.float32)
                next_states = torch.from_numpy(np.stack([x[3] for x in batch]))
                ends = torch.tensor([x[4] for x in batch], dtype=torch.float32)
                q = online(states).gather(1, acts[:, None]).squeeze(1)
                with torch.no_grad():
                    next_q = target(next_states)
                    next_mask = torch.full_like(next_q, float("-inf"))
                    for row, entry in enumerate(batch):
                        allowed_next = env.valid_action_indices_from_observation(entry[3])
                        next_mask[row, list(allowed_next)] = 0
                    wanted = rewards_t + .99 * (1 - ends) * (next_q + next_mask).max(1).values
                loss = nn.functional.smooth_l1_loss(q, wanted)
                optimizer.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(online.parameters(), 10); optimizer.step()
                updates += 1
                if updates % 500 == 0: target.load_state_dict(online.state_dict())
            if terminal: break
        row = {"episode": episode, "steps": env.steps,
               "reward0": round(totals[0], 3), "reward1": round(totals[1], 3),
               "epsilon": round(epsilon, 3), "spawn_gap": spawn_dx,
               "spawn_dy": spawn_dy,
               "map": str(args.lmf) if args.lmf else "flat_baseline",
               "hp": [info["players"][r]["hp"] for r in (0, 1)]}
        line = json.dumps(row, ensure_ascii=False)
        print(line, flush=True)
        args.log.parent.mkdir(parents=True, exist_ok=True)
        with args.log.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        temporary_checkpoint = args.checkpoint.with_suffix(args.checkpoint.suffix + ".tmp")
        torch.save({"schema": 1, "episode": episode,
                    "observation_size": env.observation_size, "action_size": env.action_size,
                    "observation_schema": env.observation_schema,
                    "brain_task": "combat",
                    "model": online.state_dict(), "target": target.state_dict(),
                    "optimizer": optimizer.state_dict()}, temporary_checkpoint)
        temporary_checkpoint.replace(args.checkpoint)
        write_status({**row, "state": "episode_complete", "tick": env.steps,
                      "max_steps": args.max_steps, "progress_percent": 100.0})


if __name__ == "__main__":
    main()
