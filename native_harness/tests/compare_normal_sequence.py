"""Align a held-input normal trace, release, and landing with the native oracle."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from oracle import PLAYER


FIELDS = ("x", "y", "motion58", "38", "3c", "68", "74", "b0", "c0", "c4", "d0", "dc", "player_header")


def live_state(raw):
    return {"x": raw["pos"][0], "y": raw["pos"][1], "motion58": raw["motion58"],
            **{key[2:]: value for key, value in raw["state"].items()},
            "player_header": raw["player_header"]}


def oracle_state(oracle):
    state = oracle.read_player_state()
    p = PLAYER - 16 + oracle.meta["state"]["slot"] * 0xF8
    state["player_header"] = list(oracle.get(p, "4i"))
    return state


def main():
    snapshot, trace_path, output = map(Path, sys.argv[1:4])
    action = sys.argv[4]
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    observed = [(sample.get("phase", "held"), live_state(sample["state"])) for sample in trace["samples"]]
    held_observed = [state for phase, state in observed if phase == "held"]
    direction = -1 if action.startswith("LEFT") else 1
    start_x = held_observed[0]["x"]
    held_end_x = min(state["x"] for state in held_observed) if direction < 0 else max(state["x"] for state in held_observed)
    held_ticks = round(abs(held_end_x - start_x) / 4.0)
    keys = ("LEFT", "UP") if action == "LEFT_UP" else ("RIGHT", "UP")

    oracle = CapturedOracle(snapshot)
    expected = [("held", oracle_state(oracle))]
    for _ in range(held_ticks):
        oracle.step_world_chain(keys)
        expected.append(("held", oracle_state(oracle)))
    release_ticks = 0
    while release_ticks < 180:
        oracle.step_world_chain(())
        release_ticks += 1
        state = oracle_state(oracle)
        expected.append(("released", state))
        if state["38"] == 7:
            break
    for _ in range(8):
        oracle.step_world_chain(())
        expected.append(("released", oracle_state(oracle)))

    matched_expected = set()
    observed_rows = []
    mismatches = 0
    torn = 0
    phase_edges = 0
    mid_tick = 0
    input_edges = 0
    for observed_index, (phase, state) in enumerate(observed):
        exact = [i for i, (expected_phase, candidate) in enumerate(expected)
                 if expected_phase == phase and candidate == state]
        if exact:
            index = min(exact, key=lambda value: abs(value - observed_index))
            matched_expected.add(index)
            status = "PASS"
        else:
            # A live sample is non-atomic because its fields are separate reads.
            # Recognize only a mix of two adjacent offline boundaries.
            status = "MISMATCH"
            index = None
            if any(candidate == state for _, candidate in expected):
                status = "PHASE_EDGE_SAMPLE"
                phase_edges += 1
            elif phase == "released" and all(
                state[field] == expected[held_ticks][1][field]
                for field in FIELDS if field != "74"
            ):
                # Key-up changes the input latch before the next gameplay tick.
                # This host-visible boundary has no counterpart in atomic step().
                status = "INPUT_RELEASE_EDGE"
                input_edges += 1
            for i in range(len(expected) - 1):
                if status != "MISMATCH":
                    break
                if expected[i][0] != phase or expected[i + 1][0] != phase:
                    continue
                if all(state[field] in (expected[i][1][field], expected[i + 1][1][field]) for field in FIELDS):
                    status = "TORN_READ"
                    torn += 1
                    break
            if status == "MISMATCH" and observed_index <= 1 and state["x"] == start_x and state["y"] == held_observed[0]["y"]:
                status = "MID_TICK_SAMPLE"
                mid_tick += 1
            if status == "MISMATCH":
                mismatches += 1
        observed_rows.append({"sample": observed_index, "phase": phase, "status": status,
                              "matched_expected_tick": index, "state": state})

    expected_missing = [i for i in range(len(expected)) if i not in matched_expected]
    result = {
        "scope": f"same-boundary normal Client versus offline original-x86 {action}, release, and landing parity",
        "snapshot": str(snapshot), "trace": str(trace_path), "held_ticks": held_ticks,
        "release_ticks_to_ground": release_ticks, "expected_boundaries": len(expected),
        "observed_samples": len(observed), "exact_expected_boundaries_observed": len(matched_expected),
        "missed_expected_boundaries": len(expected_missing), "torn_read_samples": torn,
        "phase_edge_samples": phase_edges, "mid_tick_samples": mid_tick,
        "input_release_edge_samples": input_edges,
        "coherent_mismatches": mismatches, "parity_supported": mismatches == 0,
        "normal_end": observed[-1][1], "oracle_end": expected[-1][1],
        "missing_expected_ticks": expected_missing, "observed_rows": observed_rows,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "scope", "held_ticks", "release_ticks_to_ground", "expected_boundaries", "observed_samples",
        "exact_expected_boundaries_observed", "missed_expected_boundaries", "torn_read_samples",
        "phase_edge_samples", "input_release_edge_samples", "mid_tick_samples", "coherent_mismatches", "parity_supported")}, ensure_ascii=False, indent=2))
    if mismatches:
        raise SystemExit("normal/oracle sequence mismatch")


if __name__ == "__main__":
    main()
