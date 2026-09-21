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
        # Variant curricula may use another prefix (for example 혼5) while
        # retaining the numbered mechanic family. Select the captured runtime
        # resource by that family number, not by a hard-coded filename.
        match = re.search(r"(\d+(?:\.\d+)?)", stem)
        if match:
            name = SNAPSHOTS.get(f"훈{match.group(1)}")
    name = name or "hun1_full.zip"
    return Path(root) / "private_snapshots" / name
