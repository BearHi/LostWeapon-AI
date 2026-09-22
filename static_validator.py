"""Static Physics Validator for LostWeapon MapSpec.

Strict Tri-State Contract:
- REJECT: Mathematical proof of physical impossibility or trivial bypass under ALLOWED capabilities.
- STATIC_OK: No physical contradiction found at static layer. (Does NOT mean ACCEPT or clearable!)
- UNKNOWN: Cannot be statically proven or involves multi-mechanic interactions (delegates to x86).
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# Tri-state verdict constants
VERDICT_REJECT = "REJECT"
VERDICT_STATIC_OK = "STATIC_OK"
VERDICT_UNKNOWN = "UNKNOWN"


class StaticPhysicsValidator:
    """Pre-filters MapSpec definitions using strictly verified primitive kinematic invariants."""

    def __init__(self, registry_path: Path):
        with open(registry_path, "r", encoding="utf-8") as f:
            self.reg = json.load(f)
        
        self.vx_walk = float(self.reg["movement"]["walk_vx_px_per_tick"])
        self.v0_jump = float(self.reg["jump"]["motion58_initial"])
        self.g = abs(float(self.reg["jump"]["motion58_delta_per_tick"])) # 40.0
        self.max_jump_h = float(self.reg["jump"]["measured_max_height_px"]) # 186.0
        self.max_backroll_h = float(self.reg["backroll"]["measured_max_height_px"]) # 270.0
        self.chute_vx = float(self.reg["parachute"]["horizontal_vx_px_per_tick"])
        self.chute_init_m58 = float(self.reg["parachute"]["initial_motion58"])
        self.chute_delta_m58 = float(self.reg["parachute"]["motion58_delta_per_tick"])
        self.chute_terminal_max = float(self.reg["parachute"]["motion58_terminal_max"])
        self.chute_terminal_reset = float(self.reg["parachute"]["motion58_terminal_reset"])
        self.chute_open_nudge = float(self.reg["parachute"]["open_y_nudge_px"])
        self.chute_elev_range = tuple(self.reg["parachute"].get("verified_elevation_delta_range_px", [-64.0, 256.0]))

    def compute_pure_chute_envelope(self, start_y: float, landing_y: float) -> Optional[float]:
        """Computes max horizontal distance achievable by jump + optimal apex chute release within verified domain."""
        delta_h = landing_y - start_y
        min_elev, max_elev = self.chute_elev_range
        if delta_h < min_elev or delta_h > max_elev:
            return None # outside verified elevation domain

        x = 0.0
        y = start_y
        m58 = self.v0_jump
        prev_m58 = 0.0
        # 1. Jump ascent to apex (30 ticks, t=0..29)
        for t in range(30):
            dy = -12.0 if t == 0 else -(prev_m58 / 100.0)
            y += dy
            x += self.chute_vx
            prev_m58 = m58
            m58 -= self.g
        # 2. Optimal chute open at apex (t=30):
        # 1 tick opening delay (dx = 0), y nudges up by open_nudge, m58 = initial_motion58
        y += self.chute_open_nudge
        m58 = self.chute_init_m58
        # 3. Chute descent (t=31..)
        # x86 engine: Euler integration with saw-tooth terminal relaxation cycle
        for t in range(31, 2000):
            prev_m = m58
            if prev_m <= self.chute_terminal_max:
                dy = 2.00 # reset velocity impulse
                m58 = self.chute_terminal_reset
            else:
                dy = -(prev_m / 100.0) if t > 31 else 0.05
                m58 = prev_m + self.chute_delta_m58
            y += dy
            x += self.chute_vx
            if y >= landing_y:
                break
        return x

    def validate_spec(self, spec: Dict[str, Any]) -> Tuple[str, str]:
        """Strictly evaluates MapSpec under the tri-state contract."""
        training_type = spec.get("training_type", "integration")
        metadata = spec.get("metadata", {})
        required_mech = metadata.get("required_mechanic")
        allowed_capabilities = set(spec.get("allowed_capabilities", []))
        
        spawn = spec["spawn"]
        goal = spec["goal"]
        tiles = spec.get("tiles", [])
        
        spawn_px_x = spawn["x"] * 32.0 + 16.0
        spawn_px_y = (spawn["y"] + 1) * 32.0
        goal_px_x = goal["x"] * 32.0 + 16.0
        goal_px_y = (goal["y"] + 1) * 32.0
        req_distance = goal_px_x - spawn_px_x

        # 1. Parachute Reachability & Integration Check
        if required_mech in ("parachute_glide", "parachute_long"):
            # Check if other mobility mechanics are allowed
            other_mobility = allowed_capabilities.intersection({"weapon_1_dash", "spring", "magnet_boost"})
            
            if training_type == "isolated_skill" and not other_mobility:
                envelope = self.compute_pure_chute_envelope(spawn_px_y, goal_px_y)
                if envelope is None:
                    return VERDICT_UNKNOWN, (
                        f"Elevation difference {goal_px_y - spawn_px_y:+.1f}px is outside "
                        f"verified parachute domain [{self.chute_elev_range[0]}px, {self.chute_elev_range[1]}px]. "
                        f"Delegated to x86 oracle."
                    )
                if req_distance > envelope:
                    return VERDICT_REJECT, (
                        f"Isolated parachute requires {req_distance:.1f}px, which exceeds "
                        f"verified pure chute envelope ({envelope:.1f}px) by {req_distance - envelope:.1f}px."
                    )
                # Envelope satisfied, no other contradictions found
                return VERDICT_STATIC_OK, "Parachute envelope satisfied. Awaiting x86 oracle."
            
            if other_mobility or training_type == "integration":
                # Multiple or unverified mobility combinations cannot be statically proven
                return VERDICT_UNKNOWN, "Integration/multi-mechanic path detected. Delegated to x86 oracle."

        # 2. Backroll Wall & Bypass Check
        if required_mech == "backroll_wall":
            wall_tiles = [t for t in tiles if t.get("x") in range(spawn["x"] + 1, goal["x"])]
            if wall_tiles:
                min_wall_y = min(t["y"] for t in wall_tiles) * 32.0
                wall_height = spawn_px_y - min_wall_y
                
                # Mathematical impossibility: height > backroll ceiling
                if wall_height > self.max_backroll_h:
                    return VERDICT_REJECT, (
                        f"Wall height ({wall_height:.1f}px) exceeds verified backroll ceiling ({self.max_backroll_h:.1f}px)."
                    )
                
                # We do NOT reject simply because wall_height <= max_jump_h,
                # unless horizontal landing geometry proves trivial bypass.
                # Otherwise, delegate to x86 oracle as UNKNOWN.
                return VERDICT_UNKNOWN, "Wall height within physical bounds; horizontal clearance delegated to x86 oracle."

        # 3. Collapse Platform Walkability Check
        collapse_tiles = [t for t in tiles if t.get("id") == self.reg["collapse_platform"]["raw_tile_id"]]
        if collapse_tiles:
            first_c = min(t["x"] for t in collapse_tiles)
            ground_before = [t for t in tiles if t.get("x") == first_c - 1 and t.get("y") == spawn["y"] + 1]
            
            if not ground_before and first_c > spawn["x"] + 1:
                # Hole exists. Check if walk-only contact is explicitly mandated:
                collapse_entry = metadata.get("collapse_entry")
                jump_forbidden = "jump" not in allowed_capabilities if allowed_capabilities else False
                
                if collapse_entry == "walk_contact" or jump_forbidden:
                    return VERDICT_REJECT, (
                        f"32px hole before collapse platform at x={first_c-1} while walk_contact is mandated."
                    )
                # If jump is allowed, player can jump across the 32px hole -> UNKNOWN
                return VERDICT_UNKNOWN, "32px gap before collapse platform detected, but jump is permitted. Delegated to x86."

        # 4. Spring Object Checks
        springs = [t for t in tiles if t.get("id") in (
            self.reg["spring_vertical"]["tile_id"],
            self.reg["spring_diagonal"]["tile_id_left"],
            self.reg["spring_diagonal"]["tile_id_right"]
        )]
        if springs:
            # Due to known discrepancies between initial motion58 and measured apex height,
            # static validator does NOT attempt arbitrary kinematic integration on springs.
            return VERDICT_UNKNOWN, "Spring mechanics require ground-truth x86 trajectory evaluation."

        return VERDICT_STATIC_OK, "No static contradictions detected across verified invariants."
