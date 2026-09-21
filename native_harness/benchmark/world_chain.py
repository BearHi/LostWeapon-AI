"""Benchmark the original x86 candidate gameplay chain offline."""
from pathlib import Path
import sys, time, json, statistics

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from sparse_oracle import SparseCapturedOracle
SNAPSHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'private_snapshots/hun1_full.zip'
FOOTPRINT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'evidence/world_subset_analysis.json'
OUTPUT = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / 'evidence/benchmark_world_chain.json'
CALL_LIMIT = int(sys.argv[4]) if len(sys.argv) > 4 else 2000000
N_TICKS = int(sys.argv[5]) if len(sys.argv) > 5 else 60


def trial(cls, footprint=None, n=N_TICKS):
    oracle = cls(SNAPSHOT, footprint) if footprint else cls(SNAPSHOT)
    started = time.perf_counter()
    for _ in range(n):
        oracle.step_world_chain((), call_limit=CALL_LIMIT)
    return time.perf_counter() - started, oracle.sparse_info() if footprint else None


out = {
    'scope': 'offline original x86 world-chain benchmark; initialization excluded',
    'n_ticks_per_trial': N_TICKS,
    'call_limit': CALL_LIMIT,
    'full': {},
    'sparse_world': {},
}
for label, cls, footprint in [
    ('full', CapturedOracle, None),
    ('sparse_world', SparseCapturedOracle, FOOTPRINT),
]:
    vals = []
    info = None
    for _ in range(3):
        elapsed, info = trial(cls, footprint)
        vals.append(elapsed)
    median = statistics.median(vals)
    item = {
        'trials_seconds': vals,
        'median_ticks_per_second': N_TICKS / median,
        'nominal_60Hz_multiplier': N_TICKS / median / 60,
    }
    if info:
        item.update(info)
    out[label] = item
    print(label, item, flush=True)

OUTPUT.write_text(json.dumps(out, indent=2))
