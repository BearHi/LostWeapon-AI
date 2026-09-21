"""Print compact progress from the local combat self-play log."""
from pathlib import Path
import json

path = Path(__file__).resolve().parent / "checkpoints" / "combat_training.jsonl"
if not path.exists():
    print("No completed combat-training episodes yet.")
    raise SystemExit(0)
rows = []
for line in path.read_text(encoding="utf-8").splitlines():
    try: rows.append(json.loads(line))
    except json.JSONDecodeError: pass
if not rows:
    print("No completed combat-training episodes yet.")
    raise SystemExit(0)
last = rows[-1]; recent = rows[-100:]
print(f"Completed episodes : {last['episode']}")
print(f"Latest steps       : {last['steps']}")
print(f"Latest HP          : {last['hp']}")
print(f"Latest rewards     : {last['reward0']}, {last['reward1']}")
print(f"Recent avg reward  : {sum(r['reward0'] + r['reward1'] for r in recent)/(2*len(recent)):.3f}")
print(f"Exploration epsilon: {last['epsilon']}")
