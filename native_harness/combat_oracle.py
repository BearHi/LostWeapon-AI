"""Two-policy stepping on a captured original Client team-room world."""
from __future__ import annotations
from pathlib import Path

from captured_oracle import CapturedOracle
from lmf_injector import NativeLmfOracle


class TwoPlayerCombatOracle(CapturedOracle):
    ROSTER_INDEX = 0x2248AB4
    ROSTER_TO_SLOT = 0x22C31C4
    ROSTER_STRIDE = 0x130
    PLAYER_BASE = 0x3B12A00
    PLAYER_STRIDE = 0xF8
    SELECTED_WEAPON = 0x25F1AD8

    def roster_slot(self, roster):
        return self.get(self.ROSTER_TO_SLOT + int(roster) * self.ROSTER_STRIDE, "b")[0]

    def read_combatant(self, roster):
        slot = self.roster_slot(roster)
        player = self.PLAYER_BASE + slot * self.PLAYER_STRIDE
        return {
            "roster": int(roster), "slot": slot,
            "x": self.get(player, "d")[0], "y": self.get(player + 8, "d")[0],
            "motion58": self.get(player + 0x58, "d")[0],
            "hp": self.get(player + 0x60, "d")[0],
            "weapon": self.get(self.SELECTED_WEAPON + slot * 4, "i")[0] + 1,
            "bounds": list(self.get(player + 0x18, "4i")),
            **{f"{offset:02x}": self.get(player + offset, "i")[0]
               for offset in (0x38, 0x3C, 0x68, 0x74, 0x7C, 0x80, 0x94,
                              0xB0, 0xC0, 0xC4, 0xD0, 0xDC)},
        }

    def place_combatant(self, roster, x, y, *, hp=100.0, facing_right=True):
        """Place an existing captured player slot without inventing its identity/team data."""
        slot = self.roster_slot(roster)
        player = self.PLAYER_BASE + slot * self.PLAYER_STRIDE
        old_x, old_y = self.get(player, "dd")
        self.put(player, "dd", float(x), float(y))
        dx, dy = int(x - old_x), int(y - old_y)
        for offset, delta in ((0x18, dx), (0x1C, dy), (0x20, dx), (0x24, dy)):
            self.put(player + offset, "i", self.get(player + offset, "i")[0] + delta)
        self.put(player + 0x58, "d", 0.0)
        self.put(player + 0x60, "d", float(hp))
        for offset, value in ((0x38, 7), (0x3C, 0), (0x68, 0), (0x74, -1),
                              (0x7C, 0), (0x80, 0), (0xB0, 0 if facing_right else 1),
                              (0xC0, 0), (0xC4, 0), (0xD0, 1), (0xDC, 0)):
            self.put(player + offset, "i", value)

    def step_combat_tick(self, inputs, call_limit=2_000_000):
        """Apply one independent input set per roster, then update the world once."""
        original_roster = self.get(self.ROSTER_INDEX, "i")[0]
        ms, tick = self.get(self.CONTROL + 0x800, "II")
        self.put(self.CONTROL + 0x800, "II", ms + self.CLOCK_MS_PER_TICK, tick + 1)
        try:
            for roster, keys in sorted(inputs.items()):
                self.put(self.ROSTER_INDEX, "i", int(roster))
                self.set_input(tuple(keys))
                self.call(0x4228C0, limit=call_limit)
        finally:
            self.put(self.ROSTER_INDEX, "i", original_roster)
        for address in self.WORLD_CHAIN:
            self.call(address, limit=call_limit)
        if (tick + 1) % 1024 == 0:
            self.u.ctl_flush_tb()
        return {int(roster): self.read_combatant(roster) for roster in inputs}


