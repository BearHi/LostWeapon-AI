"""Exercise the GUI physics worker across a large custom-map switch."""
from pathlib import Path
import multiprocessing as mp
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_playground import physics_worker, parse_lmf


def receive(connection, kind, timeout=30.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if connection.poll(0.1):
            event = connection.recv()
            if event["kind"] == "error":
                raise RuntimeError(event["error"])
            if event["kind"] == kind:
                return event
    raise TimeoutError(kind)


def load(connection, generation, path):
    width, height, records = parse_lmf(path)
    dynamic = [i for i, record in enumerate(records) if record[0] in (119, 124)]
    goals = [(x, y) for tile_id, x, y in records if tile_id == 140]
    connection.send(("load", generation, str(ROOT / "private_snapshots/hun1_full.zip"),
                     str(path), dynamic, goals))
    receive(connection, "loaded")
    return receive(connection, "state")


if __name__ == "__main__":
    mp.freeze_support()
    maps = Path(r"C:\Users\microsoft\Downloads\NewLostweapon\LostWeapon_v0.28.6_ControlPipeline_Verification\maps")
    parent, child = mp.Pipe()
    process = mp.Process(target=physics_worker, args=(child,), daemon=True)
    process.start()
    try:
        first = load(parent, 1, maps / "맵테스트1.LMF")
        second = load(parent, 2, maps / "맵테스트2.LMF")
        parent.send(("step", ("RIGHT",)))
        stepped = receive(parent, "state")
        assert first["generation"] == 1
        assert second["generation"] == stepped["generation"] == 2
        assert stepped["tick"] >= 1
        print("PASS maptest1 -> maptest2 worker switch and native step")
    finally:
        parent.send(("close",))
        process.join(5)
        if process.is_alive():
            process.terminate()
