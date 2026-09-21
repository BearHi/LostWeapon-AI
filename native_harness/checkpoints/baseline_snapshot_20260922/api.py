"""Small stable API surface for planner integration.

The implementation is intentionally explicit about the current scope: this
API runs the captured local gameplay closure, not the online Client session.
"""
from pathlib import Path
from captured_oracle import CapturedOracle
from lmf_injector import NativeLmfOracle, SimpleLmfOracle

class NativeOracleAPI:
    def __init__(self,snapshot):
        self.oracle=CapturedOracle(Path(snapshot))
        self._last_keys=()
    def save_state(self):
        return self.oracle.save_snapshot()
    def restore_state(self,state):
        self.oracle.restore_snapshot(state)
    def set_input(self,keys):
        self._last_keys=tuple(keys);self.oracle.set_input(self._last_keys)
    def step(self,n=1,keys=None):
        if n<0:raise ValueError('n must be non-negative')
        if keys is not None:self._last_keys=tuple(keys)
        result=None
        for _ in range(n):result=self.oracle.step_one_tick(self._last_keys)
        return result if result is not None else self.read_state()
    def read_state(self):return self.oracle.read_player_state()


class SimpleTrainingAPI:
    """Resettable full-world API for LMFs covered by captured object templates."""

    def __init__(self, snapshot, lmf, call_limit=2_000_000):
        self.oracle = SimpleLmfOracle(Path(snapshot))
        self.map = self.oracle.load_lmf(Path(lmf))
        self.call_limit = call_limit
        self._last_keys = ()
        self.oracle.begin_branching()

    def reset(self):
        self.oracle.restore_branch()
        self._last_keys = ()
        return self.read_state()

    def save_state(self):
        return self.oracle.save_branch_snapshot()

    def restore_state(self, state):
        if not isinstance(state, dict) or state.get('kind') != 'dirty-branch-v1':
            raise ValueError('SimpleTrainingAPI requires a branch snapshot from save_state()')
        self.oracle.restore_branch_snapshot(state)

    def set_input(self, keys):
        self._last_keys = tuple(keys)

    def step(self, n=1, keys=None):
        if n < 0:
            raise ValueError("n must be non-negative")
        if keys is not None:
            self._last_keys = tuple(keys)
        result = None
        for _ in range(n):
            result = self.oracle.step_world_chain(self._last_keys, call_limit=self.call_limit)
        return result if result is not None else self.read_state()

    def read_state(self):
        return self.oracle.read_player_state()


class NativeTrainingAPI(SimpleTrainingAPI):
    """Resettable full-world API using the Client's original LMF record builder."""

    # ID 18 is a static metal collision tile and ID 82 is a visual decoration.
    # The original builder still runs for both, so collision grids are exact;
    # only their inert runtime records are omitted from the per-tick scan.
    # Dense decorative/solid maps otherwise make the Client dispatcher scan
    # thousands of immutable type-200 records. Plain solids keep their grid
    # cells without a per-tick object; ladder/slope variants are replayed by
    # one original-x86 collision batch before the world update.
    INERT_RUNTIME_IDS = (3, 7, 8, 15, 18, 26, 36, 37, 40, 82,
                         110, 111, 113, 114, 115, 117)
    REFRESHED_COLLISION_IDS = (3, 26, 36, 37, 40, 110, 111, 113, 114, 115, 117)

    def __init__(self, snapshot, lmf, call_limit=2_000_000, track_dirty=True,
                 enable_weapons=True, compact_static=True,
                 spatial_field_ids=(49, 51, 63)):
        self.oracle = NativeLmfOracle(Path(snapshot))
        self.map = self.oracle.load_lmf(Path(lmf), call_limit=call_limit, fresh_spawn=True)
        _width, _height, records = self.oracle.parse_lmf(Path(lmf))
        if compact_static:
            self.map["refreshed_collision_records"] = self.oracle.configure_collision_refresh(
                records, self.REFRESHED_COLLISION_IDS)
            # raw43 is the cyan ring/black-cap contact mine.  Its type-290
            # runtime record participates in the original hazard lookup and
            # must remain in the dispatcher; treating it as an inert grid
            # writer made the picture appear while contact never detonated it.
            self.map["refreshed_grid2_records"] = self.oracle.configure_grid2_refresh(
                records, ())
            self.map["runtime_compaction"] = self.oracle.compact_runtime_objects(
                records, self.INERT_RUNTIME_IDS)
            expected_spatial_types = {49: 229, 51: 270, 63: 201}
            self.map["spatial_runtime"] = self.oracle.configure_spatial_runtime(
                records, spatial_field_ids, radius=8,
                expected_types={tile_id: expected_spatial_types[tile_id]
                                for tile_id in spatial_field_ids})
            self.map["runtime_object_counts"] = list(self.oracle.get(0x25CA048, "ii"))
        else:
            self.oracle.runtime_index_by_record = {index: index for index in range(len(records))}
        if enable_weapons:
            self.oracle.enable_weapon_slots()
        # The original Client iterates map objects. Large user maps need a
        # proportionally larger instruction budget even though they may run
        # more slowly than the compact training fixtures.
        self.call_limit = max(call_limit, self.map["records"] * 1_500)
        self._last_keys = ()
        self._branching = track_dirty
        if track_dirty:
            self.oracle.begin_branching()

    def step(self, n=1, keys=None):
        if n < 0:
            raise ValueError("n must be non-negative")
        if keys is not None:
            self._last_keys = tuple(keys)
        result = None
        for _ in range(n):
            self.oracle.refresh_compacted_collisions(call_limit=self.call_limit)
            self.oracle.refresh_spatial_runtime()
            result = self.oracle.step_world_chain(self._last_keys, call_limit=self.call_limit)
        return result if result is not None else self.read_state()

    def save_state(self):
        if not self._branching:
            # Interactive playback runs without the Python write hook so it can
            # maintain real time. Start tracking only when the user requests a
            # branch point.
            self.oracle.begin_branching()
            self._branching = True
        snapshot = self.oracle.save_branch_snapshot()
        snapshot["spatial_host_state"] = self.oracle.save_spatial_host_state()
        return snapshot

    def restore_state(self, state):
        super().restore_state(state)
        self.oracle.restore_spatial_host_state(state.get("spatial_host_state"))

    def reset(self):
        result = super().reset()
        self.oracle.restore_spatial_host_state()
        return result
