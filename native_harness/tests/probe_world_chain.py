"""Probe original no-argument main-loop candidates offline on captured state."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from captured_oracle import CapturedOracle

CANDIDATES={
    'input':0x4228c0,
    'player_dispatch':0x436e30,
    'candidate_455f00':0x455f00,
    'candidate_453a50':0x453a50,
    'candidate_476000':0x476000,
    'candidate_461ac0':0x461ac0,
    'candidate_436620':0x436620,
    'candidate_415f10':0x415f10,
}
o=CapturedOracle(ROOT/'private_snapshots/hun1_full.zip');baseline=o.save_snapshot();out={'scope':'captured hun1; each candidate restored to identical baseline before call','candidates':{}}
for name,address in CANDIDATES.items():
    o.restore_snapshot(baseline)
    try:
        if name!='input':o.call(0x4228c0)
        before=o.read_player_state();result=o.call(address);after=o.read_player_state()
        out['candidates'][name]={'status':'PASS','address':hex(address),'eax':result,'before':before,'after':after}
        print(name,'PASS',after,flush=True)
    except Exception as e:
        out['candidates'][name]={'status':'BLOCKED','address':hex(address),'error':str(e),'fault':o.fault}
        print(name,'BLOCKED',str(e),flush=True)
(ROOT/'evidence/world_chain_probe.json').write_text(json.dumps(out,indent=2))
