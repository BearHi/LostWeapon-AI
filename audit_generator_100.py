"""audit_generator_100.py - Token-Safe Quality & Distribution Auditor for Procedural Generator V1.

Token-Safe Execution Guarantee:
  - ZERO per-map/per-candidate stdout during execution.
  - Per-candidate details logged exclusively to audit_detail.jsonl.
  - Atomic progress tracking written to audit_progress.json.
  - Stdout restricted strictly to 1 start header and 1 final completion summary.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
HARNESS_DIR = ROOT / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from batch_map_pipeline import BatchMapPipeline
from procedural_generator import ARCHETYPE_CLASSES, ProceduralMapGenerator


def run_100_audit(
    output_dir: Path = ROOT / "훈련용맵" / "audit_run_100",
    quarantine_dir: Path = ROOT / "훈련용맵" / "audit_run_100" / "quarantine",
    seed: int = 20260923,
    count_per_archetype: int = 13,  # 8 * 13 = 104 maps
) -> dict:
    output_dir = Path(output_dir)
    quarantine_dir = Path(quarantine_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    generator = ProceduralMapGenerator()
    pipeline = BatchMapPipeline(
        output_dir=output_dir,
        quarantine_dir=quarantine_dir,
        enable_quarantine=True,
    )

    all_candidates = list(
        generator.generate(
            mode="sample",
            count_per_archetype=count_per_archetype,
            seed=seed,
        )
    )

    total_candidates = len(all_candidates)

    # 1. Start Header (Strictly 2 lines allowed on stdout)
    print("LostWeapon Generator Audit")
    print(f"Running {total_candidates} candidates...")
    sys.stdout.flush()

    t0 = time.time()

    # 2. Duplicate Check at generation layer
    hash_to_candidates = defaultdict(list)
    for c in all_candidates:
        h = c.compute_spec_sha256()
        hash_to_candidates[h].append(c.variation_id)

    unique_specs = len(hash_to_candidates)
    dup_rate = ((total_candidates - unique_specs) / total_candidates * 100.0) if total_candidates > 0 else 0.0

    # 3. Setup Detail Log and Progress tracking
    detail_log_file = output_dir / "audit_detail.jsonl"
    progress_file = output_dir / "audit_progress.json"

    results = []
    archetype_stats = defaultdict(lambda: {"total": 0, "passed": 0, "static_reject": 0, "ref_fail": 0, "bypass_found": 0})
    stage_attrition = Counter()

    with open(detail_log_file, "w", encoding="utf-8") as detail_f:
        for idx, cand in enumerate(all_candidates, 1):
            arch_id = cand.archetype_id
            map_id = cand.spec.map_id
            archetype_stats[arch_id]["total"] += 1

            res = pipeline.process_candidate(cand, max_ticks=250)
            status = res["status"]
            results.append(res)
            stage_attrition[status] += 1

            if status == "VERIFIED":
                archetype_stats[arch_id]["passed"] += 1
            elif status == "REJECTED_STATIC":
                archetype_stats[arch_id]["static_reject"] += 1
            elif status == "REFERENCE_FAILED":
                archetype_stats[arch_id]["ref_fail"] += 1
                pipeline._quarantine_defect(cand, "reference_failed", res)
            elif status == "BYPASS_FOUND":
                archetype_stats[arch_id]["bypass_found"] += 1
                pipeline._quarantine_defect(cand, "bypass_found", res)

            # Write candidate record to JSONL only (Zero stdout)
            cand_record = {
                "index": idx,
                "archetype_id": arch_id,
                "map_id": map_id,
                "status": status,
                "stage": res.get("stage"),
                "verdict": res.get("verdict"),
                "reason": res.get("reason"),
                "terminal_tick": res.get("terminal_tick"),
                "final_position": res.get("final_position"),
                "parameters": cand.parameters,
            }
            detail_f.write(json.dumps(cand_record, ensure_ascii=False) + "\n")
            detail_f.flush()

            # Overwrite progress JSON
            progress_data = {
                "completed": idx,
                "total": total_candidates,
                "percent": round(idx / total_candidates * 100.0, 1),
                "verified": stage_attrition["VERIFIED"],
                "rejected": idx - stage_attrition["VERIFIED"],
                "elapsed_seconds": round(time.time() - t0, 1),
            }
            progress_file.write_text(json.dumps(progress_data, indent=2), encoding="utf-8")

    elapsed = time.time() - t0
    verified_count = stage_attrition["VERIFIED"]
    rejected_count = total_candidates - verified_count
    overall_pass_rate = (verified_count / total_candidates * 100.0) if total_candidates > 0 else 0.0

    # 4. Outlier Analysis
    passed_results = [r for r in results if r["status"] == "VERIFIED"]
    passed_results.sort(key=lambda r: r.get("terminal_tick", 9999))

    fastest_maps = [
        {"map_id": r["map_id"], "tick": r.get("terminal_tick"), "pos": r.get("final_position")}
        for r in passed_results[:3]
    ]
    longest_maps = [
        {"map_id": r["map_id"], "tick": r.get("terminal_tick"), "pos": r.get("final_position")}
        for r in passed_results[-3:]
    ]

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(elapsed, 2),
        "total_candidates": total_candidates,
        "unique_specs_generated": unique_specs,
        "generation_duplicate_rate_pct": round(dup_rate, 2),
        "overall_verified_passed": verified_count,
        "overall_rejected": rejected_count,
        "overall_pass_rate_pct": round(overall_pass_rate, 2),
        "stage_attrition": dict(stage_attrition),
        "archetype_breakdown": {
            arch: dict(st) for arch, st in archetype_stats.items()
        },
        "fastest_cleared_maps": fastest_maps,
        "longest_cleared_maps": longest_maps,
        "output_directory": str(output_dir),
    }

    summary_file = output_dir / "audit_100_summary.json"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # 5. Final Output (Strictly completion summary)
    print("완료")
    print(f"Accepted: {verified_count}")
    print(f"Rejected: {rejected_count}")
    print(f"Summary: {summary_file}")
    sys.stdout.flush()

    return summary


if __name__ == "__main__":
    run_100_audit()
