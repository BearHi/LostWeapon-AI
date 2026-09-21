"""Create tiny one-action LMF probes for calibrating cliff movement."""

from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).parents[1]
HEADER_SOURCE = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\암벽수정1.LMF")
OUT = ROOT / "analysis" / "physics_probes"
W, H = 31, 80


def make(name: str, target_x1: int, target_x2: int, target_y: int) -> None:
    cells = {(x, H - 1): 8 for x in range(2, 29)}
    for x in range(target_x1, target_x2 + 1):
        cells[(x, target_y)] = 8
    cells[(15, H - 3)] = 100
    records = [(tid, x, y) for (x, y), tid in sorted(cells.items(), key=lambda item: (item[0][1], item[0][0]))]
    header = bytearray(HEADER_SOURCE.read_bytes()[:32])
    struct.pack_into("<H", header, 16, W)
    struct.pack_into("<H", header, 18, H)
    struct.pack_into("<I", header, 21, len(records))
    data = bytes(header) + b"".join(struct.pack("<Ihh", tid, x, y) for tid, x, y in records)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.LMF").write_bytes(data)


def main() -> None:
    probes = {
        "물리측정_뒷굴_높이08": (18, 19, 71),
        "물리측정_뒷굴_높이10": (18, 19, 69),
        "물리측정_뒷굴_높이12": (18, 19, 67),
        "물리측정_뒷굴_높이14": (18, 19, 65),
        "물리측정_뒷굴_거리08": (23, 24, 71),
        "물리측정_뒷굴_거리10": (25, 26, 71),
    }
    for name, args in probes.items():
        make(name, *args)
    print(OUT)


if __name__ == "__main__":
    main()
