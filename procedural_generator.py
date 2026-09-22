"""procedural_generator.py - LLM-Free Deterministic Procedural Training Map Generator.

Generates parametric MapSpec instances, intended reference solution action sequences,
and anti-bypass candidate manifests based directly on the mathematical physics invariants
in LOSTWEAPON_PHYSICS_MASTER_RULES.md.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
HARNESS_DIR = ROOT / "native_harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from family_generators import (
    DelayedBackrollFamily,
    NormalJumpWalkFamily,
    ParachuteFamily,
    Weapon1MobilityFamily,
    Weapon4BrakeFamily,
)
from map_compiler import MapSpec


@dataclass
class GeneratedCandidate:
    """A procedurally generated candidate map with paired verification metadata."""
    archetype_id: str
    variation_id: str
    spec: MapSpec
    reference_actions: List[Tuple[str, ...]]
    bypass_manifest: List[Dict[str, Any]] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    snapshot_override: Optional[str] = None

    def compute_spec_sha256(self) -> str:
        """Deterministic hash of the MapSpec JSON representation."""
        spec_dict = {
            "map_id": self.spec.map_id,
            "width": self.spec.width,
            "height": self.spec.height,
            "training_type": self.spec.training_type,
            "spawn": self.spec.spawn,
            "goal": self.spec.goal,
            "tiles": sorted(self.spec.tiles, key=lambda t: (t["x"], t["y"], t["id"])),
            "lava_y": self.spec.lava_y,
            "metadata": self.spec.metadata,
        }
        canonical = json.dumps(spec_dict, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class BaseArchetype(ABC):
    """Abstract base class for physics training map archetypes."""
    archetype_id: str = "base"
    name: str = "Base Archetype"
    description: str = ""
    default_snapshot: str = "hun6_live.zip"

    @abstractmethod
    def parameter_grid(self) -> List[Dict[str, Any]]:
        """Return all discrete parameter combinations for grid sweep mode."""
        raise NotImplementedError

    @abstractmethod
    def sample_parameters(self, rng: random.Random) -> Dict[str, Any]:
        """Sample a single parameter combination within physical bounds."""
        raise NotImplementedError

    @abstractmethod
    def build_candidate(self, params: Dict[str, Any], variation_index: int) -> GeneratedCandidate:
        """Construct the complete candidate from the given parameters."""
        raise NotImplementedError

    def generate_candidates(
        self,
        mode: str = "grid",
        count: Optional[int] = None,
        seed: int = 42,
    ) -> Iterator[GeneratedCandidate]:
        """Generate candidates in either 'grid' or 'sample' mode."""
        if mode == "grid":
            grid = self.parameter_grid()
            if count is not None:
                grid = grid[:count]
            for idx, params in enumerate(grid):
                yield self.build_candidate(params, idx)
        elif mode == "sample":
            rng = random.Random(seed)
            target_count = count if count is not None else 10
            for idx in range(target_count):
                params = self.sample_parameters(rng)
                yield self.build_candidate(params, idx)
        else:
            raise ValueError(f"Unknown mode: {mode}. Must be 'grid' or 'sample'.")


# =============================================================================
# Archetype 1: Basic Gap Jump (기본 수평 갭 점프)
# Physics: Normal jump reach <= 160px (5 tiles). Apex 186px.
# =============================================================================
class Arch01BasicGap(BaseArchetype):
    archetype_id = "ARCH_01_BASIC_GAP"
    name = "기본 수평 갭 점프"
    description = "일반 보행 및 점프로 건너는 2~4칸 갭 지형"

    def parameter_grid(self) -> List[Dict[str, Any]]:
        combos = []
        for gap in (2, 3, 4):
            for run in (6, 8):
                combos.append({"gap_tiles": gap, "run_tiles": run, "land_tiles": 12})
        return combos

    def sample_parameters(self, rng: random.Random) -> Dict[str, Any]:
        return {
            "gap_tiles": rng.choice([2, 3, 4]),
            "run_tiles": rng.randint(6, 9),
            "land_tiles": rng.randint(10, 14),
        }

    def build_candidate(self, params: Dict[str, Any], variation_index: int) -> GeneratedCandidate:
        gap = params["gap_tiles"]
        run = params["run_tiles"]
        land = params["land_tiles"]

        w = 1 + run + gap + land + 2
        h = 20
        gy = 14
        lava_y = 17

        tiles: List[Dict[str, Any]] = []
        # Run platform
        for x in range(1, 1 + run):
            tiles.append({"id": 7, "x": x, "y": gy})
        # Landing platform
        land_start = 1 + run + gap
        for x in range(land_start, land_start + land):
            tiles.append({"id": 7, "x": x, "y": gy})

        spawn = {"x": 3, "y": gy - 1}
        goal = {"x": land_start + land - 3, "y": gy - 1}

        map_id = f"arch01_gap{gap}_run{run}_v{variation_index:03d}"
        spec = MapSpec(
            map_id=map_id,
            width=w,
            height=h,
            training_type="isolated_skill",
            spawn=spawn,
            goal=goal,
            tiles=tiles,
            lava_y=lava_y,
            metadata={
                "archetype": self.archetype_id,
                "required_mechanic": "normal_jump_walk",
                "gap_tiles": gap,
                "gap_px": gap * 32.0,
            },
        )

        # Reference solution: walk to edge, jump across, walk to goal
        walk_to_edge = max(8, (run - 3) * 8)
        jump_ticks = 14 if gap == 2 else (20 if gap == 3 else 28)
        walk_to_goal = max(60, (land - 2) * 8 + 24)
        ref_actions: List[Tuple[str, ...]] = (
            [("RIGHT",)] * walk_to_edge
            + [("RIGHT", "UP")] * jump_ticks
            + [("RIGHT",)] * walk_to_goal
        )

        return GeneratedCandidate(
            archetype_id=self.archetype_id,
            variation_id=map_id,
            spec=spec,
            reference_actions=ref_actions,
            bypass_manifest=[],  # Baseline mechanic, no bypass needed
            parameters=params,
            snapshot_override=self.default_snapshot,
        )


# =============================================================================
# Archetype 2: Step-Up Ledge (수직 단차 등반)
# Physics: Normal jump max height = 186.0px (5.81 tiles). Step height 1~4 tiles.
# =============================================================================
class Arch02StepUp(BaseArchetype):
    archetype_id = "ARCH_02_STEP_UP"
    name = "수직 단차 등반"
    description = "일반 점프로 뛰어오르는 1~4칸(32~128px) 높이 단차 지형"

    def parameter_grid(self) -> List[Dict[str, Any]]:
        combos = []
        for step in (1, 2, 3, 4):
            for run in (6, 8):
                combos.append({"step_tiles": step, "run_tiles": run, "land_tiles": 12})
        return combos

    def sample_parameters(self, rng: random.Random) -> Dict[str, Any]:
        return {
            "step_tiles": rng.choice([1, 2, 3, 4]),
            "run_tiles": rng.randint(6, 8),
            "land_tiles": rng.randint(10, 14),
        }

    def build_candidate(self, params: Dict[str, Any], variation_index: int) -> GeneratedCandidate:
        step = params["step_tiles"]
        run = params["run_tiles"]
        land = params["land_tiles"]

        w = 1 + run + land + 2
        h = 20
        gy = 14
        step_y = gy - step
        lava_y = 17

        tiles: List[Dict[str, Any]] = []
        # Lower ground
        for x in range(1, 1 + run):
            tiles.append({"id": 7, "x": x, "y": gy})
        # Higher step-up platform
        step_start = 1 + run
        for x in range(step_start, step_start + land):
            tiles.append({"id": 7, "x": x, "y": step_y})

        spawn = {"x": 3, "y": gy - 1}
        goal = {"x": step_start + land - 3, "y": step_y - 1}

        map_id = f"arch02_step{step}_run{run}_v{variation_index:03d}"
        spec = MapSpec(
            map_id=map_id,
            width=w,
            height=h,
            training_type="isolated_skill",
            spawn=spawn,
            goal=goal,
            tiles=tiles,
            lava_y=lava_y,
            metadata={
                "archetype": self.archetype_id,
                "required_mechanic": "normal_jump_stepup",
                "step_tiles": step,
                "step_px": step * 32.0,
            },
        )

        walk_to_step = max(8, (run - 3) * 8)
        jump_ticks = 20 if step <= 2 else 28
        walk_to_goal = max(60, (land - 2) * 8 + 24)
        ref_actions: List[Tuple[str, ...]] = (
            [("RIGHT",)] * walk_to_step
            + [("RIGHT", "UP")] * jump_ticks
            + [("RIGHT",)] * walk_to_goal
        )

        return GeneratedCandidate(
            archetype_id=self.archetype_id,
            variation_id=map_id,
            spec=spec,
            reference_actions=ref_actions,
            bypass_manifest=[],
            parameters=params,
            snapshot_override=self.default_snapshot,
        )


# =============================================================================
# Archetype 3: Backroll High Wall (점프뒷굴 고벽 등반)
# Physics: Wall height 6~8 tiles (192~256px) > max normal jump (186px).
# Anti-bypass: Normal jump MUST fail to climb wall.
# =============================================================================
class Arch03BackrollHighWall(BaseArchetype):
    archetype_id = "ARCH_03_BACKROLL_WALL"
    name = "점프뒷굴 고벽 등반"
    description = "일반 점프(186px) 불가, 점프뒷굴(270px) 필수인 6~8칸 고벽 지형"

    def parameter_grid(self) -> List[Dict[str, Any]]:
        combos = []
        for wall_h in (6, 7):
            for run in (6, 8):
                combos.append({"wall_tiles": wall_h, "run_tiles": run, "land_tiles": 12})
        return combos

    def sample_parameters(self, rng: random.Random) -> Dict[str, Any]:
        return {
            "wall_tiles": rng.choice([6, 7]),
            "run_tiles": rng.randint(6, 8),
            "land_tiles": rng.randint(10, 14),
        }

    def build_candidate(self, params: Dict[str, Any], variation_index: int) -> GeneratedCandidate:
        wall_h = params["wall_tiles"]
        run = params["run_tiles"]
        land = params["land_tiles"]

        w = 1 + run + land + 2
        h = 20
        gy = 14
        wall_top_y = gy - wall_h
        lava_y = 17

        tiles: List[Dict[str, Any]] = []
        # Lower ground
        for x in range(1, 1 + run):
            tiles.append({"id": 7, "x": x, "y": gy})
        # High wall platform
        wall_start = 1 + run
        for x in range(wall_start, wall_start + land):
            for y in range(wall_top_y, gy + 1):
                tiles.append({"id": 7, "x": x, "y": y})

        spawn = {"x": 3, "y": gy - 1}
        goal = {"x": wall_start + land - 3, "y": wall_top_y - 1}

        map_id = f"arch03_broll_wall{wall_h}_v{variation_index:03d}"
        spec = MapSpec(
            map_id=map_id,
            width=w,
            height=h,
            training_type="isolated_skill",
            spawn=spawn,
            goal=goal,
            tiles=tiles,
            lava_y=lava_y,
            metadata={
                "archetype": self.archetype_id,
                "required_mechanic": "backroll_wall",
                "wall_tiles": wall_h,
                "wall_height_px": wall_h * 32.0,
            },
        )

        # Reference solution: Walk, jump, switch face, backroll up onto wall
        walk_ticks = max(8, (run - 3) * 8)
        ref_actions: List[Tuple[str, ...]] = (
            [("RIGHT",)] * walk_ticks
            + [("RIGHT", "UP")] * 28
            + [("LEFT",)]
            + [("RIGHT", "DOWN")] * 5
            + [("RIGHT",)] * 100
        )

        # Anti-bypass candidates: Normal jump must fail on wall_h >= 6 (> 186px)
        njw_fam = NormalJumpWalkFamily()
        cand_manifest = njw_fam.generate_manifest(
            walk_ticks_list=[walk_ticks],
            jump_ticks_list=[14, 20, 28],
            post_walk_ticks=50,
        )

        return GeneratedCandidate(
            archetype_id=self.archetype_id,
            variation_id=map_id,
            spec=spec,
            reference_actions=ref_actions,
            bypass_manifest=cand_manifest,
            parameters=params,
            snapshot_override=self.default_snapshot,
        )


# =============================================================================
# Archetype 4: Aerial Knife Dash with Ceiling Overhang (공중 칼1 돌진)
# Physics: Low ceiling blocks high backroll; shallow jump + Knife 1 dash (+119px) clears.
# Anti-bypass: Backroll hits ceiling overhang and dies.
# =============================================================================
class Arch04KnifeDash(BaseArchetype):
    archetype_id = "ARCH_04_KNIFE_DASH"
    name = "천장 차단 공중 칼1 돌진"
    description = "천장 오버행으로 뒷굴 차단, 1번칼 전방 돌진(+119px) 필수 지형"

    def parameter_grid(self) -> List[Dict[str, Any]]:
        combos = []
        for gap in (3, 4):
            for ceil_y in (7, 8):
                combos.append({"gap_tiles": gap, "ceiling_y": ceil_y, "run_tiles": 6, "land_tiles": 12})
        return combos

    def sample_parameters(self, rng: random.Random) -> Dict[str, Any]:
        return {
            "gap_tiles": rng.choice([3, 4]),
            "ceiling_y": rng.choice([7, 8]),
            "run_tiles": 6,
            "land_tiles": 12,
        }

    def build_candidate(self, params: Dict[str, Any], variation_index: int) -> GeneratedCandidate:
        gap = params["gap_tiles"]
        ceil_y = params["ceiling_y"]
        run = params["run_tiles"]
        land = params["land_tiles"]

        w = 1 + run + gap + land + 2
        h = 20
        gy = 14
        step_up_y = 11  # 3 tiles (96px) step-up
        lava_y = 17

        tiles: List[Dict[str, Any]] = []
        # Start platform: x=1..run, y=14
        for x in range(1, 1 + run):
            tiles.append({"id": 7, "x": x, "y": gy})

        # Landing platform: step-up at y=11
        land_start = 1 + run + gap
        for x in range(land_start, land_start + land):
            tiles.append({"id": 7, "x": x, "y": step_up_y})

        # Ceiling overhang over gap and landing: y=0..ceil_y
        for y in range(0, ceil_y + 1):
            for x in range(run + 1, land_start + land):
                tiles.append({"id": 7, "x": x, "y": y})

        spawn = {"x": 3, "y": gy - 1}
        goal = {"x": land_start + land - 3, "y": step_up_y - 1}

        map_id = f"arch04_knife_g{gap}_c{ceil_y}_v{variation_index:03d}"
        spec = MapSpec(
            map_id=map_id,
            width=w,
            height=h,
            training_type="isolated_skill",
            spawn=spawn,
            goal=goal,
            tiles=tiles,
            lava_y=lava_y,
            metadata={
                "archetype": self.archetype_id,
                "required_mechanic": "weapon_1_dash",
                "gap_tiles": gap,
                "ceiling_y": ceil_y,
            },
        )

        # Reference solution: Equip 1, walk, shallow jump (14 ticks), slash Z (+119px), walk
        ref_actions: List[Tuple[str, ...]] = (
            [("1",)]
            + [("RIGHT",)] * 16
            + [("RIGHT", "UP")] * 14
            + [("RIGHT", "Z")]
            + [("RIGHT",)] * 100
        )

        # Anti-bypass candidate: Delayed backroll will hit ceiling and fall into lava
        backroll_fam = DelayedBackrollFamily()
        cand_manifest = backroll_fam.generate_manifest(
            jump_durs=[28],
            switch_delays=[0],
            roll_durs=[5],
            walk_ticks=16,
            post_roll_walk=120,
        )

        return GeneratedCandidate(
            archetype_id=self.archetype_id,
            variation_id=map_id,
            spec=spec,
            reference_actions=ref_actions,
            bypass_manifest=cand_manifest,
            parameters=params,
            snapshot_override=self.default_snapshot,
        )


# =============================================================================
# Archetype 5: Narrow 1-Tile Pillar Landing (1칸 기둥 핀포인트 제동)
# Physics: 1-tile pillar (32px) over lethal hazard.
# Anti-bypass: Weapon 1 dash (+119px) overshoots into void; requires brake (0px delta).
# =============================================================================
class Arch05PillarBrake(BaseArchetype):
    archetype_id = "ARCH_05_PILLAR_BRAKE"
    name = "1칸 기둥 에어브레이크 안착"
    description = "칼1 돌진(+119px) 시 오버슈트 낙사, 4번칼 제동(0px) 안착 지형"

    def parameter_grid(self) -> List[Dict[str, Any]]:
        combos = []
        for gap in (2, 3):
            combos.append({"gap_tiles": gap, "run_tiles": 5})
        return combos

    def sample_parameters(self, rng: random.Random) -> Dict[str, Any]:
        return {"gap_tiles": rng.choice([2, 3]), "run_tiles": 5}

    def build_candidate(self, params: Dict[str, Any], variation_index: int) -> GeneratedCandidate:
        gap = params["gap_tiles"]
        run = params["run_tiles"]

        pillar_x = 1 + run + gap
        w = pillar_x + 6
        h = 20
        gy = 14
        lava_y = 17

        tiles: List[Dict[str, Any]] = []
        # Start platform: x=1..run
        for x in range(1, 1 + run):
            tiles.append({"id": 7, "x": x, "y": gy})

        # Exactly 1-tile pillar at pillar_x
        tiles.append({"id": 7, "x": pillar_x, "y": gy})

        spawn = {"x": 3, "y": gy - 1}
        goal = {"x": pillar_x, "y": gy - 1}

        map_id = f"arch05_pillar1_g{gap}_v{variation_index:03d}"
        spec = MapSpec(
            map_id=map_id,
            width=w,
            height=h,
            training_type="isolated_skill",
            spawn=spawn,
            goal=goal,
            tiles=tiles,
            lava_y=lava_y,
            metadata={
                "archetype": self.archetype_id,
                "required_mechanic": "weapon4_brake",
                "pillar_width_px": 32.0,
                "gap_tiles": gap,
            },
        )

        # Reference solution: Equip 4, jump, air brake Z at apex, land on 32px pillar
        ref_actions: List[Tuple[str, ...]] = (
            [("4",)]
            + [("RIGHT",)] * 16
            + [("RIGHT", "UP")] * 18
            + [("RIGHT",)] * 6
            + [("Z",)]
            + [()] * 45
        )

        # Anti-bypass candidate: Weapon 1 dash (+119px) overshoots 32px pillar to death
        w1_fam = Weapon1MobilityFamily()
        cand_manifest = w1_fam.generate_manifest(
            jump_durs=[14],
            attack_delays=[1],
            walk_ticks=16,
            post_dash_walk=50,
        )

        return GeneratedCandidate(
            archetype_id=self.archetype_id,
            variation_id=map_id,
            spec=spec,
            reference_actions=ref_actions,
            bypass_manifest=cand_manifest,
            parameters=params,
            snapshot_override=self.default_snapshot,
        )


# =============================================================================
# Archetype 6: Long Chasm Parachute Gliding (낙하산 장거리 활강)
# Physics: Chasm width 18~22 tiles (576~704px) > max delayed roll distance (506px).
# Anti-bypass: Delayed roll falls into chasm before reaching landing.
# =============================================================================
class Arch06ParachuteChasm(BaseArchetype):
    archetype_id = "ARCH_06_PARACHUTE_CHASM"
    name = "낙하산 장거리 협곡 활강"
    description = "지연뒷굴 한계(506px)를 초과하는 18~22칸(576~704px) 장거리 낙하산 활강"
    default_snapshot = "hun5_parachute_fast_boundary.zip"

    def parameter_grid(self) -> List[Dict[str, Any]]:
        combos = []
        for chasm in (20, 22):
            combos.append({"chasm_tiles": chasm, "run_tiles": 5, "land_tiles": 8})
        return combos

    def sample_parameters(self, rng: random.Random) -> Dict[str, Any]:
        return {
            "chasm_tiles": rng.choice([20, 22]),
            "run_tiles": 5,
            "land_tiles": 8,
        }

    def build_candidate(self, params: Dict[str, Any], variation_index: int) -> GeneratedCandidate:
        chasm = params["chasm_tiles"]
        run = params["run_tiles"]
        land = params["land_tiles"]

        w = 1 + run + chasm + land + 2
        h = 22
        start_y = 8  # Elevated start platform
        land_y = 15  # Lower landing platform
        lava_y = 19

        tiles: List[Dict[str, Any]] = []
        # Elevated start cliff
        for x in range(1, 1 + run):
            for y in range(start_y, lava_y):
                tiles.append({"id": 7, "x": x, "y": y})

        # Landing platform
        land_start = 1 + run + chasm
        for x in range(land_start, land_start + land):
            tiles.append({"id": 7, "x": x, "y": land_y})

        spawn = {"x": 3, "y": start_y - 1}
        goal = {"x": land_start + land - 3, "y": land_y - 1}

        map_id = f"arch06_chute_c{chasm}_v{variation_index:03d}"
        spec = MapSpec(
            map_id=map_id,
            width=w,
            height=h,
            training_type="isolated_skill",
            spawn=spawn,
            goal=goal,
            tiles=tiles,
            lava_y=lava_y,
            metadata={
                "archetype": self.archetype_id,
                "required_mechanic": "parachute_glide",
                "chasm_tiles": chasm,
                "chasm_px": chasm * 32.0,
            },
        )

        # Reference solution: Walk, jump, deploy parachute C, glide across, walk to goal
        ref_actions: List[Tuple[str, ...]] = (
            [("RIGHT",)] * 16
            + [("RIGHT", "UP")] * 20
            + [("RIGHT",)] * 12
            + [("RIGHT", "C")]
            + [("RIGHT",)] * 140
        )

        # Anti-bypass candidate: Delayed backroll falls short into lava (506px < 576px)
        backroll_fam = DelayedBackrollFamily()
        cand_manifest = backroll_fam.generate_manifest(
            jump_durs=[28],
            switch_delays=[0],
            roll_durs=[5],
            walk_ticks=16,
            post_roll_walk=120,
        )

        return GeneratedCandidate(
            archetype_id=self.archetype_id,
            variation_id=map_id,
            spec=spec,
            reference_actions=ref_actions,
            bypass_manifest=cand_manifest,
            parameters=params,
            snapshot_override=self.default_snapshot,
        )


# =============================================================================
# Archetype 7: Vertical Spring High Wall Launch (수직 스프링 도약)
# Physics: Vertical spring v0 = 2000.0, apex = 352px (11 tiles).
# Anti-bypass: Wall height 10 tiles (320px) > max backroll (270px).
# =============================================================================
class Arch07SpringLaunch(BaseArchetype):
    archetype_id = "ARCH_07_SPRING_LAUNCH"
    name = "수직 스프링 고벽 도약"
    description = "점프뒷굴 한계(270px) 초과 10칸(320px) 장벽을 스프링(352px)으로 돌파"
    default_snapshot = "hun85_live.zip"

    def parameter_grid(self) -> List[Dict[str, Any]]:
        combos = []
        for wall_h in (9, 10):
            combos.append({"wall_tiles": wall_h, "spring_offset": 2})
        return combos

    def sample_parameters(self, rng: random.Random) -> Dict[str, Any]:
        return {"wall_tiles": rng.choice([9, 10]), "spring_offset": 2}

    def build_candidate(self, params: Dict[str, Any], variation_index: int) -> GeneratedCandidate:
        wall_h = params["wall_tiles"]
        spring_off = params["spring_offset"]

        w = 30
        h = 20
        gy = 14
        wall_x = 10
        wall_top_y = gy - wall_h
        spring_x = wall_x - spring_off
        lava_y = 17

        tiles: List[Dict[str, Any]] = []
        # Ground before wall
        for x in range(1, wall_x):
            tiles.append({"id": 7, "x": x, "y": gy})
        # Spring tile (ID 4)
        tiles.append({"id": 4, "x": spring_x, "y": gy})

        # High barrier wall
        for y in range(wall_top_y, gy + 1):
            tiles.append({"id": 7, "x": wall_x, "y": y})

        # Landing ground after wall
        for x in range(wall_x + 1, 28):
            tiles.append({"id": 7, "x": x, "y": gy})

        spawn = {"x": 3, "y": gy - 1}
        goal = {"x": 25, "y": gy - 1}

        map_id = f"arch07_spring_w{wall_h}_v{variation_index:03d}"
        spec = MapSpec(
            map_id=map_id,
            width=w,
            height=h,
            training_type="isolated_skill",
            spawn=spawn,
            goal=goal,
            tiles=tiles,
            lava_y=lava_y,
            metadata={
                "archetype": self.archetype_id,
                "required_mechanic": "spring_vertical",
                "wall_tiles": wall_h,
                "wall_height_px": wall_h * 32.0,
            },
        )

        # Reference solution: Walk right onto spring, steer right over apex, land, walk to goal
        walk_to_spring = (spring_x - 3) * 8
        ref_actions: List[Tuple[str, ...]] = (
            [("RIGHT",)] * walk_to_spring
            + [("RIGHT",)] * 60  # Spring launches high, maintain right steering
            + [("RIGHT",)] * 60
        )

        # Anti-bypass candidate: Backroll cannot clear wall_h >= 9 (288px > 270px)
        backroll_fam = DelayedBackrollFamily()
        cand_manifest = backroll_fam.generate_manifest(
            jump_durs=[28],
            switch_delays=[0],
            roll_durs=[5],
            walk_ticks=16,
            post_roll_walk=100,
        )

        return GeneratedCandidate(
            archetype_id=self.archetype_id,
            variation_id=map_id,
            spec=spec,
            reference_actions=ref_actions,
            bypass_manifest=cand_manifest,
            parameters=params,
            snapshot_override=self.default_snapshot,
        )


# =============================================================================
# Archetype 8: Collapse Platform Bridge (시간차 붕괴 발판 다리)
# Physics: raw124 blocks collapse in 12 ticks (192ms) upon contact.
# =============================================================================
class Arch08CollapseBridge(BaseArchetype):
    archetype_id = "ARCH_08_COLLAPSE_BRIDGE"
    name = "시간차 붕괴 발판 다리"
    description = "접촉 12틱 내 점프 필수인 raw124 시간차 붕괴 발판 징검다리"

    def parameter_grid(self) -> List[Dict[str, Any]]:
        combos = []
        for bridge_len in (3, 4):
            combos.append({"bridge_len": bridge_len, "run_tiles": 5, "land_tiles": 10})
        return combos

    def sample_parameters(self, rng: random.Random) -> Dict[str, Any]:
        return {
            "bridge_len": rng.choice([3, 4]),
            "run_tiles": 5,
            "land_tiles": 10,
        }

    def build_candidate(self, params: Dict[str, Any], variation_index: int) -> GeneratedCandidate:
        b_len = params["bridge_len"]
        run = params["run_tiles"]
        land = params["land_tiles"]

        w = 1 + run + b_len + land + 2
        h = 20
        gy = 14
        lava_y = 17

        tiles: List[Dict[str, Any]] = []
        # Start solid ground
        for x in range(1, 1 + run):
            tiles.append({"id": 7, "x": x, "y": gy})

        # Collapse platform blocks (raw tile ID 124)
        bridge_start = 1 + run
        for x in range(bridge_start, bridge_start + b_len):
            tiles.append({"id": 124, "x": x, "y": gy})

        # Landing solid ground
        land_start = bridge_start + b_len
        for x in range(land_start, land_start + land):
            tiles.append({"id": 7, "x": x, "y": gy})

        spawn = {"x": 3, "y": gy - 1}
        goal = {"x": land_start + land - 3, "y": gy - 1}

        map_id = f"arch08_collapse_l{b_len}_v{variation_index:03d}"
        spec = MapSpec(
            map_id=map_id,
            width=w,
            height=h,
            training_type="isolated_skill",
            spawn=spawn,
            goal=goal,
            tiles=tiles,
            lava_y=lava_y,
            metadata={
                "archetype": self.archetype_id,
                "required_mechanic": "collapse_platform",
                "collapse_entry": "walk_contact",
                "bridge_len": b_len,
            },
        )

        # Reference solution: Run continuously across without stopping
        walk_ticks = (run - 3 + b_len + 3) * 8
        ref_actions: List[Tuple[str, ...]] = (
            [("RIGHT",)] * walk_ticks
            + [("RIGHT",)] * 40
        )

        return GeneratedCandidate(
            archetype_id=self.archetype_id,
            variation_id=map_id,
            spec=spec,
            reference_actions=ref_actions,
            bypass_manifest=[],
            parameters=params,
            snapshot_override=self.default_snapshot,
        )


# =============================================================================
# Archetype Registry & Master Procedural Generator
# =============================================================================
ARCHETYPE_CLASSES: Dict[str, type[BaseArchetype]] = {
    Arch01BasicGap.archetype_id: Arch01BasicGap,
    Arch02StepUp.archetype_id: Arch02StepUp,
    Arch03BackrollHighWall.archetype_id: Arch03BackrollHighWall,
    Arch04KnifeDash.archetype_id: Arch04KnifeDash,
    Arch05PillarBrake.archetype_id: Arch05PillarBrake,
    Arch06ParachuteChasm.archetype_id: Arch06ParachuteChasm,
    Arch07SpringLaunch.archetype_id: Arch07SpringLaunch,
    Arch08CollapseBridge.archetype_id: Arch08CollapseBridge,
}


class ProceduralMapGenerator:
    """Master Procedural Generator orchestrating archetypes, parameters, and candidates."""

    def __init__(self):
        self.archetypes: Dict[str, BaseArchetype] = {
            arch_id: cls() for arch_id, cls in ARCHETYPE_CLASSES.items()
        }

    def list_archetypes(self) -> List[Dict[str, str]]:
        return [
            {
                "archetype_id": arch.archetype_id,
                "name": arch.name,
                "description": arch.description,
            }
            for arch in self.archetypes.values()
        ]

    def generate(
        self,
        archetype_ids: Optional[Sequence[str]] = None,
        mode: str = "grid",
        count_per_archetype: Optional[int] = None,
        seed: int = 42,
    ) -> Iterator[GeneratedCandidate]:
        """Generate candidates across selected or all archetypes."""
        target_ids = archetype_ids if archetype_ids else list(self.archetypes.keys())
        for arch_id in target_ids:
            if arch_id not in self.archetypes:
                raise KeyError(f"Unknown archetype ID: {arch_id}. Available: {list(self.archetypes.keys())}")
            archetype = self.archetypes[arch_id]
            yield from archetype.generate_candidates(mode=mode, count=count_per_archetype, seed=seed)
