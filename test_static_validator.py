"""Regression Test Suite for StaticPhysicsValidator Tri-State Contract.

Verifies the 7 mandatory cases:
1. isolated jump+parachute, required distance > proven envelope -> REJECT
2. isolated jump+parachute, required distance <= proven envelope -> STATIC_OK
3. long-distance integration + weapon/magnet allowed -> UNKNOWN
4. 32px hole + walk-only collapse contact -> REJECT
5. 32px hole + jump allowed -> UNKNOWN (NOT REJECT!)
6. low wall where horizontal geometry bypass cannot be statically proven -> UNKNOWN
7. spring unverified combination -> UNKNOWN (delegated to x86)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from static_validator import (
    StaticPhysicsValidator,
    VERDICT_REJECT,
    VERDICT_STATIC_OK,
    VERDICT_UNKNOWN,
)


def run_tristate_tests():
    reg_path = ROOT / "physics_registry.json"
    validator = StaticPhysicsValidator(reg_path)

    # 1. isolated jump+parachute, required distance > envelope -> REJECT
    case1 = {
        "map_id": "chute_impossible_isolated",
        "training_type": "isolated_skill",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 24, "y": 13}, # ~672px >> 388px
        "allowed_capabilities": ["jump", "parachute_glide"],
        "metadata": {"required_mechanic": "parachute_glide"}
    }
    v1, r1 = validator.validate_spec(case1)
    assert v1 == VERDICT_REJECT, f"Case 1 failed: expected REJECT, got {v1} ({r1})"
    print(f"  [PASS] Case 1: Isolated impossible chute -> {v1}")

    # 2. isolated jump+parachute, required distance <= envelope -> STATIC_OK
    case2 = {
        "map_id": "chute_valid_envelope",
        "training_type": "isolated_skill",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 12, "y": 13}, # 288px <= 388px
        "allowed_capabilities": ["jump", "parachute_glide"],
        "metadata": {"required_mechanic": "parachute_glide"}
    }
    v2, r2 = validator.validate_spec(case2)
    assert v2 == VERDICT_STATIC_OK, f"Case 2 failed: expected STATIC_OK, got {v2} ({r2})"
    assert "ACCEPT" not in v2 and "PASS" not in v2, "Forbidden term in verdict!"
    print(f"  [PASS] Case 2: Isolated valid envelope -> {v2}")

    # 3. long-distance integration + weapon/magnet allowed -> UNKNOWN
    case3 = {
        "map_id": "long_distance_integration",
        "training_type": "integration",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 25, "y": 13}, # ~700px
        "allowed_capabilities": ["jump", "parachute_glide", "weapon_1_dash", "magnet_boost"],
        "metadata": {"required_mechanic": "parachute_glide"}
    }
    v3, r3 = validator.validate_spec(case3)
    assert v3 == VERDICT_UNKNOWN, f"Case 3 failed: expected UNKNOWN, got {v3} ({r3})"
    print(f"  [PASS] Case 3: Long-distance multi-mechanic integration -> {v3}")

    # 4. 32px hole + walk-only collapse contact -> REJECT
    case4 = {
        "map_id": "hole_walk_contact",
        "training_type": "isolated_skill",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 20, "y": 13},
        "tiles": [
            {"id": 7, "x": 3, "y": 14},
            {"id": 7, "x": 4, "y": 14},
            # x=5 hole
            {"id": 124, "x": 6, "y": 14},
        ],
        "metadata": {"required_mechanic": "collapse_platform", "collapse_entry": "walk_contact"}
    }
    v4, r4 = validator.validate_spec(case4)
    assert v4 == VERDICT_REJECT, f"Case 4 failed: expected REJECT, got {v4} ({r4})"
    print(f"  [PASS] Case 4: 32px hole + walk_contact mandated -> {v4}")

    # 5. 32px hole + jump allowed -> UNKNOWN (NOT REJECT!)
    case5 = {
        "map_id": "hole_jump_allowed",
        "training_type": "isolated_skill",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 20, "y": 13},
        "tiles": [
            {"id": 7, "x": 3, "y": 14},
            {"id": 7, "x": 4, "y": 14},
            # x=5 hole
            {"id": 124, "x": 6, "y": 14},
        ],
        "allowed_capabilities": ["jump", "collapse_platform"],
        "metadata": {"required_mechanic": "collapse_platform"} # No walk_contact mandate!
    }
    v5, r5 = validator.validate_spec(case5)
    assert v5 == VERDICT_UNKNOWN, f"Case 5 failed: expected UNKNOWN, got {v5} ({r5})"
    print(f"  [PASS] Case 5: 32px hole with jump permitted -> {v5} (not rejected!)")

    # 6. low wall where horizontal geometry bypass cannot be statically proven -> UNKNOWN
    case6 = {
        "map_id": "low_wall_unproven_geometry",
        "training_type": "isolated_skill",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 20, "y": 13},
        "tiles": [{"id": 7, "x": 10, "y": 9}], # 128px high (<= 186px), but trajectory unproven
        "metadata": {"required_mechanic": "backroll_wall"}
    }
    v6, r6 = validator.validate_spec(case6)
    assert v6 == VERDICT_UNKNOWN, f"Case 6 failed: expected UNKNOWN, got {v6} ({r6})"
    print(f"  [PASS] Case 6: Low wall with unproven landing geometry -> {v6}")

    # 7. spring unverified combination -> UNKNOWN (delegated to x86)
    case7 = {
        "map_id": "spring_combination",
        "training_type": "isolated_skill",
        "spawn": {"x": 3, "y": 13},
        "goal": {"x": 20, "y": 13},
        "tiles": [{"id": 4, "x": 6, "y": 13}],
        "metadata": {"required_mechanic": "spring_high"}
    }
    v7, r7 = validator.validate_spec(case7)
    assert v7 == VERDICT_UNKNOWN, f"Case 7 failed: expected UNKNOWN, got {v7} ({r7})"
    print(f"  [PASS] Case 7: Spring kinematics unproven statically -> {v7}")

    print("\n======================================================================")
    print(" [TRI-STATE CONTRACT 100% VERIFIED] All 7 cases strictly passed!")
    print("======================================================================")


if __name__ == "__main__":
    run_tristate_tests()
