"""Probe each original x86 gameplay function on one captured snapshot.

Each function gets a fresh emulator and a bounded instruction budget so a
map-specific loop cannot stall the investigation.
"""
from pathlib import Path
import sys, json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from unicorn import UC_HOOK_CODE

SNAPSHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'private_snapshots/hun1_full.zip'
OUTPUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'evidence/snapshot_chain_probe.json'
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 250000

FUNCTIONS = [
    ('input', 0x4228c0),
    ('player_dispatch', 0x436e30),
    ('world_455f00', 0x455f00),
    ('world_453a50', 0x453a50),
    ('world_476000', 0x476000),
    ('world_461ac0', 0x461ac0),
    ('world_436620', 0x436620),
    ('world_415f10', 0x415f10),
]


def prepare(oracle):
    oracle.set_input(())
    ms, tick = oracle.get(oracle.CONTROL + 0x800, 'II')
    oracle.put(oracle.CONTROL + 0x800, 'II', ms + ((tick + 1) * 1000 // 60 - tick * 1000 // 60), tick + 1)


out = {
    'snapshot': str(SNAPSHOT),
    'instruction_limit': LIMIT,
    'start': None,
    'functions': {},
}
base = CapturedOracle(SNAPSHOT)
out['start'] = base.read_player_state()

for name, address in FUNCTIONS:
    oracle = CapturedOracle(SNAPSHOT)
    trace = []

    def on_code(_, a, size, user_data):
        trace.append(hex(a - oracle.delta))
        if len(trace) > 32:
            del trace[0]

    oracle.u.hook_add(UC_HOOK_CODE, on_code)
    prepare(oracle)
    try:
        oracle.call(address, limit=LIMIT)
        result = {'status': 'PASS', 'end': oracle.read_player_state(), 'trace': trace}
    except Exception as exc:
        result = {
            'status': 'BLOCKED',
            'error': str(exc),
            'fault': oracle.fault,
            'trace': trace,
        }
    out['functions'][name] = result
    print(name, result['status'], result.get('error', ''), flush=True)

OUTPUT.write_text(json.dumps(out, indent=2))
