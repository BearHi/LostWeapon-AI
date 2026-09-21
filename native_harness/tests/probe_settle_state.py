"""Inspect hidden player-state convergence after native LMF spawn placement."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from lmf_injector import NativeLmfOracle
from oracle import PLAYER


def main():
    snapshot, lmf = map(Path, sys.argv[1:3])
    captured = CapturedOracle(snapshot)
    built = NativeLmfOracle(snapshot)
    built.load_lmf(lmf)
    captured_player = captured.addr(PLAYER + captured.meta["state"]["slot"] * 0xF8)
    expected = bytes(captured.u.mem_read(captured_player, 0xF8))
    rows = []
    for tick in range(46):
        if tick:
            built.step_world_chain(())
        if tick >= 16:
            actual = bytes(built.u.mem_read(built.player_address, 0xF8))
            diffs = [offset for offset, (a, b) in enumerate(zip(expected, actual)) if a != b]
            rows.append({"tick": tick, "state": built.read_player_state(), "different_bytes": len(diffs), "offsets": diffs})
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
