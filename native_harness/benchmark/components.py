"""Break down offline native-oracle cost without touching the live Client."""
from pathlib import Path
import sys,time,json,statistics
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from captured_oracle import CapturedOracle

def trial(component,n=120,tracking=False):
    o=CapturedOracle(ROOT/'private_snapshots/hun1_full.zip')
    if tracking:o.begin_branching()
    def one():
        o.set_input(())
        ms,tick=o.get(o.CONTROL+0x800,'II')
        o.put(o.CONTROL+0x800,'II',ms+((tick+1)*1000//60-tick*1000//60),tick+1)
        o.call(0x4228c0);o.call(0x436e30)
    t=time.perf_counter()
    if component=='emulation':
        for _ in range(n):one()
    elif component=='step_with_read':
        for _ in range(n):o.step_one_tick(())
    elif component=='state_read':
        for _ in range(n):o.read_player_state()
    elif component=='restore':
        o.begin_branching()
        for _ in range(n):o.restore_branch()
    elif component=='step_tracking':
        o.begin_branching()
        for _ in range(n):o.step_one_tick(())
    return time.perf_counter()-t

components=[('emulation',False),('step_with_read',False),('state_read',False),('restore',False),('step_tracking',True)]
out={'scope':'captured hun1 offline oracle; n=120 operations/trial; Python Unicorn overhead included','trials':{}}
for component,tracking in components:
    vals=[trial(component,120,tracking) for _ in range(3)]
    median=statistics.median(vals)
    out['trials'][component]={'seconds':vals,'median_seconds':median,'ops_per_second':120/median}
    print(component,out['trials'][component],flush=True)
(ROOT/'evidence/benchmark_components.json').write_text(json.dumps(out,indent=2))
