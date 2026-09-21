from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from api import NativeOracleAPI
o=NativeOracleAPI(ROOT/'private_snapshots/hun1_full.zip')
s=o.save_state();start=o.read_state();end=o.step(12,['RIGHT']);o.restore_state(s);again=o.step(12,['RIGHT'])
assert end==again
assert end['x']==start['x']+48
print({'status':'PASS','start':start,'end':end})
