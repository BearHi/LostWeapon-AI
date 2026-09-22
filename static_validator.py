"""Static Physics Validator for LostWeapon MapSpec.

Computes physical reachability envelopes in real-time using primitive constants
from physics_registry.json. Performs cheap, instant pre-filtering before x86 simulation:
- Rejects physically impossible maps (e.g., chasm > parachute envelope).
- Rejects trivial bypass maps for isolated_skill training (e.g., wall <= normal jump).
- Rejects geometry collision bugs (e.g., spring apex vs wall face collision).
"""
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple


class StaticPhysicsValidator:
    """Pre-filters MapSpec definitions using kinematic difference equations."""

    def __init__(self, registry_path: Path):
        with open(registry_path, "r", encoding="utf-8") as f:
            self.reg = json.load(f)
        
        # Load primitive constants
        self.vx_walk = float(self.reg["movement"]["walk_vx_px_per_tick"])
        self.v0_jump = float(self.reg["jump"]["motion58_initial"])
        self.g = abs(float(self.reg["jump"]["motion58_delta_per_tick"])) # 40.0
        self.max_jump_h = float(self.reg["jump"]["measured_max_height_px"]) # 186.0
        
        self.v0_backroll = float(self.reg["backroll"]["motion58_reload"]) # 760.0
        self.max_backroll_h = float(self.reg["backroll"]["measured_max_height_px"]) # 270.0
        
        self.chute_vx = float(self.reg["parachute"]["horizontal_vx_px_per_tick"]) # 4.0
        self.chute_vy = float(self.reg["parachute"]["vertical_fall_px_per_tick"]) # 2.9
        
        self.w1_dx = float(self.reg["weapon_1"]["horizontal_displacement_px"]) # 119.0
        self.spring_v0 = float(self.reg["spring_vertical"]["motion58_on_contact"]) # 2000.0
        self.spring_max_h = float(self.reg["spring_vertical"]["measured_max_height_px"]) # 352.0

    def compute_pure_chute_envelope(self, start_y: float, landing_y: float) -> float:
        """Computes max horizontal distance achievable by jump + optimal chute release."""
        # Jump apex: t_apex = v0 / g = 1160 / 40 = 29 ticks
        # At apex, natural fall starts: vy(d) = 0.4 * d.
        # Optimal chute release when natural fall reaches chute_vy: d = 2.9 / 0.4 = 7.25 -> 7 ticks.
        # Total airtime before chute: 29 + 7 = 36 ticks.
        # Apex height delta: sum((1160 - 40*k)/100 for k in range(29)) = 174.0 px (+frame bonus ~186px).
        # Fall distance during natural fall (7 ticks): sum(40*k/100 for k in range(7)) = 8.4 px.
        # Height at chute open: landing_y - 186.0 + 8.4 = landing_y - 177.6 px.
        # Remaining descent to landing_y: 177.6 px.
        # Chute ticks: 177.6 / chute_vy = 177.6 / 2.9 = 61.2 ticks.
        # Total ticks: 36 (pre-chute) + 61.2 (chute) = 97.2 ticks.
        # Max horizontal reach: 97.2 * vx_walk = ~388.8 px.
        apex_h = self.max_jump_h
        nat_fall_ticks = round(self.chute_vy / (self.g / 100.0)) # ~7 ticks
        nat_fall_dist = sum((self.g * k / 100.0) for k in range(nat_fall_ticks)) # 8.4 px
        
        remaining_descent = (landing_y - start_y) + apex_h - nat_fall_dist
        if remaining_descent < 0:
            chute_ticks = 0.0
        else:
            chute_ticks = remaining_descent / self.chute_vy
            
        total_ticks = (self.v0_jump / self.g) + nat_fall_ticks + chute_ticks
        return total_ticks * self.chute_vx

    def validate_spec(self, spec: Dict[str, Any]) -> Tuple[bool, str]:
        """Validates a MapSpec dictionary against physics registry bounds."""
        training_type = spec.get("training_type", "integration")
        metadata = spec.get("metadata", {})
        required_mech = metadata.get("required_mechanic")
        
        spawn = spec["spawn"]
        goal = spec["goal"]
        tiles = spec.get("tiles", [])
        
        spawn_px_x = spawn["x"] * 32.0 + 16.0
        spawn_px_y = (spawn["y"] + 1) * 32.0
        goal_px_x = goal["x"] * 32.0 + 16.0
        goal_px_y = (goal["y"] + 1) * 32.0

        # 1. Parachute Reachability Check
        if required_mech in ("parachute_glide", "parachute_long"):
            envelope = self.compute_pure_chute_envelope(spawn_px_y, goal_px_y)
            required_dist = goal_px_x - spawn_px_x
            if required_dist > envelope:
                return False, (f"[REJECT: UNREACHABLE] Required distance ({required_dist:.1f}px) "
                               f"exceeds calculated parachute envelope ({envelope:.1f}px) by {required_dist - envelope:.1f}px!")
            if training_type == "isolated_skill" and required_dist <= self.max_jump_h:
                return False, (f"[REJECT: BYPASS] Required distance ({required_dist:.1f}px) "
                               f"<= normal jump ({self.max_jump_h:.1f}px), bypassable without chute!")

        # 2. Backroll Wall Check
        if required_mech == "backroll_wall":
            wall_tiles = [t for t in tiles if t.get("x") in range(spawn["x"] + 1, goal["x"])]
            if wall_tiles:
                min_wall_y = min(t["y"] for t in wall_tiles) * 32.0
                wall_height = spawn_px_y - min_wall_y
                if wall_height > self.max_backroll_h:
                    return False, (f"[REJECT: IMPOSSIBLE] Wall height ({wall_height:.1f}px) "
                                   f"exceeds backroll ceiling ({self.max_backroll_h:.1f}px)!")
                if training_type == "isolated_skill" and wall_height <= self.max_jump_h:
                    return False, (f"[REJECT: BYPASS] Wall height ({wall_height:.1f}px) "
                                   f"<= normal jump ({self.max_jump_h:.1f}px), bypassable with normal jump!")

        # 3. Vertical Spring Trajectory vs Wall Collision Check
        springs = [t for t in tiles if t.get("id") == self.reg["spring_vertical"]["tile_id"]]
        if springs:
            spring_x_px = springs[0]["x"] * 32.0 + 16.0
            wall_tiles = [t for t in tiles if t.get("x") > springs[0]["x"] and t.get("x") < goal["x"]]
            if wall_tiles:
                wall_x_px = min(t["x"] for t in wall_tiles) * 32.0
                min_wall_y = min(t["y"] for t in wall_tiles) * 32.0
                wall_h = spawn_px_y - min_wall_y
                
                # Discriminant for h(t) = 20*t - 0.2*t^2 = wall_h
                disc = 400.0 - 0.8 * wall_h
                if disc < 0:
                    return False, f"[REJECT: IMPOSSIBLE] Wall height ({wall_h:.1f}px) exceeds spring ceiling ({self.spring_max_h:.1f}px)!"
                t_clear = (20.0 - math.sqrt(disc)) / 0.4
                t_horiz = (wall_x_px - spring_x_px) / self.vx_walk
                if t_horiz < t_clear:
                    return False, (f"[REJECT: COLLISION] Player collides into wall at t={t_horiz:.1f} ticks "
                                   f"before reaching clearance height at t={t_clear:.1f} ticks!")

        # 4. Collapse Platform (raw124) Walkability
        collapse_tiles = [t for t in tiles if t.get("id") == self.reg["collapse_platform"]["raw_tile_id"]]
        if collapse_tiles:
            first_c = min(t["x"] for t in collapse_tiles)
            ground_before = [t for t in tiles if t.get("x") == first_c - 1 and t.get("y") == spawn["y"] + 1]
            if not ground_before and first_c > spawn["x"] + 1:
                return False, f"[REJECT: HOLE] 1-tile gap detected before collapse platform at x={first_c-1}! Player falls into void before stepping."

        return True, "[ACCEPT: STATIC_PASS] Map satisfies all kinematic constraints."
