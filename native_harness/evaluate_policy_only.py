"""Evaluate the shared DQN without route replay, planner, or exploration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from native_env import LostWeaponEnv
from snapshot_selector import snapshot_for_map
from train_local_dqn import QNetwork, load_policy_compatible


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("maps", nargs="+", type=Path)
    parser.add_argument("--checkpoint", type=Path,
                        default=Path("checkpoints/map_clear_shared_dqn.pt"))
    parser.add_argument("--max-steps", type=int, default=500)
    args = parser.parse_args()
    torch.set_num_threads(1)
    saved = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    learned_actions = int(saved.get("action_size", saved["model"]["layers.4.bias"].shape[0]))
    root = Path(__file__).resolve().parent
    for lmf in args.maps:
        env = LostWeaponEnv(snapshot_for_map(root, lmf), lmf,
                            action_repeat=2, max_steps=args.max_steps)
        network = QNetwork(env.observation_size, env.action_size)
        transfer = load_policy_compatible(network, saved["model"],
                                          saved.get("observation_schema"),
                                          env.observation_schema)
        network.eval()
        observation, reset = env.reset()
        best_distance = env._goal_distance(reset["state"])
        success = False
        final = reset["state"]
        with torch.no_grad():
            for step in range(1, args.max_steps + 1):
                # An old checkpoint has no learned Q values for appended actions.
                # Its transferred rows exist for training, not baseline scoring.
                allowed = tuple(i for i in env.valid_action_indices()
                                if i < learned_actions)
                q = network(torch.from_numpy(observation))
                mask = torch.full_like(q, float("-inf"))
                mask[list(allowed)] = 0
                action = int((q + mask).argmax())
                observation, _reward, success, truncated, info = env.step(action)
                final = info["state"]
                best_distance = min(best_distance, env._goal_distance(final))
                if success or truncated:
                    break
        print(json.dumps({"map": str(lmf.resolve()), "policy_only": True,
                          "success": success, "steps": step,
                          "best_goal_distance_tiles": round(best_distance, 2),
                          "final_xy": [round(final["x"], 1),
                                       round(final["y"], 1)],
                          "learned_actions": learned_actions,
                          "weight_transfer": transfer}, ensure_ascii=False),
              flush=True)


if __name__ == "__main__":
    main()
