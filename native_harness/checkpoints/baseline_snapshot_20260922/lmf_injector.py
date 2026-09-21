"""Experimental LMF-to-captured-world injector for simple training maps.

The x86 gameplay code remains unchanged. This module only rebuilds the Client's
captured runtime grids/object records from an LMF. Coverage is deliberately
limited to tile IDs whose runtime object templates exist in the pinned 훈1
capture. Gimmick maps require their own captured templates and parity tests.
"""
from __future__ import annotations

from pathlib import Path
import json
import struct

from captured_oracle import CapturedOracle


class SimpleLmfOracle(CapturedOracle):
    # Captured modules occupy much of 0x60xx0000..; this verified gap sits
    # above the control shim and below the next captured module.
    INJECT_MEMORY = 0x60100000
    # 0x60100000..0x60600000 is an unmapped gap in every pinned capture.
    # Five MiB leaves room for four collision grids for maps up to roughly
    # 655k cells, instead of rejecting maps just beyond the tiny fixtures.
    INJECT_SIZE = 0x500000
    OBJECT_BASE = 0x27A5998
    OBJECT_STRIDE = 0xF8
    GRID_POINTERS = (0x8952DCC, 0x8952DEC, 0x8952E2C, 0x8952E4C)
    TEMPLATE_INDEX = {7: 0, 49: 28, 100: 56, 140: 57}
    TEMPLATE_BANK = Path(__file__).resolve().parent / "evidence" / "object_templates.json"
    # Some records do not emit runtime objects.  The normal map loader writes
    # their final collision mask in a pass after 0x41e510.  raw87/raw88 are the
    # two mine/bomb orientations: live 맵테스트2 has grid-1 code 1 at all 29
    # cells while the record builder alone leaves zero there.
    GRID_CODES = {3: 3, 7: 1, 27: 6, 37: 5, 87: 1, 88: 1}

    def __init__(self, snapshot):
        super().__init__(snapshot)
        self.u.mem_map(self.INJECT_MEMORY, self.INJECT_SIZE)
        base = self.addr(self.OBJECT_BASE)
        self.object_templates = {
            tile_id: bytes(self.u.mem_read(base + index * self.OBJECT_STRIDE, self.OBJECT_STRIDE))
            for tile_id, index in self.TEMPLATE_INDEX.items()
        }
        if self.TEMPLATE_BANK.exists():
            bank = json.loads(self.TEMPLATE_BANK.read_text(encoding="utf-8"))["templates"]
            for tile_id, entry in bank.items():
                self.object_templates.setdefault(int(tile_id), bytes.fromhex(entry["bytes_hex"]))
        self.supported_ids = frozenset(self.object_templates)
        slot = self.meta["state"]["slot"]
        self.player_address = self.addr(0x3B12A00 + slot * 0xF8)
        self.player_template = bytes(self.u.mem_read(self.player_address, 0xF8))

    def place_player_at_spawn(self, spawn):
        """Place the captured player at a fresh map-start boundary."""
        player = bytearray(self.player_template)
        old_x, old_y = struct.unpack_from("<dd", player, 0)
        new_x, new_y = spawn[0] * 32.0 + 16.0, spawn[1] * 32.0
        struct.pack_into("<dd", player, 0, new_x, new_y)
        # +0x10/+0x14 are the Client's death-respawn coordinates. The normal
        # type-300 spawn marker stores its centre X and bottom-minus-one Y.
        struct.pack_into("<ii", player, 0x10, int(new_x), spawn[1] * 32 + 31)
        dx, dy = int(new_x - old_x), int(new_y - old_y)
        for offset, delta in ((0x18, dx), (0x1C, dy), (0x20, dx), (0x24, dy)):
            struct.pack_into("<i", player, offset,
                             struct.unpack_from("<i", player, offset)[0] + delta)
        struct.pack_into("<d", player, 0x58, 0.0)
        for offset, value in ((0x38, 7), (0x3C, 0), (0x68, 0), (0x74, -1),
                              (0xC0, 0), (0xC4, 0), (0xD0, 1), (0xDC, 0)):
            struct.pack_into("<i", player, offset, value)
        self.u.mem_write(self.player_address, bytes(player))
        slot = self.meta["state"]["slot"]
        self.put(0x25CA528 + slot * 4, "i", 0)
        self.put(0x25CA078 + slot * 4, "i", -1)

    def configure_map_geometry(self, width: int, height: int, grid_bytes: int):
        """Mirror the original 0x46c690 grid-geometry metadata writes.

        The gameplay code does not derive every pixel boundary directly from
        the LMF dimensions.  In particular, the ice-inertia path clamps X
        against 0x8952dc4.  Leaving the captured 30x18 values there made wide
        custom maps stop at x=960-48=912 even though their collision grids had
        already been rebuilt at the requested size.
        """
        tile_width = self.get(0x8952ED4, "i")[0]
        tile_height = self.get(0x8952ED8, "i")[0]
        for pointer_global in self.GRID_POINTERS:
            metadata = pointer_global - 0x14
            self.put(metadata, "I", grid_bytes)
            self.put(metadata + 0x0C, "ii",
                     width * tile_width, height * tile_height)
            self.put(metadata - 0x08, "ii", width, height)

    @staticmethod
    def parse_lmf(path: Path):
        raw = path.read_bytes()
        if raw.startswith(b"NewLWMapFile_1.0"):
            if len(raw) < 32:
                raise ValueError("short LMF header")
            width, height = struct.unpack_from("<HH", raw, 16)
            count = struct.unpack_from("<I", raw, 21)[0]
            if len(raw) != 32 + 8 * count:
                raise ValueError("LMF byte length does not match record count")
            records = [struct.unpack_from("<Ihh", raw, 32 + 8 * i) for i in range(count)]
        elif raw.startswith(b"GaG Map Data File 2.0"):
            # Legacy maps use a 21-byte signature, uint16 dimensions and
            # compact five-byte records: uint8 tile ID, uint16 x, uint16 y.
            if len(raw) < 25 or (len(raw) - 25) % 5:
                raise ValueError("legacy LMF byte length does not match 5-byte records")
            width, height = struct.unpack_from("<HH", raw, 21)
            count = (len(raw) - 25) // 5
            records = [struct.unpack_from("<BHH", raw, 25 + 5 * i) for i in range(count)]
        else:
            raise ValueError("unknown LMF signature")
        return width, height, records

    @staticmethod
    def move_template(template: bytes, x: int, y: int) -> bytes:
        out = bytearray(template)
        old_x, old_y = struct.unpack_from("<dd", out, 0x10)
        new_x, new_y = x * 32.0 + 16.0, y * 32.0 + 16.0
        dx, dy = int(new_x - old_x), int(new_y - old_y)
        struct.pack_into("<dd", out, 0x10, new_x, new_y)
        for offset, delta in ((0x28, dx), (0x2C, dy), (0x30, dx), (0x34, dy)):
            struct.pack_into("<i", out, offset, struct.unpack_from("<i", out, offset)[0] + delta)
        return bytes(out)

    def load_lmf(self, path: str | Path):
        path = Path(path)
        width, height, records = self.parse_lmf(path)
        unsupported = sorted({tile_id for tile_id, _, _ in records} - self.supported_ids)
        if unsupported:
            raise ValueError(f"No captured runtime template for LMF tile IDs {unsupported}")
        cells = width * height
        grid_stride = (cells * 2 + 0xFFF) & ~0xFFF
        if grid_stride * 4 > self.INJECT_SIZE:
            raise ValueError("map exceeds reserved injected grid memory")

        grids = [bytearray(cells * 2) for _ in range(4)]
        grids[2][:] = b"\x01" * (cells * 2)
        grids[3][:] = b"\xff" * (cells * 2)
        for tile_id, x, y in records:
            if not (0 <= x < width and 0 <= y < height):
                raise ValueError(f"out-of-bounds record {(tile_id, x, y)}")
            code = self.GRID_CODES.get(tile_id)
            if code is not None:
                struct.pack_into("<H", grids[1], 2 * (y * width + x), code)

        for index, (global_address, grid) in enumerate(zip(self.GRID_POINTERS, grids)):
            pointer = self.INJECT_MEMORY + index * grid_stride
            self.u.mem_write(pointer, bytes(grid))
            self.put(global_address, "I", pointer)
        self.configure_map_geometry(width, height, cells * 2)
        self.put(0xA073150, "I" * height, *[y * width for y in range(height)])

        object_base = self.addr(self.OBJECT_BASE)
        for index, (tile_id, x, y) in enumerate(records):
            record = self.move_template(self.object_templates[tile_id], x, y)
            self.u.mem_write(object_base + index * self.OBJECT_STRIDE, record)
        self.put(0x25CA048, "ii", len(records), 0)

        spawn = next(((x, y) for tile_id, x, y in records if tile_id == 100), None)
        if spawn is None:
            raise ValueError("simple training map has no ID 100 spawn")
        self.place_player_at_spawn(spawn)
        return {
            "path": str(path.resolve()),
            "size": [width, height],
            "pixel_size": [width * self.get(0x8952ED4, "i")[0],
                           height * self.get(0x8952ED8, "i")[0]],
            "records": len(records),
            "spawn": list(spawn),
        }


