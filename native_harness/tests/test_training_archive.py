from pathlib import Path
import sys
import tempfile

import torch

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from train_local_dqn import QNetwork, load_policy_compatible
from training_archive import append_episode, rle_actions

assert rle_actions([1, 1, 2, 2, 2, 1]) == [[1, 2], [2, 3], [1, 1]]

old = QNetwork(3, 2)
new = QNetwork(4, 2)
with torch.no_grad():
    old.layers[0].weight[:, 0].fill_(1)
    old.layers[0].weight[:, 1].fill_(2)
    old.layers[0].weight[:, 2].fill_(3)
result = load_policy_compatible(new, old.state_dict(), ["a", "b", "c"],
                                ["a", "new", "b", "c"])
assert result == "mapped_3_features"
assert torch.all(new.layers[0].weight[:, 0] == 1)
assert torch.all(new.layers[0].weight[:, 2] == 2)
assert torch.all(new.layers[0].weight[:, 3] == 3)

# New roll+attack choices are appended; old learned Q rows remain unchanged.
old_actions = QNetwork(3, 19)
new_actions = QNetwork(3, 21)
with torch.no_grad():
    old_actions.layers[4].weight.fill_(0.25)
    old_actions.layers[4].bias.copy_(torch.arange(19, dtype=torch.float32))
transfer = load_policy_compatible(new_actions, old_actions.state_dict(),
                                  ["a", "b", "c"], ["a", "b", "c"])
assert transfer == "expanded_19_to_21_actions"
assert torch.equal(new_actions.layers[4].weight[:19], old_actions.layers[4].weight)
assert torch.equal(new_actions.layers[4].bias[:19], old_actions.layers[4].bias)

with tempfile.TemporaryDirectory() as directory:
    output = Path(directory) / "episodes.jsonl"
    append_episode(output, {"episode": 1, "actions_rle": [[2, 4]]})
    assert '"actions_rle":[[2,4]]' in output.read_text(encoding="utf-8")
print("PASS")
