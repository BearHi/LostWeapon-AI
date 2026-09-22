"""regression_corpus.py - Historical Defect Regression Corpus Registry.

Defines the canonical registry of past project failures and design defects.
Each entry strictly declares:
  - defect_id: Unique identifier (HIST-001 ~ HIST-004)
  - name: Machine-readable identifier
  - description: Root cause and historical defect context
  - expected_detection_stage: The earliest pipeline stage that MUST catch this defect (ASSERTION ONLY)
  - expected_verdict: The expected verdict string from that stage
  - expected_reason: Required substring in reason / evidence string
  - forbidden_verdicts: Verdicts that must NEVER be returned
  - must_not_reach_stage: Downstream stages that must NEVER be executed
  - golden_broken_path: Path to immutable broken golden artifact
  - golden_broken_sha256: Pinned SHA-256 hash of broken artifact
  - golden_fixed_path: Path to immutable fixed golden artifact
  - golden_fixed_sha256: Pinned SHA-256 hash of fixed artifact
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parent
GOLDEN_DIR = ROOT / "golden_fixtures"


def verify_file_sha256(path: Path, expected_sha256: str) -> bool:
    """Verify that a golden fixture file has not been altered."""
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    return actual == expected_sha256


# Action Schedules for HIST-001
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

# Action Schedules for HIST-002
HIST_002_BROKEN_REF_ACTIONS = (
    [("1",)]
    + [("RIGHT",)] * 16
    + [("RIGHT", "UP")] * 14
    + [("RIGHT", "Z")]                    # +119px dash launches past 32px pillar (x=8) to lethal pit
    + [("RIGHT",)] * 50
)

HIST_002_FIXED_REF_ACTIONS = (
    [("RIGHT",)] * 20
    + [("RIGHT", "UP")] * 28              # Precision jump without overshoot dash, lands directly on x=8
)


HISTORICAL_REGRESSION_CORPUS: Dict[str, Dict[str, Any]] = {
    "HIST-001": {
        "defect_id": "HIST-001",
        "name": "knife_required_but_backroll_bypass",
        "description": "칼1 돌진 필도를 의도했으나 천장 제약이 없어 점프뒷굴로 날먹 클리어됨",
        "expected_detection_stage": "bypass_verifier",
        "expected_verdict": "KNOWN_BYPASS_FOUND",
        "expected_reason": "client_collision_triggered",
        "forbidden_verdicts": [
            "NO_KNOWN_BYPASS_FOUND_IN_TESTED_SUITE",
            "SUITE_INCONCLUSIVE",
            "REFERENCE_FAILED",
            "VERIFIER_ERROR",
        ],
        "must_not_reach_stage": [],
        "type": "lmf",
        "golden_broken_path": GOLDEN_DIR / "hist001_broken_open_gap.LMF",
        "golden_broken_sha256": "1c62c57d3b26fc9bc6d385ea5f332d1017ea041088af7f2b973acbdcc3cddbd0",
        "golden_fixed_path": GOLDEN_DIR / "hist001_fixed_ceiling_gap.LMF",
        "golden_fixed_sha256": "b25b51728db804cae371ddf5363fe164dc4c99fc780452700b73aa98e9237b62",
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
        "type": "lmf",
        "golden_broken_path": GOLDEN_DIR / "hist002_pillar1_knife.LMF",
        "golden_broken_sha256": "57708bc9d5b2e53dc520d7ca1f67fb7daffd0f12dac45b62a0c4304c88f453f0",
        "golden_fixed_path": GOLDEN_DIR / "hist002_pillar1_knife.LMF",
        "golden_fixed_sha256": "57708bc9d5b2e53dc520d7ca1f67fb7daffd0f12dac45b62a0c4304c88f453f0",
        "reference_actions": HIST_002_BROKEN_REF_ACTIONS,
        "fixed_reference_actions": HIST_002_FIXED_REF_ACTIONS,
        "fixed_expected_verdict": "SUCCESS",
    },
    "HIST-003": {
        "defect_id": "HIST-003",
        "name": "impossible_parachute_gap_576px",
        "description": "단일 점프+낙하산 활강 한계(388.97px)를 초과하는 576px 갭을 요구하여 물리적으로 도달 불가",
        "expected_detection_stage": "static_validator",
        "expected_verdict": "REJECT",
        "expected_reason": "exceeds verified pure chute envelope",
        "forbidden_verdicts": ["STATIC_OK", "UNKNOWN"],
        "must_not_reach_stage": ["x86_oracle", "bypass_suite"],
        "type": "mapspec",
        "golden_broken_path": GOLDEN_DIR / "hist003_broken_glide576.json",
        "golden_broken_sha256": "f820663a3b57eb9302a320f9e39464d6aa5fb28ef02828b7825975bb3fe076f8",
        "golden_fixed_path": GOLDEN_DIR / "hist003_fixed_glide288.json",
        "golden_fixed_sha256": "28b18233662a8bc90a6d3283700c7d9bf7a093fd30e7d324e3e92b7c5724ec21",
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
        "type": "mapspec",
        "golden_broken_path": GOLDEN_DIR / "hist004_broken_collapse_hole.json",
        "golden_broken_sha256": "afaecec5540bc8395d37220194cfe774451c955ee876386aec833249071f395d",
        "golden_fixed_path": GOLDEN_DIR / "hist004_fixed_collapse_jump_allowed.json",
        "golden_fixed_sha256": "bcab2c6e37f38a7513838b1fc85e37410f35334d8e8d3fecddb1b96f879e73ef",
        "fixed_expected_verdict": "UNKNOWN",
    },
}
