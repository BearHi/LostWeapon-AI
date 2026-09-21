"""Persistent, conservative terrain memory assembled from live native crops."""
from __future__ import annotations


class DiscoveredMap:
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.cells = {}
        # Executed native transitions are distinct from geometric clearance.
        self.transitions = {}

    def update(self, view):
        """Keep every in-bounds cell seen so far, including walls and objects."""
        for row in view["cells"]:
            for cell in row:
                x, y = cell["x"], cell["y"]
                if 0 <= x < self.width and 0 <= y < self.height:
                    self.cells[(x, y)] = {
                        "solid": bool(cell["solid"]),
                        "grids": tuple(cell["grids"]),
                        "object_id": cell["object_id"],
                    }

    def classify(self, x: int, y: int) -> str:
        """Unknown is never treated as an empty tile or a possible landing."""
        if not 0 <= x < self.width or not 0 <= y < self.height:
            return "boundary"
        cell = self.cells.get((x, y))
        if cell is None:
            return "unknown"
        return "blocked" if cell["solid"] else "open"

    def clearance(self, x: int, y: int, height: int = 2) -> str:
        """Geometry only; native physics must still validate an actual move."""
        statuses = [self.classify(x, y - offset) for offset in range(height)]
        if "boundary" in statuses or "blocked" in statuses:
            return "blocked"
        if "unknown" in statuses:
            return "unknown"
        return "open"

    def forward_clearance(self, player_tile, goal_tile, distance=4):
        px, py = player_tile
        direction = 1 if goal_tile[0] >= px else -1
        return [self.clearance(px + direction * step, py - 1)
                for step in range(1, distance + 1)]

    def record_transition(self, before, action, after, *, respawn=False):
        """Remember an observed move; never infer reachability from empty tiles."""
        source = (int(before["x"] // 32), int(before["y"] // 32))
        target = (int(after["x"] // 32), int(after["y"] // 32))
        key = (source, int(action), target)
        row = self.transitions.setdefault(key, {"success": 0, "failure": 0})
        moved = (abs(float(after["x"]) - float(before["x"])) >= 1 or
                 abs(float(after["y"]) - float(before["y"])) >= 1)
        outcome = "failure" if respawn or not moved else "success"
        row[outcome] += 1
        return {"from": source, "to": target, "action": int(action),
                "outcome": outcome}

    def known_reachable(self, source, target):
        """Only a successful native transition certifies this directed edge."""
        return any(a == tuple(source) and b == tuple(target) and result["success"]
                   for (a, _action, b), result in self.transitions.items())

    def summary(self):
        counts = {"open": 0, "blocked": 0}
        for cell in self.cells.values():
            counts["blocked" if cell["solid"] else "open"] += 1
        counts["unknown"] = self.width * self.height - len(self.cells)
        counts["native_success_edges"] = sum(bool(v["success"]) for v in self.transitions.values())
        counts["native_failed_edges"] = sum(bool(v["failure"]) for v in self.transitions.values())
        return counts
