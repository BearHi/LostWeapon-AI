"""Controlled original-x86 hit envelope for each weapon, with NOOP controls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from combat_env import LostWeaponCombatEnv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distances", type=int, nargs="+", default=[48, 64, 80, 96, 112, 128, 160, 192])
    parser.add_argument("--weapons", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--ticks", type=int, default=24)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "evidence/weapon_envelope_probe.json")
    args = parser.parse_args()
    env = LostWeaponCombatEnv(ROOT / "private_snapshots/team_p2p_combat_live.zip",
                              peer_snapshot=ROOT / "private_snapshots/team_slot1_live.zip",
                              max_steps=args.ticks)
    oracle = env.oracle

    def run(weapon: int, distance: int, attack: bool) -> dict:
        env.reset(spawn_distance=distance)
        oracle.step_combat_tick({0: (str(weapon),), 1: ()})
        oracle.step_combat_tick({0: (), 1: ()})
        selected = oracle.read_combatant(0)["weapon"]
        if selected != weapon:
            raise RuntimeError(f"weapon selection failed: requested {weapon}, got {selected}")
        rows = []
        for tick in range(args.ticks):
            players = oracle.step_combat_tick({0: ("Z",) if attack and tick == 0 else (), 1: ()})
            rows.append({"tick": tick + 1,
                         "attacker_state": players[0]["38"],
                         "attacker_frame": players[0]["3c"],
                         "attacker_weapon": players[0]["weapon"],
                         "attacker_x": players[0]["x"],
                         "target_x": players[1]["x"],
                         "target_hp": players[1]["hp"]})
            if attack and players[1]["hp"] < 100:
                break
        return {"final_hp": rows[-1]["target_hp"],
                "first_attack_state": rows[0]["attacker_state"],
                "first_loss_tick": next((r["tick"] for r in rows if r["target_hp"] < 100), None),
                "trace": rows}

    result = {"scope": "original x86 dual-view; geometric starting distance, not universal weapon reach",
              "preflight_damage": env.capture_settle_damage, "rows": []}
    for weapon in args.weapons:
        for distance in args.distances:
            control = run(weapon, distance, False)
            tested = run(weapon, distance, True)
            if tested["first_attack_state"] != 14 + weapon:
                raise RuntimeError(f"attack state mismatch for weapon {weapon}: "
                                   f"{tested['first_attack_state']}")
            clean = control["final_hp"] == 100 and tested["first_loss_tick"] is not None
            result["rows"].append({"weapon": weapon, "start_dx": distance,
                                   "control_hp": control["final_hp"],
                                   "attack_hp": tested["final_hp"],
                                   "attack_first_loss_tick": tested["first_loss_tick"],
                                   "clean_hit": clean,
                                   "attack_trace": tested["trace"]})
        print(f"weapon {weapon}/4 complete", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "clean_hits": [
        {"weapon": r["weapon"], "start_dx": r["start_dx"],
         "tick": r["attack_first_loss_tick"]}
        for r in result["rows"] if r["clean_hit"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
