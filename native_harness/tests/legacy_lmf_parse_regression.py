from pathlib import Path
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from lmf_injector import NativeLmfOracle

for relative in ("Map/문어/칼전틀.LMF", "Map/문어/칼4.lmf"):
    path = HARNESS.parent / relative
    width, height, records = NativeLmfOracle.parse_lmf(path)
    assert width > 0 and height > 0 and records
    assert path.stat().st_size == 25 + len(records) * 5
print("PASS")
