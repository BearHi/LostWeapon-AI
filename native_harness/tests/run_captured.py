from pathlib import Path
import sys,time,json,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from captured_oracle import *
o=CapturedOracle(ROOT/'private_snapshots/hun1_full.zip')
initial=o.read_player_state();o.begin_branching()
scenarios={
 'noop':[()]*60,
 'right12':[('RIGHT',)]*12,
 'left12':[('LEFT',)]*12,
 'jump':[('UP',)]+[()]*80,
 'front_roll':[('RIGHT','DOWN')]*40+[()]*20,
 'back_roll':[('LEFT','DOWN')]*40+[()]*20,
 'jump_backroll':[('UP',)]+[()]*8+[('LEFT','DOWN')]*20+[()]*30,
 'backroll_chute':[('LEFT','DOWN')]*28+[('RIGHT','C')]*12+[()]*20,
 'up_down':[('UP','DOWN')]*30,
 'left_right':[('LEFT','RIGHT')]*30,
 'attack':[('Z',)]*30,
}
results={'scope':'Captured hun1 input 4228c0 + dispatcher 436e30; normal-client parity not yet verified','initial':initial,'tests':{}}
def run(actions):
    o.restore_branch();trace=[]
    for action in actions:trace.append(o.step_one_tick(action))
    h=hashlib.sha256()
    for page in sorted(o.dirty):h.update(struct.pack('<I',page));h.update(o.u.mem_read(page,4096))
    return trace,h.hexdigest(),len(o.dirty)
for name,actions in scenarios.items():
    try:
        a,ha,pages=run(actions);b,hb,_=run(actions)
        assert a==b and ha==hb,'Replay differs'
        if name=='right12':assert a[-1]['x']==initial['x']+48 and a[-1]['y']==initial['y']
        results['tests'][name]={'status':'PASS','repeat_equal':True,'all_written_pages_hash':ha,'written_pages':pages,'trace':a}
        print(name,'PASS',a[-1],flush=True)
    except Exception as e:
        results['tests'][name]={'status':'BLOCKED','error':str(e),'fault':o.fault}
        print(name,'BLOCKED',str(e),flush=True)
out=ROOT/'evidence/captured_tests.json';out.write_text(json.dumps(results,indent=2))
print('saved',out)
