"""Probe an ordinary roll across an ice wedge in a captured original-x86 world."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle

ACC = 0x25CA528
DIRECTION = 0x25CA078


def main():
    snapshot, output = map(Path, sys.argv[1:3])
    direction = sys.argv[3].upper()
    held = int(sys.argv[4])
    released = int(sys.argv[5])
    oracle = CapturedOracle(snapshot)
    slot = oracle.meta["state"]["slot"]
    rows = []

    def sample(tick, phase):
        state = oracle.read_player_state()
        state["acc"] = oracle.get(ACC + slot * 4, "i")[0]
        state["dir"] = oracle.get(DIRECTION + slot * 4, "i")[0]
        rows.append({"tick": tick, "phase": phase, "state": state})

    sample(0, "start")
    for tick in range(1, held + 1):
        oracle.step_world_chain((direction, "DOWN"))
        sample(tick, "roll_held")
    for tick in range(held + 1, held + released + 1):
        oracle.step_world_chain(())
        sample(tick, "released")

    result = {
        "scope": f"captured original-x86 {direction}+DOWN {held} then release ice route probe",
        "snapshot": str(snapshot),
        "schedule": {f"{direction}_DOWN_ticks": held, "NOOP_ticks": released},
        "samples": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "start": [rows[0]["state"]["x"], rows[0]["state"]["y"]],
        "end": [rows[-1]["state"]["x"], rows[-1]["state"]["y"]],
        "max_acc": max(row["state"]["acc"] for row in rows),
        "directions": sorted(set(row["state"]["dir"] for row in rows)),
        "x_range": [min(row["state"]["x"] for row in rows), max(row["state"]["x"] for row in rows)],
        "y_range": [min(row["state"]["y"] for row in rows), max(row["state"]["y"] for row in rows)],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
