"""Create/compare a tick-by-tick parity fixture.

The oracle fixture is generated offline. A normal-client trace can be supplied
later as JSON with the same fields; no debugger or live input injection is
needed by the comparator.
"""
from pathlib import Path
import sys,json,math,hashlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from captured_oracle import CapturedOracle

SEQUENCES={
    'noop':[()]*12,
    'right':[('RIGHT',)]*12,
    'jump':[('UP',)]+[()]*11,
    'front_roll':[('RIGHT','DOWN')]*12,
    'back_roll':[('LEFT','DOWN')]*12,
    'jump_backroll':[('UP',)]+[()]*8+[('LEFT','DOWN')]*3,
    'backroll_chute':[('LEFT','DOWN')]*8+[('RIGHT','C')]+[()]*3,
}

def canonical(s):
    return {'x':s['x'],'y':s['y'],'motion58':s['motion58'],'38':s['38'],'3c':s['3c'],'68':s['68'],'74':s['74'],'b0':s['b0'],'c0':s['c0'],'c4':s['c4'],'d0':s['d0'],'dc':s['dc']}

def digest(states):
    return hashlib.sha256(json.dumps([canonical(s) for s in states],sort_keys=True,separators=(',',':')).encode()).hexdigest()

def make():
    out={'format':'lostweapon-native-parity-v1','source':'captured hun1 offline oracle','sequences':{}}
    for name,actions in SEQUENCES.items():
        o=CapturedOracle(ROOT/'private_snapshots/hun1_full.zip')
        states=[o.read_player_state()]
        for keys in actions:states.append(o.step_one_tick(keys))
        out['sequences'][name]={'keys':[list(k) for k in actions],'states':[canonical(s) for s in states],'digest':digest(states)}
    path=ROOT/'evidence/oracle_parity_fixtures.json';path.write_text(json.dumps(out,indent=2));print(path)

def compare(path):
    expected=json.loads((ROOT/'evidence/oracle_parity_fixtures.json').read_text());actual=json.loads(Path(path).read_text());report={}
    for name,fixture in expected['sequences'].items():
        got=actual.get('sequences',{}).get(name,{}).get('states')
        if got is None:report[name]={'status':'MISSING'};continue
        diffs=[]
        for tick,(want,have) in enumerate(zip(fixture['states'],got)):
            for field in want:
                if isinstance(want[field],float):
                    if not math.isclose(want[field],float(have[field]),rel_tol=0,abs_tol=1e-9):diffs.append({'tick':tick,'field':field,'want':want[field],'have':have[field]})
                elif want[field]!=have[field]:diffs.append({'tick':tick,'field':field,'want':want[field],'have':have[field]})
        if len(got)!=len(fixture['states']):diffs.append({'length':{'want':len(fixture['states']),'have':len(got)}})
        report[name]={'status':'PASS' if not diffs else 'MISMATCH','diffs':diffs[:50]}
    print(json.dumps(report,indent=2));return report

if __name__=='__main__':
    if len(sys.argv)==1:make()
    else:compare(sys.argv[1])
