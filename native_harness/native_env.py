"""Small dependency-free RL environment around the original Client x86 oracle."""
from __future__ import annotations

from pathlib import Path
import math
import struct

import numpy as np

from api import NativeTrainingAPI
from global_planner import GlobalMapPlanner
from restriction_fields import KINDS, RestrictionFields, filter_actions


# One decision is held for ``action_repeat`` native ticks.  Combinations are
# deliberate: rolls, parachute steering and crouch movement are game actions,
# not physics approximations made by the trainer.
ACTIONS = (
    (), ("LEFT",), ("RIGHT",), ("UP",), ("DOWN",), ("C",),
    ("LEFT", "UP"), ("RIGHT", "UP"),
    ("LEFT", "DOWN"), ("RIGHT", "DOWN"),
    ("LEFT", "C"), ("RIGHT", "C"), ("UP", "C"),
    ("Z",), ("X",), ("1",), ("2",), ("3",), ("4",),
    # Append only: archived route/action indices 0..18 must stay stable.
    ("LEFT", "DOWN", "Z"), ("RIGHT", "DOWN", "Z"),
)
INPUT_FEATURES = ("LEFT", "RIGHT", "UP", "DOWN", "C", "Z", "X",
                  "1", "2", "3", "4")
OBJECT_ID_BITS = 8


