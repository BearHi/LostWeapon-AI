"""Local action-ban block fields supplied by LMF records.

The user-confirmed reach is five tiles to either side and four tiles above
and below each block. Raw IDs are identified from 금지블록.LMF placement.
"""
from __future__ import annotations

KINDS = ("parachute", "jump", "roll", "weapon")
HORIZONTAL_REACH = 5
VERTICAL_REACH = 4

KNOWN_RESTRICTION_IDS: dict[int, str] = {
    136: "jump", 137: "roll", 138: "parachute", 139: "weapon",
}


class RestrictionFields:
    def __init__(self, records, ids=None):
        ids = KNOWN_RESTRICTION_IDS if ids is None else ids
        if any(kind not in KINDS for kind in ids.values()):
            raise ValueError("unknown restriction kind")
        self.at_tile = {}
        for tile_id, x, y in records:
            kind = ids.get(int(tile_id))
            if kind:
                self.at_tile.setdefault((int(x), int(y)), set()).add(kind)

    def active_at(self, x, y):
        """Return bans around the player's current 32-pixel tile anchor."""
        px, py = int(float(x) // 32), int(float(y) // 32)
        active = set()
        for by in range(py - VERTICAL_REACH, py + VERTICAL_REACH + 1):
            for bx in range(px - HORIZONTAL_REACH, px + HORIZONTAL_REACH + 1):
                active.update(self.at_tile.get((bx, by), ()))
        return active


def filter_actions(actions, allowed, active, *, up_is_jump=True):
    """Filter requests, not outcomes; native physics still controls transitions."""
    if not active:
        return tuple(allowed)
    result = []
    for index in allowed:
        keys = actions[index]
        if "parachute" in active and "C" in keys:
            continue
        if "jump" in active and up_is_jump and "UP" in keys:
            continue
        if "roll" in active and "DOWN" in keys and ("LEFT" in keys or "RIGHT" in keys):
            continue
        if "weapon" in active and "Z" in keys:
            continue
        result.append(index)
    return tuple(result)
