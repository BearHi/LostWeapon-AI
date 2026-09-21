"""Exploratory original-x86 probe for team bases (raw122 -> type700)."""
from pathlib import Path
import json
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

LMF = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\문어\칼3.lmf")
api = NativeTrainingAPI(HARNESS / "private_snapshots/hun1_full.zip", LMF,
                        track_dirty=True)
oracle = api.oracle
BASES = (0xA074460, 0xA074558)
results = []

for x, y in ((320.0, 194.0), (1120.0, 194.0)):
    oracle.place_player_at_spawn((int(x // 32), int(y // 32)))
    oracle.put(oracle.player_address, "dd", x, y)
    baseline = api.save_state()

    branches = {}
    for name, keys in (("noop", ()), ("space", ("SPACE",))):
        api.restore_state(baseline)
        before = [bytes(oracle.u.mem_read(address, 0xF8)) for address in BASES]
        trace = [api.step(1, keys) for _ in range(60)]
        after = [bytes(oracle.u.mem_read(address, 0xF8)) for address in BASES]
        branches[name] = {
            "final_player": trace[-1],
            "base_changed_offsets": [
                [index for index, (a, b) in enumerate(zip(old, new)) if a != b]
                for old, new in zip(before, after)
            ],
        }
    results.append({"position": [x, y], **branches})

payload = {
    "map": str(LMF),
    "special_object_count": oracle.get(0xA072AA4, "i")[0],
    "special_objects": [
        {"address": hex(address), "type": oracle.get(address, "i")[0],
         "bounds": list(oracle.get(address + 0x28, "4i")),
         "team_flag_94": oracle.get(address + 0x94, "i")[0]}
        for address in BASES
    ],
    "results": results,
}
(HARNESS / "evidence/raw122_base_space_offline_probe.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2))