class NativeLmfOracle(SimpleLmfOracle):
    """Build Client runtime map state with original x86 function 0x41e510."""

    MATERIALIZE_RECORD = 0x41E510
    AUX_MEMORY = 0x7F000000
    AUX_SIZE = 0x10000

    def __init__(self, snapshot):
        super().__init__(snapshot)
        for candidate in (0x7F000000, 0x70000000, 0x20000000, 0x10000000):
            try:
                self.u.mem_map(candidate, self.AUX_SIZE)
                self.AUX_MEMORY = candidate
                break
            except Exception:
                continue
        else:
            raise RuntimeError("no free auxiliary x86 memory region")
        self._collision_refresh_ready = False

    def configure_collision_refresh(self, records, record_ids):
        """Build an x86 batch which replays static type-200 grid updates."""
        record_ids = frozenset(record_ids)
        count = self.get(0x25CA048, "i")[0]
        base = self.addr(self.OBJECT_BASE)
        raw = bytes(self.u.mem_read(base, count * self.OBJECT_STRIDE))
        code_for_variant = {1: 1, 2: 6, 3: 5, 4: 3}
        refresh = []
        direct_grid = []
        for index, (tile_id, x, y) in enumerate(records):
            if tile_id not in record_ids:
                continue
            runtime_index = self.runtime_index_by_record.get(index)
            if runtime_index is None:
                raise RuntimeError(f"tile {tile_id} did not create a runtime collision record")
            start = runtime_index * self.OBJECT_STRIDE
            runtime_type = struct.unpack_from("<i", raw, start)[0]
            variant = struct.unpack_from("<i", raw, start + 0x48)[0]
            if runtime_type != 200 or variant not in code_for_variant:
                raise RuntimeError(f"tile {tile_id} is not a supported static type-200 record")
            refresh.append((code_for_variant[variant], x, y))
            if tile_id in (27, 37):
                direct_grid.append((code_for_variant[variant], x, y))
        data_address = self.AUX_MEMORY + 0x100
        payload = b"".join(struct.pack("<iii", *item) for item in refresh)
        if data_address + len(payload) > self.AUX_MEMORY + self.AUX_SIZE:
            raise RuntimeError("collision refresh payload exceeds auxiliary memory")
        # mov esi,data; mov edi,count; push y/x/code; call 0x42ed50;
        # clean args; advance record; loop; ret.
        code = bytearray(b"\xBE" + struct.pack("<I", data_address)
                         + b"\xBF" + struct.pack("<I", len(refresh))
                         + b"\xFF\x76\x08\xFF\x76\x04\xFF\x36\xE8\0\0\0\0"
                         + b"\x83\xC4\x0C\x83\xC6\x0C\x4F\x75\xEA\xC3")
        call_next = self.AUX_MEMORY + 23
        struct.pack_into("<i", code, 19, self.addr(0x42ED50) - call_next)
        self.u.mem_write(self.AUX_MEMORY, bytes(code))
        self.u.mem_write(data_address, payload)
        self._collision_refresh_ready = bool(refresh)
        self._collision_refresh_count = len(refresh)
        self._collision_refresh_direct_grid = direct_grid
        return len(refresh)

    def configure_grid2_refresh(self, records, record_ids):
        """Record inert type-290 cells whose original update writes grid2=2."""
        record_ids = frozenset(record_ids)
        count = self.get(0x25CA048, "i")[0]
        base = self.addr(self.OBJECT_BASE)
        raw = bytes(self.u.mem_read(base, count * self.OBJECT_STRIDE))
        cells = []
        width = self.get(0x8952DB0, "i")[0]
        for index, (tile_id, x, y) in enumerate(records):
            if tile_id not in record_ids:
                continue
            runtime_index = self.runtime_index_by_record.get(index)
            if runtime_index is None:
                raise RuntimeError(f"tile {tile_id} did not create a runtime grid record")
            runtime_type = struct.unpack_from("<i", raw, runtime_index * self.OBJECT_STRIDE)[0]
            if runtime_type != 290:
                raise RuntimeError(f"tile {tile_id} is not an inert type-290 grid record")
            cells.append(y * width + x)
        self._grid2_refresh_cells = cells
        return len(cells)

    def refresh_compacted_collisions(self, call_limit=2_000_000):
        if self._collision_refresh_ready:
            self.call(self.AUX_MEMORY, limit=max(call_limit,
                                                 self._collision_refresh_count * 500))
            if self._collision_refresh_direct_grid:
                width = self.get(0x8952DB0, "i")[0]
                pointer = self.get(0x8952E0C, "I")[0]
                for code, x, y in self._collision_refresh_direct_grid:
                    self.u.mem_write(pointer + 2 * (y * width + x), struct.pack("<H", code))
        if getattr(self, "_grid2_refresh_cells", None):
            pointer = self.get(self.GRID_POINTERS[2], "I")[0]
            for cell in self._grid2_refresh_cells:
                self.u.mem_write(pointer + 2 * cell, b"\x02\x00")

    def compact_runtime_objects(self, records, excluded_ids):
        """Remove proven presentation-only records from the per-tick list.

        The original builder has already populated the four collision grids.
        This only compacts the contiguous object dispatcher array and preserves
        the relative order and complete bytes of every retained object.
        Callers must independently establish that each excluded tile has no
        required per-tick gameplay state.
        """
        excluded_ids = frozenset(excluded_ids)
        count = self.get(0x25CA048, "i")[0]
        base = self.addr(self.OBJECT_BASE)
        raw = bytes(self.u.mem_read(base, count * self.OBJECT_STRIDE))
        retained = []
        compact_index_by_record = {}
        for record_index, (tile_id, _x, _y) in enumerate(records):
            source_runtime_index = self.runtime_index_by_record.get(record_index)
            if source_runtime_index is None:
                continue
            if tile_id in excluded_ids:
                continue
            compact_index_by_record[record_index] = len(retained)
            start = source_runtime_index * self.OBJECT_STRIDE
            retained.append(raw[start:start + self.OBJECT_STRIDE])
        packed = b"".join(retained)
        self.u.mem_write(base, packed)
        self.put(0x25CA048, "i", len(retained))
        self.runtime_index_by_record = compact_index_by_record
        return {
            "before": count,
            "after": len(retained),
            "excluded_ids": sorted(excluded_ids),
            "excluded_records": count - len(retained),
        }

    def configure_spatial_runtime(self, records, tile_ids=(49,), radius=6,
                                  expected_types=None):
        """Keep local-contact objects only near the controlled player.

        Dense user maps can contain hundreds of identical local field objects.
        Preserve the complete Client-built bytes for every record, but omit
        distant records from the per-tick dispatcher and reinsert them before
        the player can contact them. ``expected_types`` prevents an incorrect
        LMF identity from silently removing a different runtime object.
        """
        tile_ids = frozenset(tile_ids)
        expected_types = dict(expected_types or {49: 229})
        base = self.addr(self.OBJECT_BASE)
        count = self.get(0x25CA048, "i")[0]
        raw = bytes(self.u.mem_read(base, count * self.OBJECT_STRIDE))
        state = {}
        spatial = set()
        positions = {}
        for record_index, runtime_index in self.runtime_index_by_record.items():
            start = runtime_index * self.OBJECT_STRIDE
            state[record_index] = raw[start:start + self.OBJECT_STRIDE]
            tile_id, x, y = records[record_index]
            if tile_id in tile_ids:
                runtime_type = struct.unpack_from("<i", state[record_index])[0]
                expected = expected_types.get(tile_id)
                if expected is None or runtime_type != expected:
                    raise RuntimeError(
                        f"tile {tile_id} runtime type {runtime_type} != expected {expected}")
                spatial.add(record_index)
                positions[record_index] = (x, y)
        self._spatial_runtime_state = state
        self._spatial_runtime_indices = spatial
        self._spatial_runtime_positions = positions
        self._spatial_runtime_radius = int(radius)
        self._spatial_runtime_enabled = bool(spatial)
        self.refresh_spatial_runtime(sync_current=False)
        self._spatial_baseline = self.save_spatial_host_state()
        return {"managed_records": len(spatial), "radius_tiles": int(radius),
                "active_records": sum(i in self.runtime_index_by_record for i in spatial)}

    def refresh_spatial_runtime(self, sync_current=True):
        if not getattr(self, "_spatial_runtime_enabled", False):
            return
        base = self.addr(self.OBJECT_BASE)
        extras = []
        if sync_current:
            count = self.get(0x25CA048, "i")[0]
            raw = bytes(self.u.mem_read(base, count * self.OBJECT_STRIDE))
            mapped_runtime_indices = set(self.runtime_index_by_record.values())
            for record_index, runtime_index in self.runtime_index_by_record.items():
                start = runtime_index * self.OBJECT_STRIDE
                self._spatial_runtime_state[record_index] = raw[start:start + self.OBJECT_STRIDE]
            # Attacks and other gameplay code append transient objects to the
            # same array.  They have no LMF record index.  The old spatial
            # rebuild silently dropped them on the next tick, which made mines
            # and projectiles disappear on maps containing spatially-managed
            # lava.  Preserve their exact Client-built bytes after the map
            # objects; the original dispatcher remains responsible for them.
            for runtime_index in range(count):
                if runtime_index not in mapped_runtime_indices:
                    start = runtime_index * self.OBJECT_STRIDE
                    extras.append(raw[start:start + self.OBJECT_STRIDE])
        state = self.read_player_state()
        px, py = int(state["x"] // 32), int(state["y"] // 32)
        radius = self._spatial_runtime_radius
        active = []
        for record_index in sorted(self._spatial_runtime_state):
            if record_index not in self._spatial_runtime_indices:
                active.append(record_index)
                continue
            x, y = self._spatial_runtime_positions[record_index]
            if abs(x - px) <= radius and abs(y - py) <= radius:
                active.append(record_index)
        packed = [self._spatial_runtime_state[i] for i in active]
        packed.extend(extras)
        self.u.mem_write(base, b"".join(packed))
        self.put(0x25CA048, "i", len(packed))
        self.runtime_index_by_record = {record_index: runtime_index
                                        for runtime_index, record_index in enumerate(active)}

    def read_unmapped_runtime_objects(self):
        """Return live Client objects that were not created by an LMF record."""
        count = self.get(0x25CA048, "i")[0]
        mapped = set(self.runtime_index_by_record.values())
        result = []
        for runtime_index in range(count):
            if runtime_index in mapped:
                continue
            address = self.OBJECT_BASE + runtime_index * self.OBJECT_STRIDE
            result.append({
                "index": runtime_index,
                "type": self.get(address, "i")[0],
                "animation": self.get(address + 0x08, "i")[0],
                "frame": self.get(address + 0x4C, "i")[0],
                "bounds": list(self.get(address + 0x28, "4i")),
                "state_c8": self.get(address + 0xC8, "i")[0],
            })
        return result

    def save_spatial_host_state(self):
        if not getattr(self, "_spatial_runtime_enabled", False):
            return None
        self.refresh_spatial_runtime(sync_current=True)
        return {
            "state": dict(self._spatial_runtime_state),
            "mapping": dict(self.runtime_index_by_record),
        }

    def restore_spatial_host_state(self, snapshot=None):
        if not getattr(self, "_spatial_runtime_enabled", False):
            return
        snapshot = self._spatial_baseline if snapshot is None else snapshot
        self._spatial_runtime_state = dict(snapshot["state"])
        self.runtime_index_by_record = dict(snapshot["mapping"])

    def materialize_records(self, records, grid_bytes, call_limit):
        """Call the original record builder in one emulated x86 batch."""
        if not records:
            self.runtime_index_by_record = {}
            return
        code_address = self.INJECT_MEMORY + grid_bytes
        data_address = (code_address + 0x3F) & ~0x0F
        # The fourth dword is filled by the x86 loop with the cumulative
        # runtime-object count after each original builder call. Some LMF IDs
        # are editor/control records and intentionally emit no object.
        payload = b"".join(struct.pack("<iiiI", *record, 0) for record in records)
        if data_address + len(payload) > self.INJECT_MEMORY + self.INJECT_SIZE:
            # Grids still fit. Very record-dense maps can use the slower path
            # without reserving another address range in the captured process.
            mapping = {}
            for record_index, (tile_id, x, y) in enumerate(records):
                before = self.get(0x25CA048, "i")[0]
                self.call(self.MATERIALIZE_RECORD, struct.pack("<iii", tile_id, x, y),
                          limit=call_limit)
                after = self.get(0x25CA048, "i")[0]
                if after == before + 1:
                    mapping[record_index] = before
                elif after != before:
                    raise RuntimeError(f"LMF record {record_index} emitted {after - before} objects")
            self.runtime_index_by_record = mapping
            return

        # mov esi,data; mov edi,count; push [esi+8/+4/+0]; call builder;
        # clean args; advance; loop; ret. The called Client function is
        # unchanged; only the Python call boundary is removed from the loop.
        code = bytearray(b"\xBE" + struct.pack("<I", data_address)
                         + b"\xBF" + struct.pack("<I", len(records))
                         + b"\xFF\x76\x08\xFF\x76\x04\xFF\x36\xE8\0\0\0\0"
                         + b"\x83\xC4\x0C\xA1" + struct.pack("<I", self.addr(0x25CA048))
                         + b"\x89\x46\x0C\x83\xC6\x10\x4F\x75\xE2\xC3")
        call_next = code_address + 23
        struct.pack_into("<i", code, 19, self.addr(self.MATERIALIZE_RECORD) - call_next)
        self.u.mem_write(code_address, bytes(code))
        self.u.mem_write(data_address, payload)
        # The Client builder also updates existing object lists, so dense maps
        # cost more than a fixed amount per record.
        self.call(code_address, limit=max(call_limit, min(2_000_000_000,
                                                          len(records) * 100_000)))
        result = bytes(self.u.mem_read(data_address, len(payload)))
        mapping = {}
        before = 0
        for record_index in range(len(records)):
            after = struct.unpack_from("<I", result, record_index * 16 + 12)[0]
            if after == before + 1:
                mapping[record_index] = before
            elif after != before:
                raise RuntimeError(f"LMF record {record_index} emitted {after - before} objects")
            before = after
        self.runtime_index_by_record = mapping

    def enable_weapon_slots(self):
        """Configure the captured room as the Client's weapon-enabled mode.

        This changes the same room-mode byte observed in the weapon-capable
        live captures. Selection and attacks still execute the original
        0x4228c0/0x42e610 Client paths.
        """
        room = self.get(0xAA16538, "i")[0]
        if self.call(0x402BB0, struct.pack("<i", room)) != 1:
            raise RuntimeError("captured room does not support weapon-enabled mode")
        self.put(0xAA04118 + room * 0x124, "B", 2)

    def load_lmf(self, path: str | Path, call_limit=2_000_000, fresh_spawn=False):
        path = Path(path)
        width, height, records = self.parse_lmf(path)
        cells = width * height
        grid_stride = (cells * 2 + 0xFFF) & ~0xFFF
        if grid_stride * 4 > self.INJECT_SIZE:
            raise ValueError("map exceeds reserved injected grid memory")

        grids = [bytearray(cells * 2) for _ in range(4)]
        grids[2][:] = b"\x01" * (cells * 2)
        grids[3][:] = b"\xff" * (cells * 2)
        for index, (global_address, grid) in enumerate(zip(self.GRID_POINTERS, grids)):
            pointer = self.INJECT_MEMORY + index * grid_stride
            self.u.mem_write(pointer, bytes(grid))
            self.put(global_address, "I", pointer)
        self.configure_map_geometry(width, height, cells * 2)
        self.put(0xA073150, "I" * height, *[y * width for y in range(height)])

        room = self.get(0xAA16538, "i")[0]
        self.put(0xAA0411E + room * 0x124, "hh", width, height)
        self.put(0x25CA048, "ii", 0, 0)
        object_base = self.addr(self.OBJECT_BASE)
        self.u.mem_write(object_base, bytes(len(records) * self.OBJECT_STRIDE))
        self.materialize_records(records, grid_stride * 4, call_limit)
        # raw87/raw88/raw95/raw96 are built into the Client's separate type-60
        # array, not OBJECT_BASE. Keep a record mapping so observation/rendering
        # follows the live native object instead of the immutable LMF cell.
        special_count = self.get(0xA072AA4, "i")[0]
        self.special_index_by_record = {}
        special_cursor = 0
        for record_index, (tile_id, x, y) in enumerate(records):
            if tile_id not in (87, 88, 95, 96):
                continue
            # Later builder calls already advance gravity for earlier special
            # objects, so their final coordinates need not equal the LMF cell.
            # Creation order and the Client's retained raw ID are stable.
            match = next((i for i in range(special_cursor, special_count)
                          if self.get(0xA074460 + i * 0xF8 + 0xD0, "i")[0] == tile_id), None)
            if match is not None:
                self.special_index_by_record[record_index] = match
                special_cursor = match + 1

        # The original record materializer creates these runtime objects but
        # leaves their collision masks to the map-loader pass that follows it.
        # Captured grids establish the loader's codes for ladders and the two
        # triangular ice orientations. Preserve that loader state here.
        grid1 = self.get(self.GRID_POINTERS[1], "I")[0]
        for tile_id, x, y in records:
            code = self.GRID_CODES.get(tile_id)
            if code is not None:
                self.u.mem_write(grid1 + 2 * (y * width + x), struct.pack("<H", code))

        spawn = next(((x, y) for tile_id, x, y in records if tile_id == 100), None)
        if spawn is None:
            raise ValueError("training map has no ID 100 spawn")
        if fresh_spawn:
            # ID 100 is the spawn point itself. The normal Client applies
            # gravity after placing the player there. Starting one tile lower
            # skipped the visible spawn fall and could place it into water.
            self.place_player_at_spawn(spawn)
        else:
            # Keep the older settled-boundary behavior for parity fixtures
            # whose normal Client capture starts after the spawn fall.
            self.u.mem_write(self.player_address, self.player_template)
            self.u.mem_write(self.player_address, struct.pack(
                "<dd", spawn[0] * 32.0 + 16.0, (spawn[1] + 1) * 32.0))
        return {
            "path": str(path.resolve()),
            "size": [width, height],
            "pixel_size": list(self.get(0x8952DC4, "ii")),
            "records": len(records),
            "runtime_object_counts": list(self.get(0x25CA048, "ii")),
            "spawn": list(spawn),
            "builder": hex(self.MATERIALIZE_RECORD),
        }
