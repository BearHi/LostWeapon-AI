from pathlib import Path
import sys, json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle

SNAPSHOTS = sys.argv[1:] or [
    str(ROOT / 'private_snapshots/hun1_full.zip'),
    str(ROOT / 'private_snapshots/hun1_live.zip'),
    str(ROOT / 'private_snapshots/current_live.zip'),
]
ADDRESSES = [0xaa16538, 0xaa16540, 0x25a2518, 0x25ca048, 0x2248ab4, 0x4ae67c, 0x8952db0, 0x8952db4]
out = {}
for raw in SNAPSHOTS:
    path = Path(raw)
    oracle = CapturedOracle(path)
    values = {}
    for address in ADDRESSES:
        try:
            values[hex(address)] = oracle.get(address, 'I')[0]
        except Exception as exc:
            values[hex(address)] = str(exc)
    out[str(path)] = {
        'state': oracle.meta['state'],
        'player': oracle.read_player_state(),
        'globals': values,
    }
print(json.dumps(out, indent=2))
