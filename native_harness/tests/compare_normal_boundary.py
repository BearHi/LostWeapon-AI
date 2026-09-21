"""Compare normal Client movement boundaries with the same captured oracle."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from oracle import PLAYER


def normalized_live(state):
    return {
        "x": state["pos"][0], "y": state["pos"][1],
        "motion58": state["motion58"],
        **{key[2:]: value for key, value in state["state"].items()},
        "player_header": state["player_header"],
    }


def normalized_oracle(oracle):
    state = oracle.read_player_state()
    state["player_header"] = list(oracle.get(PLAYER - 16 + oracle.meta["state"]["slot"] * 0xF8, "4i"))
    # Older read-only traces predate the additional 7c/80/b8 diagnostics.
    # Compare only fields actually captured by both sides.
    return {key: state[key] for key in
            ("x", "y", "motion58", "38", "3c", "68", "74", "b0", "c0", "c4", "d0", "dc", "player_header")}


def main():
    snapshot, trace_path, output = map(Path, sys.argv[1:4])
    action = sys.argv[4] if len(sys.argv) > 4 else "RIGHT"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    normal_by_x = {}
    for sample in trace["samples"]:
        normal_by_x.setdefault(sample["state"]["pos"][0], []).append(sample["state"])

    oracle = CapturedOracle(snapshot)
    start_x = expected_x = oracle.read_player_state()["x"]
    end_x = max(normal_by_x)
    ticks = round((end_x - start_x) / 4.0)
    keys = ("RIGHT", "UP") if action == "RIGHT_UP" else ("RIGHT",)
    expected = [normalized_oracle(oracle)]
    for _ in range(ticks):
        oracle.step_world_chain(keys)
        expected.append(normalized_oracle(oracle))

    rows = []
    for tick, offline in enumerate(expected):
        candidates = [normalized_live(item) for item in normal_by_x.get(offline["x"], [])]
        if offline in candidates:
            status = "PASS"
        elif not candidates:
            status = "MISSED_SAMPLE"
        else:
            # ReadProcessMemory calls are individually safe but live_state reads
            # fields separately.  A sample can therefore mix two adjacent game
            # ticks.  Label that case only if every value comes from this or the
            # next expected boundary.
            adjacent = expected[tick:min(tick + 2, len(expected))]
            keys_to_check = offline.keys()
            status = "TORN_READ" if all(
                any(candidate[key] == nearby[key] for nearby in adjacent)
                for candidate in candidates for key in keys_to_check
            ) else "MISMATCH"
        rows.append({"tick": tick, "x": offline["x"], "status": status,
                     "normal_candidates": candidates, "oracle": offline})
    counts = {status: sum(row["status"] == status for row in rows)
              for status in ("PASS", "TORN_READ", "MISSED_SAMPLE", "MISMATCH")}
    result = {
        "scope": f"same-boundary normal Client versus offline original-x86 world-chain {action} parity",
        "snapshot": str(snapshot), "trace": str(trace_path),
        "compared_fields": ["x", "y", "motion58", "38", "3c", "68", "74", "b0", "c0", "c4", "d0", "dc", "player_header"],
        "movement_boundaries": len(rows),
        "extra_same_position_samples": len(trace["samples"]) - len(normal_by_x),
        "counts": counts,
        "strict_all_pass": counts["PASS"] == len(rows),
        "coherent_mismatches": counts["MISMATCH"],
        "parity_supported": counts["MISMATCH"] == 0,
        "rows": rows,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("scope", "movement_boundaries", "extra_same_position_samples", "counts", "strict_all_pass", "coherent_mismatches", "parity_supported")}, ensure_ascii=False, indent=2))
    if not result["parity_supported"]:
        raise SystemExit("normal/oracle boundary mismatch")


if __name__ == "__main__":
    main()
