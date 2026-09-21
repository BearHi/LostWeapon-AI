"""Read/write/execute footprint for the candidate gameplay main-loop chain."""
from pathlib import Path
import sys, json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
SNAPSHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'private_snapshots/hun1_full.zip'
OUTPUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'evidence/world_subset_analysis.json'
CALL_LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 2000000
TICKS = int(sys.argv[4]) if len(sys.argv) > 4 else 12

SCENARIOS = {
    'noop': [()] * 12,
    'right': [('RIGHT',)] * 12,
    'jump': [('UP',)] + [()] * 11,
    'front_roll': [('RIGHT', 'DOWN')] * 12,
    'back_roll': [('LEFT', 'DOWN')] * 12,
    'jump_backroll': [('UP',)] + [()] * 8 + [('LEFT', 'DOWN')] * 3,
    'backroll_chute': [('LEFT', 'DOWN')] * 8 + [('RIGHT', 'C')] + [()] * 3,
    'parachute_fall': [('RIGHT',)] * 35 + [('RIGHT', 'C')] + [('RIGHT',)] * 60,
    'right_up': [('RIGHT', 'UP')] * 96,
    'right_z': [('RIGHT', 'Z')] * 96,
}


def classify(page, oracle):
    if oracle.base <= page < oracle.base + oracle.size:
        return 'client-image'
    if oracle.CONTROL <= page < oracle.CONTROL + 0x10000:
        return 'harness-control'
    if oracle.STACK <= page < oracle.STACK + 0x100000:
        return 'harness-stack'
    return 'mapped-private'


def run(actions):
    oracle = CapturedOracle(SNAPSHOT)
    reads, writes, execs = set(), set(), set()
    read_bytes = write_bytes = 0

    def on_read(_, __, address, size, ___, user_data):
        nonlocal read_bytes
        reads.update(range(address & ~0xfff, (address + size - 1 & ~0xfff) + 0x1000, 0x1000))
        read_bytes += size

    def on_write(_, __, address, size, ___, user_data):
        nonlocal write_bytes
        writes.update(range(address & ~0xfff, (address + size - 1 & ~0xfff) + 0x1000, 0x1000))
        write_bytes += size

    def on_code(_, address, size, user_data):
        execs.add(address & ~0xfff)

    oracle.u.hook_add(UC_HOOK_MEM_READ, on_read)
    oracle.u.hook_add(UC_HOOK_MEM_WRITE, on_write)
    oracle.u.hook_add(UC_HOOK_CODE, on_code)
    for keys in actions[:TICKS]:
        oracle.step_world_chain(keys, call_limit=CALL_LIMIT)

    union = reads | writes | execs
    classes = {}
    for page in union:
        kind = classify(page, oracle)
        classes[kind] = classes.get(kind, 0) + 1
    return {
        'ticks': len(actions),
        'read_pages': len(reads),
        'write_pages': len(writes),
        'exec_pages': len(execs),
        'union_pages': len(union),
        'classes': classes,
        'read_ranges': [hex(x) for x in sorted(reads)],
        'write_ranges': [hex(x) for x in sorted(writes)],
        'exec_ranges': [hex(x) for x in sorted(execs)],
        'read_bytes_instructions': read_bytes,
        'write_bytes_instructions': write_bytes,
    }


out = {
    'scope': f'original x86 candidate gameplay chain, {TICKS} ticks/scenario',
    'chain': [hex(x) for x in CapturedOracle.WORLD_CHAIN],
    'instruction_limit': CALL_LIMIT,
    'scenarios': {},
}
for name, actions in SCENARIOS.items():
    result = run(actions)
    out['scenarios'][name] = result
    print(name, result['union_pages'], result['classes'], flush=True)

OUTPUT.write_text(json.dumps(out, indent=2))
