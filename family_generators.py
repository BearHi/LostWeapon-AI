"""family_generators.py - Decoupled Known Bypass Family Generators and Semantic Contracts.

Provides decoupled candidate generation and native execution trace validation for:
  1. NormalJumpWalkFamily:
     - Permitted capabilities: walk, normal jump.
     - Forbidden: DOWN, weapon keys, roll state (state 38 == 2).
     - Semantic Invariant: strictly clean keys and character never enters roll state.
  2. DelayedBackrollFamily:
     - Permitted capabilities: directional keys + DOWN for roll trigger.
     - Forbidden: weapon attacks, item usage.
     - Semantic Invariant: strictly verifies that backroll actually activated in native x86 state
       (state 38 == 2 AND motion58 reload == 760.0). Unactivated attempts are invalidated.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple


class BaseFamily:
    name: str = "base"

    def generate_manifest(self, *args, **kwargs) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def validate_semantics(
        self,
        candidate: Dict[str, Any],
        trace: List[Dict[str, Any]],
        trial: Dict[str, Any],
    ) -> Tuple[bool, str]:
        raise NotImplementedError


class NormalJumpWalkFamily(BaseFamily):
    name: str = "normal_jump_walk"
    ALLOWED_KEYS = {"LEFT", "RIGHT", "UP"}
    FORBIDDEN_KEYS = {"DOWN", "1", "2", "3", "4", "Z", "X", "C", "A", "S", "D"}

    def generate_manifest(
        self,
        walk_ticks_list: Sequence[int] = (16,),
        jump_ticks_list: Sequence[int] = (14, 20, 28),
        post_walk_ticks: int = 50,
        direction: str = "RIGHT",
    ) -> List[Dict[str, Any]]:
        manifest: List[Dict[str, Any]] = []
        for w_ticks in walk_ticks_list:
            for j_ticks in jump_ticks_list:
                c_name = f"njw_w{w_ticks}_j{j_ticks}"
                actions: List[Tuple[str, ...]] = (
                    [(direction,)] * w_ticks
                    + [(direction, "UP")] * j_ticks
                    + [(direction,)] * post_walk_ticks
                )
                manifest.append({
                    "candidate_name": c_name,
                    "family": self.name,
                    "parameters": {
                        "walk_ticks": w_ticks,
                        "jump_ticks": j_ticks,
                        "post_walk_ticks": post_walk_ticks,
                        "direction": direction,
                    },
                    "action_sequence": actions,
                    "semantic_validator": self.validate_semantics,
                })
        return manifest

    def validate_semantics(
        self,
        candidate: Dict[str, Any],
        trace: List[Dict[str, Any]],
        trial: Dict[str, Any],
    ) -> Tuple[bool, str]:
        actions = candidate["action_sequence"]

        # 1. Key Invariant: only LEFT, RIGHT, UP, () permitted
        for t, keys in enumerate(actions):
            keys_set = set(keys)
            bad_keys = keys_set.intersection(self.FORBIDDEN_KEYS)
            if bad_keys:
                return (
                    False,
                    f"forbidden_keys_at_tick_{t}: {bad_keys} (only {self.ALLOWED_KEYS} permitted)"
                )

        # 2. Native State Invariant: character must NEVER enter roll state (38 == 2)
        roll_frames = [s["tick"] for s in trace if s.get("38") == 2]
        if roll_frames:
            return (
                False,
                f"entered_forbidden_roll_state_38==2_at_ticks: {roll_frames[:5]}"
            )

        return (
            True,
            "normal_jump_walk_verified: keys_clean=True, state38_never_2=True"
        )


class DelayedBackrollFamily(BaseFamily):
    name: str = "delayed_backroll"
    ALLOWED_KEYS = {"LEFT", "RIGHT", "UP", "DOWN"}
    FORBIDDEN_KEYS = {"1", "2", "3", "4", "Z", "X", "C", "A", "S", "D"}

    def generate_manifest(
        self,
        jump_durs: Sequence[int] = (20, 28),
        switch_delays: Sequence[int] = (0, 1),
        roll_durs: Sequence[int] = (5,),
        walk_ticks: int = 16,
        post_roll_walk: int = 120,
        forward_dir: str = "RIGHT",
        backward_dir: str = "LEFT",
    ) -> List[Dict[str, Any]]:
        manifest: List[Dict[str, Any]] = []
        for j_dur in jump_durs:
            for sw in switch_delays:
                for rd in roll_durs:
                    c_name = f"backroll_j{j_dur}_sw{sw}_rd{rd}"
                    actions: List[Tuple[str, ...]] = (
                        [(forward_dir,)] * walk_ticks
                        + [(forward_dir, "UP")] * j_dur
                        + [(forward_dir,)] * sw
                        + [(backward_dir,)]
                        + [(forward_dir, "DOWN")] * rd
                        + [(forward_dir,)] * post_roll_walk
                    )
                    manifest.append({
                        "candidate_name": c_name,
                        "family": self.name,
                        "parameters": {
                            "walk_ticks": walk_ticks,
                            "jump_duration": j_dur,
                            "switch_delay": sw,
                            "roll_duration": rd,
                            "post_roll_walk": post_roll_walk,
                        },
                        "action_sequence": actions,
                        "semantic_validator": self.validate_semantics,
                    })
        return manifest

    def validate_semantics(
        self,
        candidate: Dict[str, Any],
        trace: List[Dict[str, Any]],
        trial: Dict[str, Any],
    ) -> Tuple[bool, str]:
        actions = candidate["action_sequence"]

        # 1. Key Invariant: weapon/item keys forbidden
        for t, keys in enumerate(actions):
            keys_set = set(keys)
            bad_keys = keys_set.intersection(self.FORBIDDEN_KEYS)
            if bad_keys:
                return (
                    False,
                    f"forbidden_weapon_keys_at_tick_{t}: {bad_keys}"
                )

        # 2. Native Mechanic Activation Invariant:
        # Must observe state 38 == 2 (Rolling) and motion58 reload to 760.0
        roll_ticks = [s["tick"] for s in trace if s.get("38") == 2]
        reloaded_ticks = [s["tick"] for s in trace if s.get("motion58") == 760.0]

        if not roll_ticks:
            return (
                False,
                "backroll_never_activated: state 38 == 2 never observed in trace"
            )

        if not reloaded_ticks:
            return (
                False,
                "backroll_never_activated: motion58 == 760.0 reload never observed in trace"
            )

        first_roll_tick = roll_ticks[0]
        return (
            True,
            f"native_backroll_verified: activated_at_tick_{first_roll_tick}, "
            f"state38==2, motion58_reload==760.0"
        )
