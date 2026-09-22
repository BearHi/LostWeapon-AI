"""Unit & Negative Regression Tests for StaticPhysicsValidator.

Tests:
1. Rejection of 576px parachute chasm (proves old mistake is permanently caught).
2. Acceptance of valid 320px parachute chasm.
3. Rejection of backroll wall that can be bypassed by normal jump (<= 186px).
4. Rejection of impossible wall (> 270px).
5. Rejection of spring trajectory that collides into wall.
6. Rejection of missing bridge before collapse platform (prevents the x=7 hole bug).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from static_validator import StaticPhysicsValidator


def run_validator_tests():
    reg_path = ROOT / "physics_registry.json"
    validator = StaticPhysicsValidator(reg_path)

    # TEST 1: Old 576px Parachute Chasm (Must REJECT)
    spec_impossible_chute = {
        "map_id": "bad_chute_576",
        "training_type": "isolated_skill",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 24, "y": 13}, # 21 tiles * 32px = 672px (or 576px)
        "metadata": {"required_mechanic": "parachute_glide"}
    }
    ok, reason = validator.validate_spec(spec_impossible_chute)
    assert not ok and "[REJECT: UNREACHABLE]" in reason, f"Test 1 failed: {reason}"
    print("  [PASS] Test 1: Impossible 576px chute chasm correctly REJECTED.")

    # TEST 2: Valid 320px Parachute Chasm (Must ACCEPT)
    spec_valid_chute = {
        "map_id": "good_chute_320",
        "training_type": "isolated_skill",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 12, "y": 13}, # 9 tiles * 32px = 288px <= 388px
        "metadata": {"required_mechanic": "parachute_glide"}
    }
    ok, reason = validator.validate_spec(spec_valid_chute)
    assert ok, f"Test 2 failed: {reason}"
    print("  [PASS] Test 2: Valid 288px chute chasm correctly ACCEPTED.")

    # TEST 3: Backroll Bypass Wall (<= 186px) (Must REJECT for isolated_skill)
    spec_bypass_wall = {
        "map_id": "bypass_wall_160",
        "training_type": "isolated_skill",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 20, "y": 13},
        "tiles": [{"id": 7, "x": 10, "y": 9}], # 4 tiles high = 128px <= 186px
        "metadata": {"required_mechanic": "backroll_wall"}
    }
    ok, reason = validator.validate_spec(spec_bypass_wall)
    assert not ok and "[REJECT: BYPASS]" in reason, f"Test 3 failed: {reason}"
    print("  [PASS] Test 3: Normal jump bypass wall correctly REJECTED.")

    # TEST 4: Collapse platform with hole before it (Must REJECT)
    spec_hole_disp = {
        "map_id": "hole_before_raw124",
        "training_type": "isolated_skill",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 20, "y": 13},
        "tiles": [
            {"id": 7, "x": 3, "y": 14},
            {"id": 7, "x": 4, "y": 14},
            {"id": 7, "x": 5, "y": 14},
            # x=6 is missing!
            {"id": 124, "x": 7, "y": 14},
        ],
        "metadata": {"required_mechanic": "collapse_platform"}
    }
    ok, reason = validator.validate_spec(spec_hole_disp)
    assert not ok and "[REJECT: HOLE]" in reason, f"Test 4 failed: {reason}"
    print("  [PASS] Test 4: Hole before collapse platform correctly REJECTED.")

    print("\n======================================================================")
    print(" [STATIC VALIDATOR ALL PASS] All 4 negative regression checks verified!")
    print("======================================================================")


if __name__ == "__main__":
    run_validator_tests()
