"""Select the captured runtime resource base used by the native playground."""
from pathlib import Path
import re

SNAPSHOTS = {
    "훈1": "hun1_full.zip", "훈2": "hun2_live.zip", "훈5": "hun5_live.zip",
    "훈6": "hun6_live.zip", "훈7": "hun7_live.zip", "훈8.5": "hun85_live.zip",
    "훈10": "hun10_live.zip", "훈12": "hun12_live.zip", "훈13": "hun13_live.zip",
    "훈14": "hun14_live.zip", "훈15": "hun14_live.zip", "훈16": "hun16_live.zip",
    "훈17": "hun17_live.zip", "훈18": "hun18_live.zip", "훈19": "hun19_live.zip",
    "훈20": "hun20_live.zip",
}


def snapshot_for_map(root: Path, lmf: Path) -> Path:
    stem = Path(lmf).stem
    name = SNAPSHOTS.get(stem)
    if name is None:
        try:
            from lmf_injector import SimpleLmfOracle
            _w, _h, recs = SimpleLmfOracle.parse_lmf(Path(lmf))
            if any(tile == 4 for tile, _x, _y in recs):
                name = "hun85_live.zip"
            elif any(tile in (5, 6) for tile, _x, _y in recs):
                name = "hun2_live.zip"
        except Exception:
            pass
    if name is None:
        match = re.search(r"(\d+(?:\.\d+)?)", stem)
        if match:
            num_str = match.group(1)
            num = float(num_str) if "." in num_str else int(num_str)
            name = SNAPSHOTS.get(f"훈{num}")
    name = name or "hun1_full.zip"
    return Path(root) / "private_snapshots" / name
