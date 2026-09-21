# Local physics trainer verification — 2026-09-18

Entry point: `local_physics_train.py`; user launcher: `로컬물리_훈련시작.bat`.
Existing physics, masks, maps, snapshots and old checkpoints were not edited.

## Checked

- 9 focused contract tests passed (`tests/test_local_physics_train.py`). Covers clean-reset acceptance, native-clock snapshot isolation, local terrain/state discrimination, conditional chute deployment, no blanket lava/damage exclusion, complete existing action vocabulary, persistent experience, version mismatch refusal, bounded candidate count, stop/time checks.
- All 23 훈1~20 maps (including 6.5, 7.5, 8.5) loaded in the original x86 harness and passed a short non-initial branch restore/player-state replay check. Evidence: `evidence/local_physics_preflight/*.summary.json`.
- 훈1: an existing 56-decision route imported and replayed from reset to the configured goal region. 8 fresh candidate tests completed; a separate resume increased the total to 12 without replacing earlier experience. A fresh jump-roll candidate reached the goal region but did not beat the imported best.
- 훈6.5: 8 initial candidate tests completed (6 suspected returns to start, 2 horizon endings). No goal was found in this small check. Subsequent stop/lock tests also preserved their completed candidate records.
- Live coordinator stop marker test passed; candidate commits survived stopping. Concurrent launch was rejected. A Windows byte-lock read error found during this check was fixed and retested.
- Launchers normalized to CRLF. No long user training job was left running.

## Boundaries

This is local archive exploration, native branching, route improvement and contextual technique-priority learning. It does not train a neural network or control the normal Client. The 9x9 context is read at launch and every 8 decisions during trial execution; native state/masks are consulted every decision. Candidate simulation still has the complete native map, so this is not a strict partial-observation navigation benchmark.

Goal evidence is the existing coordinate-region predicate, not the normal Client flag event. Reset detection is a coordinate-discontinuity heuristic. The branch check compares exposed player state; it is not a proof that all native/internal state or every game mechanic has parity. Performance and generalization are not established by the small smoke runs. All real training writes go to `checkpoints/local_physics_v1`, separate from these evidence runs.
