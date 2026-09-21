# Native harness prototype

Current project handoff: [NEXT_SESSION_HANDOFF_2026-09-17.md](../NEXT_SESSION_HANDOFF_2026-09-17.md). Read it before using older training instructions below.

This directory runs original x86 instructions from the supplied LostWeapon
`Client.exe`. It is an experimental research harness, not a replacement game
client and not an online automation tool.

The captured snapshot under `private_snapshots` is local evidence and may
contain process data. Keep it private.

Typical offline checks:

```powershell
python native_harness/inspect_binary.py
python native_harness/tests/run_captured.py
python native_harness/tests/parity_fixture.py
python native_harness/benchmark/run_benchmark.py
python native_harness/benchmark/components.py
python native_harness/analysis/subset_analysis.py
python native_harness/tests/run_sparse.py
python native_harness/benchmark/sparse.py
python native_harness/analysis/world_footprint.py
python native_harness/tests/run_world_chain.py
python native_harness/tests/run_sparse_world.py
python native_harness/benchmark/world_chain.py
python native_harness/tests/probe_snapshot_chain.py
python native_harness/tests/adaptive_sparse_world.py
```

`tests/parity_fixture.py` creates the oracle-side tick fixture and can compare a
later normal-client trace with `python native_harness/tests/parity_fixture.py trace.json`.

`capture.py` accepts a PID only to read a deliberately selected running Client,
briefly suspends it, reads committed memory, and resumes it. It does not write
the executable or send game/network input.

For a running normal Client, the following are fully read-only and do not
change focus or input:

```powershell
python native_harness/identify_live_map.py <PID> --output native_harness/evidence/live_map_identity.json
python native_harness/sample_normal_noop.py <PID> --output native_harness/evidence/normal_noop.json
```

`identify_live_map.py` matches the loaded runtime object records to the supplied
`훈련용맵/*.LMF` files. `sample_normal_noop.py` is for stable-state checks; it
separates gameplay-core fields from animation-frame changes.
