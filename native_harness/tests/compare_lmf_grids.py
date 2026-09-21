"""Compare captured and original-builder collision grids for one LMF."""
from pathlib import Path
import hashlib
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from lmf_injector import NativeLmfOracle


def main():
    snapshot, lmf = map(Path, sys.argv[1:3])
    captured = CapturedOracle(snapshot)
    built = NativeLmfOracle(snapshot)
    info = built.load_lmf(lmf)
    width, height = info["size"]
    size = width * height * 2
    grids = []
    for index, global_address in enumerate(built.GRID_POINTERS):
        cp = captured.get(global_address, "I")[0]
        bp = built.get(global_address, "I")[0]
        expected = bytes(captured.u.mem_read(cp, size))
        actual = bytes(built.u.mem_read(bp, size))
        diffs = []
        for cell in range(width * height):
            a, b = struct.unpack_from("<H", expected, cell * 2)[0], struct.unpack_from("<H", actual, cell * 2)[0]
            if a != b:
                diffs.append({"x": cell % width, "y": cell // width, "captured": a, "built": b})
        grids.append({"grid": index, "captured_sha256": hashlib.sha256(expected).hexdigest(),
                      "built_sha256": hashlib.sha256(actual).hexdigest(), "differences": diffs})
    print(json.dumps(grids, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
