"""x86_oracle_verifier.py - Ground-Truth Oracle Verifier for LostWeapon MapSpec/LMF.

Phase 3A.1 - Generic Oracle Audit:
1. Dynamic Flag Resolution:
   - Identifies all Tile ID 140 objects dynamically from parsed LMF records.
   - Zero hardcoding of record indices (e.g. rec_31).
   - Checks native object memory in OBJECT_BASE for flag_object.offset_0x8c == 1.
2. Verified Terminal Semantics:
   - SUCCESS: Native flag collision trigger (offset_0x8c == 1). Negative controls proven.
   - DEATH: Native death respawn sentinel (player.offset_0x7c == -1).
            Non-lethal damage (7c > 0, state38 == 5) is strictly excluded.
   - TIMEOUT: Exceeded max_ticks without terminal event. Neutral input () is applied
              after action sequence exhaustion to permit delayed coasting/landing.
   - INVALID: Unregistered input keys or emulator execution faults.
3. Simultaneous Event Handling:
   - If DEATH (0x7c == -1) and SUCCESS (0x8c == 1) occur on the same tick, both raw
     signals are logged in evidence_source, resolved to DEATH (engine respawn overrides).
4. Full Snapshot Signature:
   - RAM hash (SHA-256 of all mapped regions) + CPU context (x86 registers) + tick counter.
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
from unicorn.x86_const import (
    UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
    UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP,
    UC_X86_REG_EIP, UC_X86_REG_EFLAGS
)


def compute_full_snapshot_signature(oracle) -> str:
    """Compute comprehensive SHA-256 over all mapped RAM, CPU registers, and tick counter."""
    hasher = hashlib.sha256()

    # 1. All mapped RAM regions in ascending order
    for start, end, _ in sorted(oracle.u.mem_regions(), key=lambda r: r[0]):
        hasher.update(bytes(oracle.u.mem_read(start, end - start + 1)))

    # 2. Key 32-bit x86 registers
    regs = [
        oracle.u.reg_read(reg_id)
        for reg_id in (
            UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
            UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP,
            UC_X86_REG_EIP, UC_X86_REG_EFLAGS
        )
    ]
    hasher.update(struct.pack("<10I", *regs))

    # 3. Emulator tick and clock at CONTROL + 0x800
    ms, tick = oracle.get(oracle.CONTROL + 0x800, "II")
    hasher.update(struct.pack("<II", ms, tick))

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

        # Parse LMF records to locate goal flags (Tile ID 140) dynamically
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
        self.initial_signature = compute_full_snapshot_signature(self.api.oracle)

    def reset(self) -> str:
        """Reset world to settled baseline and verify full state integrity."""
        self.api.restore_state(self.baseline_state)
        current_sig = compute_full_snapshot_signature(self.api.oracle)
        if current_sig != self.initial_signature:
            raise RuntimeError(
                f"Snapshot corruption detected: current signature {current_sig[:16]} "
                f"!= initial {self.initial_signature[:16]}"
            )
        return current_sig

    def check_flag_triggered(self) -> tuple[bool, int | None]:
        """Check if any Tile 140 object triggered the native collision flag (0x8c == 1)."""
        for r_idx in self.flag_record_indices:
            flag_addr = self.api.oracle.OBJECT_BASE + r_idx * self.api.oracle.OBJECT_STRIDE
            f_8c = self.api.oracle.get(flag_addr + 0x8C, "i")[0]
            if f_8c == 1:
                return True, r_idx
        return False, None

    def run_trial(
        self,
        action_sequence: Sequence[Sequence[str]],
        max_ticks: int = 1000
    ) -> dict[str, Any]:
        """Execute action sequence with neutral coasting up to max_ticks."""
        self.reset()

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

        terminal_type = "TIMEOUT"
        terminal_tick = max_ticks
        evidence_source = f"tick_limit_reached (max_ticks={max_ticks}, action_len={len(action_sequence)})"
        final_position = (0.0, 0.0)
        final_motion_state = 0.0
        final_st = {}
        state_trace: list[dict[str, Any]] = []

        seq_len = len(action_sequence)
        for t in range(max_ticks):
            # Apply scheduled action if available; otherwise apply neutral input () for coasting
            action = tuple(action_sequence[t]) if t < seq_len else ()

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
                    "state_trace": state_trace,
                }

            final_st = st
            final_position = (float(st["x"]), float(st["y"]))
            final_motion_state = float(st["motion58"])
            state_trace.append({
                "tick": t,
                "x": final_position[0],
                "y": final_position[1],
                "motion58": final_motion_state,
                "38": st.get("38"),
                "c0": st.get("c0", 0),
                "dc": st.get("dc", 0),
                "dash90": st.get("dash90", 0.0),
                "action": action,
            })

            # Check both raw events on current tick
            death_hit = (st.get("7c") == -1)
            flag_hit, flag_r_idx = self.check_flag_triggered()

            # Handle simultaneous events explicitly
            if death_hit and flag_hit:
                terminal_type = "DEATH"
                terminal_tick = t
                evidence_source = (
                    f"simultaneous_event: death(0x7c==-1) and flag_contact[rec_{flag_r_idx}](0x8c==1) "
                    f"on tick {t}; engine death respawn overrides clear"
                )
                break

            if death_hit:
                terminal_type = "DEATH"
                terminal_tick = t
                coasting_note = f" (coasting tick +{t - seq_len})" if t >= seq_len else ""
                evidence_source = f"native_player:offset_0x7c==-1 (respawn_triggered){coasting_note}"
                break

            if flag_hit:
                terminal_type = "SUCCESS"
                terminal_tick = t
                coasting_note = f" (coasting tick +{t - seq_len})" if t >= seq_len else ""
                evidence_source = (
                    f"native_object:flag[rec_{flag_r_idx}].offset_0x8c==1 "
                    f"(client_collision_triggered){coasting_note}"
                )
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
            "state_trace": state_trace,
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
