"""Measure sword hit timing against a native roll; exploratory, not online parity."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from combat_oracle import DualPerspectiveCombatOracle


oracle = DualPerspectiveCombatOracle(
    ROOT / "private_snapshots/team_p2p_combat_live.zip",
    ROOT / "private_snapshots/team_slot1_live.zip",
)
oracle.begin_branching()
for _ in range(64):
    oracle.step_combat_tick({0: (), 1: ()})
for roster, x, facing in ((0, 700, True), (1, 760, False)):
    oracle.place_combatant(roster, x, 736, hp=100, facing_right=facing)
    for view in oracle.views:
        slot = view.roster_slot(roster)
        view.put(view.SELECTED_WEAPON + slot * 4, "i", 0)  # dagger
for _ in range(8):
    oracle.step_combat_tick({0: (), 1: ()})
if any(oracle.read_combatant(roster)["hp"] != 100 for roster in (0, 1)):
    raise RuntimeError("queued damage in capture; do not use this probe")
start = oracle.save_branch_snapshot()

results = []
for roll_start in (None, -2, 0, 1, 2, 4):
    oracle.restore_branch_snapshot(start)
    rows = []
    for tick in range(-4, 13):
        attack = ("Z",) if tick == 0 else ()
        roll = ("LEFT", "DOWN") if roll_start is not None and tick >= roll_start else ()
        players = oracle.step_combat_tick({0: attack, 1: roll})
        rows.append({
            "tick": tick,
            "attacker": {key: players[0][key] for key in ("x", "hp", "38", "3c")},
            "defender": {key: players[1][key] for key in ("x", "hp", "38", "3c")},
        })
    hits = [row for row in rows if row["defender"]["hp"] < 100]
    results.append({"roll_start": roll_start, "first_damage_tick": hits[0]["tick"] if hits else None,
                    "final_hp": rows[-1]["defender"]["hp"], "trace": rows})

output = ROOT / "evidence/combat_roll_window_probe.json"
output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"output": str(output), "summary": [
    {key: result[key] for key in ("roll_start", "first_damage_tick", "final_hp")}
    for result in results]}, ensure_ascii=False))
