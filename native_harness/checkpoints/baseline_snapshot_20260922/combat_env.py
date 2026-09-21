"""Self-play environment backed by a real two-player Client capture."""
from __future__ import annotations
from pathlib import Path
import random
import struct

import numpy as np

from combat_oracle import (TwoPlayerCombatOracle, DualPerspectiveCombatOracle,
                           DualPerspectiveLmfCombatOracle)
from restriction_fields import KINDS, RestrictionFields, filter_actions


COMBAT_ACTIONS = (
    (), ("LEFT",), ("RIGHT",), ("UP",), ("DOWN",), ("C",),
    ("LEFT", "UP"), ("RIGHT", "UP"),
    ("LEFT", "DOWN"), ("RIGHT", "DOWN"),
    ("LEFT", "C"), ("RIGHT", "C"),
    ("Z",), ("LEFT", "Z"), ("RIGHT", "Z"),
    ("UP", "Z"), ("DOWN", "Z"),
    ("1",), ("2",), ("3",), ("4",),
    # Append only so earlier combat checkpoint output rows keep their meaning.
    ("LEFT", "DOWN", "Z"), ("RIGHT", "DOWN", "Z"),
)


class LostWeaponCombatEnv:
    """Symmetric two-policy environment; no scripted combat decisions."""

    def __init__(self, snapshot: str | Path, *, peer_snapshot: str | Path | None = None,
                 lmf: str | Path | None = None, crop=9, max_steps=4000,
                 validate_capture=True):
        if crop < 3 or crop % 2 == 0:
            raise ValueError("crop must be an odd integer >= 3")
        if lmf and peer_snapshot:
            self.oracle = DualPerspectiveLmfCombatOracle(Path(snapshot), Path(peer_snapshot), Path(lmf))
        else:
            self.oracle = (DualPerspectiveCombatOracle(Path(snapshot), Path(peer_snapshot))
                           if peer_snapshot else TwoPlayerCombatOracle(Path(snapshot)))
        self.width, self.height = self.oracle.get(0x8952DB0, "ii")
        # Flat, hazard-free lane established by the controlled P2P hit fixture
        # (attacker/target at x=700/760). Distances vary around this lane.
        self.duel_center_x = 740.0
        self.lmf = Path(lmf).resolve() if lmf else None
        records = self.oracle.primary.parse_lmf(self.lmf)[2] if self.lmf else []
        self.restrictions = RestrictionFields(records)
        self.crop = crop
        self.max_steps = int(max_steps)
        self.spawn_pairs = self._find_spawn_pairs() if self.lmf else []
        self.oracle.begin_branching()
        self.capture_settle_ticks = 0
        self.capture_settle_damage = {0: 0.0, 1: 0.0}
        if validate_capture and not self.lmf:
            # Reject captures with a queued server hit instead of silently
            # teaching that repeated artifact. A safe P2P snapshot remains at
            # full HP throughout this short NOOP preflight.
            center = self.duel_center_x
            ground_y = max(self.oracle.read_combatant(r)["y"] for r in (0, 1))
            self.oracle.place_combatant(0, center - 40, ground_y, hp=100,
                                        facing_right=True)
            self.oracle.place_combatant(1, center + 40, ground_y, hp=100,
                                        facing_right=False)
            previous = {r: self.oracle.read_combatant(r) for r in (0, 1)}
            for tick in range(1, 65):
                current = self.oracle.step_combat_tick({0: (), 1: ()})
                for roster in (0, 1):
                    loss = max(0.0, previous[roster]["hp"] - current[roster]["hp"])
                    self.capture_settle_damage[roster] += loss
                previous = current
                self.capture_settle_ticks = tick
            if any(self.capture_settle_damage.values()):
                raise RuntimeError(
                    f"combat capture has queued damage: {self.capture_settle_damage}")
            self.oracle.restore_branch()
        self._start = self.oracle.save_branch_snapshot()
        self.steps = 0
        self.last_inputs = {0: (), 1: ()}
        self.attack_age = {0: 999, 1: 999}

    def _find_spawn_pairs(self):
        """Find hazard-free standing cells without supplying a map solution."""
        _, _, records = self.oracle.primary.parse_lmf(self.lmf)
        hazards = {(x, y) for tile, x, y in records
                   if tile in (43, 48, 86, 87, 88, 95, 96, 119, 126)}
        pointer = self.oracle.get(0x8952DEC, "I")[0]
        raw = self.oracle.u.mem_read(pointer, self.width * self.height * 2)
        grid = struct.unpack(f"<{self.width*self.height}H", raw)
        def solid(x, y):
            return not (0 <= x < self.width and 0 <= y < self.height) or grid[y*self.width+x] != 0
        safe = []
        for y in range(2, self.height):
            for x in range(1, self.width - 1):
                if solid(x, y) and not solid(x, y-1) and not solid(x, y-2):
                    if all(abs(x-hx) > 2 or abs((y-1)-hy) > 2 for hx,hy in hazards):
                        safe.append((x*32.0+16.0, y*32.0))
        pairs = []
        for i, a in enumerate(safe):
            for b in safe[i+1:]:
                dx, dy = abs(a[0]-b[0]), abs(a[1]-b[1])
                if 64 <= dx <= 384 and dy <= 256:
                    pairs.append((a, b))
                    if len(pairs) >= 512: return pairs
        if not pairs:
            raise ValueError("LMF has no two safe combat starting cells")
        return pairs

    @property
    def action_size(self):
        return len(COMBAT_ACTIONS)

    @staticmethod
    def valid_action_indices_from_observation(observation):
        """Mask only inputs known to be ineffective in definite native states."""
        state38 = round(float(observation[4]) * 32)
        direction74 = round(float(observation[7]) * 32)
        action_c0 = round(float(observation[11]) * 8)
        chute_dc = round(float(observation[12]) * 4)
        ladder = state38 == 0 and direction74 == 1
        water = action_c0 == 21
        if ladder:
            allowed = tuple(i for i, keys in enumerate(COMBAT_ACTIONS)
                         if not keys or keys in (("UP",), ("DOWN",),
                                                  ("LEFT", "UP"), ("RIGHT", "UP"))
                         or len(keys) == 1 and keys[0] in "1234")
        elif water:
            allowed = tuple(i for i, keys in enumerate(COMBAT_ACTIONS)
                         if not keys or set(keys) <= {"LEFT", "RIGHT", "UP", "DOWN"})
        elif chute_dc:
            allowed = tuple(i for i, keys in enumerate(COMBAT_ACTIONS)
                         if not keys or keys in (("LEFT",), ("RIGHT",), ("C",),
                                                  ("LEFT", "C"), ("RIGHT", "C"))
                         or len(keys) == 1 and keys[0] in "1234")
        else:
            allowed = tuple(range(len(COMBAT_ACTIONS)))
        active = {kind for offset, kind in enumerate(KINDS)
                  if float(observation[28 + offset]) > 0.5}
        return filter_actions(COMBAT_ACTIONS, allowed, active,
                              up_is_jump=not (ladder or water))

    @property
    def observation_size(self):
        # Opponent keys are unavailable online. Observe their resulting state instead.
        return 28 + len(KINDS) + self.action_size + 4 * self.crop * self.crop

    @property
    def observation_schema(self):
        actor = ("x", "y", "vertical_motion", "hp", "state38", "animation3c",
                 "state68", "direction74", "damage7c", "state80", "facing_b0",
                 "action_c0", "parachute_dc", "weapon")
        values = [f"self_{name}" for name in actor]
        values += [f"opponent_{name}" for name in actor]
        values += [f"restriction_{kind}" for kind in KINDS]
        values += [f"self_last_{'+'.join(keys) or 'NOOP'}" for keys in COMBAT_ACTIONS]
        half = self.crop // 2
        values += [f"grid{grid}_dx{dx}_dy{dy}" for grid in range(4)
                   for dy in range(-half, half + 1)
                   for dx in range(-half, half + 1)]
        return values

    def _local_grids(self, state):
        half = self.crop // 2
        cx, cy = int(state["x"] // 32), int(state["y"] // 32)
        cells = []
        for pointer_global in (0x8952DCC, 0x8952DEC, 0x8952E2C, 0x8952E4C):
            pointer = self.oracle.get(pointer_global, "I")[0]
            for y in range(cy - half, cy + half + 1):
                x0, x1 = cx - half, cx + half + 1
                if not 0 <= y < self.height:
                    cells.extend([1.0] * self.crop)
                    continue
                valid0, valid1 = max(0, x0), min(self.width, x1)
                cells.extend([1.0] * (valid0 - x0))
                if valid1 > valid0:
                    raw = self.oracle.u.mem_read(pointer + 2 * (y * self.width + valid0),
                                                 2 * (valid1 - valid0))
                    values = struct.unpack(f"<{valid1-valid0}H", raw)
                    cells.extend(min(value, 1024) / 1024.0 for value in values)
                cells.extend([1.0] * (x1 - valid1))
        return cells

    @staticmethod
    def _action_index(keys):
        try:
            return COMBAT_ACTIONS.index(tuple(keys))
        except ValueError:
            return 0

    def observe(self, roster):
        opponent = 1 - int(roster)
        own = self.oracle.read_combatant(roster)
        other = self.oracle.read_combatant(opponent)
        own_values = [
            own["x"] / max(1, self.width * 32), own["y"] / max(1, self.height * 32),
            own["motion58"] / 2000, own["hp"] / 100,
            own["38"] / 32, own["3c"] / 16, own["68"] / 16,
            own["74"] / 32, own["7c"] / 32, own["80"] / 32,
            own["b0"], own["c0"] / 8, own["dc"] / 4, own["weapon"] / 4,
        ]
        relative = [
            (other["x"] - own["x"]) / max(1, self.width * 32),
            (other["y"] - own["y"]) / max(1, self.height * 32),
            other["motion58"] / 2000, other["hp"] / 100,
            other["38"] / 32, other["3c"] / 16, other["68"] / 16,
            other["74"] / 32, other["7c"] / 32, other["80"] / 32,
            other["b0"], other["c0"] / 8, other["dc"] / 4, other["weapon"] / 4,
        ]
        actions = np.zeros(self.action_size, dtype=np.float32)
        actions[self._action_index(self.last_inputs[roster])] = 1
        active = self.restrictions.active_at(own["x"], own["y"])
        bans = [float(kind in active) for kind in KINDS]
        return np.concatenate((np.asarray(own_values + relative + bans, dtype=np.float32),
                               actions,
                               np.asarray(self._local_grids(own), dtype=np.float32)))

    def reset(self, *, spawn_distance=None):
        self.oracle.restore_branch_snapshot(self._start)
        if self.spawn_pairs:
            if spawn_distance is None:
                pair = random.choice(self.spawn_pairs)
            else:
                target = max(48.0, float(spawn_distance))
                def score(candidate):
                    (ax, ay), (bx, by) = candidate
                    return abs(abs(ax - bx) - target) + 0.5 * abs(ay - by)
                best = min(map(score, self.spawn_pairs))
                nearby = [candidate for candidate in self.spawn_pairs
                          if score(candidate) <= best + 32]
                pair = random.choice(nearby)
            (x0, y0), (x1, y1) = pair
            self.oracle.place_combatant(0, x0, y0, hp=100, facing_right=x0 < x1)
            self.oracle.place_combatant(1, x1, y1, hp=100, facing_right=x1 < x0)
        elif spawn_distance is not None:
            distance = max(48.0, float(spawn_distance))
            center = self.duel_center_x
            ground_y = max(self.oracle.read_combatant(r)["y"] for r in (0, 1))
            self.oracle.place_combatant(0, center - distance / 2, ground_y,
                                        facing_right=True)
            self.oracle.place_combatant(1, center + distance / 2, ground_y,
                                        facing_right=False)
        self.steps = 0
        self.last_inputs = {0: (), 1: ()}
        self.attack_age = {0: 999, 1: 999}
        return {roster: self.observe(roster) for roster in (0, 1)}, {
            "players": {roster: self.oracle.read_combatant(roster) for roster in (0, 1)},
            "capture_preflight_ticks": self.capture_settle_ticks,
            "capture_preflight_damage": dict(self.capture_settle_damage)}

    def step(self, actions):
        chosen = {roster: COMBAT_ACTIONS[int(actions[roster])] for roster in (0, 1)}
        before = {roster: self.oracle.read_combatant(roster) for roster in (0, 1)}
        after = self.oracle.step_combat_tick(chosen)
        self.last_inputs = chosen
        self.steps += 1
        for roster in (0, 1):
            if "Z" in chosen[roster] or 15 <= after[roster]["38"] <= 18:
                self.attack_age[roster] = 0
            else:
                self.attack_age[roster] += 1
        rewards = {}
        for roster in (0, 1):
            opponent = 1 - roster
            raw_opponent_loss = max(0.0, before[opponent]["hp"] - after[opponent]["hp"])
            # A captured team room also contains self-inflicted inactivity
            # explosions. Until the native damage-source field is identified,
            # only a recent attack can earn dealt-damage credit. The victim
            # still receives the ordinary taken-damage penalty.
            dealt = raw_opponent_loss if self.attack_age[roster] <= 12 else 0.0
            taken = max(0.0, before[roster]["hp"] - after[roster]["hp"])
            rewards[roster] = dealt - taken - 0.001
        terminated = any(after[roster]["hp"] <= 0 for roster in (0, 1))
        if terminated:
            for roster in (0, 1):
                if after[1 - roster]["hp"] <= 0 < after[roster]["hp"]:
                    rewards[roster] += 100
                elif after[roster]["hp"] <= 0 < after[1 - roster]["hp"]:
                    rewards[roster] -= 100
        truncated = self.steps >= self.max_steps
        observations = {roster: self.observe(roster) for roster in (0, 1)}
        return observations, rewards, terminated, truncated, {
            "players": after, "inputs": chosen, "attack_age": dict(self.attack_age)}
