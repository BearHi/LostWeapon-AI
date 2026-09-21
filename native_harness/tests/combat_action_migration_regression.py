"""Append-only combat actions keep old policy features and Q rows aligned."""
from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from combat_env import COMBAT_ACTIONS, LostWeaponCombatEnv
from train_combat_selfplay import network, load_combat_policy_compatible

assert len(COMBAT_ACTIONS) == 23
assert COMBAT_ACTIONS[-2:] == (("LEFT", "DOWN", "Z"), ("RIGHT", "DOWN", "Z"))
probe = object.__new__(LostWeaponCombatEnv)
probe.crop = 9
new_schema = probe.observation_schema
old_schema = [name for name in new_schema
              if not name.startswith("restriction_") and
              not name.endswith("LEFT+DOWN+Z") and
              not name.endswith("RIGHT+DOWN+Z")]
assert len(old_schema) == 394 and len(new_schema) == 402
old = network(len(old_schema), 21)
new = network(len(new_schema), 23)
with torch.no_grad():
    old[0].weight[:, old_schema.index("grid0_dx0_dy0")].fill_(7)
    old[4].bias.copy_(torch.arange(21, dtype=torch.float32))
result = load_combat_policy_compatible(new, old.state_dict(), old_schema, new_schema)
assert result == "mapped_features_expanded_21_to_23_actions"
assert torch.all(new[0].weight[:, new_schema.index("grid0_dx0_dy0")] == 7)
assert torch.equal(new[4].bias[:21], old[4].bias)

observation = torch.zeros(len(new_schema))
def allowed(**fields):
    observation.zero_()
    for index, value in fields.items():
        observation[int(index)] = value
    return set(probe.valid_action_indices_from_observation(observation))

roll_attacks = {21, 22}
assert roll_attacks <= allowed()
assert roll_attacks.isdisjoint(allowed(**{"4": 0, "7": 1 / 32}))
assert roll_attacks.isdisjoint(allowed(**{"11": 21 / 8}))
assert roll_attacks.isdisjoint(allowed(**{"12": 1 / 4}))
assert roll_attacks <= allowed(**{"4": 5 / 32})  # hold through hit recovery
observation.zero_()
observation[28] = 1  # parachute-ban block
assert {5, 10, 11}.isdisjoint(probe.valid_action_indices_from_observation(observation))
observation.zero_()
observation[29] = 1  # jump-ban block
assert {3, 6, 7}.isdisjoint(probe.valid_action_indices_from_observation(observation))
observation.zero_()
observation[30] = 1  # roll-ban block
assert {8, 9, 21, 22}.isdisjoint(probe.valid_action_indices_from_observation(observation))
observation.zero_()
observation[31] = 1  # weapon-ban block
assert {12, 13, 14, 15, 16, 21, 22}.isdisjoint(
    probe.valid_action_indices_from_observation(observation))
print("PASS")
