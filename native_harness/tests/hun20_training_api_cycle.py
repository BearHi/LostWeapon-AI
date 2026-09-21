"""Exercise save/restore and deterministic raw124 cycles through NativeTrainingAPI."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api import NativeTrainingAPI

OBJECT_C8 = 0x27A5998 + 29 * 0xF8 + 0xC8


def observed(api):
    oracle = api.oracle
    state = api.read_state()
    width = oracle.get(0x8952DB0, "i")[0]
    grid1 = oracle.get(0x8952DEC, "I")[0]
    return {"player": state, "object_c8": oracle.get(OBJECT_C8, "i")[0],
            "collision_code": struct.unpack("<H", oracle.u.mem_read(grid1 + 2 * (14 * width + 6), 2))[0]}


def run_cycle(api):
    rows = [observed(api)]
    start = time.perf_counter()
    for _ in range(143):
        api.step(1, ())
        rows.append(observed(api))
    elapsed = time.perf_counter() - start
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return rows, elapsed, digest


def main():
    snapshot, lmf, output = map(Path, sys.argv[1:4])
    api = NativeTrainingAPI(snapshot, lmf)
    api.step(143, ())
    branch = api.save_state()
    first, first_seconds, first_hash = run_cycle(api)
    restore_start = time.perf_counter()
    api.restore_state(branch)
    restore_ms = (time.perf_counter() - restore_start) * 1000
    second, second_seconds, second_hash = run_cycle(api)
    exact = first == second
    result = {
        "scope": "NativeTrainingAPI deterministic raw124 cycle after an original-x86 warmup",
        "snapshot": str(snapshot), "lmf": str(lmf), "warmup_ticks": 143, "cycle_ticks": 143,
        "saved_dirty_pages": len(branch["dirty"]), "saved_dirty_bytes": len(branch["dirty"]) * 4096,
        "restore_ms": restore_ms, "first_seconds": first_seconds, "second_seconds": second_seconds,
        "first_ticks_per_second": 143 / first_seconds, "second_ticks_per_second": 143 / second_seconds,
        "first_hash": first_hash, "second_hash": second_hash, "exact_replay": exact,
        "start": first[0], "end": first[-1],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not exact:
        raise SystemExit("raw124 API replay mismatch")


if __name__ == "__main__":
    main()
