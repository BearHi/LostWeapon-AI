from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from captured_oracle import CapturedOracle
SNAPSHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'private_snapshots/hun1_full.zip'
OUTPUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'evidence/world_chain_tests.json'
CALL_LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 2000000
sequences={
    'noop':[()]*12,
    'right':[('RIGHT',)]*12,
    'jump':[('UP',)]+[()]*11,
    'front_roll':[('RIGHT','DOWN')]*12,
    'back_roll':[('LEFT','DOWN')]*12,
    'jump_backroll':[('UP',)]+[()]*8+[('LEFT','DOWN')]*3,
    'backroll_chute':[('LEFT','DOWN')]*8+[('RIGHT','C')]+[()]*3,
}
out={'scope':'candidate gameplay main-loop chain; render/network omitted','chain':[hex(x) for x in CapturedOracle.WORLD_CHAIN],'tests':{}}
for name,actions in sequences.items():
    o=CapturedOracle(SNAPSHOT)
    try:
        start=o.read_player_state();trace=[o.step_world_chain(keys,call_limit=CALL_LIMIT) for keys in actions]
        out['tests'][name]={'status':'PASS','start':start,'end':trace[-1]};print(name,'PASS',trace[-1],flush=True)
    except Exception as e:
        out['tests'][name]={'status':'BLOCKED','error':str(e),'fault':o.fault};print(name,'BLOCKED',str(e),flush=True)
OUTPUT.write_text(json.dumps(out,indent=2))
