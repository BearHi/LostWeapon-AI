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
  3. Weapon1MobilityFamily:
     - Permitted capabilities: directional keys, jump, weapon 1 equip ('1'), knife slash ('Z').
     - Forbidden: DOWN, weapon 2..4, item keys.
     - Semantic Invariant: strictly verifies that aerial knife dash activated in native x86 state
       (state 38 == 15).
  4. ParachuteFamily:
     - Permitted capabilities: directional keys, jump, parachute deploy ('C').
     - Forbidden: DOWN, weapon keys (1..4, Z, X).
     - Semantic Invariant: strictly verifies that parachute glide activated in native x86 state
       (state 38 == 3 or dc == 1).
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


class Weapon1MobilityFamily(BaseFamily):
    name: str = "weapon1_mobility"
    ALLOWED_KEYS = {"LEFT", "RIGHT", "UP", "1", "Z"}
    FORBIDDEN_KEYS = {"DOWN", "2", "3", "4", "X", "C", "A", "S", "D"}

    def generate_manifest(
        self,
        jump_durs: Sequence[int] = (14,),
        attack_delays: Sequence[int] = (1,),
        walk_ticks: int = 16,
        post_dash_walk: int = 100,
        direction: str = "RIGHT",
    ) -> List[Dict[str, Any]]:
        manifest: List[Dict[str, Any]] = []
        for j_dur in jump_durs:
            for atk_del in attack_delays:
                c_name = f"w1_dash_j{j_dur}_del{atk_del}"
                del_ticks = max(0, atk_del - 1)
                actions: List[Tuple[str, ...]] = (
                    [("1",)]
                    + [(direction,)] * walk_ticks
                    + [(direction, "UP")] * j_dur
                    + [(direction,)] * del_ticks
                    + [(direction, "Z")]
                    + [(direction,)] * post_dash_walk
                )
                manifest.append({
                    "candidate_name": c_name,
                    "family": self.name,
                    "parameters": {
                        "walk_ticks": walk_ticks,
                        "jump_duration": j_dur,
                        "attack_delay": atk_del,
                        "post_dash_walk": post_dash_walk,
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

        # 1. Key Invariant: weapon 2..4, roll (DOWN), item (C) forbidden
        has_w1_key = False
        has_z_key = False
        for t, keys in enumerate(actions):
            keys_set = set(keys)
            if "1" in keys_set:
                has_w1_key = True
            if "Z" in keys_set:
                has_z_key = True
            bad_keys = keys_set.intersection(self.FORBIDDEN_KEYS)
            if bad_keys:
                return (
                    False,
                    f"forbidden_keys_at_tick_{t}: {bad_keys} (only {self.ALLOWED_KEYS} permitted)",
                )

        if not has_w1_key:
            return (
                False,
                "missing_required_w1_key_in_action_sequence",
            )
        if not has_z_key:
            return (
                False,
                "missing_required_z_key_in_action_sequence",
            )

        # 2. Native State Invariant:
        # Must observe state 38 == 15 (Aerial Knife Dash / Slash)
        dash_indices = [i for i, s in enumerate(trace) if s.get("38") == 15]
        if not dash_indices:
            return (
                False,
                "weapon1_dash_never_activated: state 38 == 15 never observed in trace",
            )

        # Native Weapon & Internal dash velocity check:
        # Must observe state 38 == 15, active_weapon == 0 (Weapon 1), and dash90 >= 1000.0 (initial 1400.0)
        w1_dash_states = [s for s in trace if s.get("38") == 15 and s.get("active_weapon", 0) == 0 and s.get("dash90", 0.0) >= 1000.0]
        if not w1_dash_states:
            return (
                False,
                "weapon1_dash_evidence_missing: required state38==15, active_weapon==0, dash90>=1000.0",
            )
        max_dash_v90 = max(s.get("dash90", 0.0) for s in w1_dash_states)

        # Must not enter roll (38 == 2) or parachute glide (38 == 3)
        roll_ticks = [s["tick"] for s in trace if s.get("38") == 2]
        if roll_ticks:
            return (
                False,
                f"forbidden_roll_state_in_weapon1_at_ticks: {roll_ticks[:5]}",
            )

        chute_ticks = [s["tick"] for s in trace if s.get("38") == 3]
        if chute_ticks:
            return (
                False,
                f"forbidden_parachute_state_in_weapon1_at_ticks: {chute_ticks[:5]}",
            )

        first_dash_tick = trace[dash_indices[0]]["tick"]
        return (
            True,
            f"native_weapon1_verified: activated_at_tick_{first_dash_tick}, "
            f"state38==15, active_weapon==0, internal_dash90={max_dash_v90:.1f}",
        )


class ParachuteFamily(BaseFamily):
    name: str = "parachute"
    ALLOWED_KEYS = {"LEFT", "RIGHT", "UP", "C"}
    FORBIDDEN_KEYS = {"DOWN", "1", "2", "3", "4", "Z", "X", "A", "S", "D"}

    def generate_manifest(
        self,
        jump_ticks_list: Sequence[int] = (20,),
        descent_delays: Sequence[int] = (12,),
        walk_ticks: int = 16,
        post_glide_walk: int = 120,
        direction: str = "RIGHT",
    ) -> List[Dict[str, Any]]:
        manifest: List[Dict[str, Any]] = []
        for j_ticks in jump_ticks_list:
            for d_del in descent_delays:
                c_name = f"chute_j{j_ticks}_del{d_del}"
                actions: List[Tuple[str, ...]] = (
                    [(direction,)] * walk_ticks
                    + [(direction, "UP")] * j_ticks
                    + [(direction,)] * d_del
                    + [(direction, "C")]
                    + [(direction,)] * post_glide_walk
                )
                manifest.append({
                    "candidate_name": c_name,
                    "family": self.name,
                    "parameters": {
                        "walk_ticks": walk_ticks,
                        "jump_ticks": j_ticks,
                        "descent_delay": d_del,
                        "post_glide_walk": post_glide_walk,
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

        # 1. Key Invariant: weapon attacks, weapon switches, and roll forbidden
        has_c_key = False
        for t, keys in enumerate(actions):
            keys_set = set(keys)
            if "C" in keys_set:
                has_c_key = True
            bad_keys = keys_set.intersection(self.FORBIDDEN_KEYS)
            if bad_keys:
                return (
                    False,
                    f"forbidden_keys_at_tick_{t}: {bad_keys} (only {self.ALLOWED_KEYS} permitted)",
                )

        if not has_c_key:
            return (
                False,
                "missing_required_c_key_in_action_sequence",
            )

        # 2. Native State Invariant:
        # Must observe state 38 == 3 AND dc == 1 co-occurring in the trace
        co_chute_ticks = [
            s["tick"] for s in trace
            if s.get("38") == 3 and s.get("dc") == 1
        ]
        if not co_chute_ticks:
            return (
                False,
                "parachute_never_activated: simultaneous state 38 == 3 and dc == 1 never observed in trace",
            )

        # Must not enter roll (38 == 2) or knife dash (38 == 15)
        roll_ticks = [s["tick"] for s in trace if s.get("38") == 2]
        if roll_ticks:
            return (
                False,
                f"forbidden_roll_state_in_parachute_at_ticks: {roll_ticks[:5]}",
            )

        dash_ticks = [s["tick"] for s in trace if s.get("38") == 15]
        if dash_ticks:
            return (
                False,
                f"forbidden_weapon1_state_in_parachute_at_ticks: {dash_ticks[:5]}",
            )

        first_chute_tick = co_chute_ticks[0]
        return (
            True,
            f"native_parachute_verified: activated_at_tick_{first_chute_tick}, "
            f"state38==3, dc==1 co-occurring",
        )

