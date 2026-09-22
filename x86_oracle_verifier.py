"""x86_oracle_verifier.py - Ground-Truth Oracle Verifier for LostWeapon MapSpec/LMF.

Ground-Truth Evidence Contracts:
- SUCCESS: Native Client flag trigger in OBJECT_BASE:
           flag_object.offset_0x8c == 1 (and 0xc0 == 1).
           NEVER relies on Euclidean bounding boxes or coordinate thresholds.
- DEATH: Native player respawn trigger:
         player_object.offset_0x7c == -1.
         At this tick, the engine marks death and resets player coordinates to spawn point.
- TIMEOUT: Reached max_ticks (or end of action sequence) without SUCCESS or DEATH.
- INVALID: Illegal keys, missing assets, or emulator execution faults.

Determinism Contract:
- Uses full snapshot dirty-page tracking + Unicorn CPU context restoration.
- 100% bit-exact parity across repeated trial executions.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Sequence

# Add native_harness to path
HARNESS_DIR = Path(__file__).resolve().parent / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

from api import NativeTrainingAPI
from headless import KEYS
from snapshot_selector import snapshot_for_map


def compute_memory_hash(oracle) -> str:
    """Compute SHA-256 over all mapped memory regions in Unicorn."""
    hasher = hashlib.sha256()
    for start, end, _ in sorted(oracle.u.mem_regions(), key=lambda r: r[0]):
        hasher.update(bytes(oracle.u.mem_read(start, end - start + 1)))
    return hasher.hexdigest()


class X86OracleVerifier:
    """Ground-Truth x86 execution verifier."""

    def __init__(self, snapshot: str | Path, lmf: str | Path, settle_ticks: int = 15):
        self.snapshot_path = Path(snapshot).resolve()
        self.lmf_path = Path(lmf).resolve()
        self.settle_ticks = settle_ticks

        if not self.snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot not found: {self.snapshot_path}")
        if not self.lmf_path.exists():
            raise FileNotFoundError(f"LMF file not found: {self.lmf_path}")

        # NativeTrainingAPI with compact_static=False to guarantee 1:1 LMF record-to-runtime object mapping
        self.api = NativeTrainingAPI(
            self.snapshot_path,
            self.lmf_path,
            track_dirty=True,
            compact_static=False
        )

        # Parse LMF records to locate goal flags (Tile ID 140)
        _w, _h, self.records = self.api.oracle.parse_lmf(self.lmf_path)
        self.flag_record_indices = [
            i for i, (tile_id, _x, _y) in enumerate(self.records) if tile_id == 140
        ]
        if not self.flag_record_indices:
            raise ValueError(f"LMF has no Tile 140 (goal flag): {self.lmf_path}")

        # Settle world initial physics (spawn drop / initial settling)
        for _ in range(self.settle_ticks):
            self.api.step(1, ())

        # Save baseline snapshot for fast, bit-exact resets
        self.baseline_state = self.api.save_state()
        self.initial_signature = compute_memory_hash(self.api.oracle)

    def reset(self) -> str:
        """Reset world to settled baseline and verify memory integrity."""
        self.api.restore_state(self.baseline_state)
        current_hash = compute_memory_hash(self.api.oracle)
        if current_hash != self.initial_signature:
            raise RuntimeError(
                f"Snapshot corruption detected: current hash {current_hash[:16]} "
                f"!= initial {self.initial_signature[:16]}"
            )
        return current_hash

    def check_flag_triggered(self) -> tuple[bool, int | None]:
        """Check if any Tile 140 object triggered the native collision flag (0x8c == 1)."""
        for r_idx in self.flag_record_indices:
            flag_addr = self.api.oracle.OBJECT_BASE + r_idx * self.api.oracle.OBJECT_STRIDE
            f_8c = self.api.oracle.get(flag_addr + 0x8C, "i")[0]
            f_c0 = self.api.oracle.get(flag_addr + 0xC0, "i")[0]
            if f_8c == 1 or f_c0 == 1:
                return True, r_idx
        return False, None

    def run_trial(
        self,
        action_sequence: Sequence[Sequence[str]],
        max_ticks: int = 1000
    ) -> dict[str, Any]:
        """Execute action sequence and observe ground-truth terminal events."""
        self.reset()

        terminal_type = "TIMEOUT"
        terminal_tick = len(action_sequence)
        evidence_source = f"tick_limit_reached (max_ticks={max_ticks}, seq_len={len(action_sequence)})"
        final_position = (0.0, 0.0)
        final_motion_state = 0.0
        final_st = {}

        # Validate action sequence upfront
        for t, keys in enumerate(action_sequence):
            unknown_keys = set(keys) - KEYS.keys()
            if unknown_keys:
                return {
                    "terminal_type": "INVALID",
                    "terminal_tick": t,
                    "evidence_source": f"unknown_keys_in_action: {unknown_keys}",
                    "final_position": (0.0, 0.0),
                    "final_motion_state": 0.0,
                    "initial_snapshot_signature": self.initial_signature,
                    "final_state_signature": hashlib.sha256(f"INVALID_{unknown_keys}".encode()).hexdigest(),
                }

        limit = min(max_ticks, len(action_sequence))
        for t in range(limit):
            action = tuple(action_sequence[t])
            try:
                st = self.api.step(1, action)
            except Exception as e:
                return {
                    "terminal_type": "INVALID",
                    "terminal_tick": t,
                    "evidence_source": f"emulator_fault: {e}",
                    "final_position": final_position,
                    "final_motion_state": final_motion_state,
                    "initial_snapshot_signature": self.initial_signature,
                    "final_state_signature": hashlib.sha256(f"FAULT_{e}".encode()).hexdigest(),
                }

            final_st = st
            final_position = (float(st["x"]), float(st["y"]))
            final_motion_state = float(st["motion58"])

            # 1. Ground-Truth Check: Player Death (0x7c == -1)
            if st.get("7c") == -1:
                terminal_type = "DEATH"
                terminal_tick = t
                evidence_source = "native_player:offset_0x7c==-1 (respawn_triggered)"
                break

            # 2. Ground-Truth Check: Flag Collision (flag.offset_0x8c == 1)
            flag_hit, flag_r_idx = self.check_flag_triggered()
            if flag_hit:
                terminal_type = "SUCCESS"
                terminal_tick = t
                evidence_source = f"native_object:flag[rec_{flag_r_idx}].offset_0x8c==1 (client_collision_triggered)"
                break

        # Final state signature: deterministic hash of key terminal metrics
        state_payload = (
            f"{terminal_type}:{terminal_tick}:{final_position[0]:.4f}:{final_position[1]:.4f}:"
            f"{final_motion_state:.4f}:{final_st.get('7c')}:{final_st.get('38')}:{final_st.get('74')}"
        )
        final_state_signature = hashlib.sha256(state_payload.encode()).hexdigest()

        return {
            "terminal_type": terminal_type,
            "terminal_tick": terminal_tick,
            "evidence_source": evidence_source,
            "final_position": final_position,
            "final_motion_state": final_motion_state,
            "initial_snapshot_signature": self.initial_signature,
            "final_state_signature": final_state_signature,
        }


def run_trial(
    snapshot: str | Path,
    lmf: str | Path,
    action_sequence: Sequence[Sequence[str]],
    max_ticks: int = 1000
) -> dict[str, Any]:
    """Convenience standalone runner."""
    verifier = X86OracleVerifier(snapshot, lmf)
    return verifier.run_trial(action_sequence, max_ticks=max_ticks)
