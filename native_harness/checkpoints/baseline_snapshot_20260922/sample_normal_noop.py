"""Read-only normal Client NOOP sampler for a currently loaded fixture.

No window focus, key input, debugger, suspension, or memory writes are used.
The sampler is intended for stable states (for example 훈12 after the automatic
fall into water), where a short sequence of repeated observations can be
compared with the native-oracle post-entry closure.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from live_state import Reader


def sample(pid: int, duration: float, interval: float, output: Path | None):
    reader = Reader(pid)
    try:
        samples = []
        deadline = time.perf_counter() + duration
        while time.perf_counter() < deadline:
            samples.append({"perf_ns": time.perf_counter_ns(), "state": reader.state()})
            time.sleep(interval)
        if not samples:
            samples.append({"perf_ns": time.perf_counter_ns(), "state": reader.state()})
        fields = []
        core_fields = []
        for item in samples:
            s = item["state"]
            fields.append((tuple(s.get("pos", ())), s.get("motion58"), tuple(sorted(s.get("state", {}).items()))))
            game_state = s.get("state", {})
            core_fields.append((tuple(s.get("pos", ())), s.get("motion58"),
                                tuple((key, game_state.get(key)) for key in
                                      ("0x38", "0x68", "0x74", "0xb0", "0xc0", "0xc4", "0xd0", "0xdc"))))
        result = {
            "scope": "read-only normal Client NOOP stability sample",
            "pid": pid,
            "duration_seconds": duration,
            "interval_seconds": interval,
            "samples": samples,
            "all_signature_equal": len(set(fields)) == 1,
            "unique_signatures": len(set(fields)),
            "core_signature_equal": len(set(core_fields)) == 1,
            "unique_core_signatures": len(set(core_fields)),
            "start": samples[0]["state"],
            "end": samples[-1]["state"],
        }
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
        print(json.dumps({
            "samples": len(samples),
            "all_signature_equal": result["all_signature_equal"],
            "unique_signatures": result["unique_signatures"],
            "core_signature_equal": result["core_signature_equal"],
            "unique_core_signatures": result["unique_core_signatures"],
            "start": result["start"]["pos"],
            "end": result["end"]["pos"],
            "state38_start_end": [result["start"].get("state", {}).get("0x38"), result["end"].get("state", {}).get("0x38")],
            "c0_start_end": [result["start"].get("state", {}).get("0xc0"), result["end"].get("state", {}).get("0xc0")],
        }, ensure_ascii=False, indent=2))
        return result
    finally:
        reader.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int)
    parser.add_argument("--duration", type=float, default=1.0)
    parser.add_argument("--interval", type=float, default=0.02)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sample(args.pid, args.duration, args.interval, args.output)


if __name__ == "__main__":
    main()
