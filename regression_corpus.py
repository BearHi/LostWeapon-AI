"""regression_corpus.py - Historical Defect Regression Corpus Registry.

Defines the canonical registry of past project failures and design defects.
Each entry strictly declares:
  - defect_id: Unique identifier (HIST-001 ~ HIST-004)
  - name: Machine-readable identifier
  - description: Root cause and historical defect context
  - expected_detection_stage: The earliest pipeline stage that MUST catch this defect
  - expected_verdict: The expected verdict string from that stage
  - expected_reason: Required substring/evidence in reason/evidence string
  - forbidden_verdicts: Verdicts that must NEVER be returned
  - must_not_reach_stage: Subsequent pipeline stages that must NEVER be executed
  - broken_fixture: MapSpec / generator for the defect reproduction
  - fixed_fixture: MapSpec / generator for the corrected control
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def build_lmf_binary(width: int, height: int, records: list[tuple[int, int, int]], out_path: Path) -> Path:
    """Build a standard 32-byte header + 8-byte record LMF binary."""
    import struct
    header = bytearray(32)
    header[:16] = b"NewLWMapFile_1.0"
    struct.pack_into("<HH", header, 16, width, height)
    header[20] = 0x12
    struct.pack_into("<I", header, 21, len(records))
    body = bytearray()
    for tile_id, x, y in records:
        body.extend(struct.pack("<Ihh", int(tile_id), int(x), int(y)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(header) + bytes(body))
    return out_path


# =========================================================================
# HIST-001: Knife required but delayed backroll bypass
# =========================================================================
def get_hist001_fixtures(base_dir: Path) -> tuple[Path, Path]:
    w, h, gy = 30, 20, 14
    base_records = []
    for x in range(w):
        base_records.append((49, x, 17))
    base_records.append((100, 3, gy - 1)) # Spawn: tile (3, 13)
    base_records.append((140, 20, 10))    # Flag: tile (20, 10)
    for x in range(1, 6):
        base_records.append((7, x, gy))   # Start: x=1..5, y=14
    for x in range(10, 26):
        base_records.append((7, x, 11))   # Target: x=10..25, y=11 (step-up 96px)

    # Broken: Open air gap without ceiling
    broken_lmf = base_dir / "hist001_broken_open_gap.LMF"
    build_lmf_binary(w, h, base_records, broken_lmf)

    # Fixed: Step-up with ceiling overhang (y=0..7, bottom Y=256)
    fixed_lmf = base_dir / "hist001_fixed_ceiling_gap.LMF"
    recs_fixed = list(base_records)
    for y in range(0, 8):
        for x in range(8, 26):
            recs_fixed.append((7, x, y))
    build_lmf_binary(w, h, recs_fixed, fixed_lmf)

    return broken_lmf, fixed_lmf


HIST_001_REF_ACTIONS = (
    [("1",)]
    + [("RIGHT",)] * 16
    + [("RIGHT", "UP")] * 14
    + [("RIGHT", "Z")]
    + [("RIGHT",)] * 100
)

HIST_001_CAND_MANIFEST = [
    {
        "candidate_name": "delayed_backroll_j28_sw0_rd5",
        "family": "delayed_backroll",
        "parameters": {"jump_duration": 28, "switch_delay": 0, "roll_duration": 5},
        "action_sequence": (
            [("RIGHT",)] * 16
            + [("RIGHT", "UP")] * 28
            + [("LEFT",)]
            + [("RIGHT", "DOWN")] * 5
            + [("RIGHT",)] * 120
        ),
    }
]


# =========================================================================
# HIST-002: 1-tile pillar overshoot with weapon1 dash (+119px)
# =========================================================================
def get_hist002_fixtures(base_dir: Path) -> Path:
    w, h, gy = 20, 20, 14
    records = []
    for x in range(w):
        records.append((49, x, 17))       # Bottom lethal hazard
    records.append((100, 2, gy - 1))      # Spawn at tile (2, 13)
    records.append((140, 8, gy - 1))      # Flag at tile (8, 13) on 1-tile pillar
    for x in range(1, 5):
        records.append((7, x, gy))        # Start platform: x=1..4 (ends at 159)
    records.append((7, 8, gy))            # 1-tile pillar: x=8 (width 32px: 256..288)

    lmf_path = base_dir / "hist002_pillar1_knife.LMF"
    build_lmf_binary(w, h, records, lmf_path)
    return lmf_path


HIST_002_BROKEN_REF_ACTIONS = (
    [("1",)]
    + [("RIGHT",)] * 16
    + [("RIGHT", "UP")] * 14
    + [("RIGHT", "Z")]                    # +119px dash launches past x=288 to pit
    + [("RIGHT",)] * 50
)

HIST_002_FIXED_REF_ACTIONS = (
    [("RIGHT",)] * 20
    + [("RIGHT", "UP")] * 28              # Precision jump without overshoot dash
)


# =========================================================================
# HIST-003: Impossible parachute gap (576px)
# =========================================================================
HIST_003_BROKEN_SPEC: Dict[str, Any] = {
    "version": "1.0",
    "map_id": "hist003_broken_glide576",
    "training_type": "isolated_skill",
    "metadata": {
        "required_mechanic": "parachute_glide",
        "collapse_entry": "none",
    },
    "allowed_capabilities": ["jump", "parachute"],
    "spawn": {"x": 2, "y": 14},
    "goal": {"x": 20, "y": 14}, # req_distance = 18 * 32 = 576px > verified envelope ~353px
    "tiles": [
        {"id": 7, "x": 1, "y": 15},
        {"id": 7, "x": 2, "y": 15},
        {"id": 7, "x": 20, "y": 15},
    ],
}

HIST_003_FIXED_SPEC: Dict[str, Any] = {
    "version": "1.0",
    "map_id": "hist003_fixed_glide288",
    "training_type": "isolated_skill",
    "metadata": {
        "required_mechanic": "parachute_glide",
        "collapse_entry": "none",
    },
    "allowed_capabilities": ["jump", "parachute"],
    "spawn": {"x": 2, "y": 14},
    "goal": {"x": 11, "y": 14}, # req_distance = 9 * 32 = 288px <= 353px
    "tiles": [
        {"id": 7, "x": 1, "y": 15},
        {"id": 7, "x": 2, "y": 15},
        {"id": 7, "x": 11, "y": 15},
    ],
}


# =========================================================================
# HIST-004: Hole before collapse block prevents mandated walk_contact
# =========================================================================
HIST_004_BROKEN_SPEC: Dict[str, Any] = {
    "version": "1.0",
    "map_id": "hist004_broken_collapse_hole",
    "training_type": "isolated_skill",
    "metadata": {
        "required_mechanic": "collapse_timing",
        "collapse_entry": "walk_contact",
    },
    "allowed_capabilities": ["walk"],
    "spawn": {"x": 2, "y": 14},
    "goal": {"x": 15, "y": 14},
    "tiles": [
        {"id": 7, "x": 1, "y": 15},
        {"id": 7, "x": 2, "y": 15},
        # Missing ground at x=3 (32px pit hole)
        {"id": 124, "x": 4, "y": 15}, # First collapse platform at x=4
        {"id": 7, "x": 15, "y": 15},
    ],
}

HIST_004_FIXED_SPEC: Dict[str, Any] = {
    "version": "1.0",
    "map_id": "hist004_fixed_collapse_jump_allowed",
    "training_type": "isolated_skill",
    "metadata": {
        "required_mechanic": "collapse_timing",
        "collapse_entry": "jump_permitted",
    },
    "allowed_capabilities": ["walk", "jump"], # Jump allowed across 32px hole
    "spawn": {"x": 2, "y": 14},
    "goal": {"x": 15, "y": 14},
    "tiles": [
        {"id": 7, "x": 1, "y": 15},
        {"id": 7, "x": 2, "y": 15},
        # Hole still at x=3, but jump capability allowed
        {"id": 124, "x": 4, "y": 15},
        {"id": 7, "x": 15, "y": 15},
    ],
}


# =========================================================================
# Unified Corpus Registry
# =========================================================================
HISTORICAL_REGRESSION_CORPUS: Dict[str, Dict[str, Any]] = {
    "HIST-001": {
        "defect_id": "HIST-001",
        "name": "knife_required_but_backroll_bypass",
        "description": "맵 설계자가 칼1 전방 돌진을 의도했으나 천장 제약이 없어 점프뒷굴로 날먹 클리어됨",
        "expected_detection_stage": "bypass_verifier",
        "expected_verdict": "KNOWN_BYPASS_FOUND",
        "expected_reason": "flag collision triggered",
        "forbidden_verdicts": [
            "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE",
            "SUITE_INCONCLUSIVE",
            "REFERENCE_FAILED",
            "VERIFIER_ERROR",
        ],
        "must_not_reach_stage": [],
        "fixture_builder": get_hist001_fixtures,
        "reference_actions": HIST_001_REF_ACTIONS,
        "candidate_manifest": HIST_001_CAND_MANIFEST,
        "fixed_expected_verdict": "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE",
    },
    "HIST-002": {
        "defect_id": "HIST-002",
        "name": "pillar1_weapon1_overshoot_fall",
        "description": "1칸 좁은 기둥(32px)에 칼1 돌진(+119px) 사용 시 기둥을 지나쳐 낙사함 (Reference 실패)",
        "expected_detection_stage": "x86_oracle",
        "expected_verdict": "REFERENCE_FAILED",
        "expected_reason": "native_player:offset_0x7c==-1",
        "forbidden_verdicts": ["SUCCESS", "TIMEOUT"],
        "must_not_reach_stage": ["bypass_suite"],
        "fixture_builder": get_hist002_fixtures,
        "reference_actions": HIST_002_BROKEN_REF_ACTIONS,
        "fixed_reference_actions": HIST_002_FIXED_REF_ACTIONS,
        "fixed_expected_verdict": "SUCCESS",
    },
    "HIST-003": {
        "defect_id": "HIST-003",
        "name": "impossible_parachute_gap_576px",
        "description": "단일 점프+낙하산 활강 한계(353px)를 초과하는 576px 갭을 요구하여 물리적으로 도달 불가",
        "expected_detection_stage": "static_validator",
        "expected_verdict": "REJECT",
        "expected_reason": "exceeds verified pure chute envelope",
        "forbidden_verdicts": ["STATIC_OK", "UNKNOWN"],
        "must_not_reach_stage": ["x86_oracle", "bypass_suite"],
        "broken_spec": HIST_003_BROKEN_SPEC,
        "fixed_spec": HIST_003_FIXED_SPEC,
        "fixed_expected_verdict": "STATIC_OK",
    },
    "HIST-004": {
        "defect_id": "HIST-004",
        "name": "collapse_platform_unreachable_hole",
        "description": "붕괴 발판에 walk_contact를 강제하면서 바로 앞에 32px 구멍을 배치해 물리적 접근 불가",
        "expected_detection_stage": "static_validator",
        "expected_verdict": "REJECT",
        "expected_reason": "hole before collapse platform",
        "forbidden_verdicts": ["STATIC_OK", "UNKNOWN"],
        "must_not_reach_stage": ["x86_oracle", "bypass_suite"],
        "broken_spec": HIST_004_BROKEN_SPEC,
        "fixed_spec": HIST_004_FIXED_SPEC,
        "fixed_expected_verdict": "UNKNOWN",
    },
}
