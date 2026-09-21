"""Compare a normal Client walk-off + one C press with the native oracle."""
from pathlib import Path
import json
import sys
import math

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from oracle import PLAYER

FIELDS = ("x", "y", "motion58", "38", "3c", "68", "74", "b0", "c0", "c4", "d0", "dc", "player_header")
CORE_FIELDS = ("x", "y", "motion58", "38", "68", "74", "b0", "c0", "c4", "d0", "dc")


def norm_live(raw):
    return {"x": raw["pos"][0], "y": raw["pos"][1], "motion58": raw["motion58"],
            **{key[2:]: value for key, value in raw["state"].items()},
            "player_header": raw["player_header"]}


def norm_oracle(o):
    s = o.read_player_state()
    p = PLAYER - 16 + o.meta["state"]["slot"] * 0xF8
    s["player_header"] = list(o.get(p, "4i"))
    return s


def equal(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-6)
    return a == b


def same_fields(left, right, fields):
    return all(equal(left[field], right[field]) for field in fields)


def main():
    snapshot, trace_path, output = map(Path, sys.argv[1:4])
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    observed = [norm_live(item["state"]) for item in trace["samples"]]
    c_down = trace["input_events"][0]["state"]["pos"][0]
    start_x = observed[0]["x"]
    pre_c_ticks = round((c_down - start_x) / 4.0)
    # Opening the parachute consumes one tick without horizontal movement.
    max_ticks = round((max(s["x"] for s in observed) - start_x) / 4.0) + 1

    oracle = CapturedOracle(snapshot)
    expected = [norm_oracle(oracle)]
    for tick in range(max_ticks):
        keys = ("RIGHT", "C") if tick == pre_c_ticks else ("RIGHT",)
        oracle.step_world_chain(keys)
        expected.append(norm_oracle(oracle))

    rows = []
    matched = set()
    edge_samples = 0
    mismatches = 0
    for index, state in enumerate(observed):
        exact = [tick for tick, candidate in enumerate(expected) if same_fields(candidate, state, FIELDS)]
        if exact:
            matched.add(min(exact, key=lambda tick: abs(tick - index)))
            status = "PASS"
        elif state["x"] == c_down and state["38"] == 9 and state["dc"] == 1:
            status = "INPUT_EDGE"
            edge_samples += 1
        elif any(same_fields(candidate, state, CORE_FIELDS) for candidate in expected):
            status = "ANIMATION_ONLY"
        elif any(
            all(any(equal(state[field], candidate[field]) for candidate in pair) for field in CORE_FIELDS)
            for pair in zip(expected, expected[1:])
        ):
            status = "TORN_READ"
        else:
            status = "MISMATCH"
            mismatches += 1
        rows.append({"sample": index, "status": status, "state": state})

    result = {
        "scope": "same-boundary normal Client versus offline original-x86 walk-off + C parachute parity",
        "snapshot": str(snapshot), "trace": str(trace_path), "pre_c_ticks": pre_c_ticks,
        "compared_ticks": len(expected), "observed_samples": len(observed),
        "exact_expected_ticks_observed": len(matched), "input_edge_samples": edge_samples,
        "animation_only_samples": sum(row["status"] == "ANIMATION_ONLY" for row in rows),
        "torn_read_samples": sum(row["status"] == "TORN_READ" for row in rows),
        "coherent_mismatches": mismatches, "parity_supported": mismatches == 0,
        "input_events": trace["input_events"], "rows": rows,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("scope", "pre_c_ticks", "compared_ticks", "observed_samples", "exact_expected_ticks_observed", "input_edge_samples", "animation_only_samples", "torn_read_samples", "coherent_mismatches", "parity_supported")}, ensure_ascii=False, indent=2))
    if mismatches:
        raise SystemExit("normal/oracle parachute mismatch")


if __name__ == "__main__":
    main()
