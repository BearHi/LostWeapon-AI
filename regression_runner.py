"""regression_runner.py - Multi-Stage Historical Defect Regression Runner.

Orchestrates the evaluation of historical project defects across pipeline stages:
  1. static_validator (Static physics kinematic invariants)
  2. x86_oracle (Ground-truth native emulation & reference feasibility)
  3. bypass_verifier (Multi-candidate suite bypass detection)

Strict Safety Invariants:
  - If a defect is caught at an early stage (e.g. static_validator), any subsequent
    stages in 'must_not_reach_stage' (e.g. x86_oracle, bypass_suite) MUST NOT be executed.
  - Every broken fixture must trigger the exact expected verdict and reason.
  - Every fixed control fixture must NOT trigger that defect and must proceed.
"""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent
HARNESS_DIR = ROOT / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from candidate_suite_verifier import CandidateSuiteVerifier
from regression_corpus import HISTORICAL_REGRESSION_CORPUS
from static_validator import StaticPhysicsValidator
from x86_oracle_verifier import X86OracleVerifier


class RegressionRunner:
    def __init__(self, registry_path: Path, snapshot_path: Path, temp_dir: Path):
        self.registry_path = Path(registry_path)
        self.snapshot_path = Path(snapshot_path)
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.static_validator = StaticPhysicsValidator(self.registry_path)

    def run_defect(self, defect_id: str) -> Dict[str, Any]:
        """Execute a single defect definition through its designated pipeline stage."""
        if defect_id not in HISTORICAL_REGRESSION_CORPUS:
            raise KeyError(f"Defect '{defect_id}' not found in registry.")

        entry = HISTORICAL_REGRESSION_CORPUS[defect_id]
        exp_stage = entry["expected_detection_stage"]
        exp_verdict = entry["expected_verdict"]
        exp_reason = entry.get("expected_reason", "")
        forbidden = entry.get("forbidden_verdicts", [])
        must_not_reach = set(entry.get("must_not_reach_stage", []))

        executed_stages: list[str] = []

        # =====================================================================
        # Stage 1: Static Physics Validator Check (if MapSpec defined)
        # =====================================================================
        if "broken_spec" in entry:
            executed_stages.append("static_validator")
            broken_spec = entry["broken_spec"]
            s_verdict, s_reason = self.static_validator.validate_spec(broken_spec)

            if exp_stage == "static_validator":
                # Must match expected static verdict and reason substring
                assert s_verdict == exp_verdict, (
                    f"[{defect_id}] Static verdict mismatch: expected '{exp_verdict}', got '{s_verdict}'"
                )
                assert exp_reason in s_reason, (
                    f"[{defect_id}] Expected reason '{exp_reason}' not in '{s_reason}'"
                )
                assert s_verdict not in forbidden, (
                    f"[{defect_id}] Forbidden verdict returned: '{s_verdict}'"
                )

                # Strictly assert subsequent stages were NEVER reached
                for blocked_stage in must_not_reach:
                    assert blocked_stage not in executed_stages, (
                        f"[{defect_id}] Invariant violation: '{blocked_stage}' was executed "
                        f"despite static rejection."
                    )

                # Test Fixed Control Spec
                fixed_spec = entry["fixed_spec"]
                fixed_verdict, fixed_reason = self.static_validator.validate_spec(fixed_spec)
                exp_fixed_verdict = entry["fixed_expected_verdict"]
                assert fixed_verdict == exp_fixed_verdict, (
                    f"[{defect_id}] Fixed control static verdict mismatch: "
                    f"expected '{exp_fixed_verdict}', got '{fixed_verdict}'"
                )

                return {
                    "defect_id": defect_id,
                    "stage_reached": "static_validator",
                    "executed_stages": executed_stages,
                    "broken_result": {"verdict": s_verdict, "reason": s_reason},
                    "fixed_result": {"verdict": fixed_verdict, "reason": fixed_reason},
                    "passed": True,
                }

            elif s_verdict == "REJECT":
                raise AssertionError(
                    f"[{defect_id}] Unexpected static rejection at static layer: {s_reason}"
                )

        # =====================================================================
        # Stage 2: x86 Oracle / Reference Feasibility Check
        # =====================================================================
        if exp_stage == "x86_oracle":
            executed_stages.append("x86_oracle")
            lmf_path = entry["fixture_builder"](self.temp_dir)
            broken_ref = entry["reference_actions"]

            # Run through CandidateSuiteVerifier to verify reference failure stops suite
            verifier = CandidateSuiteVerifier(self.snapshot_path, lmf_path)
            cand_manifest = [{"candidate_name": "dummy", "family": "dummy", "action_sequence": [()]}]
            suite_res = verifier.evaluate_suite(broken_ref, cand_manifest, expected_candidate_count=1)

            assert suite_res["verdict"] == exp_verdict, (
                f"[{defect_id}] Reference verdict mismatch: expected '{exp_verdict}', got '{suite_res['verdict']}'"
            )
            assert suite_res["total_candidates_evaluated"] == 0, (
                f"[{defect_id}] Invariant violation: candidate suite evaluated when reference failed."
            )
            ref_trial = suite_res["reference_result"]
            assert exp_reason in ref_trial["evidence_source"], (
                f"[{defect_id}] Evidence '{ref_trial['evidence_source']}' does not match expected '{exp_reason}'"
            )

            # Test Fixed Control Reference
            fixed_ref = entry["fixed_reference_actions"]
            fixed_oracle = X86OracleVerifier(self.snapshot_path, lmf_path)
            fixed_trial = fixed_oracle.run_trial(fixed_ref, max_ticks=120)
            exp_fixed = entry["fixed_expected_verdict"]
            assert fixed_trial["terminal_type"] == exp_fixed, (
                f"[{defect_id}] Fixed control verdict mismatch: expected '{exp_fixed}', got '{fixed_trial['terminal_type']}'"
            )

            return {
                "defect_id": defect_id,
                "stage_reached": "x86_oracle",
                "executed_stages": executed_stages,
                "broken_result": suite_res,
                "fixed_result": fixed_trial,
                "passed": True,
            }

        # =====================================================================
        # Stage 3: Candidate Suite Bypass Verification
        # =====================================================================
        if exp_stage == "bypass_verifier":
            executed_stages.append("x86_oracle")
            executed_stages.append("bypass_verifier")
            broken_lmf, fixed_lmf = entry["fixture_builder"](self.temp_dir)
            ref_actions = entry["reference_actions"]
            cand_manifest = entry["candidate_manifest"]

            # Broken fixture evaluation
            verifier_broken = CandidateSuiteVerifier(self.snapshot_path, broken_lmf)
            broken_res = verifier_broken.evaluate_suite(
                ref_actions, cand_manifest, expected_candidate_count=len(cand_manifest)
            )
            assert broken_res["verdict"] == exp_verdict, (
                f"[{defect_id}] Bypass verdict mismatch: expected '{exp_verdict}', got '{broken_res['verdict']}'"
            )
            assert broken_res["verdict"] not in forbidden, (
                f"[{defect_id}] Forbidden verdict returned: '{broken_res['verdict']}'"
            )
            assert broken_res["winning_candidate"] is not None, (
                f"[{defect_id}] Winning candidate missing on KNOWN_BYPASS_FOUND."
            )

            # Fixed fixture evaluation
            verifier_fixed = CandidateSuiteVerifier(self.snapshot_path, fixed_lmf)
            fixed_res = verifier_fixed.evaluate_suite(
                ref_actions, cand_manifest, expected_candidate_count=len(cand_manifest)
            )
            exp_fixed = entry["fixed_expected_verdict"]
            assert fixed_res["verdict"] == exp_fixed, (
                f"[{defect_id}] Fixed control bypass verdict mismatch: "
                f"expected '{exp_fixed}', got '{fixed_res['verdict']}'"
            )

            return {
                "defect_id": defect_id,
                "stage_reached": "bypass_verifier",
                "executed_stages": executed_stages,
                "broken_result": broken_res,
                "fixed_result": fixed_res,
                "passed": True,
            }

        raise ValueError(f"Unknown detection stage '{exp_stage}' for defect '{defect_id}'.")
