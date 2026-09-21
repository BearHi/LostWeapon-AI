from pathlib import Path
import sys,time,json,statistics
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sparse_oracle import SparseCapturedOracle
o=SparseCapturedOracle(ROOT/'private_snapshots/hun1_full.zip');n=120;vals=[]
for _ in range(3):
    t=time.perf_counter()
    for _ in range(n):o.step_one_tick(())
    vals.append(time.perf_counter()-t)
median=statistics.median(vals)
out={'scope':'sparse 112-page captured closure; initialization excluded','selected_pages':o.sparse_info()['selected_pages'],'selected_bytes':o.sparse_info()['selected_bytes'],'original_bytes':o.sparse_info()['original_bytes'],'trials_seconds':vals,'median_ticks_per_second':n/median,'nominal_60Hz_multiplier':n/median/60}
(ROOT/'evidence/benchmark_sparse.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
