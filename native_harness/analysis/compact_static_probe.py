"""Compare a full native LMF runtime with a compacted dispatcher list."""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))

from lmf_injector import NativeLmfOracle


MAP = HARNESS.parent / "Map" / "낙라.LMF"
SNAPSHOT = HARNESS / "private_snapshots" / "hun1_full.zip"
OUTPUT = HARNESS / "evidence" / "nakra_static_compaction_probe.json"
# Runtime type 200 is the Client's grid-backed static collision family. The
# dispatcher merely reasserts its grid code each tick. ID 82 is visual-only.
EXCLUDED = frozenset((3, 18, 26, 36, 37, 43, 82))
REFRESHED = frozenset((3, 26, 36, 37))


def object_bytes(oracle, index):
    address = oracle.addr(oracle.OBJECT_BASE + index * oracle.OBJECT_STRIDE)
    return bytes(oracle.u.mem_read(address, oracle.OBJECT_STRIDE))


def main():
    full = NativeLmfOracle(SNAPSHOT)
    full_map = full.load_lmf(MAP, fresh_spawn=True)
    full.enable_weapon_slots()
    width, height, records = full.parse_lmf(MAP)

    compact = NativeLmfOracle(SNAPSHOT)
    compact_map = compact.load_lmf(MAP, fresh_spawn=True)
    compact.enable_weapon_slots()
    refreshed_records = compact.configure_collision_refresh(records, REFRESHED)
    refreshed_grid2 = compact.configure_grid2_refresh(records, (43,))
    compaction = compact.compact_runtime_objects(records, EXCLUDED)

    # The map loader's collision result must remain byte exact.
    grid_hash_equal = []
    import hashlib
    for pointer_address in full.GRID_POINTERS:
        full_pointer = full.get(pointer_address, "I")[0]
        compact_pointer = compact.get(pointer_address, "I")[0]
        size = width * height * 2
        full_grid = bytes(full.u.mem_read(full_pointer, size))
        compact_grid = bytes(compact.u.mem_read(compact_pointer, size))
        grid_hash_equal.append(hashlib.sha256(full_grid).digest() ==
                               hashlib.sha256(compact_grid).digest())

    segments = [
        (30, ()), (30, ("RIGHT",)), (30, ("RIGHT", "UP")),
        (30, ("RIGHT", "C")), (30, ("LEFT",)),
        (30, ("LEFT", "UP")), (30, ("LEFT", "C")), (30, ()),
    ]
    mismatches = []
    retained_object_mismatches = []
    full_seconds = compact_seconds = 0.0
    tick = 0
    for count, keys in segments:
        for _ in range(count):
            started = time.perf_counter()
            full_state = full.step_world_chain(keys, call_limit=full_map["records"] * 1500)
            full_seconds += time.perf_counter() - started
            started = time.perf_counter()
            compact.refresh_compacted_collisions()
            compact_state = compact.step_world_chain(
                keys, call_limit=compact_map["records"] * 1500)
            compact_seconds += time.perf_counter() - started
            tick += 1
            if full_state != compact_state:
                mismatches.append({"tick": tick, "keys": list(keys),
                                   "full": full_state, "compact": compact_state})
                break
            if tick % 30 == 0:
                for record_index, compact_index in compact.runtime_index_by_record.items():
                    if object_bytes(full, record_index) != object_bytes(compact, compact_index):
                        retained_object_mismatches.append({
                            "tick": tick,
                            "record_index": record_index,
                            "runtime_index": compact_index,
                            "tile_id": records[record_index][0],
                        })
                        break
        if mismatches:
            break

    timed_ticks = tick
    # Exercise collision at representative static-metal tiles after the
    # ordinary spawn trace. The player's feet start exactly on each tile top;
    # gravity, walking, jumping and rolling must remain byte-for-byte equal.
    contact_cases = []
    samples = []
    for candidate_id in (3, 18, 26, 36, 37, 43):
        positions = [(x, y) for tile_id, x, y in records if tile_id == candidate_id]
        if not positions:
            continue
        chosen = ([positions[0], positions[len(positions) // 2], positions[-1]]
                  if candidate_id == 18 else [positions[len(positions) // 2]])
        samples.extend((candidate_id, x, y) for x, y in chosen)
    for tile_id, x, y in samples:
        for keys in ((), ("RIGHT",), ("LEFT",), ("UP",), ("DOWN",)):
            # Put the body through a ladder cell; solid/slope samples start
            # with their feet exactly on the tile top.
            player_y = y + 1 if tile_id == 3 else y
            full.place_player_at_spawn((x, player_y))
            compact.place_player_at_spawn((x, player_y))
            states_equal = True
            for _ in range(8):
                full_state = full.step_world_chain(keys, call_limit=full_map["records"] * 1500)
                compact.refresh_compacted_collisions()
                compact_state = compact.step_world_chain(keys, call_limit=compact_map["records"] * 1500)
                tick += 1
                if full_state != compact_state:
                    states_equal = False
                    mismatches.append({"tick": tick, "keys": list(keys),
                                       "position": [x, y], "full": full_state,
                                       "compact": compact_state})
                    break
            contact_cases.append({"tile_id": tile_id, "tile": [x, y], "keys": list(keys),
                                  "ticks": 8, "exact": states_equal})
            if mismatches:
                break
        if mismatches:
            break

    payload = {
        "ok": not mismatches and not retained_object_mismatches and all(grid_hash_equal),
        "map": str(MAP),
        "map_size": [width, height],
        "tile_counts": dict(sorted(Counter(record[0] for record in records).items())),
        "compaction": compaction,
        "refreshed_static_collision_records": refreshed_records,
        "refreshed_grid2_records": refreshed_grid2,
        "collision_grids_exact": grid_hash_equal,
        "ticks_compared": tick,
        "input_segments": [{"ticks": n, "keys": list(keys)} for n, keys in segments],
        "player_state_mismatches": mismatches[:3],
        "retained_object_mismatches": retained_object_mismatches[:3],
        "metal_contact_cases": contact_cases,
        "full_tick_rate": round(timed_ticks / full_seconds, 2),
        "compact_tick_rate": round(timed_ticks / compact_seconds, 2),
        "speedup": round(full_seconds / compact_seconds, 2),
        "scope": "spawn-area trace; does not prove every interaction on the map",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