class LmfCombatOracle(NativeLmfOracle):
    """Two-player controls on an LMF world built by the original Client."""
    ROSTER_INDEX = TwoPlayerCombatOracle.ROSTER_INDEX
    ROSTER_TO_SLOT = TwoPlayerCombatOracle.ROSTER_TO_SLOT
    ROSTER_STRIDE = TwoPlayerCombatOracle.ROSTER_STRIDE
    PLAYER_BASE = TwoPlayerCombatOracle.PLAYER_BASE
    PLAYER_STRIDE = TwoPlayerCombatOracle.PLAYER_STRIDE
    SELECTED_WEAPON = TwoPlayerCombatOracle.SELECTED_WEAPON
    roster_slot = TwoPlayerCombatOracle.roster_slot
    read_combatant = TwoPlayerCombatOracle.read_combatant
    place_combatant = TwoPlayerCombatOracle.place_combatant
    step_combat_tick = TwoPlayerCombatOracle.step_combat_tick

    def load_lmf(self, path, call_limit=2_000_000, fresh_spawn=False):
        result = super().load_lmf(path, call_limit=call_limit, fresh_spawn=fresh_spawn)
        _width, _height, records = self.parse_lmf(Path(path))
        # Sword-team rooms treat raw49 hell/lava artwork as decoration. The
        # viewer still draws its LMF record, while the production-map damage
        # handler and its loader collision marker are omitted from this mode.
        result["combat_decorative_raw49"] = self.compact_runtime_objects(records, (49,))
        width = self.get(0x8952DB0, "i")[0]
        raw49_cells = [(x, y) for tile_id, x, y in records if tile_id == 49]
        for pointer_global in self.GRID_POINTERS:
            pointer = self.get(pointer_global, "I")[0]
            for x, y in raw49_cells:
                self.u.mem_write(pointer + 2 * (y * width + x), b"\0\0")
        result["combat_decorative_raw49"]["cleared_grid_cells"] = len(raw49_cells)
        return result


class DualPerspectiveCombatOracle:
    """Combine complementary P2P captures so both hit directions are authoritative."""
    SYNC_DOUBLE = (0x00, 0x08, 0x50, 0x58, 0x60)
    SYNC_INT = (0x18, 0x1C, 0x20, 0x24, 0x38, 0x3C, 0x68, 0x74, 0x7C,
                0x80, 0xB0, 0xC0, 0xC4, 0xD8, 0xDC)

    def __init__(self, target0_snapshot, target1_snapshot):
        self.views = (TwoPlayerCombatOracle(target0_snapshot),
                      TwoPlayerCombatOracle(target1_snapshot))
        self.primary = self.views[0]
        self.u = self.primary.u

    def get(self, *args): return self.primary.get(*args)

    def begin_branching(self):
        for view in self.views: view.begin_branching()

    def save_branch_snapshot(self):
        return tuple(view.save_branch_snapshot() for view in self.views)

    def restore_branch_snapshot(self, snapshots):
        for view, snapshot in zip(self.views, snapshots):
            view.restore_branch_snapshot(snapshot)

    def restore_branch(self):
        return sum(view.restore_branch() for view in self.views)

    def read_combatant(self, roster):
        return self.views[int(roster)].read_combatant(roster)

    def place_combatant(self, roster, *args, **kwargs):
        for view in self.views: view.place_combatant(roster, *args, **kwargs)

    def _sync_roster(self, roster):
        source = self.views[roster]
        source_slot = source.roster_slot(roster)
        source_player = source.PLAYER_BASE + source_slot * source.PLAYER_STRIDE
        for destination in self.views:
            if destination is source: continue
            slot = destination.roster_slot(roster)
            player = destination.PLAYER_BASE + slot * destination.PLAYER_STRIDE
            for offset in self.SYNC_DOUBLE:
                destination.put(player + offset, "d", source.get(source_player + offset, "d")[0])
            for offset in self.SYNC_INT:
                destination.put(player + offset, "i", source.get(source_player + offset, "i")[0])
            weapon = source.get(source.SELECTED_WEAPON + source_slot * 4, "i")[0]
            destination.put(destination.SELECTED_WEAPON + slot * 4, "i", weapon)

    def step_combat_tick(self, inputs, call_limit=2_000_000):
        for view in self.views: view.step_combat_tick(inputs, call_limit=call_limit)
        self._sync_roster(0); self._sync_roster(1)
        return {roster: self.read_combatant(roster) for roster in inputs}


class DualPerspectiveLmfCombatOracle(DualPerspectiveCombatOracle):
    def __init__(self, target0_snapshot, target1_snapshot, lmf):
        self.views = (LmfCombatOracle(target0_snapshot), LmfCombatOracle(target1_snapshot))
        maps = [view.load_lmf(lmf, fresh_spawn=True) for view in self.views]
        if maps[0]["size"] != maps[1]["size"] or maps[0]["records"] != maps[1]["records"]:
            raise RuntimeError("two Client views built different LMF worlds")
        self.map = maps[0]
        self.primary = self.views[0]
        self.u = self.primary.u
