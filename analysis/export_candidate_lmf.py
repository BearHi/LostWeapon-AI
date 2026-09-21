"""Export a JSON cliff candidate to an LMF using a known-good header."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def export(candidate_path: Path, header_source: Path, output_path: Path) -> None:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    source = header_source.read_bytes()
    if len(source) < 32:
        raise ValueError("header source is shorter than 32 bytes")
    width = int(candidate["width"])
    height = int(candidate["height"])
    cells = {(int(x), int(y)): 8 for x, y in candidate["solid_cells"]}
    # Existing cliff maps place the respawn marker two cells above the floor.
    floor_y = max(y for x, y in cells)
    spawn_x = int(candidate["start"]["x"])
    spawn_y = floor_y - 2
    cells[(spawn_x, spawn_y)] = 100

    records = [(tile_id, x, y) for (x, y), tile_id in sorted(cells.items(), key=lambda item: (item[0][1], item[0][0]))]
    header = bytearray(source[:32])
    struct.pack_into("<H", header, 16, width)
    struct.pack_into("<H", header, 18, height)
    struct.pack_into("<I", header, 21, len(records))
    body = b"".join(struct.pack("<Ihh", tile_id, x, y) for tile_id, x, y in records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes(header) + body)
    print(json.dumps({"output": str(output_path), "width": width, "height": height, "records": len(records), "spawn": [spawn_x, spawn_y]}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("header_source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.candidate, args.header_source, args.output)


if __name__ == "__main__":
    main()
