"""Read-only online combat risk signal. Never sends input to the Client."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from live_state import Reader


ATTACK_STATES = frozenset(range(15, 21))
EVIDENCE = Path(__file__).resolve().parent / "evidence"
ENVELOPES = (
    EVIDENCE / "weapon_envelope_verified_20260917.json",
    EVIDENCE / "weapon_envelope_fine_12_20260917.json",
    EVIDENCE / "weapon_envelope_fine_34_20260917.json",
)


def load_envelope(paths) -> dict[int, dict]:
    rows = []
    for path in paths:
        if path.exists():
            rows.extend(json.loads(path.read_text(encoding="utf-8"))["rows"])
    result = {}
    for weapon in range(1, 5):
        samples = [row for row in rows if row["weapon"] == weapon and row["control_hp"] == 100]
        hits = [row["start_dx"] for row in samples if row["clean_hit"]]
        misses = [row["start_dx"] for row in samples if not row["clean_hit"]]
        result[weapon] = {"observed_hit_start_dx": max(hits) if hits else None,
                          "observed_miss_start_dx": min(misses) if misses else None}
    return result


def assess(own: dict, opponent: dict, *, alert_radius=160, envelope=None) -> dict:
    dx = own["pos"][0] - opponent["pos"][0]
    dy = own["pos"][1] - opponent["pos"][1]
    facing_right = opponent["state"]["0xb0"] == 0
    facing_toward = (dx >= 0) == facing_right
    attacking = opponent["state"]["0x38"] in ATTACK_STATES
    near = abs(dx) <= alert_radius and abs(dy) <= 96
    selected_weapon = opponent.get("weapon")
    # A player may switch the selected slot while an earlier attack animates.
    # The attack state is the measured weapon identity for states 15..18.
    attack_weapon = opponent["state"]["0x38"] - 14 if 15 <= opponent["state"]["0x38"] <= 18 else None
    return {
        "candidate_threat": attacking and near and facing_toward,
        "selected_weapon": selected_weapon,
        "attack_weapon": attack_weapon,
        "flat_probe": (envelope or {}).get(attack_weapon),
        "attack_state": opponent["state"]["0x38"],
        "attack_frame": opponent["state"]["0x3c"],
        "dx": round(dx, 1), "dy": round(dy, 1),
        "own_roll_state": own["state"]["0x38"] in (1, 2),
        "note": "Alert radius is user-chosen, not exact hit reach; flat probe is one Z attack only",
    }


def live_players(reader: Reader) -> tuple[int, list[dict]]:
    own_slot = reader.state()["slot"]
    players = []
    for slot in range(8):
        address = 0x3B12A00 + slot * 0xF8
        header = reader.get(address - 16, "4i")
        if not any(header):
            continue
        players.append({"slot": slot, "pos": reader.get(address, "dd"),
                        "hp": reader.get(address + 0x60, "d")[0],
                        "weapon": reader.get(0x25F1AD8 + slot * 4, "i")[0] + 1,
                        "state": {hex(offset): reader.get(address + offset, "i")[0]
                                  for offset in (0x38, 0x3C, 0xB0)}})
    return own_slot, players


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pid", type=int)
    source.add_argument("--trace", type=Path)
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--alert-radius", type=float, default=160,
                        help="Conservative warning distance in pixels; not exact weapon reach")
    args = parser.parse_args()
    envelope = load_envelope(ENVELOPES)
    if args.trace:
        rows = (json.loads(line) for line in args.trace.open(encoding="utf-8"))
        reader = None
    else:
        reader = Reader(args.pid)
        deadline = time.perf_counter() + args.seconds

        def poll():
            while time.perf_counter() < deadline:
                slot, players = live_players(reader)
                yield {"local_slot": slot, "players": players}
                time.sleep(.016)
        rows = poll()
    last = None
    emitted = 0
    try:
        for row in rows:
            players = {p["slot"]: p for p in row["players"]}
            own = players.get(row.get("local_slot", 0))
            if own is None:
                continue
            for opponent in players.values():
                if opponent["slot"] == own["slot"]:
                    continue
                assessment = assess(own, opponent, alert_radius=args.alert_radius,
                                    envelope=envelope)
                current = (opponent["slot"], assessment["candidate_threat"],
                           assessment["attack_state"], assessment["attack_frame"])
                if assessment["candidate_threat"] and current != last:
                    print(json.dumps({"opponent_slot": opponent["slot"], **assessment},
                                     ensure_ascii=False), flush=True)
                    emitted += 1
                    if args.max_events and emitted >= args.max_events:
                        return
                last = current
    finally:
        if reader is not None:
            reader.close()


if __name__ == "__main__":
    main()
