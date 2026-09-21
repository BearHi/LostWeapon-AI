"""Summarize observed online hit phases without inventing invulnerability rules."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path


def analyze(paths: list[Path]) -> dict:
    hits = []
    close_attack_samples = Counter()
    roll_attack_samples = Counter()
    for path in paths:
        previous = None
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            players = {p["slot"]: p for p in row["players"]}
            local = row.get("local_slot", 0)
            other = next((slot for slot in players if slot != local), None)
            if local not in players or other is None:
                previous = row
                continue
            own, opponent = players[local], players[other]
            distance = math.dist(own["pos"], opponent["pos"])
            attack = opponent["state"]["0x38"] in range(15, 21)
            rolling = own["state"]["0x38"] in (1, 2)
            phase = (opponent["state"]["0x38"], opponent["state"]["0x3c"])
            if distance <= 128 and attack:
                close_attack_samples[phase] += 1
                if rolling:
                    roll_attack_samples[phase] += 1
            before = ({p["slot"]: p for p in previous["players"]}
                      if previous is not None else {})
            if local in before and own["hp"] < before[local]["hp"]:
                rolling_before_hit = before[local]["state"]["0x38"] in (1, 2)
                hits.append({"trace": path.name, "perf_ns": row["perf_ns"],
                             "damage": round(before[local]["hp"] - own["hp"], 3),
                             "distance": round(distance, 1),
                             "opponent_state": phase[0], "opponent_animation": phase[1],
                             "own_state": own["state"]["0x38"],
                             "own_rolling_before_hit": rolling_before_hit,
                             "close": distance <= 128})
            previous = row
    return {
        "scope": "read-only normal-client observations; not a confirmed hitbox or invulnerability table",
        "hits": hits,
        "close_attack_samples": {f"{state}:{frame}": count
                                 for (state, frame), count in sorted(close_attack_samples.items())},
        "roll_attack_samples": {f"{state}:{frame}": count
                                for (state, frame), count in sorted(roll_attack_samples.items())},
        "warning": "A roll state is not assumed invulnerable; damage may also come from hazards.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("traces", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.traces)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"hits": len(result["hits"]),
                      "close_hits": sum(hit["close"] for hit in result["hits"]),
                      "rolling_hits": sum(hit["own_rolling_before_hit"] for hit in result["hits"]),
                      "attack_phases_seen": len(result["close_attack_samples"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
