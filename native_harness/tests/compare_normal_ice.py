"""Compare a normal-Client ice-roll trace with captured original x86 boundaries."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle

ACC = 0x25CA528
DIRECTION = 0x25CA078
FIELDS = ("x", "y", "motion58", "38", "68", "74", "b0", "c0", "c4", "d0", "dc", "acc", "dir")


def normal_state(raw):
    return {
        "x": raw["pos"][0], "y": raw["pos"][1], "motion58": raw["motion58"],
        **{key[2:]: value for key, value in raw["state"].items()},
        "acc": raw["stored_momentum"], "dir": raw["stored_direction"],
    }


def oracle_state(oracle, slot):
    state = oracle.read_player_state()
    state["acc"] = oracle.get(ACC + slot * 4, "i")[0]
    state["dir"] = oracle.get(DIRECTION + slot * 4, "i")[0]
    return state


def same(a, b):
    return all(a[field] == b[field] for field in FIELDS)


def main():
    snapshot, trace_path, output = map(Path, sys.argv[1:4])
    direction = sys.argv[4].upper()
    held = int(sys.argv[5])
    released = int(sys.argv[6])
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    oracle = CapturedOracle(snapshot)
    slot = oracle.meta["state"]["slot"]
    expected = [("start", oracle_state(oracle, slot))]
    for _ in range(held):
        oracle.step_world_chain((direction, "DOWN"))
        expected.append(("roll_held", oracle_state(oracle, slot)))
    for _ in range(released):
        oracle.step_world_chain(())
        expected.append(("released", oracle_state(oracle, slot)))

    phase_ranges = {
        "start": range(0, 1),
        "roll_held": range(1, held + 1),
        "released": range(held + 1, len(expected)),
    }
    rows = []
    exact_count = torn_count = edge_count = update_count = mismatches = 0
    matched_ticks = set()
    for sample_index, sample in enumerate(trace["samples"]):
        phase = sample["phase"]
        state = normal_state(sample["state"])
        indices = phase_ranges[phase]
        exact = [i for i in indices if same(state, expected[i][1])]
        status = "MISMATCH"
        matched = None
        if exact:
            matched = min(exact, key=lambda i: abs(i - sample_index))
            matched_ticks.add(matched)
            status = "PASS"
            exact_count += 1
        else:
            # ReadProcessMemory fields are sampled separately while the game thread
            # can advance. Accept only mixtures of two adjacent atomic boundaries.
            for i in range(max(0, indices.start - 1), min(len(expected) - 1, indices.stop)):
                if all(state[field] in (expected[i][1][field], expected[i + 1][1][field]) for field in FIELDS):
                    status = "TORN_READ"
                    torn_count += 1
                    break
            if status == "MISMATCH":
                # Key down/up can change input latches before the next gameplay
                # boundary while the physical state still equals the edge state.
                edge = 0 if phase == "roll_held" else held
                non_input = tuple(field for field in FIELDS if field not in ("74", "c0"))
                if all(state[field] == expected[edge][1][field] for field in non_input):
                    status = "INPUT_EDGE"
                    edge_count += 1
            if status == "MISMATCH" and phase == "roll_held":
                # 0x4228c0 installs the roll state and upward impulse before the
                # world chain moves the player and applies its first -40 step.
                before, after = expected[0][1], expected[1][1]
                copied = tuple(field for field in FIELDS if field not in ("x", "y", "motion58"))
                if (state["x"] == before["x"] and state["y"] == before["y"]
                        and state["motion58"] == after["motion58"] + 40
                        and all(state[field] == after[field] for field in copied)):
                    status = "INPUT_UPDATE_WINDOW"
                    update_count += 1
            if status == "MISMATCH":
                mismatches += 1
        rows.append({"sample": sample_index, "phase": phase, "status": status,
                     "matched_tick": matched, "state": state})

    result = {
        "scope": f"same-input normal Client versus captured original-x86 triangular ice raw37 parity",
        "snapshot": str(snapshot), "normal_trace": str(trace_path),
        "schedule": {f"{direction}_DOWN_ticks": held, "NOOP_ticks": released},
        "fields": list(FIELDS), "observed_samples": len(rows),
        "exact_samples": exact_count, "torn_samples": torn_count,
        "input_edge_samples": edge_count, "input_update_window_samples": update_count,
        "coherent_mismatches": mismatches,
        "unique_expected_ticks_observed": len(matched_ticks),
        "parity_supported": mismatches == 0, "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "observed_samples", "exact_samples", "torn_samples", "input_edge_samples", "input_update_window_samples",
        "coherent_mismatches", "unique_expected_ticks_observed", "parity_supported")},
        ensure_ascii=False, indent=2))
    if mismatches:
        raise SystemExit("normal/oracle ice trace mismatch")


if __name__ == "__main__":
    main()
