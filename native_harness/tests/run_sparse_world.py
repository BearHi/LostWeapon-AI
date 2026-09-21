from pathlib import Path
import sys, json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sparse_oracle import SparseCapturedOracle
SNAPSHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'private_snapshots/hun1_full.zip'
FOOTPRINT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'evidence/world_subset_analysis.json'
OUTPUT = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / 'evidence/sparse_world_tests.json'
CALL_LIMIT = int(sys.argv[4]) if len(sys.argv) > 4 else 2000000

SEQUENCES = {
    'noop': [()] * 12,
    'right': [('RIGHT',)] * 12,
    'jump': [('UP',)] + [()] * 11,
    'front_roll': [('RIGHT', 'DOWN')] * 12,
    'back_roll': [('LEFT', 'DOWN')] * 12,
    'jump_backroll': [('UP',)] + [()] * 8 + [('LEFT', 'DOWN')] * 3,
    'backroll_chute': [('LEFT', 'DOWN')] * 8 + [('RIGHT', 'C')] + [()] * 3,
}

out = {
    'scope': 'world-chain footprint sparse mapping',
    'tests': {},
    'sparse': None,
}

for name, actions in SEQUENCES.items():
    oracle = SparseCapturedOracle(
        SNAPSHOT,
        FOOTPRINT,
    )
    if out['sparse'] is None:
        out['sparse'] = oracle.sparse_info()
    try:
        start = oracle.read_player_state()
        trace = [oracle.step_world_chain(keys, call_limit=CALL_LIMIT) for keys in actions]
        out['tests'][name] = {
            'status': 'PASS',
            'start': start,
            'end': trace[-1],
        }
        print(name, 'PASS', trace[-1], flush=True)
    except Exception as exc:
        out['tests'][name] = {
            'status': 'BLOCKED',
            'error': str(exc),
            'fault': oracle.fault,
        }
        print(name, 'BLOCKED', str(exc), flush=True)

OUTPUT.write_text(json.dumps(out, indent=2))
