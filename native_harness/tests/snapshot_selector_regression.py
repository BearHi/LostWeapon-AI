from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from snapshot_selector import snapshot_for_map

expected = {
    "혼5.LMF": "hun5_live.zip",
    "혼7.LMF": "hun7_live.zip",
    "혼8.5.LMF": "hun85_live.zip",
    "혼12.LMF": "hun12_live.zip",
    "혼20.LMF": "hun20_live.zip",
}
actual = {name: snapshot_for_map(ROOT, Path(name)).name for name in expected}
assert actual == expected, actual
print({"ok": True, "variants": actual})
