"""Trace original x86 writes to raw124 timer and collision cell."""
from pathlib import Path
import json
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from captured_oracle import CapturedOracle
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.x86_const import UC_X86_REG_EIP

OBJECT_BASE = 0x27A5998
OBJECT_STRIDE = 0xF8


def main():
    snapshot, output = map(Path, sys.argv[1:3])
    oracle = CapturedOracle(snapshot)
    object_c8 = oracle.addr(OBJECT_BASE + 29 * OBJECT_STRIDE + 0xC8)
    width = oracle.get(0x8952DB0, "i")[0]
    grid1 = oracle.get(0x8952DEC, "I")[0]
    cell = grid1 + 2 * (14 * width + 6)
    events = []
    tick = 0

    def on_write(u, access, address, size, value, data):
        if address <= object_c8 < address + size or address <= cell < address + size:
            eip = u.reg_read(UC_X86_REG_EIP)
            original_eip = eip - oracle.delta if oracle.base <= eip < oracle.base + oracle.size else eip
            events.append({"tick": tick, "pc": hex(original_eip), "address": "object_c8" if address <= object_c8 < address + size else "collision_cell",
                           "size": size, "value": value})

    oracle.u.hook_add(UC_HOOK_MEM_WRITE, on_write)
    for current in range(1, 82):
        tick = current
        oracle.step_world_chain(())
    result = {"scope": "original x86 write trace for raw124 timer and collision cell",
              "snapshot": str(snapshot), "ticks": 81, "events": events,
              "writer_pcs": sorted(set(event["pc"] for event in events))}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "events": len(events),
                      "writer_pcs": result["writer_pcs"],
                      "collision_writes": [event for event in events if event["address"] == "collision_cell"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
