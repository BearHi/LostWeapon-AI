"""candidate_suite_verifier.py - Phase 3D Multi-Candidate Suite Verifier.

Orchestrates evaluation of a candidate bypass suite against a reference sequence
on native x86 game state with strict verdict semantics and determinism guarantees:

Verdict Hierarchy:
  - Reference INVALID       -> VERIFIER_ERROR (candidate suite skipped)
  - Reference DEATH/TIMEOUT -> REFERENCE_FAILED (candidate suite skipped)
  - Reference SUCCESS       -> evaluate candidate suite:
      - ANY candidate SUCCESS -> KNOWN_BYPASS_FOUND (early termination with winning candidate record)
      - All candidates DEATH/TIMEOUT cleanly -> NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE
      - No SUCCESS but >=1 candidate INVALID -> SUITE_INCONCLUSIVE (prevents false security)

CRITICAL SAFETY INVARIANT:
  NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE does NOT mean the map is bypass-proof or verified safe.
  It strictly means none of the specific candidate parameter schedules in the tested suite succeeded.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any

# Ensure native harness path is available
HARNESS_DIR = Path(__file__).resolve().parent / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))

from x86_oracle_verifier import X86OracleVerifier


class CandidateSuiteVerifier:
    def __init__(self, snapshot_path: str | Path, lmf_path: str | Path):
        self.snapshot_path = Path(snapshot_path)
        self.lmf_path = Path(lmf_path)
        self.verifier = X86OracleVerifier(self.snapshot_path, self.lmf_path)
        self.baseline_signature = self.verifier.initial_signature

    @staticmethod
    def compute_action_hash(actions: list[tuple[str, ...]]) -> str:
        """Compute deterministic SHA-256 hash of an action sequence."""
        canonical = ",".join("+".join(sorted(tick)) for tick in actions)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def evaluate_suite(
        self,
        reference_actions: list[tuple[str, ...]],
        candidate_manifest: list[dict[str, Any]],
        expected_candidate_count: int | None = None,
        max_ticks: int = 200,
    ) -> dict[str, Any]:
        """Evaluate reference sequence and candidate manifest against native x86 oracle.
        
        Args:
            reference_actions: The intended reference solution schedule.
            candidate_manifest: List of candidate dictionaries. Each must contain:
                - 'candidate_name': str
                - 'family': str
                - 'parameters': dict
                - 'action_sequence': list[tuple[str, ...]]
            expected_candidate_count: Expected length of candidate_manifest for validation.
            max_ticks: Maximum execution ticks per trial.
            
        Returns:
            Dictionary with verdict, reference_result, winning_candidate, evaluated_candidates, etc.
        """
        if expected_candidate_count is not None:
            if len(candidate_manifest) != expected_candidate_count:
                raise AssertionError(
                    f"Candidate count mismatch: expected {expected_candidate_count}, "
                    f"got {len(candidate_manifest)}"
                )

        # 1. Evaluate Reference Sequence
        ref_trial = self.verifier.run_trial(reference_actions, max_ticks=max_ticks)
        ref_sig = ref_trial["initial_snapshot_signature"]
        if ref_sig != self.baseline_signature:
            raise AssertionError(
                f"Reference snapshot baseline drift: {ref_sig} != {self.baseline_signature}"
            )

        if ref_trial["terminal_type"] == "INVALID":
            return {
                "verdict": "VERIFIER_ERROR",
                "reference_result": ref_trial,
                "winning_candidate": None,
                "evaluated_candidates": [],
                "total_candidates_in_manifest": len(candidate_manifest),
                "total_candidates_evaluated": 0,
                "baseline_snapshot_signature": self.baseline_signature,
            }

        if ref_trial["terminal_type"] in ("DEATH", "TIMEOUT"):
            return {
                "verdict": "REFERENCE_FAILED",
                "reference_result": ref_trial,
                "winning_candidate": None,
                "evaluated_candidates": [],
                "total_candidates_in_manifest": len(candidate_manifest),
                "total_candidates_evaluated": 0,
                "baseline_snapshot_signature": self.baseline_signature,
            }

        # 2. Reference succeeded; evaluate candidate suite
        evaluated_candidates: list[dict[str, Any]] = []
        winning_candidate: dict[str, Any] | None = None
        has_invalid = False

        for cand in candidate_manifest:
            c_name = cand["candidate_name"]
            c_family = cand["family"]
            c_params = cand.get("parameters", {})
            c_actions = cand["action_sequence"]
            c_hash = self.compute_action_hash(c_actions)

            trial = self.verifier.run_trial(c_actions, max_ticks=max_ticks)
            c_sig = trial["initial_snapshot_signature"]
            if c_sig != self.baseline_signature:
                raise AssertionError(
                    f"Candidate '{c_name}' snapshot baseline drift: {c_sig} != {self.baseline_signature}"
                )

            # Family Semantic Contract Validation
            validator_fn = cand.get("semantic_validator")
            if validator_fn is not None:
                is_valid, sem_evidence = validator_fn(cand, trial.get("state_trace", []), trial)
                if not is_valid:
                    trial["terminal_type"] = "INVALID_CANDIDATE_SEMANTICS"
                    trial["evidence_source"] = f"semantic_violation: {sem_evidence}"
                cand_record_sem = sem_evidence
            else:
                cand_record_sem = "unvalidated"

            cand_record: dict[str, Any] = {
                "candidate_name": c_name,
                "family": c_family,
                "parameters": dict(c_params),
                "action_sequence_hash": c_hash,
                "terminal_type": trial["terminal_type"],
                "terminal_tick": trial["terminal_tick"],
                "evidence_source": trial["evidence_source"],
                "mechanic_activation_evidence": cand_record_sem,
                "final_position": trial["final_position"],
                "initial_snapshot_signature": c_sig,
            }
            evaluated_candidates.append(cand_record)

            if trial["terminal_type"] in ("INVALID", "INVALID_CANDIDATE_SEMANTICS"):
                has_invalid = True

            elif trial["terminal_type"] == "SUCCESS":
                # Early termination on first successful bypass
                winning_candidate = cand_record
                return {
                    "verdict": "KNOWN_BYPASS_FOUND",
                    "reference_result": ref_trial,
                    "winning_candidate": winning_candidate,
                    "evaluated_candidates": evaluated_candidates,
                    "total_candidates_in_manifest": len(candidate_manifest),
                    "total_candidates_evaluated": len(evaluated_candidates),
                    "baseline_snapshot_signature": self.baseline_signature,
                }

        # 3. No candidate succeeded in the tested suite
        if has_invalid:
            verdict = "SUITE_INCONCLUSIVE"
        else:
            verdict = "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE"

        return {
            "verdict": verdict,
            "reference_result": ref_trial,
            "winning_candidate": None,
            "evaluated_candidates": evaluated_candidates,
            "total_candidates_in_manifest": len(candidate_manifest),
            "total_candidates_evaluated": len(evaluated_candidates),
            "baseline_snapshot_signature": self.baseline_signature,
        }
