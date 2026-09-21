"""raw43 cyan-ring/black-cap mine must retain its Client runtime record."""
from pathlib import Path
import json
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

snapshot = HARNESS / "private_snapshots" / "hun1_full.zip"
lmf = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\기존\자석낙라1.LMF")
api = NativeTrainingAPI(snapshot, lmf, track_dirty=False)
width, height, records = api.oracle.parse_lmf(lmf)
mine_records = [(i, x, y) for i, (tile, x, y) in enumerate(records) if tile == 43]
retained = [i for i, _x, _y in mine_records if i in api.oracle.runtime_index_by_record]

# Touch the raw43 mine at (3,12) from immediately above.
api.oracle.place_player_at_spawn((3, 11))
trace = []
for tick in range(1, 25):
    state = api.step(1, ())
    trace.append({"tick": tick, **state})
first_hit = next((row for row in trace if row["38"] == 5 or row["7c"] not in (0, -1)), None)
result = {"ok": len(mine_records) == len(retained) and first_hit is not None,
          "raw43_records": len(mine_records), "retained_runtime_records": len(retained),
          "first_hit": first_hit, "trace": trace}
(HARNESS / "evidence" / "raw43_blue_mine_regression.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "trace"}, ensure_ascii=False, indent=2))
if not result["ok"]:
    raise SystemExit(1)
