"""Offline read/write-page footprint analysis for the captured native oracle.

This records pages touched by original x86 instructions during the selected
gameplay closure. It is a candidate set, not proof that untouched pages can be
deleted: allocator, TLS, imported-library, and reset paths still need testing.
"""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from captured_oracle import CapturedOracle
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE

SCENARIOS={
    'noop':[()]*20,
    'right':[('RIGHT',)]*20,
    'jump':[('UP',)]+[()]*19,
    'front_roll':[('RIGHT','DOWN')]*20,
    'back_roll':[('LEFT','DOWN')]*20,
    'jump_backroll':[('UP',)]+[()]*8+[('LEFT','DOWN')]*11,
    'backroll_chute':[('LEFT','DOWN')]*12+[('RIGHT','C')]+[()]*7,
}

def classify(page,oracle):
    if oracle.base<=page<oracle.base+oracle.size:return 'client-image'
    if oracle.CONTROL<=page<oracle.CONTROL+0x10000:return 'harness-control'
    if oracle.STACK<=page<oracle.STACK+0x100000:return 'harness-stack'
    for start,end,perms in oracle.u.mem_regions():
        if start<=page<=end:return 'mapped-private'
    return 'unmapped'

def run(name,actions):
    o=CapturedOracle(ROOT/'private_snapshots/hun1_full.zip')
    reads=set();writes=set();exec_pages=set();read_bytes=0;write_bytes=0
    def on_read(u,access,address,size,value,data):
        nonlocal read_bytes
        reads.add(address&~4095);read_bytes+=size
    def on_write(u,access,address,size,value,data):
        nonlocal write_bytes
        writes.add(address&~4095);write_bytes+=size
    def on_code(u,address,size,data):exec_pages.add(address&~4095)
    o.u.hook_add(UC_HOOK_MEM_READ,on_read)
    o.u.hook_add(UC_HOOK_MEM_WRITE,on_write)
    o.u.hook_add(UC_HOOK_CODE,on_code)
    for keys in actions:o.step_one_tick(keys)
    all_pages=reads|writes
    counts={}
    for p in all_pages:
        c=classify(p,o);counts[c]=counts.get(c,0)+1
    return {'ticks':len(actions),'read_pages':len(reads),'write_pages':len(writes),'exec_pages':len(exec_pages),'union_pages':len(all_pages),'read_bytes_instructions':read_bytes,'write_bytes_instructions':write_bytes,'classes':counts,'read_ranges':[hex(x) for x in sorted(reads)],'write_ranges':[hex(x) for x in sorted(writes)],'exec_ranges':[hex(x) for x in sorted(exec_pages)]}

out={'scope':'original x86 instructions in captured hun1 gameplay closure; 20 ticks per scenario','scenarios':{}}
for name,actions in SCENARIOS.items():
    out['scenarios'][name]=run(name,actions)
    x=out['scenarios'][name];print(name,'union',x['union_pages'],'read',x['read_pages'],'write',x['write_pages'],x['classes'],flush=True)
(ROOT/'evidence/subset_analysis.json').write_text(json.dumps(out,indent=2))
