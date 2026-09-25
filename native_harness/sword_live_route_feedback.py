"""Re-observe dispatched live navigation; no emulator or keyboard IO."""
from __future__ import annotations

import math


def state_value(row, key, default=0):
    state = (row or {}).get("state") or {}
    return state.get("0x" + key, state.get(key, state.get("state" + key, default)))


def contact_surface(graph, own):
    if own is None or state_value(own, "74", -1) == 1:
        return None
    # Being near a platform during ascent/fall is not evidence of contact.
    if state_value(own, "38") in (3, 5, 9) or state_value(own, "dc") != 0:
        return None
    return graph.surface_at(dict(zip(("x", "y"), own["pos"])), tolerance=4.0)


class LiveRouteProgressGuard:
    """Session-local failures scoped to an edge and opponent region/posture.

    Time alone never makes a failed edge eligible again. Only actions actually
    dispatched by the route controller start an attempt. Live contact evidence
    is logged separately and never promotes a geometry edge to native-verified.
    """

    def __init__(self, *, stuck_seconds=1.5, progress_distance=8.0,
                 attempt_seconds=8.0):
        self.stuck_seconds = float(stuck_seconds)
        self.progress_distance = float(progress_distance)
        self.attempt_seconds = float(attempt_seconds)
        self.active = None
        self.failures = {}

    @staticmethod
    def edge_key(edge):
        if not edge:
            return None
        return (edge.get("source"), edge.get("target"),
                edge.get("primitive"), edge.get("condition", "always"))

    @staticmethod
    def context(graph, target):
        if target is None:
            return None
        node = graph.surface_for_target({"x": target["pos"][0],
                                         "y": target["pos"][1],
                                         "74": state_value(target, "74", -1)})
        identity = target.get("identity_key") or (
            f"{target.get('global_user_index')}:{target.get('nickname', '')}")
        return (identity, node.node_id if node else None,
                state_value(target, "74", -1) == 1)

    def reset(self):
        self.active = None
        self.failures.clear()

    def excluded_edges(self, now, *, graph, target):
        context = self.context(graph, target)
        return tuple(key for key, ctx in self.failures if ctx == context)

    def _finish(self, now, own, status, reason, *, failed=False):
        active = self.active
        key = self.edge_key(active["edge"])
        event = {"edge": list(key), "status": status, "reason": reason,
                 "position": list(own["pos"]) if own else None,
                 "elapsed_seconds": round(float(now) - active["started"], 3),
                 "verification": "live_observation_only"}
        if failed:
            self.failures[(key, active["context"])] = event
            event["retry_policy"] = "exclude_in_same_target_context_for_session"
        self.active = None
        return event

    def observe(self, now, own, *, graph, target, control_available):
        active = self.active
        if active is None:
            return None
        if (not control_available or own is None or own.get("hp", 0) <= 0 or
                state_value(own, "c0") == 6):
            return self._finish(now, own, "cancelled", "control_or_local_state_changed")
        if self.context(graph, target) != active["context"]:
            return self._finish(now, own, "cancelled", "target_context_changed")
        if own.get("hp", 0) < active["hp"]:
            return self._finish(now, own, "cancelled", "damage_confounds_navigation")
        if now <= active["started"]:
            return None
        pos = tuple(map(float, own["pos"]))
        edge = active["edge"]
        surface = contact_surface(graph, own)
        on_ladder = state_value(own, "74", -1) == 1
        if on_ladder and edge["primitive"] == "ladder_attach":
            ladder = graph.nearest_ladder(dict(zip(("x", "y"), pos)))
            if ladder is not None and ladder.node_id == edge["target"]:
                return self._finish(now, own, "ladder_entered", "observed_ladder_state")
        if surface is None and not on_ladder:
            active["departed"] = True
        # Require two observations on the same support, with stable Y, before
        # reporting landing (a nearest-surface projection is never enough).
        contact = surface.node_id if surface else None
        stable = (contact is not None and contact == active.get("contact") and
                  abs(pos[1] - active["last_pos"][1]) <= 1.0)
        active["contact"] = contact
        active["last_pos"] = pos
        if stable and contact == edge["target"]:
            return self._finish(now, own, "landed", "observed_target_surface_contact")
        if stable and (active["departed"] or contact != edge["source"]):
            return self._finish(now, own, "failed", "landed_wrong_surface", failed=True)
        if now - active["started"] >= self.attempt_seconds:
            return self._finish(now, own, "failed", "transition_deadline_exceeded", failed=True)
        waypoint = edge.get("control_waypoint", edge["waypoint"])
        distance = math.dist(pos, waypoint)
        if distance <= active["best_distance"] - self.progress_distance:
            active["best_distance"] = distance
            active["last_progress"] = float(now)
            return {"edge": list(self.edge_key(edge)), "status": "progress",
                    "reason": "closer_to_control_waypoint", "position": list(pos),
                    "verification": "live_observation_only"}
        if now - active["last_progress"] >= self.stuck_seconds:
            return self._finish(now, own, "failed", "no_route_progress", failed=True)
        return None

    def record_action(self, now, own, edge, *, graph, target, keys, sent):
        """Call after final overrides and output gating, not at planning time."""
        if not sent or own is None or edge is None:
            self.active = None
            return
        key = self.edge_key(edge)
        context = self.context(graph, target)
        if self.active and (self.edge_key(self.active["edge"]),
                            self.active["context"]) == (key, context):
            old_waypoint = self.active["edge"].get("control_waypoint")
            if old_waypoint != edge.get("control_waypoint"):
                self.active["best_distance"] = math.dist(
                    own["pos"], edge.get("control_waypoint", edge["waypoint"]))
                self.active["last_progress"] = float(now)
            self.active["edge"] = dict(edge)
            return
        self.active = None
        if not keys or (key, context) in self.failures:
            return
        pos = tuple(map(float, own["pos"]))
        self.active = {"edge": dict(edge), "context": context,
                       "started": float(now), "last_progress": float(now),
                       "best_distance": math.dist(pos, edge.get("control_waypoint", edge["waypoint"])),
                       "last_pos": pos, "contact": None,
                       "departed": False, "hp": own.get("hp", 0)}

    def continuation_edge(self):
        return self.active["edge"] if self.active else None
