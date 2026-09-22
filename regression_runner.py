"""regression_runner.py - Neutral Multi-Stage Historical Defect Regression Runner.

Orchestrates the evaluation of historical project defects through a neutral,
objective pipeline:
  1. static_validator (Static physics kinematic invariants)
  2. x86_oracle (Ground-truth native emulation & reference feasibility)
  3. bypass_verifier (Multi-candidate suite bypass detection)

Strict Invariants:
  - The pipeline runs standard logic without awareness of 'expected_detection_stage'.
  - 'expected_detection_stage' is exclusively used post-execution for assertion.
  - If a stage terminates early (e.g. static REJECT or reference DEATH), downstream stages
    are never reached.
  - All 6 audit metadata fields are preserved for every execution.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
HARNESS_DIR = ROOT / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from candidate_suite_verifier import CandidateSuiteVerifier
from map_compiler import MapCompiler
from regression_corpus import HISTORICAL_REGRESSION_CORPUS, verify_file_sha256
from static_validator import StaticPhysicsValidator
from x86_oracle_verifier import X86OracleVerifier


class RegressionRunner:
    def __init__(self, registry_path: Path, snapshot_path: Path, temp_dir: Path):
        self.registry_path = Path(registry_path)
        self.snapshot_path = Path(snapshot_path)
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.static_validator = StaticPhysicsValidator(self.registry_path)
        self.compiler = MapCompiler()

    def run_pipeline(
        self,
        spec_dict: Optional[Dict[str, Any]] = None,
        lmf_path: Optional[Path] = None,
        ref_actions: Optional[List[tuple[str, ...]]] = None,
        candidate_manifest: Optional[List[Dict[str, Any]]] = None,
        max_ticks: int = 200,
    ) -> Dict[str, Any]:
        """Neutral, objective multi-stage execution pipeline.
        
        Does NOT accept or read 'expected_detection_stage'. Executes standard
        pipeline stages sequentially with organic short-circuiting on failure.
        """
        executed_stages: List[str] = []

        # ---------------------------------------------------------------------
        # Stage 1: Static Physics Validator (when spec_dict is available)
        # ---------------------------------------------------------------------
        if spec_dict is not None:
            executed_stages.append("static_validator")
            s_verdict, s_reason = self.static_validator.validate_spec(spec_dict)
            if s_verdict == "REJECT":
                # Static impossibility: short-circuit pipeline immediately
                return {
                    "terminal_stage": "static_validator",
                    "verdict": "REJECT",
                    "evidence_source": s_reason,
                    "executed_stages": executed_stages,
                    "details": {"static_verdict": s_verdict, "static_reason": s_reason},
                }

            # If no downstream reference actions provided, complete at static layer
            if ref_actions is None:
                return {
                    "terminal_stage": "static_validator",
                    "verdict": s_verdict,
                    "evidence_source": s_reason,
                    "executed_stages": executed_stages,
                    "details": {"static_verdict": s_verdict, "static_reason": s_reason},
                }

            # If downstream execution requested and no LMF provided, compile MapSpec into LMF
            if lmf_path is None:
                from map_compiler import MapSpec
                map_id = spec_dict.get("map_id", "compiled_temp")
                lmf_path = self.temp_dir / f"{map_id}.LMF"
                self.compiler.compile(MapSpec.from_dict(spec_dict), lmf_path)

        # ---------------------------------------------------------------------
        # Stage 2: x86 Oracle / Reference Feasibility (when ref_actions given)
        # ---------------------------------------------------------------------
        if ref_actions is not None:
            if lmf_path is None:
                raise ValueError("Cannot run x86 oracle without a compiled LMF path.")

            executed_stages.append("x86_oracle")
            oracle = X86OracleVerifier(self.snapshot_path, lmf_path)
            ref_trial = oracle.run_trial(ref_actions, max_ticks=max_ticks)
            terminal_type = ref_trial["terminal_type"]

            if terminal_type == "INVALID":
                return {
                    "terminal_stage": "x86_oracle",
                    "verdict": "VERIFIER_ERROR",
                    "evidence_source": ref_trial["evidence_source"],
                    "executed_stages": executed_stages,
                    "details": {"reference_result": ref_trial},
                }

            if terminal_type in ("DEATH", "TIMEOUT"):
                return {
                    "terminal_stage": "x86_oracle",
                    "verdict": "REFERENCE_FAILED",
                    "evidence_source": ref_trial["evidence_source"],
                    "executed_stages": executed_stages,
                    "details": {"reference_result": ref_trial},
                }

            # Reference succeeded. If no candidate suite to evaluate, return SUCCESS.
            if not candidate_manifest:
                return {
                    "terminal_stage": "x86_oracle",
                    "verdict": "SUCCESS",
                    "evidence_source": ref_trial["evidence_source"],
                    "executed_stages": executed_stages,
                    "details": {"reference_result": ref_trial},
                }

        # ---------------------------------------------------------------------
        # Stage 3: Candidate Suite Bypass Verification (when suite provided)
        # ---------------------------------------------------------------------
        if candidate_manifest is not None and ref_actions is not None and lmf_path is not None:
            executed_stages.append("bypass_verifier")
            suite_verifier = CandidateSuiteVerifier(self.snapshot_path, lmf_path)
            suite_res = suite_verifier.evaluate_suite(
                ref_actions,
                candidate_manifest,
                expected_candidate_count=len(candidate_manifest),
                max_ticks=max_ticks,
            )
            winner = suite_res.get("winning_candidate")
            evidence = winner["evidence_source"] if winner else "all_candidates_failed_cleanly"
            return {
                "terminal_stage": "bypass_verifier",
                "verdict": suite_res["verdict"],
                "evidence_source": evidence,
                "executed_stages": executed_stages,
                "details": {"suite_result": suite_res},
            }

        # Fallback for spec-only cases that pass static validator
        return {
            "terminal_stage": "static_validator",
            "verdict": s_verdict,
            "evidence_source": s_reason,
            "executed_stages": executed_stages,
            "details": {"static_verdict": s_verdict, "static_reason": s_reason},
        }

    def evaluate_defect(self, defect_id: str) -> Dict[str, Any]:
        """Evaluate a historical defect and its fixed control, asserting all invariants."""
        if defect_id not in HISTORICAL_REGRESSION_CORPUS:
            raise KeyError(f"Defect '{defect_id}' not found in registry.")

        entry = HISTORICAL_REGRESSION_CORPUS[defect_id]
        f_type = entry["type"]
        broken_path = entry["golden_broken_path"]
        broken_sha = entry["golden_broken_sha256"]
        fixed_path = entry["golden_fixed_path"]
        fixed_sha = entry["golden_fixed_sha256"]

        # 1. Assert immutable Golden Fixture integrity
        assert verify_file_sha256(broken_path, broken_sha), (
            f"[{defect_id}] Broken golden fixture hash mismatch: {broken_path}"
        )
        assert verify_file_sha256(fixed_path, fixed_sha), (
            f"[{defect_id}] Fixed golden fixture hash mismatch: {fixed_path}"
        )

        # 2. Run neutral pipeline on Broken Fixture
        ref_actions = entry.get("reference_actions")
        cand_manifest = entry.get("candidate_manifest")

        if f_type == "lmf":
            broken_out = self.run_pipeline(
                lmf_path=broken_path,
                ref_actions=ref_actions,
                candidate_manifest=cand_manifest,
            )
        elif f_type == "mapspec":
            spec = json.loads(broken_path.read_text(encoding="utf-8"))
            broken_out = self.run_pipeline(
                spec_dict=spec,
                ref_actions=ref_actions,
                candidate_manifest=cand_manifest,
            )
        else:
            raise ValueError(f"Unknown fixture type: {f_type}")

        # 3. Post-execution assertions against defect metadata
        exp_stage = entry["expected_detection_stage"]
        exp_verdict = entry["expected_verdict"]
        exp_reason = entry.get("expected_reason", "")
        forbidden = entry.get("forbidden_verdicts", [])
        must_not_reach = entry.get("must_not_reach_stage", [])

        # Assertion: Pipeline stopped at the exact expected stage
        assert broken_out["terminal_stage"] == exp_stage, (
            f"[{defect_id}] Terminal stage mismatch: expected '{exp_stage}', "
            f"got '{broken_out['terminal_stage']}'"
        )

        # Assertion: Stage verdict matches expectation
        assert broken_out["verdict"] == exp_verdict, (
            f"[{defect_id}] Verdict mismatch: expected '{exp_verdict}', "
            f"got '{broken_out['verdict']}'"
        )

        # Assertion: Verdict not forbidden
        assert broken_out["verdict"] not in forbidden, (
            f"[{defect_id}] Forbidden verdict returned: '{broken_out['verdict']}'"
        )

        # Assertion: Evidence/reason substring check
        assert exp_reason in broken_out["evidence_source"], (
            f"[{defect_id}] Expected reason '{exp_reason}' not in '{broken_out['evidence_source']}'"
        )

        # Assertion: Downstream stages in must_not_reach were NEVER invoked
        for blocked_stage in must_not_reach:
            assert blocked_stage not in broken_out["executed_stages"], (
                f"[{defect_id}] Invariant violation: Stage '{blocked_stage}' was executed "
                f"despite short-circuiting. Executed: {broken_out['executed_stages']}"
            )

        # 4. Run neutral pipeline on Fixed Control Fixture
        fixed_ref_actions = entry.get("fixed_reference_actions", ref_actions)
        if f_type == "lmf":
            fixed_out = self.run_pipeline(
                lmf_path=fixed_path,
                ref_actions=fixed_ref_actions,
                candidate_manifest=cand_manifest,
            )
        elif f_type == "mapspec":
            fixed_spec = json.loads(fixed_path.read_text(encoding="utf-8"))
            fixed_out = self.run_pipeline(
                spec_dict=fixed_spec,
                ref_actions=fixed_ref_actions,
                candidate_manifest=cand_manifest,
            )

        exp_fixed_verdict = entry["fixed_expected_verdict"]
        assert fixed_out["verdict"] == exp_fixed_verdict, (
            f"[{defect_id}] Fixed control verdict mismatch: expected '{exp_fixed_verdict}', "
            f"got '{fixed_out['verdict']}'"
        )

        # 5. Return full audit record with the 6 mandatory fields
        return {
            "defect_id": defect_id,
            "fixture_sha256": broken_sha,
            "expected_stage": exp_stage,
            "actual_executed_stages": broken_out["executed_stages"],
            "expected_verdict": exp_verdict,
            "actual_verdict": broken_out["verdict"],
            "native_evidence_source": broken_out["evidence_source"],
            "fixed_fixture_sha256": fixed_sha,
            "fixed_verdict": fixed_out["verdict"],
            "passed": True,
        }