class LostWeaponEnv:
    """Gym-shaped API without requiring Gymnasium.

    Observation = normalized player fields, nearest-goal vector, and a local
    crop of all four collision grids.  The physics transition itself always
    comes from NativeTrainingAPI/original Client instructions.
    """

    def __init__(self, snapshot: str | Path, lmf: str | Path, *, crop=9,
                 action_repeat=2, max_steps=3000, global_size=16,
                 restriction_ids=None):
        if crop < 3:
            raise ValueError("crop must be >= 3")
        self.api = NativeTrainingAPI(Path(snapshot), Path(lmf), track_dirty=True)
        self.width, self.height, self.records = self.api.oracle.parse_lmf(Path(lmf))
        self.goals = [(x, y) for tile, x, y in self.records if tile == 140]
        self.restrictions = RestrictionFields(self.records, restriction_ids)
        if not self.goals:
            raise ValueError("LMF has no ID 140 goal")
        self.crop = crop
        self.global_size = int(global_size)
        if self.global_size < 4:
            raise ValueError("global_size must be >= 4")
        self.action_repeat = int(action_repeat)
        self.max_steps = int(max_steps)
        self._start = self.api.save_state()
        self.steps = 0
        self.visited = set()
        self.global_visits = {}
        self.last_keys = ()
        self.last_goal_distance = 0.0
        self.global_map = self._build_global_map()
        grid1_pointer = self.api.oracle.get(self.api.oracle.GRID_POINTERS[1], "I")[0]
        grid1_raw = self.api.oracle.u.mem_read(grid1_pointer, self.width * self.height * 2)
        self.planner = GlobalMapPlanner(
            self.width, self.height, self.records,
            struct.unpack(f"<{self.width*self.height}H", grid1_raw))
        self.mechanic_profile = self.planner.mechanic_profile()
        # Preserve each LMF raw ID without assigning its behavior by hand.
        # The policy must learn what those identity bits mean through contact.
        self.object_ids = {}
        for tile_id, x, y in self.records:
            self.object_ids[(x, y)] = self.object_ids.get((x, y), 0) | int(tile_id)

    @property
    def observation_size(self):
        return (16 + len(KINDS) + len(INPUT_FEATURES) +
                (4 + OBJECT_ID_BITS) * self.crop * self.crop +
                4 * self.global_size * self.global_size)

    def valid_action_indices(self, state=None):
        """Return inputs the Client can act on in the current native state."""
        state = state or self.api.read_state()
        active = self.restrictions.active_at(state["x"], state["y"]) if hasattr(
            self, "restrictions") else set()
        return self._valid_actions_for(state, active)

    def valid_action_indices_from_observation(self, observation):
        """Rebuild the same mask for stored next states during Q updates."""
        state = {"38": round(float(observation[3]) * 32),
                 "74": round(float(observation[6]) * 32),
                 "c0": round(float(observation[10]) * 8),
                 "dc": round(float(observation[11]) * 4)}
        active = {kind for offset, kind in enumerate(KINDS)
                  if float(observation[14 + offset]) > 0.5}
        return self._valid_actions_for(state, active)

    @staticmethod
    def _valid_actions_for(state, active):
        # Do not mask hit/knockdown inputs. The Client may ignore them during
        # locked frames, but repeated roll/Z input can catch the first recovery
        # frame. Native timing decides the outcome.
        # Native ladder parity identifies the climbing state as state38=0,
        # state74=1. Horizontal-only, downward diagonals, C and Z do nothing;
        # vertical/upward-diagonal movement, X and number keys remain usable.
        ladder = state.get("38") == 0 and state.get("74") == 1
        water = state.get("c0") == 21
        st38 = state.get("38")
        c0 = state.get("c0")

        if ladder:
            allowed = (0, 3, 4, 6, 7, 14, 15, 16, 17, 18)
        elif water:
            allowed = (0, 1, 2, 3, 4, 6, 7, 8, 9, 14)
        elif state.get("dc"):
            # While open, horizontal steering and C (collapse) remain meaningful.
            allowed = (0, 1, 2, 5, 10, 11, 14, 15, 16, 17, 18)
        elif c0 in (3, 4) or st38 == 2:
            # Rolling: UP (3, 6, 7, 12) and single LEFT/RIGHT (1, 2) are completely ignored.
            # Only neutral, late parachute (5, 10, 11), attack (13), and weapon slots are valid.
            allowed = (0, 5, 10, 11, 13, 14, 15, 16, 17, 18, 19, 20)
        elif st38 == 9:
            # In-air jumping/falling: in-air UP (double jump: 3, 6, 7, 12) is completely blocked.
            allowed = (0, 1, 2, 4, 5, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18)
        elif st38 == 6:
            # Crouch: walking (1, 2) is blocked; roll (8, 9), jump/stand (3, 6, 7), attack (13) allowed.
            allowed = (0, 3, 4, 6, 7, 8, 9, 13, 14, 15, 16, 17, 18, 19, 20)
        else:
            allowed = tuple(index for index in range(len(ACTIONS)) if index != 12)
        return filter_actions(ACTIONS, allowed, active, up_is_jump=not (ladder or water))

    @property
    def observation_schema(self):
        scalars = [
            "player_x", "player_y", "vertical_motion", "state38", "animation3c",
            "state68", "direction74", "damage7c", "state80", "facing_b0",
            "action_c0", "parachute_dc", "goal_dx", "goal_dy",
        ]
        scalars += [f"restriction_{kind}" for kind in KINDS]
        scalars += ["route_next_edge_dx", "route_next_gap_width"]
        inputs = [f"held_{key}" for key in INPUT_FEATURES]
        first = -(self.crop // 2)
        last = first + self.crop
        grids = [f"grid{grid}_dx{dx}_dy{dy}"
                 for grid in range(4)
                 for dy in range(first, last)
                 for dx in range(first, last)]
        object_ids = [f"object_id_bit{bit}_dx{dx}_dy{dy}"
                      for bit in range(OBJECT_ID_BITS)
                      for dy in range(first, last)
                      for dx in range(first, last)]
        global_cells = [f"global_grid{grid}_x{x}_y{y}"
                        for grid in range(4)
                        for y in range(self.global_size)
                        for x in range(self.global_size)]
        return scalars + inputs + grids + object_ids + global_cells

    def _build_global_map(self):
        """Max-pool original collision grids into a fixed-size global view."""
        output = []
        size = self.global_size
        for pointer_global in self.api.oracle.GRID_POINTERS:
            pointer = self.api.oracle.get(pointer_global, "I")[0]
            raw = self.api.oracle.u.mem_read(pointer, self.width * self.height * 2)
            source = np.frombuffer(raw, dtype="<u2").reshape(self.height, self.width)
            pooled = np.zeros((size, size), dtype=np.float32)
            for gy in range(size):
                y0, y1 = gy * self.height // size, (gy + 1) * self.height // size
                for gx in range(size):
                    x0, x1 = gx * self.width // size, (gx + 1) * self.width // size
                    cell = source[y0:max(y0 + 1, y1), x0:max(x0 + 1, x1)]
                    pooled[gy, gx] = min(int(cell.max(initial=0)), 1024) / 1024.0
            output.append(pooled.reshape(-1))
        return np.concatenate(output)

    @property
    def action_size(self):
        return len(ACTIONS)

    def _nearest_goal(self, state):
        px, py = state["x"] / 32.0, state["y"] / 32.0
        return min(self.goals, key=lambda g: (g[0] - px) ** 2 + (g[1] - py) ** 2)

    def reached_goal(self, state):
        px, py = state["x"], state["y"]
        return any(gx * 32 - 24 <= px <= gx * 32 + 32 and
                   gy * 32 <= py <= gy * 32 + 64 for gx, gy in self.goals)

    def _goal_distance(self, state):
        gx, gy = self._nearest_goal(state)
        return math.hypot(gx - state["x"] / 32.0, gy - state["y"] / 32.0)

    def _route_geometry(self, state, goal):
        """Distance to the next unsupported span toward the flag, in tiles."""
        px, py = state["x"] / 32.0, state["y"] / 32.0
        direction = 1 if goal[0] >= px else -1
        surface = self.planner.surface_below((int(px), int(py)))
        if surface is None:
            return 1.0, 0.0
        edge = surface.x1 + 1 if direction > 0 else surface.x0
        distance = (edge - px) if direction > 0 else (px - edge)
        if (goal[0] - px) * direction <= distance:
            return 1.0, 0.0
        next_surfaces = [row for row in self.planner.surfaces
                         if row.y == surface.y and
                         ((row.x0 > surface.x1) if direction > 0
                          else (row.x1 < surface.x0))]
        if not next_surfaces:
            return min(1.0, max(0.0, distance) / self.width), 1.0
        next_surface = min(next_surfaces, key=lambda row: row.x0 - surface.x1)
        if direction < 0:
            next_surface = max(next_surfaces, key=lambda row: row.x1)
        gap = (next_surface.x0 - surface.x1 - 1 if direction > 0
               else surface.x0 - next_surface.x1 - 1)
        return (min(1.0, max(0.0, distance) / self.width),
                min(1.0, max(0, gap) / self.width))

    def navigation_view(self, state=None, size=3):
        """Read a fresh player-centred tile window from the native world.

        This is a planning sensor, separate from the saved DQN input schema.
        It does not assume that an empty tile is safely reachable: hazards and
        movement timing still require native execution.
        """
        if not 3 <= size <= 21 or size % 2 != 1:
            raise ValueError("navigation view size must be odd and 3..21 tiles")
        state = state or self.api.read_state()
        px, py = int(state["x"] // 32), int(state["y"] // 32)
        x0, y0 = px - size // 2, py - size // 2
        pointers = [self.api.oracle.get(address, "I")[0]
                    for address in self.api.oracle.GRID_POINTERS]
        cells = []
        for y in range(y0, y0 + size):
            row = []
            for x in range(x0, x0 + size):
                if 0 <= x < self.width and 0 <= y < self.height:
                    grids = [self.api.oracle.get(pointer + 2 * (y * self.width + x), "H")[0]
                             for pointer in pointers]
                    tile = self.object_ids.get((x, y), 0)
                    row.append({"x": x, "y": y, "solid": bool(grids[1]),
                                "grids": grids, "object_id": tile})
                else:
                    row.append({"x": x, "y": y, "solid": True,
                                "grids": None, "object_id": 0})
            cells.append(row)
        goal = self._nearest_goal(state)
        return {"player_xy": [float(state["x"]), float(state["y"])],
                "player_tile": [px, py], "goal_tile": list(goal),
                "window_origin": [x0, y0], "size": size, "cells": cells}

    def adaptive_navigation_view(self, state=None, *, minimum_size=3, maximum_size=21):
        """Read one small native crop; enlarge near a gap or blocked forward tile.

        The cached full-map collision topology is used only to choose crop size.
        This is a sensor policy, not a claim that a route is already safe.
        """
        if not (3 <= minimum_size <= maximum_size <= 21
                and minimum_size % 2 and maximum_size % 2):
            raise ValueError("navigation view range must be odd and fit 3..21 tiles")
        state = state or self.api.read_state()
        px = int(state["x"] // 32)
        goal = self._nearest_goal(state)
        direction = 1 if goal[0] >= px else -1
        surface = self.planner.surface_below((px, int(state["y"] // 32)))
        needed = None
        if surface is not None:
            edge = surface.x1 + 1 if direction > 0 else surface.x0 - 1
            if (goal[0] - edge) * direction >= 0:
                needed = edge
        size = minimum_size
        # A roll spans several tiles; see farther only when its next landing
        # could cross a platform edge. One crop is read after choosing size.
        if needed is not None and 0 <= (needed - px) * direction <= 4:
            size = min(maximum_size, max(minimum_size, 9))
            landings = [s.x0 if direction > 0 else s.x1
                        for s in self.planner.surfaces
                        if abs(s.y - surface.y) <= 4
                        and 0 < ((s.x0 if direction > 0 else s.x1) - edge)
                        * direction <= 10]
            if landings:
                distance = min((x - px) * direction for x in landings)
                size = min(maximum_size, max(size, 2 * distance + 1))
        forward_x = px + direction
        py = int(state["y"] // 32)
        if (self.planner.solid(forward_x, py - 1)
                or self.planner.solid(forward_x, py - 2)):
            size = min(maximum_size, max(size, 7))
        view = self.navigation_view(state, size=size)
        view["next_gap_tile"] = needed
        return view

    def observe(self, state=None):
        state = state or self.api.read_state()
        gx, gy = self._nearest_goal(state)
        px, py = state["x"] / 32.0, state["y"] / 32.0
        active = self.restrictions.active_at(state["x"], state["y"])
        edge_distance, gap_width = self._route_geometry(state, (gx, gy))
        scalars = np.asarray([
            px / max(1, self.width), py / max(1, self.height),
            state["motion58"] / 1000.0,
            state["38"] / 32.0, state["3c"] / 16.0,
            state["68"] / 16.0, state["74"] / 32.0,
            state["7c"] / 32.0, state["80"] / 32.0,
            state["b0"], state["c0"] / 8.0, state["dc"] / 4.0,
            (gx - px) / max(1, self.width), (gy - py) / max(1, self.height),
            *[float(kind in active) for kind in KINDS],
            edge_distance, gap_width,
        ], dtype=np.float32)
        # GetAsyncKeyState edge/held state affects the next original Client
        # transition.  Exposing it makes the observation Markov for sequences
        # such as jump -> release -> back-roll.
        held = set(self.last_keys)
        input_state = np.asarray([1.0 if key in held else 0.0
                                  for key in INPUT_FEATURES], dtype=np.float32)
        first = -(self.crop // 2)
        last = first + self.crop
        cx, cy = int(px), int(py)
        cells = []
        for pointer_global in self.api.oracle.GRID_POINTERS:
            pointer = self.api.oracle.get(pointer_global, "I")[0]
            for y in range(cy + first, cy + last):
                x0, x1 = cx + first, cx + last
                if not 0 <= y < self.height:
                    cells.extend([1.0] * self.crop)
                    continue
                valid0, valid1 = max(0, x0), min(self.width, x1)
                cells.extend([1.0] * (valid0 - x0))
                if valid1 > valid0:
                    raw = self.api.oracle.u.mem_read(
                        pointer + 2 * (y * self.width + valid0), 2 * (valid1 - valid0))
                    values = struct.unpack(f"<{valid1-valid0}H", raw)
                    cells.extend(min(value, 1024) / 1024.0 for value in values)
                cells.extend([1.0] * (x1 - valid1))
        identity = []
        for bit in range(OBJECT_ID_BITS):
            for y in range(cy + first, cy + last):
                for x in range(cx + first, cx + last):
                    tile_id = self.object_ids.get((x, y), 0)
                    identity.append(float((tile_id >> bit) & 1))
        return np.concatenate((scalars, input_state,
                               np.asarray(cells, dtype=np.float32),
                               np.asarray(identity, dtype=np.float32), self.global_map))

    def reset(self):
        self.api.restore_state(self._start)
        self.steps = 0
        self.last_keys = ()
        state = self.api.read_state()
        cell = (round(state["x"] / 16), round(state["y"] / 16))
        self.visited = {cell}
        self.last_goal_distance = self._goal_distance(state)
        self.mechanic_events = set()
        self.mechanic_best_x = abs(float(state["x"]) - self.goals[0][0] * 32.0)
        self.mechanic_best_y = abs(float(state["y"]) - self.goals[0][1] * 32.0)
        return self.observe(state), {"state": state, "global_plan": self.planner.summary()}

    def _mechanic_reward(self, state):
        """Reward new native-confirmed mechanic milestones, never guessed outcomes."""
        mode = self.mechanic_profile["mode"]
        if mode == "platform":
            return 0.0
        reward = 0.0
        event = (round(float(state["x"]) / 32), round(float(state["y"]) / 32),
                 state.get("38"), state.get("c0"), state.get("dc"), state.get("68"))
        if event not in self.mechanic_events:
            self.mechanic_events.add(event)
            reward += 0.02
        x_distance = abs(float(state["x"]) - self.goals[0][0] * 32.0)
        y_distance = abs(float(state["y"]) - self.goals[0][1] * 32.0)
        if mode in ("air_traverse", "water", "special_transport") and x_distance < self.mechanic_best_x:
            reward += min(0.10, (self.mechanic_best_x - x_distance) / 320.0)
            self.mechanic_best_x = x_distance
        if mode in ("ladder", "special_transport") and y_distance < self.mechanic_best_y:
            reward += min(0.10, (self.mechanic_best_y - y_distance) / 320.0)
            self.mechanic_best_y = y_distance
        if mode == "air_traverse" and state.get("dc") and "parachute_open" not in self.mechanic_events:
            self.mechanic_events.add("parachute_open"); reward += 1.0
        if mode == "water" and state.get("c0") == 21 and "water_entered" not in self.mechanic_events:
            self.mechanic_events.add("water_entered"); reward += 1.0
        return reward

    def step(self, action):
        if not 0 <= int(action) < len(ACTIONS):
            raise ValueError("action index out of range")
        if int(action) not in self.valid_action_indices():
            action = 0
        previous = self.api.read_state()
        self.last_keys = ACTIONS[int(action)]
        state = self.api.step(self.action_repeat, self.last_keys)
        self.steps += 1
        distance = self._goal_distance(state)
        # Do not reward Euclidean progress toward the flag.  On maps where a
        # wall separates the player from a nearby flag, that signal teaches the
        # agent to press against the wall instead of discovering the route.
        # Every decision costs time, even when novelty signals are present.
        # A detour must not outscore a shorter native-verified clear.
        reward = -0.05
        # Animation/state changes at the same place are not exploration.
        # This prevents repeatedly opening a parachute or changing stance from
        # manufacturing novelty reward without discovering map space.
        cell = (round(state["x"] / 16), round(state["y"] / 16))
        if cell not in self.visited:
            reward += 0.01
            self.visited.add(cell)
        else:
            reward -= 0.005
        visits = self.global_visits.get(cell, 0) + 1
        self.global_visits[cell] = visits
        reward += 0.03 / math.sqrt(visits)
        reward += self._mechanic_reward(state)
        if (state["x"], state["y"], state["motion58"], state["38"]) == (
                previous["x"], previous["y"], previous["motion58"], previous["38"]):
            reward -= 0.02
        # Do not assign a generic penalty to damage/knockdown. Some user maps
        # require spikes, explosions or knockback to reach the route. Whether a
        # hit was useful is learned from the eventual clear and elapsed time.
        terminated = self.reached_goal(state)
        if terminated:
            # Earlier genuine clears are better. This is based on reaching the
            # real raw140 trigger, never on merely getting geometrically close.
            reward += 100.0 + 100.0 * (self.max_steps - self.steps) / self.max_steps
        truncated = self.steps >= self.max_steps
        self.last_goal_distance = distance
        return self.observe(state), float(reward), terminated, truncated, {
            "state": state, "keys": ACTIONS[int(action)], "goal_distance": distance,
        }
