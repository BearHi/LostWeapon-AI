"""Build a disposable 훈3 variant with the middle platform raised one tile."""
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
source = ROOT.parent / "훈련용맵" / "훈3.LMF"
target = ROOT / "tests" / "hun3_middle_platform_up_one.LMF"
data = bytearray(source.read_bytes())
if data[:16] != b"NewLWMapFile_1.0":
    raise ValueError("unexpected LMF header")
count = struct.unpack_from("<H", data, 21)[0]
changed = 0
for index in range(count):
    offset = 32 + index * 8
    tile, x, y = struct.unpack_from("<IHH", data, offset)
    if tile == 7 and 13 <= x <= 17 and y == 12:
        struct.pack_into("<IHH", data, offset, tile, x, 11)
        changed += 1
if changed != 5:
    raise ValueError(f"expected five platform records, changed {changed}")
target.write_bytes(data)
print({"output": str(target), "changed_records": changed,
       "mutation": "middle platform y12 -> y11"})
