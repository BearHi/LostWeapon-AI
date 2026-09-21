"""User-confirmed LostWeapon input-mask rules remain permissive where uncertain."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_env import ACTIONS, LostWeaponEnv


class Planner:
    def surface_for_player(self, state):
        return object() if state.get("grounded") else None


env = object.__new__(LostWeaponEnv)
env.planner = Planner()


def allowed(**changes):
    state = {"38": 0, "7c": 0, "c0": 0, "dc": 0, "grounded": False}
    state.update(changes)
    return set(env.valid_action_indices(state))


assert {10, 11}.issubset(allowed(grounded=True)) and 12 not in allowed(grounded=True)
assert {5, 10, 11}.issubset(allowed(grounded=False)) and 12 not in allowed(grounded=False)
assert {5, 8, 9, 13, 14, 15, 16, 17, 18}.issubset(allowed(**{"38": 5}))
assert allowed(**{"38": 0, "74": 1}) == {0, 3, 4, 6, 7, 14, 15, 16, 17, 18}
# A damage/protection code can outlive the definite state38=5 hit frame.
# Keep uncertain recovery states permissive and let native physics decide.
assert {1, 2, 14}.issubset(allowed(**{"7c": 12}))
assert allowed(c0=21) == {0, 1, 2, 3, 4, 6, 7, 8, 9, 14}
assert allowed(dc=1) == {0, 1, 2, 5, 10, 11, 14, 15, 16, 17, 18}
assert ACTIONS[19:] == (("LEFT", "DOWN", "Z"), ("RIGHT", "DOWN", "Z"))
assert {19, 20}.issubset(allowed(grounded=True))
assert {19, 20}.issubset(allowed(**{"38": 5}))
assert {19, 20}.isdisjoint(allowed(c0=21) | allowed(dc=1) | allowed(**{"38": 0, "74": 1}))
print({"ok": True,
       "ground_blocked": [ACTIONS[12]],
       "ground_horizontal_c_deferred_to_native": [ACTIONS[i] for i in (10, 11)],
       "air_parachute_inputs": [ACTIONS[i] for i in (5, 10, 11)],
       "hit_allowed": [ACTIONS[i] for i in sorted(allowed(**{"38": 5}))],
       "ladder_allowed": [ACTIONS[i] for i in sorted(allowed(**{"38": 0, "74": 1}))],
       "water_allowed": [ACTIONS[i] for i in sorted(allowed(c0=21))],
       "parachute_allowed": [ACTIONS[i] for i in sorted(allowed(dc=1))]})
