"""Team-mode rule: raw49 is decoration; raw86 downs then respawns."""
from pathlib import Path
import json
import struct
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from combat_oracle import LmfCombatOracle

SNAPSHOT = HARNESS / "private_snapshots" / "team_p2p_combat_live.zip"


def write_fixture(path, hazard=None):
    width, height = 20, 16
    records = [(7, x, 14) for x in range(width)]
    records += [(7, 0, y) for y in range(14)] + [(7, width - 1, y) for y in range(14)]
    records += [(100, 2, 13)]
    if hazard is not None:
        records.append((hazard, 10, 13))
    header = bytearray(32)
    header[:16] = b"NewLWMapFile_1.0"
    struct.pack_into("<HH", header, 16, width, height)
    struct.pack_into("<I", header, 21, len(records))
    path.write_bytes(header + b"".join(struct.pack("<Ihh", *r) for r in records))


def run(hazard=None):
    label = f"raw{hazard}" if hazard is not None else "control"
    fixture = HARNESS / "tests" / f"team_mode_{label}_minimal.LMF"
    write_fixture(fixture, hazard)
    oracle = LmfCombatOracle(SNAPSHOT)
    info = oracle.load_lmf(fixture, fresh_spawn=True)
    oracle.place_combatant(0, 10 * 32 + 16, 11 * 32, hp=100)
    start = oracle.read_combatant(0)
    trace = []
    full = []
    for tick in range(180):
        state = oracle.step_combat_tick({0: ()})[0]
        full.append(state)
        if state["hp"] != start["hp"] or state["38"] != start["38"] or tick % 20 == 0:
            trace.append({"tick": tick + 1, **state})
    return info, start, trace, full, oracle.read_combatant(0)


control_info, control_start, control_trace, control_full, control_end = run()
raw49_info, raw49_start, raw49_trace, raw49_full, raw49_end = run(49)
raw86_info, raw86_start, raw86_trace, raw86_full, raw86_end = run(86)

fields = ("x", "y", "motion58", "hp", "38", "3c", "68", "74", "7c", "80", "b0", "c0", "c4", "d0", "dc")
assert [[row[k] for k in fields] for row in raw49_full] == [
    [row[k] for k in fields] for row in control_full], raw49_trace
baseline_first_damage = next(i for i, row in enumerate(control_full) if row["hp"] < 100.0)
spike_first_damage = next(i for i, row in enumerate(raw86_full) if row["hp"] < 100.0)
assert spike_first_damage < baseline_first_damage, raw86_trace
assert raw86_full[spike_first_damage]["38"] == 5, raw86_trace
assert any(abs(row["x"] - 80.0) < 0.01 and row["7c"] == -1
           for row in raw86_full[spike_first_damage + 1:]), raw86_trace
result = {
    "ok": True,
    "control": {"load": control_info, "first_inactivity_damage_tick": baseline_first_damage + 1},
    "raw49": {"rule": "decorative_and_control_equivalent", "load": raw49_info, "end": raw49_end,
              "events": raw49_trace},
    "raw86": {"rule": "damage_knockdown_then_respawn", "load": raw86_info,
              "end": raw86_end, "events": raw86_trace},
}
(HARNESS / "evidence" / "team_mode_hazard_regression.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("PASS", {"raw49_matches_control": True,
               "raw86_hit_tick": spike_first_damage + 1,
               "raw86_respawn": True})
