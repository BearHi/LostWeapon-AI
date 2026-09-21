"""Compare asynchronous normal raw124 samples with original-x86 boundaries."""
from pathlib import Path
import json
import struct
import sys

FIELDS = ("x", "y", "motion58", "38", "68", "74", "b0", "c0", "c4", "d0", "dc", "object_c8", "collision_code")


def normal_state(sample):
    raw = sample["state"]
    obj = bytes.fromhex(sample["object_hex"])
    return {"x": raw["pos"][0], "y": raw["pos"][1], "motion58": raw["motion58"],
            **{key[2:]: value for key, value in raw["state"].items()},
            "object_c8": struct.unpack_from("<i", obj, 0xC8)[0],
            "collision_code": sample["collision_code"]}


def native_state(sample):
    raw = sample["state"]
    return {**raw, "object_c8": sample["object_c8"], "collision_code": sample["collision_code"]}


def same(a, b):
    return all(a[field] == b[field] for field in FIELDS)


def main():
    normal_path, native_path, output = map(Path, sys.argv[1:4])
    normal = json.loads(normal_path.read_text(encoding="utf-8"))
    native = json.loads(native_path.read_text(encoding="utf-8"))
    expected = [native_state(sample) for sample in native["samples"]]
    rows = []
    exact = torn = write_windows = reset_windows = mismatches = 0
    matched = set()
    for index, sample in enumerate(normal["samples"]):
        state = normal_state(sample)
        hits = [tick for tick, candidate in enumerate(expected) if same(state, candidate)]
        status = "MISMATCH"
        tick = None
        if hits:
            tick = hits[0]
            matched.add(tick % 143)
            status = "PASS"
            exact += 1
        else:
            for candidate_tick in range(len(expected) - 1):
                a, b = expected[candidate_tick:candidate_tick + 2]
                if all(state[field] in (a[field], b[field]) for field in FIELDS):
                    status = "TORN_READ"
                    torn += 1
                    break
            if status == "MISMATCH":
                # The object timer and collision cell are distinct writes in the
                # raw124 handler. Accept only the two values of one adjacent pair.
                for candidate_tick in range(len(expected) - 1):
                    a, b = expected[candidate_tick:candidate_tick + 2]
                    player_fields = tuple(field for field in FIELDS if field not in ("object_c8", "collision_code"))
                    if (all(state[field] in (a[field], b[field]) for field in player_fields)
                            and state["object_c8"] in (a["object_c8"], b["object_c8"])
                            and state["collision_code"] in (a["collision_code"], b["collision_code"])):
                        status = "OBJECT_WRITE_WINDOW"
                        write_windows += 1
                        break
            if status == "MISMATCH":
                # The death/respawn handler writes the falling y boundary before
                # resetting the remaining player fields to the spawn boundary.
                for candidate_tick in range(len(expected) - 1):
                    a, b = expected[candidate_tick:candidate_tick + 2]
                    stable_fields = tuple(field for field in FIELDS if field not in ("y", "motion58", "d0", "object_c8"))
                    if (state["y"] == a["y"] + abs(a["motion58"]) / 100.0
                            and state["motion58"] == a["motion58"] - 40
                            and state["d0"] == b["d0"] == 0
                            and state["object_c8"] == b["object_c8"]
                            and all(state[field] == a[field] for field in stable_fields)):
                        status = "RESPAWN_WRITE_WINDOW"
                        reset_windows += 1
                        break
            if status == "MISMATCH":
                mismatches += 1
        rows.append({"sample": index, "status": status, "matched_tick": tick, "state": state})
    result = {
        "scope": "normal Client versus captured original-x86 raw124 disappearing-block cycle parity",
        "normal_trace": str(normal_path), "native_trace": str(native_path),
        "fields": list(FIELDS), "observed_samples": len(rows), "exact_samples": exact,
        "torn_samples": torn, "object_write_window_samples": write_windows,
        "respawn_write_window_samples": reset_windows, "coherent_mismatches": mismatches,
        "unique_cycle_boundaries_observed": len(matched), "cycle_ticks": 143,
        "parity_supported": mismatches == 0, "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "observed_samples", "exact_samples", "torn_samples", "object_write_window_samples",
        "respawn_write_window_samples", "coherent_mismatches", "unique_cycle_boundaries_observed",
        "cycle_ticks", "parity_supported")}, ensure_ascii=False, indent=2))
    if mismatches:
        raise SystemExit("normal/native disappearing-block mismatch")


if __name__ == "__main__":
    main()
