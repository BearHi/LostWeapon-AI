"""Conservative whole-map topology used before learned local control.

Only collision-supported horizontal surfaces are certified here. More complex
transitions are emitted as native-validation work, never assumed possible.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True)
class Surface:
    index: int
    y: int
    x0: int
    x1: int


class GlobalMapPlanner:
    def __init__(self, width, height, records, collision_grid):
        self.width, self.height = int(width), int(height)
        self.records = list(records)
        self.grid = list(collision_grid)
        self.starts = [(x, y) for tile, x, y in records if tile == 100]
        self.goals = [(x, y) for tile, x, y in records if tile == 140]
        self.object_inventory = {}
        for tile, _x, _y in records:
            self.object_inventory[tile] = self.object_inventory.get(tile, 0) + 1
        self.surfaces = self._extract_surfaces()

    def solid(self, x, y):
        if not (0 <= x < self.width and 0 <= y < self.height):
            return True
        return self.grid[y * self.width + x] != 0

    def _extract_surfaces(self):
        result = []
        for y in range(2, self.height):
            x = 0
            while x < self.width:
                if not (self.solid(x, y) and not self.solid(x, y - 1)
                        and not self.solid(x, y - 2)):
                    x += 1
                    continue
                x0 = x
                while (x + 1 < self.width and self.solid(x + 1, y)
                       and not self.solid(x + 1, y - 1)
                       and not self.solid(x + 1, y - 2)):
                    x += 1
                result.append(Surface(len(result), y, x0, x))
                x += 1
        return result

    def surface_below(self, point, max_drop=3):
        x, y = point
        candidates = [surface for surface in self.surfaces
                      if surface.x0 <= x <= surface.x1 and y <= surface.y <= y + max_drop]
        return min(candidates, key=lambda surface: surface.y, default=None)

    def surface_for_player(self, state, contact_tolerance=1.0):
        """Return the surface the native player is actually standing on.

        The native collision anchor settles at the surface's pixel Y.  Merely
        looking a few tiles below it also labels jump arcs as landings and
        creates one-step surface-to-surface skills.  Require contact with the
        collision surface instead.
        """
        x = int(float(state["x"]) // 32)
        anchor_y = float(state["y"])
        candidates = [surface for surface in self.surfaces
                      if surface.x0 <= x <= surface.x1
                      and abs(surface.y * 32.0 - anchor_y) <= contact_tolerance]
        return min(candidates, key=lambda surface: surface.y, default=None)

    def direct_candidate(self):
        """Return a same-surface walk candidate; native execution must verify it."""
        if not self.starts or not self.goals:
            return None
        start = self.starts[0]
        start_surface = self.surface_below(start)
        if start_surface is None:
            return None
        for goal in self.goals:
            goal_surface = self.surface_below(goal)
            if goal_surface == start_surface:
                return {"kind": "same_surface_walk", "surface": start_surface.index,
                        "from": list(start), "to": list(goal),
                        "keys": ["RIGHT" if goal[0] > start[0] else "LEFT"]}
        return None

    def summary(self):
        direct = self.direct_candidate()
        return {"size": [self.width, self.height], "starts": [list(v) for v in self.starts],
                "goals": [list(v) for v in self.goals],
                "surface_count": len(self.surfaces),
                "surfaces": [surface.__dict__ for surface in self.surfaces],
                "object_inventory": {str(k): v for k, v in sorted(self.object_inventory.items())},
                "mechanic_profile": self.mechanic_profile(),
                "direct_candidate": direct,
                "unverified_transition_policy": "native_branch_required"}

    def mechanic_profile(self):
        """Classify route structure only; behavior still comes from native x86."""
        ids = set(self.object_inventory)
        if 123 in ids:
            return {"mode": "water", "object_ids": [123]}
        if ids & {27, 37}:
            return {"mode": "ice_slope", "object_ids": sorted(ids & {27, 37})}
        if 3 in ids:
            return {"mode": "ladder", "object_ids": [3]}
        # raw136/138 are jump/parachute-ban fields, not transport machinery.
        # They constrain local actions but do not themselves justify progress
        # shaping toward the flag or a special movement controller.
        if self.starts and self.goals:
            start_surface = self.surface_below(self.starts[0])
            goal_surface = self.surface_below(self.goals[0])
            if start_surface is not None and goal_surface is not None:
                gap = max(0, goal_surface.x0 - start_surface.x1,
                          start_surface.x0 - goal_surface.x1)
                if gap > 16 or abs(goal_surface.y - start_surface.y) > 10:
                    return {"mode": "air_traverse", "object_ids": []}
        return {"mode": "platform", "object_ids": []}

    def topology_signature(self):
        """Route-layout identity; decoration is ignored but endpoints are retained."""
        mechanics = sorted((tile, x, y) for tile, x, y in self.records
                           if tile not in (7, 49, 82, 100, 140))
        payload = {
            "size": [self.width, self.height],
            "starts": sorted(self.starts),
            "goals": sorted(self.goals),
            "surfaces": [[s.y, s.x0, s.x1] for s in self.surfaces],
            "mechanics": mechanics,
        }
        return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()

    def transition_context(self, source, target, margin=2):
        """Describe collision and raw objects around an edge in source-relative cells."""
        x0 = min(source.x0, target.x0) - margin
        x1 = max(source.x1, target.x1) + margin
        y0 = min(source.y, target.y) - margin
        y1 = max(source.y, target.y) + margin
        collision = [[x - source.x0, y - source.y]
                     for y in range(y0, y1 + 1)
                     for x in range(x0, x1 + 1) if self.solid(x, y)]
        objects = [[int(tile), x - source.x0, y - source.y]
                   for tile, x, y in self.records
                   if x0 <= x <= x1 and y0 <= y <= y1
                   and tile not in (7, 49, 82, 100, 140)]
        return {"collision": collision, "objects": sorted(objects)}

    def goal_surfaces(self):
        result = []
        for goal in self.goals:
            surface = self.surface_below(goal)
            if surface is not None and surface not in result:
                result.append(surface)
        return result

    def candidate_targets(self, source, max_dx=16, max_dy=10):
        """Return nearby graph edges to validate, without asserting reachability."""
        result = []
        for target in self.surfaces:
            if target == source:
                continue
            gap = max(0, target.x0 - source.x1, source.x0 - target.x1)
            if gap <= max_dx and abs(target.y - source.y) <= max_dy:
                result.append(target)
        goals = self.goal_surfaces()
        def score(target):
            goal_distance = min((abs(target.y - goal.y) +
                                 abs((target.x0 + target.x1) / 2 -
                                     (goal.x0 + goal.x1) / 2)
                                 for goal in goals), default=0)
            gap = max(0, target.x0 - source.x1, source.x0 - target.x1)
            # Prefer a locally plausible next edge before global goal
            # closeness. Goal-first sorting attempted long platform skips and
            # wasted the bounded native search on the wrong target.
            return gap + abs(target.y - source.y), goal_distance, gap
        return sorted(result, key=score)
