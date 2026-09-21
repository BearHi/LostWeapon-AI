"""Keep custom-map pixel bounds synchronized with rebuilt LMF grids."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(ROOT))

from lmf_injector import NativeLmfOracle


oracle = NativeLmfOracle(ROOT / "private_snapshots" / "hun1_full.zip")
info = oracle.load_lmf(PROJECT / "훈련용맵" / "훈3.LMF", fresh_spawn=True)
width, height = info["size"]
assert info["pixel_size"] == [width * 32, height * 32]
assert list(oracle.get(0x8952DC4, "ii")) == info["pixel_size"]

for pointer_global in oracle.GRID_POINTERS:
    metadata = pointer_global - 0x14
    assert list(oracle.get(metadata - 8, "ii")) == [width, height]
    assert list(oracle.get(metadata + 0x0C, "ii")) == info["pixel_size"]

print({"status": "PASS", "map": info["path"], "tiles": info["size"],
       "pixels": info["pixel_size"]})
