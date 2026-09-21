"""Temporary multi-map rehearsal probe; never overwrites the shared brain."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import argparse

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from native_env import LostWeaponEnv
from snapshot_selector import snapshot_for_map
from train_local_dqn import QNetwork, load_policy_compatible

torch.set_num_threads(1)
parser = argparse.ArgumentParser()
parser.add_argument("--updates", type=int, default=600)
parser.add_argument("--recovery-rounds", type=int, default=0)
parser.add_argument("--save", type=Path,
                    help="write a separate checkpoint only if all policy-only checks clear")
args = parser.parse_args()
torch.manual_seed(7)
np.random.seed(7)
maps = [ROOT.parent / "훈련용맵" / "훈5.LMF",
        ROOT.parent / "훈련용맵" / "혼련용" / "혼2.LMF"]
archive = ROOT / "checkpoints" / "map_clear_shared_dqn.episodes.jsonl"
rows = [json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines()]
saved = torch.load(ROOT / "checkpoints" / "map_clear_shared_dqn.pt",
                   map_location="cpu", weights_only=False)
envs = []
samples = []
for lmf in maps:
    env = LostWeaponEnv(snapshot_for_map(ROOT, lmf), lmf,
                        action_repeat=2, max_steps=500)
    candidates = [row for row in rows if row.get("success") and
                  Path(row.get("map", "")).resolve() == lmf.resolve()]
    row = min(candidates, key=lambda candidate: candidate["steps"])
    actions = [action for action, count in row["actions_rle"] for _ in range(count)]
    obs, _info = env.reset()
    states = []; labels = []; native_states = []; done = False
    for action in actions:
        states.append(obs.copy()); labels.append(action)
        native_states.append(env.api.read_state())
        obs, _reward, done, truncated, _info = env.step(action)
        if done or truncated:
            break
    assert done, (lmf, row["episode"])
    envs.append(env)
    samples.append({"states": torch.from_numpy(np.stack(states)),
                    "labels": torch.tensor(labels, dtype=torch.long),
                    "native": native_states, "corrections": []})

network = QNetwork(envs[0].observation_size, envs[0].action_size)
load_policy_compatible(network, saved["model"], saved.get("observation_schema"),
                       envs[0].observation_schema)
optimizer = torch.optim.Adam(network.parameters(), lr=3e-4)
def rehearse(updates):
    network.train()
    for _ in range(updates):
        batch_states = []; batch_labels = []
        for sample in samples:
            states, labels = sample["states"], sample["labels"]
            indices = torch.randint(len(labels), (32,))
            batch_states.append(states[indices]); batch_labels.append(labels[indices])
            if sample["corrections"]:
                corrections = sample["corrections"]
                picked = torch.randint(len(corrections), (16,))
                batch_states.append(torch.from_numpy(np.stack(
                    [corrections[int(index)][0] for index in picked])))
                batch_labels.append(torch.tensor(
                    [corrections[int(index)][1] for index in picked],
                    dtype=torch.long))
        logits = network(torch.cat(batch_states))
        loss = nn.functional.cross_entropy(logits, torch.cat(batch_labels))
        optimizer.zero_grad(); loss.backward(); optimizer.step()


def teacher_action(sample, native):
    # Nearest demonstrated pose in this same map, with a strong phase penalty.
    # Only labels are reused: new transitions always come from native x86.
    distances = []
    for index, reference in enumerate(sample["native"]):
        score = ((float(native["x"]) - float(reference["x"])) ** 2 +
                 (float(native["y"]) - float(reference["y"])) ** 2 +
                 (5000 if bool(native.get("dc")) != bool(reference.get("dc")) else 0) +
                 (2000 if (native.get("38") == 0) != (reference.get("38") == 0)
                  else 0))
        distances.append(score)
    return int(sample["labels"][min(range(len(distances)), key=distances.__getitem__)])


rehearse(args.updates)
for round_index in range(args.recovery_rounds):
    for env, sample in zip(envs, samples):
        obs, _info = env.reset()
        with torch.no_grad():
            for _ in range(240):
                native = env.api.read_state()
                teacher = teacher_action(sample, native)
                if teacher in env.valid_action_indices(native):
                    sample["corrections"].append((obs.copy(), teacher))
                values = network(torch.from_numpy(obs))
                mask = torch.full_like(values, float("-inf"))
                mask[list(env.valid_action_indices(native))] = 0
                action = int((values + mask).argmax())
                obs, _reward, done, truncated, _info = env.step(action)
                if done or truncated:
                    break
        sample["corrections"] = sample["corrections"][-500:]
    print(json.dumps({"recovery_round": round_index + 1,
                      "correction_samples": [len(s["corrections"]) for s in samples]}),
          flush=True)
    rehearse(600)

all_clear = True
for env, sample, lmf in zip(envs, samples, maps):
    states, labels = sample["states"], sample["labels"]
    network.eval()
    with torch.no_grad():
        accuracy = (network(states).argmax(1) == labels).float().mean().item()
        obs, _info = env.reset(); done = False
        for step in range(1, 501):
            values = network(torch.from_numpy(obs))
            mask = torch.full_like(values, float("-inf"))
            mask[list(env.valid_action_indices())] = 0
            action = int((values + mask).argmax())
            obs, _reward, done, truncated, info = env.step(action)
            if done or truncated:
                break
    print(json.dumps({"map": lmf.stem, "imitation_accuracy": round(accuracy, 3),
                      "policy_only_clear": done, "steps": step,
                      "final_xy": [round(info["state"]["x"], 1),
                                   round(info["state"]["y"], 1)]},
                     ensure_ascii=False), flush=True)
    all_clear = all_clear and done

if args.save:
    if not all_clear:
        raise SystemExit("not saved: at least one policy-only map failed")
    args.save.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model": network.state_dict(),
                "observation_size": envs[0].observation_size,
                "observation_schema": envs[0].observation_schema,
                "action_size": envs[0].action_size,
                "brain_task": "navigate_balanced_probe",
                "training_maps": [str(path.resolve()) for path in maps],
                "policy_only_verified": True,
                "rehearsal_updates": args.updates}, args.save)
    print(json.dumps({"saved": str(args.save.resolve()),
                      "verified_maps": len(maps)}, ensure_ascii=False), flush=True)
