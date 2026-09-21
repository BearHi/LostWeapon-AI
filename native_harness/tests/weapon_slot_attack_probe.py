"""Probe original-x86 weapon selection, attack states and switch locking."""
from pathlib import Path
import json
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

api = NativeTrainingAPI(HARNESS / "private_snapshots/hun1_full.zip",
                        HARNESS.parent / "훈련용맵/훈1.LMF", track_dirty=True)
oracle = api.oracle
base = api.save_state()
selected_address = 0x25F1AD8


def row(tick, keys):
    state = api.step(1, keys)
    player = oracle.player_address
    return {"tick": tick, "keys": list(keys), "selected": oracle.get(selected_address, "i")[0],
            "attack_bounds": list(oracle.get(player + 0x18, "4i")), **state}


results = []
for slot in range(1, 5):
    for attack in ("Z", "X"):
        api.restore_state(base)
        trace = [row(0, (str(slot),)), row(1, ())]
        trace.append(row(2, (attack,)))
        # Try switching to the next slot throughout the attack animation.
        requested = slot % 4 + 1
        for tick in range(3, 93):
            keys = (str(requested),)
            trace.append(row(tick, keys))
        initial_selected = trace[1]["selected"]
        first_attack = next((r for r in trace if r["38"] not in (7, 8, 9)), None)
        first_switch = next((r for r in trace[3:] if r["selected"] != initial_selected), None)
        results.append({"slot_key": slot, "attack_key": attack,
                        "selected_after_slot": initial_selected,
                        "requested_during_attack": requested,
                        "first_attack_state": first_attack,
                        "first_accepted_switch": first_switch,
                        "selected_timeline": [[r["tick"], r["selected"], r["38"], r["3c"]]
                                              for r in trace
                                              if r["tick"] == 0 or r["selected"] != trace[r["tick"]-1]["selected"]
                                              or r["38"] != trace[r["tick"]-1]["38"]]})

output = HARNESS / "evidence/weapon_slot_attack_probe.json"
for result in results:
    if result["attack_key"] == "Z":
        assert result["first_attack_state"]["38"] == 14 + result["slot_key"], result
        assert result["first_accepted_switch"] is not None, result
        assert result["first_accepted_switch"]["38"] == 7, result
    else:
        assert result["first_attack_state"] is None, result
        assert result["first_accepted_switch"]["tick"] == 3, result
output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"output": str(output), "cases": len(results),
                  "summary": [{"slot": r["slot_key"], "attack": r["attack_key"],
                               "selected": r["selected_after_slot"],
                               "attack_state": (r["first_attack_state"] or {}).get("38"),
                               "switch_tick": (r["first_accepted_switch"] or {}).get("tick")}
                              for r in results]}, ensure_ascii=False, indent=2))
