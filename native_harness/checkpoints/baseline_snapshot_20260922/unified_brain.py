"""Shared feature space and policy trunk for movement, mechanics and combat."""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import torch
from torch import nn


TASKS = ("navigate", "mechanic", "combat")
UNIVERSAL_ACTIONS = (
    (), ("LEFT",), ("RIGHT",), ("UP",), ("DOWN",), ("C",),
    ("LEFT", "UP"), ("RIGHT", "UP"), ("LEFT", "DOWN"), ("RIGHT", "DOWN"),
    ("LEFT", "C"), ("RIGHT", "C"), ("UP", "C"),
    ("Z",), ("LEFT", "Z"), ("RIGHT", "Z"), ("UP", "Z"), ("DOWN", "Z"),
    ("X",), ("1",), ("2",), ("3",), ("4",),
    ("LEFT", "DOWN", "Z"), ("RIGHT", "DOWN", "Z"),
)

ALIASES = {
    "player_x": "self_x", "player_y": "self_y",
    "vertical_motion": "self_vertical_motion", "state38": "self_state38",
    "animation3c": "self_animation3c", "state68": "self_state68",
    "direction74": "self_direction74", "damage7c": "self_damage7c",
    "state80": "self_state80", "facing_b0": "self_facing_b0",
    "action_c0": "self_action_c0", "parachute_dc": "self_parachute_dc",
}


def canonical_feature(name):
    return ALIASES.get(name, name)


def merged_schema(*schemas):
    common = []
    for schema in schemas:
        for name in schema:
            name = canonical_feature(name)
            if name not in common:
                common.append(name)
    return [f"task_{task}" for task in TASKS] + common


@dataclass
class FeatureProjector:
    source_schema: list[str]
    unified_schema: list[str]
    task: str

    def __post_init__(self):
        if self.task not in TASKS:
            raise ValueError(f"unknown task: {self.task}")
        destination = {name: index for index, name in enumerate(self.unified_schema)}
        self.mapping = [(source, destination[canonical_feature(name)])
                        for source, name in enumerate(self.source_schema)
                        if canonical_feature(name) in destination]

    def __call__(self, observation):
        result = np.zeros(len(self.unified_schema), dtype=np.float32)
        result[self.unified_schema.index(f"task_{self.task}")] = 1.0
        for source, destination in self.mapping:
            result[destination] = observation[source]
        return result


def action_indices(actions):
    lookup = {keys: index for index, keys in enumerate(UNIVERSAL_ACTIONS)}
    return [lookup[tuple(keys)] for keys in actions]


class UnifiedQNetwork(nn.Module):
    """One shared representation with small task heads and a common action language."""
    def __init__(self, inputs, hidden=384):
        super().__init__()
        self.trunk = nn.Sequential(nn.Linear(inputs, hidden), nn.ReLU(),
                                   nn.Linear(hidden, hidden), nn.ReLU())
        self.heads = nn.ModuleDict({task: nn.Linear(hidden, len(UNIVERSAL_ACTIONS))
                                    for task in TASKS})

    def forward(self, values, task):
        return self.heads[task](self.trunk(values))
