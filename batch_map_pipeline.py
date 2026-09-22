"""batch_map_pipeline.py - Orchestrates Bulk Procedural Map Generation & Validation.

Utilizes Map Validation Pipeline V1 to process procedurally generated MapSpecs:
  1. StaticPhysicsValidator (Pre-filter kinematic violations in 0ms)
  2. MapCompiler (Compiles declarative MapSpec into binary LMF)
  3. X86OracleVerifier (Ensures intended reference path succeeds)
  4. CandidateSuiteVerifier (Ensures anti-bypass candidates fail cleanly)
  5. Dataset Storage (Saves verified LMF, spec JSON, ref actions, and manifest)
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parent
HARNESS_DIR = ROOT / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from candidate_suite_verifier import CandidateSuiteVerifier
from map_compiler import MapCompiler
from procedural_generator import ARCHETYPE_CLASSES, GeneratedCandidate, ProceduralMapGenerator
from static_validator import StaticPhysicsValidator, VERDICT_REJECT
from x86_oracle_verifier import X86OracleVerifier


class BatchMapPipeline:
    """Executes full Map Validation Pipeline V1 on procedurally generated candidates."""

    def __init__(
        self,
        output_dir: Path = ROOT / "훈련용맵" / "generated_curriculum",
        quarantine_dir: Path = ROOT / "훈련용맵" / "quarantine",
        temp_dir: Path = ROOT / "scratch" / "pipeline_temp",
        registry_path: Path = ROOT / "physics_registry.json",
        snapshots_dir: Path = HARNESS_DIR / "private_snapshots",
        enable_quarantine: bool = True,
    ):
        self.output_dir = Path(output_dir)
        self.quarantine_dir = Path(quarantine_dir)
        self.temp_dir = Path(temp_dir)
        self.registry_path = Path(registry_path)
        self.snapshots_dir = Path(snapshots_dir)
        self.enable_quarantine = enable_quarantine

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.static_validator = StaticPhysicsValidator(self.registry_path)
        self.compiler = MapCompiler()
        self.generator = ProceduralMapGenerator()

    def resolve_snapshot_path(self, override: Optional[str] = None) -> Path:
        """Resolve snapshot zip path, falling back to hun6_live.zip if needed."""
        default_snap = self.snapshots_dir / "hun6_live.zip"
        if override:
            snap_path = self.snapshots_dir / override
            if snap_path.exists():
                return snap_path
        if default_snap.exists():
            return default_snap
        raise FileNotFoundError(f"No baseline snapshot found in: {self.snapshots_dir}")

    def process_candidate(self, candidate: GeneratedCandidate, max_ticks: int = 250) -> Dict[str, Any]:
        """Runs the 3-stage validation pipeline on a single generated candidate."""
        map_id = candidate.spec.map_id
        spec_dict = asdict(candidate.spec)

        # ---------------------------------------------------------------------
        # Stage 1: Static Physics Validator (0ms pre-filter)
        # ---------------------------------------------------------------------
        s_verdict, s_reason = self.static_validator.validate_spec(spec_dict)
        if s_verdict == VERDICT_REJECT:
            return {
                "map_id": map_id,
                "status": "REJECTED_STATIC",
                "stage": "static_validator",
                "verdict": s_verdict,
                "reason": s_reason,
                "candidate": candidate,
            }

        # ---------------------------------------------------------------------
        # Stage 2: Compilation & x86 Oracle Reference Verification
        # ---------------------------------------------------------------------
        temp_lmf = self.temp_dir / f"{map_id}.LMF"
        self.compiler.compile(candidate.spec, temp_lmf)

        snap_path = self.resolve_snapshot_path(candidate.snapshot_override)
        oracle = X86OracleVerifier(snap_path, temp_lmf)
        ref_trial = oracle.run_trial(candidate.reference_actions, max_ticks=max_ticks)

        if ref_trial["terminal_type"] != "SUCCESS":
            return {
                "map_id": map_id,
                "status": "REFERENCE_FAILED",
                "stage": "x86_oracle",
                "verdict": ref_trial["terminal_type"],
                "reason": ref_trial["evidence_source"],
                "trial": ref_trial,
                "candidate": candidate,
            }

        # ---------------------------------------------------------------------
        # Stage 3: Candidate Suite Bypass Verification (Anti-Bypass)
        # ---------------------------------------------------------------------
        bypass_summary = None
        if candidate.bypass_manifest:
            suite_verifier = CandidateSuiteVerifier(snap_path, temp_lmf)
            suite_res = suite_verifier.evaluate_suite(
                candidate.reference_actions,
                candidate.bypass_manifest,
                expected_candidate_count=len(candidate.bypass_manifest),
                max_ticks=max_ticks,
            )
            bypass_summary = suite_res

            if suite_res["verdict"] == "KNOWN_BYPASS_FOUND":
                winner = suite_res.get("winning_candidate", {})
                w_name = winner.get("candidate_name", "unknown")
                w_fam = winner.get("family", "unknown")
                return {
                    "map_id": map_id,
                    "status": "BYPASS_FOUND",
                    "stage": "bypass_verifier",
                    "verdict": suite_res["verdict"],
                    "reason": f"Bypassed by candidate '{w_name}' (family: {w_fam})",
                    "suite_result": suite_res,
                    "candidate": candidate,
                }

        # ---------------------------------------------------------------------
        # Passed All Stages: Save to permanent dataset
        # ---------------------------------------------------------------------
        arch_dir = self.output_dir / candidate.archetype_id
        arch_dir.mkdir(parents=True, exist_ok=True)

        perm_lmf = arch_dir / f"{map_id}.LMF"
        shutil.copy2(temp_lmf, perm_lmf)

        perm_spec = arch_dir / f"{map_id}.spec.json"
        perm_spec.write_text(json.dumps(spec_dict, indent=2, ensure_ascii=False), encoding="utf-8")

        perm_ref = arch_dir / f"{map_id}.ref.json"
        ref_data = {
            "map_id": map_id,
            "archetype_id": candidate.archetype_id,
            "terminal_tick": ref_trial["terminal_tick"],
            "final_position": ref_trial["final_position"],
            "action_count": len(candidate.reference_actions),
            "reference_actions": [list(keys) for keys in candidate.reference_actions],
        }
        perm_ref.write_text(json.dumps(ref_data, indent=2), encoding="utf-8")

        lmf_sha256 = hashlib.sha256(perm_lmf.read_bytes()).hexdigest()

        return {
            "map_id": map_id,
            "status": "VERIFIED",
            "stage": "complete",
            "verdict": "VERIFIED",
            "reason": "Passed static invariants, positive x86 oracle, and anti-bypass suite.",
            "lmf_path": str(perm_lmf),
            "spec_path": str(perm_spec),
            "ref_path": str(perm_ref),
            "lmf_sha256": lmf_sha256,
            "terminal_tick": ref_trial["terminal_tick"],
            "final_position": ref_trial["final_position"],
            "candidate": candidate,
        }

    def run_batch(
        self,
        archetype_ids: Optional[Sequence[str]] = None,
        mode: str = "grid",
        count_per_archetype: Optional[int] = None,
        seed: int = 42,
        max_ticks: int = 250,
    ) -> Dict[str, Any]:
        """Executes procedural generation and batch validation across specified archetypes."""
        t0 = time.time()
        candidates = list(
            self.generator.generate(
                archetype_ids=archetype_ids,
                mode=mode,
                count_per_archetype=count_per_archetype,
                seed=seed,
            )
        )

        total = len(candidates)
        print("=" * 80)
        print(f" [LostWeapon AI Procedural Map Pipeline] Total Candidates: {total}")
        print(f" Mode: {mode.upper()} | Archetypes: {archetype_ids or 'ALL (8)'} | Seed: {seed}")
        print("=" * 80)

        verified_maps: List[Dict[str, Any]] = []
        quarantined_maps: List[Dict[str, Any]] = []
        stats = {
            "total_candidates": total,
            "verified_passed": 0,
            "static_rejected": 0,
            "reference_failed": 0,
            "bypass_found": 0,
        }

        for idx, cand in enumerate(candidates, 1):
            map_id = cand.spec.map_id
            print(f"[{idx:03d}/{total:03d}] {cand.archetype_id} :: {map_id} ... ", end="", flush=True)

            res = self.process_candidate(cand, max_ticks=max_ticks)
            status = res["status"]

            if status == "VERIFIED":
                stats["verified_passed"] += 1
                verified_maps.append({
                    "map_id": map_id,
                    "archetype_id": cand.archetype_id,
                    "lmf_path": res["lmf_path"],
                    "spec_path": res["spec_path"],
                    "ref_path": res["ref_path"],
                    "lmf_sha256": res["lmf_sha256"],
                    "terminal_tick": res["terminal_tick"],
                    "final_position": res["final_position"],
                    "parameters": cand.parameters,
                })
                print(f"PASS (tick {res['terminal_tick']}, SHA: {res['lmf_sha256'][:8]})")

            elif status == "REJECTED_STATIC":
                stats["static_rejected"] += 1
                print(f"REJECT_STATIC ({res['reason'][:40]}...)")

            elif status == "REFERENCE_FAILED":
                stats["reference_failed"] += 1
                print(f"REF_FAILED ({res['verdict']}: {res['reason']})")
                if self.enable_quarantine:
                    self._quarantine_defect(cand, "reference_failed", res)

            elif status == "BYPASS_FOUND":
                stats["bypass_found"] += 1
                print(f"BYPASS_DETECTED ({res['reason']})")
                if self.enable_quarantine:
                    self._quarantine_defect(cand, "bypass_found", res)

        elapsed = time.time() - t0
        pass_rate = (stats["verified_passed"] / total * 100.0) if total > 0 else 0.0

        # Save dataset manifest
        manifest_data = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": round(elapsed, 2),
            "stats": stats,
            "pass_rate_pct": round(pass_rate, 2),
            "verified_maps_count": len(verified_maps),
            "verified_maps": verified_maps,
        }
        manifest_path = self.output_dir / "dataset_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\n" + "=" * 80)
        print(f" [PIPELINE COMPLETE] Elapsed: {elapsed:.2f}s | Pass Rate: {pass_rate:.1f}%")
        print(f"  - Total Candidates:    {stats['total_candidates']}")
        print(f"  - Verified Passed:     {stats['verified_passed']} -> Saved to {self.output_dir}")
        print(f"  - Static Rejected:     {stats['static_rejected']}")
        print(f"  - Reference Failed:    {stats['reference_failed']}")
        print(f"  - Bypass Detected:     {stats['bypass_found']}")
        print(f"  - Master Manifest:     {manifest_path}")
        print("=" * 80)

        return manifest_data

    def _quarantine_defect(self, candidate: GeneratedCandidate, category: str, result: Dict[str, Any]):
        """Isolate failed or bypassed candidates into quarantine for defect auditing."""
        q_dir = self.quarantine_dir / category / candidate.archetype_id
        q_dir.mkdir(parents=True, exist_ok=True)
        q_file = q_dir / f"{candidate.spec.map_id}.defect.json"
        defect_data = {
            "map_id": candidate.spec.map_id,
            "archetype_id": candidate.archetype_id,
            "category": category,
            "reason": result.get("reason"),
            "stage": result.get("stage"),
            "verdict": result.get("verdict"),
            "spec": asdict(candidate.spec),
            "parameters": candidate.parameters,
        }
        q_file.write_text(json.dumps(defect_data, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="LostWeapon Procedural Map Batch Generator & Pipeline")
    parser.add_argument(
        "--archetype",
        "-a",
        type=str,
        default=None,
        help="Specific archetype ID to run (e.g. ARCH_01_BASIC_GAP). Defaults to all.",
    )
    parser.add_argument(
        "--mode",
        "-m",
        type=str,
        choices=["grid", "sample"],
        default="grid",
        help="Generation mode: 'grid' (discrete sweep) or 'sample' (random seed).",
    )
    parser.add_argument(
        "--count",
        "-c",
        type=int,
        default=None,
        help="Max candidates to generate per archetype.",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=42,
        help="Random seed for sampling.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=ROOT / "훈련용맵" / "generated_curriculum",
        help="Output directory for verified dataset.",
    )
    parser.add_argument(
        "--no-quarantine",
        action="store_true",
        help="Disable saving rejected/bypassed maps to quarantine.",
    )
    args = parser.parse_args()

    arch_ids = [args.archetype] if args.archetype else None
    pipeline = BatchMapPipeline(
        output_dir=args.output_dir,
        enable_quarantine=not args.no_quarantine,
    )
    pipeline.run_batch(
        archetype_ids=arch_ids,
        mode=args.mode,
        count_per_archetype=args.count,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
