"""Continuous rectangle collision, independent of uncalibrated game physics.

Coordinates are in cells, positive Y downward, position = body bottom center.
Standing edge contact is allowed; positive-area penetration is a collision.
Sweeps are exact for straight translation with a fixed rectangular body.
They do NOT establish the game's hitbox, curved motion, slope response or clear.
User lab04 correction: a one-row rock platform with open underside can be
mounted from below in a case where a filled nine-cell pillar cannot. This
rectangle-only kernel does not reproduce that behavior. Do not infer global
one-way platforms or inflate jump height to make that case pass.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.left, self.top, self.right, self.bottom)):
            raise ValueError("Rectangle coordinates must be finite")
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("Rectangle must have positive area")


@dataclass(frozen=True)
class Body:
    width: float
    height: float

    def __post_init__(self):
        if not all(math.isfinite(v) and v > 0 for v in (self.width, self.height)):
            raise ValueError("Body dimensions must be positive and finite")


def _axis_interval(position, delta, low, high):
    """Open time interval where a coordinate is strictly inside (low, high)."""
    if delta == 0:
        return (-math.inf, math.inf) if low < position < high else None
    a, b = (low-position)/delta, (high-position)/delta
    return min(a, b), max(a, b)


def sweep_rect(start, end, body: Body, obstacle: Rect):
    """Return penetration interval in normalized time [0,1], or None.

    entry/exit are boundary times (contact), not positive-area penetration
    themselves. A single tangent contact is not a penetrating interval.
    No launch/landing part of the sweep is skipped.
    """
    if len(start) != 2 or len(end) != 2 or not all(math.isfinite(v) for v in (*start, *end)):
        raise ValueError("Positions must be two finite coordinates")
    # Minkowski expansion for bottom-center representation.
    intervals = [
        _axis_interval(start[0], end[0]-start[0],
                       obstacle.left-body.width/2, obstacle.right+body.width/2),
        _axis_interval(start[1], end[1]-start[1], obstacle.top, obstacle.bottom+body.height),
    ]
    if any(i is None for i in intervals):
        return None
    entry = max(0., *(i[0] for i in intervals))
    exit_time = min(1., *(i[1] for i in intervals))
    if entry >= exit_time:
        return None
    return {"entry_t": entry, "exit_t": exit_time}


def trace_polyline(points, body: Body, obstacles):
    """Inspect supplied path segments; does not invent or fit a trajectory.

    Times strictly increase. Body/trajectory uncertainty is the caller's
    responsibility. Empty hits means only this supplied geometry is clear.
    Slopes, dynamics and unknown tiles must not be passed as empty space by a
    caller claiming to check a whole LMF map.
    """
    if len(points) < 2:
        raise ValueError("At least two timed points are required")
    if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError("Each point must contain finite (time, x, y)")
    if any(b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise ValueError("Times must strictly increase")
    obstacles = list(obstacles)
    hits = []
    for segment, (a, b) in enumerate(zip(points, points[1:])):
        for index, obstacle in enumerate(obstacles):
            hit = sweep_rect(a[1:], b[1:], body, obstacle)
            if hit:
                hits.append({"segment": segment, "obstacle": index,
                             "entry_time": a[0]+hit['entry_t']*(b[0]-a[0]),
                             "exit_time": a[0]+hit['exit_t']*(b[0]-a[0])})
    return {"status": "collision_in_supplied_geometry" if hits else "supplied_geometry_clear",
            "engine_clear_certified": False,
            "assumptions": "fixed rectangular body; linear path segments; static rectangles; edge touch allowed",
            "hits": sorted(hits, key=lambda h: (h['entry_time'], h['obstacle']))}
