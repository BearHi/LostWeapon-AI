"""Declarative MapSpec Compiler for LostWeapon.

Translates high-level declarative MapSpec into standard LMF binary format.
Strictly decoupled from physics validation (Compilation only: schema validation,
coordinate normalization, tile expansion, and LMF binary packing).
"""
from dataclasses import dataclass, field
from pathlib import Path
import struct
from typing import Any, Dict, List, Optional


@dataclass
class MapSpec:
    """Declarative specification of a LostWeapon map."""
    map_id: str
    width: int
    height: int
    training_type: str # 'isolated_skill' or 'integration'
    spawn: Dict[str, int] # {'x': int, 'y': int}
    goal: Dict[str, int]  # {'x': int, 'y': int}
    tiles: List[Dict[str, Any]] = field(default_factory=list) # [{'id': int, 'x': int, 'y': int}, ...]
    lava_y: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MapSpec":
        """Validates schema types and returns MapSpec."""
        required = ("map_id", "width", "height", "training_type", "spawn", "goal")
        for field_name in required:
            if field_name not in data:
                raise ValueError(f"MapSpec missing required field: {field_name}")
        
        if data["training_type"] not in ("isolated_skill", "integration"):
            raise ValueError(f"Invalid training_type: {data['training_type']}")
        
        return cls(
            map_id=str(data["map_id"]),
            width=int(data["width"]),
            height=int(data["height"]),
            training_type=str(data["training_type"]),
            spawn=dict(data["spawn"]),
            goal=dict(data["goal"]),
            tiles=list(data.get("tiles", [])),
            lava_y=data.get("lava_y"),
            metadata=dict(data.get("metadata", {}))
        )


class MapCompiler:
    """Compiles a MapSpec into a binary .LMF map file."""

    TILE_SPAWN = 100
    TILE_GOAL = 140
    TILE_LAVA = 49

    @staticmethod
    def compile(spec: MapSpec, output_path: Path) -> Path:
        """Converts MapSpec into canonical 32-byte header + 8-byte record LMF."""
        records: List[tuple] = []

        # 1. Player Spawn (Tile 100)
        records.append((MapCompiler.TILE_SPAWN, spec.spawn["x"], spec.spawn["y"]))

        # 2. Goal / Flag (Tile 140)
        records.append((MapCompiler.TILE_GOAL, spec.goal["x"], spec.goal["y"]))

        # 3. Explicit Tile Blocks
        for tile in spec.tiles:
            records.append((int(tile["id"]), int(tile["x"]), int(tile["y"])))

        # 4. Global Lava Floor (if defined)
        if spec.lava_y is not None:
            for x in range(spec.width):
                records.append((MapCompiler.TILE_LAVA, x, spec.lava_y))

        # Pack into canonical LMF binary format
        header = bytearray(32)
        header[:16] = b"NewLWMapFile_1.0"
        struct.pack_into("<HH", header, 16, spec.width, spec.height)
        header[20] = 0x12
        struct.pack_into("<I", header, 21, len(records))

        body = bytearray()
        for tile_id, x, y in records:
            body.extend(struct.pack("<Ihh", tile_id, x, y))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(bytes(header) + bytes(body))
        return output_path
