"""Spatial map optimization must retain Client-created transient objects."""
from pathlib import Path
import struct
import sys

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from api import NativeTrainingAPI

api = NativeTrainingAPI(HARNESS / "private_snapshots" / "hun1_full.zip",
                        Path(r"C:\Users\microsoft\Downloads\NewLostweapon\Map\훈1.LMF"),
                        track_dirty=False)
oracle = api.oracle
assert oracle._spatial_runtime_enabled

count = oracle.get(0x25CA048, "i")[0]
sentinel = bytearray(oracle.OBJECT_STRIDE)
struct.pack_into("<i", sentinel, 0, 0x12345678)
struct.pack_into("<4i", sentinel, 0x28, 101, 202, 303, 404)
base = oracle.addr(oracle.OBJECT_BASE)
oracle.u.mem_write(base + count * oracle.OBJECT_STRIDE, bytes(sentinel))
oracle.put(0x25CA048, "i", count + 1)

oracle.refresh_spatial_runtime(sync_current=True)
extras = oracle.read_unmapped_runtime_objects()
assert len(extras) == 1, extras
assert extras[0]["type"] == 0x12345678, extras
assert extras[0]["bounds"] == [101, 202, 303, 404], extras

# A second rebuild used to be the point at which such an object vanished.
oracle.refresh_spatial_runtime(sync_current=True)
extras = oracle.read_unmapped_runtime_objects()
assert len(extras) == 1 and extras[0]["type"] == 0x12345678, extras
print("PASS", extras[0])
