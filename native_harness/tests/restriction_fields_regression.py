"""Synthetic IDs test geometry and input semantics, not game ID discovery."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_env import ACTIONS, LostWeaponEnv
from restriction_fields import (KINDS, KNOWN_RESTRICTION_IDS,
                                RestrictionFields, filter_actions)
from lmf_injector import NativeLmfOracle

assert KNOWN_RESTRICTION_IDS == {136: "jump", 137: "roll",
                                 138: "parachute", 139: "weapon"}
fixture = ROOT.parent / "훈련용맵" / "금지블록.LMF"
_width, _height, records = NativeLmfOracle.parse_lmf(fixture)
assert [(tile, x, y) for tile, x, y in records if tile in (136, 137, 138) ] == [
    (136, 6, 11), (137, 12, 11), (138, 18, 11)]
assert sum(tile == 139 for tile, _x, _y in records) == 15

ids = {201: "parachute", 202: "jump", 203: "roll", 204: "weapon"}
fields = RestrictionFields([(tile, 20, 20) for tile in ids], ids)
assert fields.active_at(25 * 32, 24 * 32) == set(KINDS)
assert fields.active_at(15 * 32, 16 * 32) == set(KINDS)
assert not fields.active_at(26 * 32, 24 * 32)
assert not fields.active_at(25 * 32, 25 * 32)

allowed = filter_actions(ACTIONS, range(len(ACTIONS)), set(KINDS))
assert {0, 1, 2, 4, 14, 15, 16, 17, 18}.issubset(allowed)
assert {3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 19, 20}.isdisjoint(allowed)
assert 3 in filter_actions(ACTIONS, range(len(ACTIONS)), {"jump"}, up_is_jump=False)

env = object.__new__(LostWeaponEnv)
env.restrictions = fields
inside = {"x": 25 * 32, "y": 24 * 32, "38": 7, "74": 0, "c0": 0, "dc": 0}
outside = {**inside, "x": 26 * 32}
assert set(env.valid_action_indices(inside)) == set(allowed) - {12}
assert {3, 5, 8, 13, 19}.issubset(env.valid_action_indices(outside))
observation = [0.0] * (14 + len(KINDS))
observation[3] = inside["38"] / 32
observation[6] = inside["74"] / 32
observation[10] = inside["c0"] / 8
observation[11] = inside["dc"] / 4
for offset in range(len(KINDS)):
    observation[14 + offset] = 1.0
assert set(env.valid_action_indices_from_observation(observation)) == set(
    env.valid_action_indices(inside))
print("PASS: four bans, inclusive +/-5 x +/-4 tile boundary, unchanged outside")
