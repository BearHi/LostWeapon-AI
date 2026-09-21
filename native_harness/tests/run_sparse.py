from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sparse_oracle import SparseCapturedOracle
sequences={
    'noop':[()]*12,
    'right':[('RIGHT',)]*12,
    'jump':[('UP',)]+[()]*11,
    'front_roll':[('RIGHT','DOWN')]*12,
    'back_roll':[('LEFT','DOWN')]*12,
    'jump_backroll':[('UP',)]+[()]*8+[('LEFT','DOWN')]*3,
    'backroll_chute':[('LEFT','DOWN')]*8+[('RIGHT','C')]+[()]*3,
}
out={'scope':'offline sparse mapping from closure footprint','sparse':None,'tests':{}}
for name,actions in sequences.items():
    try:
        o=SparseCapturedOracle(ROOT/'private_snapshots/hun1_full.zip')
        if out['sparse'] is None:out['sparse']=o.sparse_info()
        start=o.read_player_state();trace=[]
        for keys in actions:trace.append(o.step_one_tick(keys))
        out['tests'][name]={'status':'PASS','start':start,'end':trace[-1]}
        print(name,'PASS',trace[-1],flush=True)
    except Exception as e:
        out['tests'][name]={'status':'BLOCKED','error':str(e),'fault':getattr(o,'fault',None)}
        print(name,'BLOCKED',str(e),flush=True)
(ROOT/'evidence/sparse_tests.json').write_text(json.dumps(out,indent=2))
