"""Grow a captured-state sparse footprint from bounded unmapped-page faults."""
from pathlib import Path
import sys, json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sparse_oracle import SparseCapturedOracle

SNAPSHOT = Path(sys.argv[1])
FOOTPRINT = Path(sys.argv[2])
OUTPUT = Path(sys.argv[3])
CALL_LIMIT = int(sys.argv[4]) if len(sys.argv) > 4 else 10000000
MAX_ROUNDS = int(sys.argv[5]) if len(sys.argv) > 5 else 32

SEQUENCES = {
    'noop': [()] * 12,
    'right': [('RIGHT',)] * 12,
    'jump': [('UP',)] + [()] * 11,
    'front_roll': [('RIGHT', 'DOWN')] * 12,
    'back_roll': [('LEFT', 'DOWN')] * 12,
    'jump_backroll': [('UP',)] + [()] * 8 + [('LEFT', 'DOWN')] * 3,
    'backroll_chute': [('LEFT', 'DOWN')] * 8 + [('RIGHT', 'C')] + [()] * 3,
}


def add_page(data, page):
    token = hex(page)
    changed = False
    for item in data['scenarios'].values():
        for field in ('read_ranges', 'write_ranges', 'exec_ranges'):
            values = item.setdefault(field, [])
            if token not in values:
                values.append(token)
                changed = True
    return changed


footprint = json.loads(FOOTPRINT.read_text())
faults = []
tests = {}
for round_no in range(1, MAX_ROUNDS + 1):
    progressed = False
    for name, actions in SEQUENCES.items():
        oracle = SparseCapturedOracle(SNAPSHOT, FOOTPRINT)
        try:
            start = oracle.read_player_state()
            trace = [oracle.step_world_chain(keys, call_limit=CALL_LIMIT) for keys in actions]
            tests[name] = {'status': 'PASS', 'start': start, 'end': trace[-1]}
            print('round', round_no, name, 'PASS', flush=True)
        except Exception as exc:
            fault = oracle.fault or {}
            address = int(fault.get('address', '0'), 16) & ~0xfff
            if not address or not add_page(footprint, address):
                tests[name] = {'status': 'BLOCKED', 'error': str(exc), 'fault': fault}
                raise
            faults.append({'round': round_no, 'scenario': name, 'page': hex(address), 'fault': fault})
            FOOTPRINT.write_text(json.dumps(footprint, indent=2))
            print('round', round_no, name, 'ADD', hex(address), flush=True)
            progressed = True
            break
    if not progressed and len(tests) == len(SEQUENCES):
        break
else:
    raise RuntimeError(f'Adaptive footprint did not converge in {MAX_ROUNDS} rounds')

result = {
    'scope': 'adaptive sparse world-chain validation',
    'snapshot': str(SNAPSHOT),
    'call_limit': CALL_LIMIT,
    'fault_pages_added': faults,
    'sparse': SparseCapturedOracle(SNAPSHOT, FOOTPRINT).sparse_info(),
    'tests': tests,
}
OUTPUT.write_text(json.dumps(result, indent=2))
