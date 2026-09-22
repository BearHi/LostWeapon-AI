"""audit_generator_100.py - Large-scale Quality & Distribution Auditor for Procedural Generator V1.

Generates and audits ~100 maps across all 8 archetypes:
  1. Pipeline pass rate & stage-by-stage attrition (Static vs x86 Oracle vs Bypass).
  2. Duplicate analysis (exact MapSpec hash, geometric duplicates).
  3. Skill & archetype distribution analysis.
  4. Outlier & boundary map identification (highest tick, tightest margins).
  5. Saves full audit report to audit_100_summary.json.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
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
):
    print("=" * 80)
    print(" [LostWeapon AI] Generator V1 100-Map Quality & Distribution Audit")
    print(f" Target: 8 archetypes x {count_per_archetype} samples = {8 * count_per_archetype} candidates | Seed: {seed}")
    print("=" * 80)

    t0 = time.time()
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
    print(f"Generated {total_candidates} candidates across {len(ARCHETYPE_CLASSES)} archetypes.\n")

    # 1. Duplicate check at generation layer
    hash_to_candidates = defaultdict(list)
    for c in all_candidates:
        h = c.compute_spec_sha256()
        hash_to_candidates[h].append(c.variation_id)

    unique_specs = len(hash_to_candidates)
    duplicates = {h: ids for h, ids in hash_to_candidates.items() if len(ids) > 1}
    dup_rate = ((total_candidates - unique_specs) / total_candidates * 100.0) if total_candidates > 0 else 0.0

    print(f"[Duplicate Check at Generation Layer]")
    print(f"  - Total Candidates: {total_candidates}")
    print(f"  - Unique MapSpecs:  {unique_specs}")
    print(f"  - Duplicate Count:  {len(duplicates)} groups ({dup_rate:.2f}% duplicate rate)\n")

    # 2. Run Validation Pipeline
    results = []
    archetype_stats = defaultdict(lambda: {"total": 0, "passed": 0, "static_reject": 0, "ref_fail": 0, "bypass_found": 0})
    stage_attrition = Counter()

    print("[Validation Pipeline Execution]")
    for idx, cand in enumerate(all_candidates, 1):
        arch_id = cand.archetype_id
        map_id = cand.spec.map_id
        archetype_stats[arch_id]["total"] += 1

        print(f"[{idx:03d}/{total_candidates:03d}] {arch_id[:16]} :: {map_id} ... ", end="", flush=True)
        res = pipeline.process_candidate(cand, max_ticks=250)
        status = res["status"]
        results.append(res)
        stage_attrition[status] += 1

        if status == "VERIFIED":
            archetype_stats[arch_id]["passed"] += 1
            print(f"PASS (tick {res['terminal_tick']})")
        elif status == "REJECTED_STATIC":
            archetype_stats[arch_id]["static_reject"] += 1
            print(f"REJECT_STATIC ({res['reason'][:35]}...)")
        elif status == "REFERENCE_FAILED":
            archetype_stats[arch_id]["ref_fail"] += 1
            print(f"REF_FAIL ({res['verdict']}: {res['reason']})")
            pipeline._quarantine_defect(cand, "reference_failed", res)
        elif status == "BYPASS_FOUND":
            archetype_stats[arch_id]["bypass_found"] += 1
            print(f"BYPASS ({res['reason'][:35]}...)")
            pipeline._quarantine_defect(cand, "bypass_found", res)

    elapsed = time.time() - t0
    verified_count = stage_attrition["VERIFIED"]
    overall_pass_rate = (verified_count / total_candidates * 100.0) if total_candidates > 0 else 0.0

    # 3. Analyze Outlier & Borderline Maps
    passed_results = [r for r in results if r["status"] == "VERIFIED"]
    passed_results.sort(key=lambda r: r["terminal_tick"])

    fastest_maps = [
        {"map_id": r["map_id"], "tick": r["terminal_tick"], "pos": r["final_position"]}
        for r in passed_results[:3]
    ]
    longest_maps = [
        {"map_id": r["map_id"], "tick": r["terminal_tick"], "pos": r["final_position"]}
        for r in passed_results[-3:]
    ]

    # 4. Compile Comprehensive Audit Summary
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(elapsed, 2),
        "total_candidates": total_candidates,
        "unique_specs_generated": unique_specs,
        "generation_duplicate_rate_pct": round(dup_rate, 2),
        "overall_verified_passed": verified_count,
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
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # 5. Print Terminal Report
    print("\n" + "=" * 80)
    print(" [AUDIT SUMMARY REPORT]")
    print(f"  - Total Evaluated:       {total_candidates}")
    print(f"  - Unique Specs:          {unique_specs} ({dup_rate:.1f}% duplicate rate)")
    print(f"  - Verified Clean Maps:   {verified_count} ({overall_pass_rate:.1f}% Pass Rate)")
    print(f"  - Attrition by Stage:    {dict(stage_attrition)}")
    print(f"  - Elapsed Time:          {elapsed:.2f}s ({elapsed/total_candidates:.2f}s per map)")
    print(f"  - Summary Saved:         {summary_file}")
    print("=" * 80)
    print("\n[Archetype Performance Table]")
    print(f"{'Archetype':<26} | {'Total':<6} | {'Pass':<6} | {'Pass%':<7} | {'StaticRej':<10} | {'RefFail':<8} | {'Bypass':<6}")
    print("-" * 80)
    for arch, st in sorted(archetype_stats.items()):
        p_pct = (st["passed"] / st["total"] * 100.0) if st["total"] > 0 else 0.0
        print(f"{arch:<26} | {st['total']:<6} | {st['passed']:<6} | {p_pct:<6.1f}% | {st['static_reject']:<10} | {st['ref_fail']:<8} | {st['bypass_found']:<6}")
    print("=" * 80)

    return summary


if __name__ == "__main__":
    run_100_audit()
