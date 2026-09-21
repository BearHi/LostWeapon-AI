from pathlib import Path
import sys,time,json,statistics
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from captured_oracle import *
o=CapturedOracle(ROOT/'private_snapshots/hun1_full.zip');o.begin_branching()
times=[];restores=[]
for run in range(3):
    start=time.perf_counter()
    for episode in range(20):
        t=time.perf_counter();o.restore_branch();restores.append(time.perf_counter()-t)
        for tick in range(60):o.step_one_tick(['UP'] if tick==0 else [])
    times.append(time.perf_counter()-start)
result={'scope':'hun1 captured player input + physics dispatcher; includes Python state reads and dirty-page tracking; excludes initial snapshot loading','dispatch_steps_per_trial':1200,'trials_seconds':times,'median_steps_per_second':1200/statistics.median(times),'nominal_60Hz_multiplier':1200/statistics.median(times)/60,'median_branch_restore_ms':statistics.median(restores)*1000,'full_game_tick_parity':'not yet established'}
(ROOT/'evidence/benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
