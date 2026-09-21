"""Both team-room player slots accept independent original-x86 Z input."""
from pathlib import Path
import json
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from combat_oracle import TwoPlayerCombatOracle

oracle = TwoPlayerCombatOracle(HARNESS / "private_snapshots/team_slot0_live.zip")
initial = {roster: oracle.read_combatant(roster) for roster in (0, 1)}
trace = []
for tick in range(8):
    if tick < 3:
        inputs = {0: (), 1: ()}
    elif tick == 3:
        inputs = {0: ("Z",), 1: ()}
    elif tick == 5:
        inputs = {0: (), 1: ("Z",)}
    else:
        inputs = {0: (), 1: ()}
    trace.append({"tick": tick, "inputs": inputs,
                  "players": oracle.step_combat_tick(inputs)})

slot0_attack = next((row for row in trace if row["players"][0]["38"] in range(15, 19)), None)
slot1_attack = next((row for row in trace if row["players"][1]["38"] in range(15, 19)), None)
assert slot0_attack is not None, trace
assert slot1_attack is not None, trace
payload = {"initial": initial, "slot0_attack_tick": slot0_attack["tick"],
           "slot1_attack_tick": slot1_attack["tick"], "trace": trace,
           "verdict": "PASS"}
(HARNESS / "evidence/two_player_input_regression.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"slot0_attack_tick": slot0_attack["tick"],
                  "slot1_attack_tick": slot1_attack["tick"], "verdict": "PASS"}, indent=2))
