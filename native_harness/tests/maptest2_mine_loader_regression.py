"""Verify the normal Client's post-builder grid mask for raw87/raw88 mines."""
from pathlib import Path
import json
import struct
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

SNAPSHOT = HARNESS / "private_snapshots" / "hun1_full.zip"
LMF = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\맵테스트2.LMF")
OUTPUT = HARNESS / "evidence" / "maptest2_mine_loader_regression.json"

api = NativeTrainingAPI(SNAPSHOT, LMF, track_dirty=False)
width, _height, records = api.oracle.parse_lmf(LMF)
grid1 = api.oracle.get(api.oracle.GRID_POINTERS[1], "I")[0]
mine_cells = [(index, tile_id, x, y) for index, (tile_id, x, y) in enumerate(records)
              if tile_id in (87, 88)]
values = [struct.unpack("<H", api.oracle.u.mem_read(grid1 + 2 * (y * width + x), 2))[0]
          for _index, _tile_id, x, y in mine_cells]

# Start one cell above the raw88 floor mine at (11, 9). The Client coordinate stored
# by place_player_at_spawn is the player's upper edge, so (11, 8) makes the
# feet land on the mine. raw87 is the other bomb orientation and is not this
# floor-contact fixture.
api.oracle.place_player_at_spawn((11, 8))
route = []
for tick in range(1, 61):
    state = api.step(1, ())
    route.append({"tick": tick, **state})
first_hit = next((row for row in route
                  if row["38"] == 5 or row["7c"] not in (0, -1)), None)
result = {
    "ok": len(mine_cells) == 29 and all(value == 1 for value in values)
          and first_hit is not None,
    "map": str(LMF),
    "mine_cells": len(mine_cells),
    "grid1_values": sorted(set(values)),
    "first_hit": first_hit,
    "route": route,
}
OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "route"}, ensure_ascii=False, indent=2))
if not result["ok"]:
    raise SystemExit(1)
