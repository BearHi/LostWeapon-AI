"""bypass_verifier.py - Minimal 1:1 Intended Reference vs Candidate Bypass Verifier.

Phase 3B - Minimal Unit:
Evaluates exactly ONE intended reference sequence against ONE candidate bypass sequence
from the exact same fresh, deterministic x86 snapshot baseline.

Evaluation Semantics:
1. Reference Sequence:
   - SUCCESS -> Reference valid; proceed to evaluate candidate bypass.
   - DEATH or TIMEOUT -> 'REFERENCE_FAILED' (intended clear path is broken).
   - INVALID -> 'VERIFIER_ERROR' (input encoding or emulator fault).

2. Candidate Bypass Sequence:
   - SUCCESS -> 'KNOWN_BYPASS_FOUND' (candidate successfully reached flag).
   - DEATH or TIMEOUT -> 'KNOWN_BYPASS_NOT_FOUND' (this specific candidate did not reach flag).
   - INVALID -> 'INCONCLUSIVE' (emulator/input fault on bypass candidate must NOT be treated as bypass failure).

Important Principles:
- A bypass candidate does NOT need to die to fail; TIMEOUT / stopping short is also a valid failure.
- 'KNOWN_BYPASS_NOT_FOUND' applies strictly to the tested candidate; it NEVER implies the map as a whole has no bypass or is approved.
"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Optional, Sequence

# Add workspace and native_harness to path
ROOT = Path(__file__).resolve().parent
HARNESS_DIR = ROOT / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from x86_oracle_verifier import X86OracleVerifier


class SingleBypassVerifier:
    """1:1 Reference vs Candidate Bypass Verifier."""

    def __init__(self, snapshot: str | Path, lmf: str | Path, settle_ticks: int = 15):
        self.verifier = X86OracleVerifier(snapshot, lmf, settle_ticks=settle_ticks)

    def evaluate(
        self,
        reference_actions: Sequence[Sequence[str]],
        bypass_candidate_actions: Sequence[Sequence[str]],
        max_ticks: int = 1000
    ) -> dict[str, Any]:
        """Evaluate reference and candidate bypass sequences from identical fresh baselines."""
        initial_sig = self.verifier.initial_signature

        # 1. Evaluate Intended Reference Sequence
        ref_trial = self.verifier.run_trial(reference_actions, max_ticks=max_ticks)
        ref_summary = {
            "terminal_type": ref_trial["terminal_type"],
            "terminal_tick": ref_trial["terminal_tick"],
            "evidence_source": ref_trial["evidence_source"],
            "final_position": ref_trial["final_position"],
            "final_motion_state": ref_trial["final_motion_state"],
            "initial_snapshot_signature": ref_trial["initial_snapshot_signature"],
        }

        # Validate Reference outcome
        if ref_trial["terminal_type"] == "INVALID":
            return {
                "verdict": "VERIFIER_ERROR",
                "initial_snapshot_signature": initial_sig,
                "reference_result": ref_summary,
                "bypass_result": None,
                "detail": f"Reference sequence invalid: {ref_trial['evidence_source']}"
            }

        if ref_trial["terminal_type"] in ("DEATH", "TIMEOUT"):
            return {
                "verdict": "REFERENCE_FAILED",
                "initial_snapshot_signature": initial_sig,
                "reference_result": ref_summary,
                "bypass_result": None,
                "detail": (
                    f"Intended reference path failed with {ref_trial['terminal_type']} "
                    f"at tick {ref_trial['terminal_tick']} ({ref_trial['evidence_source']})"
                )
            }

        assert ref_trial["terminal_type"] == "SUCCESS", f"Unexpected terminal_type: {ref_trial['terminal_type']}"

        # 2. Evaluate Candidate Bypass Sequence from identical fresh baseline
        bypass_trial = self.verifier.run_trial(bypass_candidate_actions, max_ticks=max_ticks)
        bypass_summary = {
            "terminal_type": bypass_trial["terminal_type"],
            "terminal_tick": bypass_trial["terminal_tick"],
            "evidence_source": bypass_trial["evidence_source"],
            "final_position": bypass_trial["final_position"],
            "final_motion_state": bypass_trial["final_motion_state"],
            "initial_snapshot_signature": bypass_trial["initial_snapshot_signature"],
        }

        # Assert bit-exact baseline state equivalence between reference and candidate trials
        assert ref_trial["initial_snapshot_signature"] == bypass_trial["initial_snapshot_signature"], (
            f"Baseline snapshot drift detected between trials: "
            f"ref={ref_trial['initial_snapshot_signature'][:16]} != bypass={bypass_trial['initial_snapshot_signature'][:16]}"
        )

        if bypass_trial["terminal_type"] == "INVALID":
            verdict = "INCONCLUSIVE"
            detail = f"Bypass candidate execution invalid/faulted: {bypass_trial['evidence_source']}"
        elif bypass_trial["terminal_type"] == "SUCCESS":
            verdict = "KNOWN_BYPASS_FOUND"
            detail = (
                f"Candidate bypass reached flag at tick {bypass_trial['terminal_tick']} "
                f"({bypass_trial['evidence_source']})"
            )
        elif bypass_trial["terminal_type"] in ("DEATH", "TIMEOUT"):
            verdict = "KNOWN_BYPASS_NOT_FOUND"
            detail = (
                f"Candidate bypass terminated with {bypass_trial['terminal_type']} "
                f"at tick {bypass_trial['terminal_tick']} ({bypass_trial['evidence_source']})"
            )
        else:
            verdict = "INCONCLUSIVE"
            detail = f"Unknown bypass terminal type: {bypass_trial['terminal_type']}"

        return {
            "verdict": verdict,
            "initial_snapshot_signature": initial_sig,
            "reference_result": ref_summary,
            "bypass_result": bypass_summary,
            "detail": detail
        }


def evaluate_single_bypass(
    snapshot: str | Path,
    lmf: str | Path,
    reference_actions: Sequence[Sequence[str]],
    bypass_candidate_actions: Sequence[Sequence[str]],
    max_ticks: int = 1000
) -> dict[str, Any]:
    """Convenience standalone function for 1:1 evaluation."""
    evaluator = SingleBypassVerifier(snapshot, lmf)
    return evaluator.evaluate(reference_actions, bypass_candidate_actions, max_ticks=max_ticks)
