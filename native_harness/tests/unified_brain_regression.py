"""The shared brain must preserve common state semantics and every native action."""
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from combat_env import COMBAT_ACTIONS
from combat_env import LostWeaponCombatEnv
from native_env import ACTIONS
from unified_brain import (FeatureProjector, UnifiedQNetwork, action_indices,
                           merged_schema)

map_schema = ["player_x", "player_y", "vertical_motion", "grid0_dx0_dy0"]
combat_schema = ["self_x", "self_y", "self_vertical_motion", "opponent_hp",
                 "grid0_dx0_dy0"]
schema = merged_schema(map_schema, combat_schema)
mapped = FeatureProjector(map_schema, schema, "navigate")(
    np.asarray([.25, .5, -.1, 1.0], dtype=np.float32))
combat = FeatureProjector(combat_schema, schema, "combat")(
    np.asarray([.25, .5, -.1, .8, 1.0], dtype=np.float32))
assert mapped[schema.index("self_x")] == combat[schema.index("self_x")] == .25
assert mapped[schema.index("task_navigate")] == 1 and combat[schema.index("task_combat")] == 1
assert len(action_indices(ACTIONS)) == len(ACTIONS)
assert len(action_indices(COMBAT_ACTIONS)) == len(COMBAT_ACTIONS)
schema_probe = object.__new__(LostWeaponCombatEnv)
schema_probe.crop = 9
assert len(schema_probe.observation_schema) == schema_probe.observation_size == 402
brain = UnifiedQNetwork(len(schema), hidden=16)
assert brain(torch.from_numpy(mapped), "navigate").shape == (25,)
assert brain(torch.from_numpy(combat), "combat").shape == (25,)
print({"ok": True, "features": len(schema), "universal_actions": 25,
       "shared_trunk": True, "task_heads": ["navigate", "mechanic", "combat"]})
