"""Fast, observation-driven stage07 navigation for the live baseline bot.

This module only chooses ordinary Client keys from the verified static route
graph. It never runs the native emulator or sends input itself.
"""
from __future__ import annotations
from collections import Counter, deque
import math
from sword_live_route_feedback import LiveRouteProgressGuard, contact_surface
from sword_navigation_graph import RouteEdge, SurfaceNode

LADDER_ALIGNMENT_TOLERANCE_PX = 8.0

def player_identity(row):
    return row.get("identity_key") or (
        f"{row.get('global_user_index')}:{row.get('nickname', '')}")


def policy_eligible_targets(players, local_slot):
    return [row for row in players
            if row.get("room_slot", row.get("slot")) != local_slot
            and row.get("present", True)
            and row.get("policy_targetable") is True
            and row.get("hp", 0) > 0]


def choose_target(players, local_slot, own, sticky_identity=None,
                  preferred_identity=None):
    targets = policy_eligible_targets(players, local_slot)
    if not targets:
        return None
    if preferred_identity is not None:
        preferred = next((row for row in targets
                          if player_identity(row) == preferred_identity), None)
        if preferred is not None:
            return preferred
    if sticky_identity is not None:
        current = next((row for row in targets
                        if player_identity(row) == sticky_identity), None)
        if current is not None:
            return current
    if own is None:
        return None
    ox, oy = own["pos"]
    return min(targets, key=lambda row:
               (row["pos"][0] - ox) ** 2 + (row["pos"][1] - oy) ** 2)


def _state_value(row, *keys, default=0):
    state = row.get("state") or {}
    for key in keys:
        if key in state:
            return state[key]
    return default


def incoming_attack_candidate(own, opponent, *, horizontal_radius=160.0,
                              vertical_radius=96.0):
    """A facing attack-state near us; evidence candidate, not hit attribution."""
    if (own is None or opponent is None or
            not opponent.get("present", True) or
            opponent.get("policy_targetable") is not True or
            opponent.get("hp", 0) <= 0):
        return None
    state = opponent.get("state") or {}
    attack_state = state.get("0x38", state.get("38", state.get("state38")))
    if attack_state not in range(15, 21):
        return None
    ox, oy = map(float, own["pos"])
    tx, ty = map(float, opponent["pos"])
    dx, dy = ox - tx, oy - ty
    if abs(dx) > horizontal_radius or abs(dy) > vertical_radius:
        return None
    facing_right = state.get("0xb0", state.get("b0", 0)) == 0
    if (dx >= 0) != facing_right:
        return None
    away = ("LEFT" if tx > ox else "RIGHT" if tx < ox else
            ("LEFT" if _state_value(own, "0xb0", "b0", "stateb0") == 0
             else "RIGHT"))
    return {"identity": player_identity(opponent),
            "room_slot": opponent.get("room_slot", opponent.get("slot")),
            "state38_raw": attack_state, "weapon": opponent.get("weapon"),
            "relative_dx": dx, "relative_dy": dy,
            "distance": math.hypot(dx, dy), "roll_direction": away}


class OpponentBehaviorWindows:
    """Small in-memory, per-identity window for fast threat adaptation."""

    def __init__(self, window_seconds=5.0):
        self.window_seconds = float(window_seconds)
        self.samples_by_identity = {}

    def update(self, now, own, players, local_slot):
        if own is None:
            return [], None, []
        ox, oy = map(float, own["pos"])
        profiles, current_candidates = [], []
        for opponent in players:
            slot = opponent.get("room_slot", opponent.get("slot"))
            if slot == local_slot or not opponent.get("present", True):
                continue
            identity = player_identity(opponent)
            state = opponent.get("state") or {}
            state38 = state.get("0x38", state.get("38", state.get("state38")))
            px, py = map(float, opponent["pos"])
            threat = incoming_attack_candidate(own, opponent)
            history = self.samples_by_identity.setdefault(identity, deque())
            history.append({
                "time": float(now), "x": px, "y": py,
                "distance": math.hypot(px - ox, py - oy),
                "state38": state38, "weapon": opponent.get("weapon"),
                "incoming_attack_candidate": threat is not None,
            })
            while history and now - history[0]["time"] > self.window_seconds:
                history.popleft()
            if threat is not None:
                current_candidates.append(threat)
            last_candidate = next((sample["time"] for sample in reversed(history)
                                   if sample["incoming_attack_candidate"]), None)
            state_counts = Counter(str(sample["state38"]) for sample in history
                                   if sample["state38"] is not None)
            candidate_samples = sum(sample["incoming_attack_candidate"]
                                    for sample in history)
            first, last = history[0], history[-1]
            profiles.append({
                "identity": identity, "room_slot": slot,
                "window_seconds": self.window_seconds,
                "sample_count": len(history),
                "state38_raw_sample_counts": dict(state_counts),
                "weapon_slots_observed": sorted({sample["weapon"] for sample in history
                                                  if sample["weapon"] is not None}),
                "incoming_attack_candidate_samples": candidate_samples,
                "incoming_attack_candidate_fraction": round(
                    candidate_samples / len(history), 3) if history else 0.0,
                "last_incoming_attack_candidate_age_s": (
                    round(float(now) - last_candidate, 3)
                    if last_candidate is not None else None),
                "relative_distance_delta_px": round(last["distance"] - first["distance"], 1),
                "opponent_position_delta_px": [round(last["x"] - first["x"], 1),
                                                round(last["y"] - first["y"], 1)],
            })
        present = {profile["identity"] for profile in profiles}
        for identity in list(self.samples_by_identity):
            history = self.samples_by_identity[identity]
            if identity not in present and now - history[-1]["time"] > 30:
                del self.samples_by_identity[identity]
        if current_candidates:
            preferred = min(current_candidates, key=lambda row: row["distance"])["identity"]
        else:
            recent = [profile for profile in profiles
                      if profile["last_incoming_attack_candidate_age_s"] is not None
                      and profile["last_incoming_attack_candidate_age_s"] <= self.window_seconds
                      and any(row.get("identity_key") == profile["identity"] and
                              row.get("policy_targetable") is True for row in players)]
            recent.sort(key=lambda profile: profile["last_incoming_attack_candidate_age_s"])
            preferred = recent[0]["identity"] if recent else None
        return profiles, preferred, current_candidates


def needs_parachute_recovery(graph, own, previous_y=None):
    """Whether a falling local player lacks a mapped support directly below.

    This is only a live recovery trigger, not a claim that every airborne
    transition needs a parachute. DC is kept as raw state and any nonzero
    value suppresses another deploy attempt.
    """
    if own is None or own.get("hp", 0) <= 0:
        return False
    state = own.get("state") or {}
    if state.get("0x38", state.get("38", state.get("state38"))) != 9:
        return False
    if state.get("0xdc", state.get("dc", state.get("statedc", 0))) != 0:
        return False
    x, y = map(float, own["pos"])
    if previous_y is None or y <= float(previous_y):
        return False
    has_support_below = any(
        surface.pixel_y >= y - 24.0
        and surface.x0 * 32.0 - 32.0 <= x <= (surface.x1 + 1) * 32.0 + 32.0
        for surface in graph.surfaces
    )
    return not has_support_below


def parachute_glide_action(own, target, navigation, previous_direction=None):
    """Steer horizontally toward the next safe transition while DC is active.

    Vertical keys fight the passive parachute/wind trajectory. The live
    controller therefore releases UP/DOWN and keeps only a small horizontal
    correction, using the route waypoint when available.
    """
    if own is None:
        return (), {"reason": "no_local_player"}
    own_x = float(own["pos"][0])
    edge = (navigation or {}).get("next_edge") or {}
    waypoint = edge.get("waypoint")
    if waypoint and len(waypoint) >= 1:
        aim_x = float(waypoint[0])
        aim_source = "route_waypoint"
    elif target is not None:
        aim_x = float(target["pos"][0])
        aim_source = "target_x"
    else:
        return (), {"reason": "no_horizontal_landing_aim"}
    dx = aim_x - own_x
    direction = hysteretic_horizontal(dx, previous_direction,
                                      deadzone=12.0, switch_margin=24.0)
    keys = (direction,) if direction else ()
    return keys, {"reason": "horizontal_only_while_parachute_active",
                  "aim_source": aim_source, "aim_x": aim_x,
                  "relative_dx": dx, "vertical_keys_released": True}


def hysteretic_horizontal(dx, previous_direction=None, *, deadzone=28.0,
                           switch_margin=44.0):
    if abs(dx) <= deadzone:
        return None
    desired = "RIGHT" if dx > 0 else "LEFT"
    if previous_direction and desired != previous_direction and abs(dx) < switch_margin:
        return None
    return desired


def _route_action(graph, route, own, previous_direction=None):
    path = route.get("path") or []
    if not path:
        return (), None
    edge = path[0]
    primitive = edge.primitive
    x, _ = own["pos"]
    dx = float(edge.waypoint[0]) - float(x)
    direction = hysteretic_horizontal(dx, previous_direction,
                                      deadzone=22.0, switch_margin=40.0)
    future_primitive = (path[1].primitive if len(path) > 1 else
                        route.get("followup_primitive"))
    control_waypoint = edge.waypoint
    phase = "approach"
    on_ladder = _state_value(own, "0x74", "74", "state74", default=-1) == 1
    airborne = _state_value(own, "0x38", "38", "state38") in (3, 9)

    if primitive == "walk":
        keys = (direction,) if direction else ()
        if edge.waypoint[1] < float(own["pos"][1]) - 28 and not airborne:
            keys = (*keys, "UP")
    elif primitive == "ladder_attach":
        if abs(dx) > LADDER_ALIGNMENT_TOLERANCE_PX:
            # Do not apply the prior-walk direction hysteresis while aligning
            # to a ladder: it can suppress the needed reversal and hold forever.
            keys = (("RIGHT" if dx > 0 else "LEFT"),)
        else:
            climb = ("DOWN" if future_primitive == "ladder_descend" else "UP")
            keys = (climb,)
    elif primitive == "ladder_ascend":
        keys = (("RIGHT" if dx > 0 else "LEFT",)
                if abs(dx) > LADDER_ALIGNMENT_TOLERANCE_PX else
                ("UP",))
        if on_ladder and abs(float(own["pos"][1]) - edge.waypoint[1]) <= 28:
            landing = graph.nodes.get(edge.target)
            if isinstance(landing, SurfaceNode):
                keys = ("RIGHT" if landing.center_x >= float(x) else "LEFT", "UP")
                phase = "ladder_exit"
    elif primitive == "ladder_descend":
        keys = (("RIGHT" if dx > 0 else "LEFT",)
                if abs(dx) > LADDER_ALIGNMENT_TOLERANCE_PX else
                ("DOWN",))
    elif primitive == "jump_or_running_jump":
        keys = tuple(([direction] if direction else []) + ([] if airborne else ["UP"]))
        phase = "air_steer" if airborne else "takeoff"
    elif primitive == "safe_drop":
        # DOWN is a roll input in this Client and turns an ordinary drop into
        # a roll. Geometry-selected drops need horizontal steering only. Also
        # bypass reversal hysteresis here so a previous chase direction cannot
        # leave the bot holding beside the selected drop point.
        # The waypoint is just beyond the source ledge. A normal chase-sized
        # deadzone would stop on the platform and leave the character waiting.
        drop_direction = ("RIGHT" if dx > 1.0 else
                          "LEFT" if dx < -1.0 else None)
        source = graph.nodes.get(edge.source)
        if (isinstance(source, SurfaceNode) and not airborne and
                abs(float(own["pos"][1]) - source.pixel_y) <= 4):
            # Centre crossing a geometric boundary is not proof of falling;
            # continue off the ledge until a vertical/state change is observed.
            drop_direction = "RIGHT" if edge.waypoint[0] > source.center_x else "LEFT"
            phase = "leave_source_ledge"
        keys = (drop_direction,) if drop_direction else ()
    elif primitive == "airborne_horizontal_transition":
        support = graph.nodes.get(edge.source)
        if (isinstance(support, SurfaceNode) and not airborne and not on_ladder and
                abs(float(own["pos"][1]) - support.pixel_y) <= 4):
            # The lower platform's centre may be UNDER our current floor.
            # Leave a source ledge first; horizontal alignment cannot drop us.
            exits = [support.x0 * 32.0 - 16.0, (support.x1 + 1) * 32.0 + 16.0]
            exits = [exit_x for exit_x in exits if 0 < exit_x < graph.width * 32]
            if not exits:
                return (), None
            exit_x = min(exits, key=lambda v: abs(v - edge.waypoint[0]))
            control_waypoint = (exit_x, support.pixel_y)
            keys = ("RIGHT" if exit_x > support.center_x else "LEFT",)
            phase = "leave_source_ledge"
        else:
            direction = "RIGHT" if dx > 8 else "LEFT" if dx < -8 else None
            keys = (direction,) if direction else ()
            phase = "air_steer" if keys else "await_contact"
    else:
        # Wind/parachute and unknown transitions stay out of this first live
        # controller until they have a direct live observation path.
        keys = ()

    if not keys and airborne and primitive in (
            "safe_drop", "jump_or_running_jump", "airborne_horizontal_transition"):
        phase = "await_contact"

    return keys, {"source": edge.source, "target": edge.target,
                  "primitive": primitive, "condition": edge.condition,
                  "verification": edge.verification,
                  "waypoint": list(edge.waypoint),
                  "control_waypoint": list(control_waypoint), "phase": phase,
                  "followup_primitive": future_primitive}


def _same_surface(graph, own, target):
    # A nearest surface is only a geometric guess while a player is airborne.
    # Use actual surface contact for same-level combat; route otherwise.
    local_surface = contact_surface(graph, own)
    target_surface = contact_surface(graph, target)
    return local_surface, target_surface


def _live_route(graph, local_state, target_state, own, previous_direction, excluded):
    """Bounded replan around edges with no executable action at this state."""
    excluded = set(excluded)
    skipped = []
    for _ in range(8):
        route = graph.route_candidates(local_state, target_state, wind_active=False,
                                       excluded_edges=excluded)
        path = route.get("path") or []
        if not path:
            break
        keys, edge = _route_action(graph, route, own, previous_direction)
        if keys or (edge and edge.get("phase") == "await_contact"):
            return route, skipped
        key = (path[0].source, path[0].target, path[0].primitive, path[0].condition)
        skipped.append(list(key))
        excluded.add(key)
    # No full route: take a geometry-derived intermediate hop only if it
    # improves target distance. This can move toward an accessible ladder or
    # support without pretending the remaining route has been solved.
    source = getattr(graph, "nodes", {}).get(route.get("source"))
    if isinstance(source, SurfaceNode):
        tx, ty = float(target_state["x"]), float(target_state["y"])
        distance = lambda x, y: abs(tx - x) + abs(ty - y)
        current = distance(float(own["pos"][0]), float(own["pos"][1]))
        candidates = []
        for candidate in graph.outgoing(source.node_id, wind_active=False):
            key = (candidate.source, candidate.target, candidate.primitive, candidate.condition)
            score = distance(*candidate.waypoint)
            if key not in excluded and score + 8 < current:
                candidates.append((score, candidate))
        for _, candidate in sorted(candidates, key=lambda item: (item[0], item[1].target)):
            partial = {**route, "path": [candidate], "partial": True}
            keys, _ = _route_action(graph, partial, own, previous_direction)
            if keys:
                return partial, skipped
    return {**route, "path": []}, skipped


def decide_live_action(graph, own, target, *, now, started,
                       previous_direction=None, map_verified=False,
                       excluded_edges=(), active_edge=None):
    """Return mode, requested keys, and an auditable navigation decision."""
    if own is None:
        return "WAIT_LOCAL_PLAYER", (), {"reason": "local_slot_unresolved"}
    if not map_verified:
        return "WAIT_STAGE07_MAP", (), {"reason": "runtime_collision_not_verified"}
    if own.get("hp", 0) <= 0:
        return "WAIT_RESPAWN", (), {"reason": "local_hp_zero"}
    if _state_value(own, "0xc0", "c0", "statec0") == 6:
        return "WAIT_JAJA", (), {"reason": "local_jaja_state"}
    if target is None:
        # Stay on the current support and keep collecting the live room state.
        return "WAIT_OPPONENT", (), {"reason": "no_policy_targetable_opponent"}
    if _state_value(own, "0xc0", "c0", "statec0") in (3, 4):
        return "NAV_MOTION_WAIT", (), {"reason": "roll_motion_locks_direction_and_jump"}

    if active_edge is not None:
        edge = RouteEdge(**{key: active_edge[key] for key in (
            "source", "target", "primitive", "waypoint", "condition", "verification")})
        if LiveRouteProgressGuard.edge_key(active_edge) not in excluded_edges:
            keys, next_edge = _route_action(graph, {
                "path": [edge], "followup_primitive": active_edge.get("followup_primitive")},
                own, previous_direction)
            return ("NAVIGATE" if keys else "NAV_TRANSITION_WAIT"), keys, {
                "reason": "continue_dispatched_transition_until_observed_outcome",
                "next_edge": next_edge, "target_identity": player_identity(target)}

    local_surface, target_surface = _same_surface(graph, own, target)
    own_is_on_ladder = _state_value(own, "0x74", "74", "state74", default=-1) == 1
    target_is_on_ladder = _state_value(
        target, "0x74", "74", "state74", default=-1) == 1
    if own_is_on_ladder and target_is_on_ladder:
        own_ladder = graph.nearest_ladder({"x": own["pos"][0],
                                           "y": own["pos"][1]})
        target_ladder = graph.nearest_ladder({"x": target["pos"][0],
                                              "y": target["pos"][1]})
        if (own_ladder is not None and target_ladder is not None and
                own_ladder.node_id == target_ladder.node_id):
            dx = float(target["pos"][0]) - float(own["pos"][0])
            dy = float(target["pos"][1]) - float(own["pos"][1])
            if abs(dy) > 72.0:
                keys = ("UP",) if dy < 0 else ("DOWN",)
                mode = "COMBAT_LADDER_APPROACH"
            elif abs(dx) > 48.0:
                keys = ("RIGHT" if dx > 0 else "LEFT",)
                mode = "COMBAT_LADDER_APPROACH"
            else:
                facing_right = _state_value(own, "0xb0", "b0", "stateb0") == 0
                if abs(dx) > 4.0 and (dx > 0) != facing_right:
                    keys = ("RIGHT" if dx > 0 else "LEFT",)
                    mode = "COMBAT_LADDER_FACE"
                else:
                    keys = ("Z",) if now % 0.8 < 0.12 else ()
                    mode = "COMBAT_LADDER_ATTACK"
            return mode, keys, {
                "reason": "both_players_on_same_ladder",
                "ladder_id": own_ladder.node_id,
                "target_identity": player_identity(target),
                "relative_dx": dx, "relative_dy": dy}
    if local_surface is not None and target_surface is not None and \
            local_surface.node_id == target_surface.node_id:
        dx = float(target["pos"][0]) - float(own["pos"][0])
        dy = float(target["pos"][1]) - float(own["pos"][1])
        horizontal = hysteretic_horizontal(dx, previous_direction)
        if abs(dx) > 60.0:
            keys = (horizontal,) if horizontal else ()
            return "COMBAT_APPROACH", keys, {
                "reason": "same_surface_horizontal_approach",
                "source_surface": local_surface.node_id,
                "target_surface": target_surface.node_id,
                "target_identity": player_identity(target)}
        if abs(dy) > 78.0:
            return "COMBAT_ALIGN", (), {
                "reason": "same_surface_vertical_separation",
                "source_surface": local_surface.node_id,
                "target_surface": target_surface.node_id,
                "target_identity": player_identity(target)}
        facing_right = _state_value(own, "0xb0", "b0", "stateb0") == 0
        desired_right = dx > 0
        if abs(dx) > 4.0 and desired_right != facing_right:
            return "COMBAT_FACE", ("RIGHT" if desired_right else "LEFT",), {
                "reason": "turn_toward_target", "source_surface": local_surface.node_id,
                "target_surface": target_surface.node_id,
                "target_identity": player_identity(target)}
        keys = ("Z",) if now % 0.8 < 0.12 else ()
        return "COMBAT_ATTACK", keys, {
            "reason": "same_surface_attack_baseline",
            "source_surface": local_surface.node_id,
            "target_surface": target_surface.node_id,
            "target_identity": player_identity(target)}

    local_state = {"x": own["pos"][0], "y": own["pos"][1],
                   "74": _state_value(own, "0x74", "74", "state74", default=-1)}
    target_state = {"x": target["pos"][0], "y": target["pos"][1],
                    "74": _state_value(target, "0x74", "74", "state74", default=-1)}
    # Wind routes are intentionally not enabled here; live wind observation is
    # not yet authoritative enough to make their conditional edge executable.
    route, skipped = _live_route(graph, local_state, target_state, own,
                                 previous_direction, excluded_edges)
    connected = route.get("source") is not None and route.get("target") is not None
    cursor = route.get("source")
    for edge in route.get("path", ()):
        if edge.source != cursor:
            connected = False
            break
        cursor = edge.target
    connected = connected and cursor == route.get("target")
    if (not connected and not route.get("partial")) or not route.get("path"):
        # Both airborne players can project to the same nearest graph surface
        # while being vertically separated. Keep horizontal pursuit responsive
        # instead of returning an empty COMBAT_ALIGN action for every poll.
        dx = float(target["pos"][0]) - float(own["pos"][0])
        dy = float(target["pos"][1]) - float(own["pos"][1])
        if (dy < -78.0 and
                _state_value(own, "0x38", "38", "state38") == 7):
            direction = ("RIGHT" if dx > 22 else "LEFT" if dx < -22 else None)
            return "COMBAT_JUMP_ALIGN", tuple(([direction] if direction else []) + ["UP"]), {
                "reason": "target_above_grounded_player", "relative_dx": dx,
                "relative_dy": dy, "target_identity": player_identity(target)}
        if (local_surface is None and not own_is_on_ladder and
                route.get("source") is not None and
                route.get("source") == route.get("target")):
            dx = float(target["pos"][0]) - float(own["pos"][0])
            dy = float(target["pos"][1]) - float(own["pos"][1])
            if abs(dx) > 22.0:
                direction = "RIGHT" if dx > 0 else "LEFT"
                return "COMBAT_AIR_ALIGN", (direction,), {
                    "reason": "airborne_same_region_horizontal_alignment",
                    "source_surface": route.get("source"),
                    "target_surface": route.get("target"),
                    "target_identity": player_identity(target),
                    "relative_dx": dx, "relative_dy": dy}
        if local_surface is None and not own_is_on_ladder:
            dx = float(target["pos"][0]) - float(own["pos"][0])
            dy = float(target["pos"][1]) - float(own["pos"][1])
            if abs(dx) > 12.0:
                direction = "RIGHT" if dx > 0 else "LEFT"
                return "COMBAT_AIR_RECOVERY", (direction,), {
                    "reason": "airborne_no_route_horizontal_recovery",
                    "source_surface": route.get("source"),
                    "target_surface": route.get("target"),
                    "target_identity": player_identity(target),
                    "relative_dx": dx, "relative_dy": dy}
            own_state38 = _state_value(own, "0x38", "38", "state38")
            if dy < -78.0 and own_state38 == 7:
                return "COMBAT_JUMP_ALIGN", ("UP",), {
                    "reason": "target_above_same_projected_region",
                    "source_surface": route.get("source"),
                    "target_surface": route.get("target"),
                    "target_identity": player_identity(target),
                    "relative_dx": dx, "relative_dy": dy}
        return "NAV_NO_ROUTE", (), {
            "reason": "no_connected_geometry_route",
            "source_surface": route.get("source"),
            "target_surface": route.get("target"),
            "target_identity": player_identity(target),
            "excluded_edges": [list(edge) for edge in excluded_edges],
            "non_executable_edges": skipped}
    keys, next_edge = _route_action(graph, route, own, previous_direction)
    if next_edge and next_edge.get("phase") == "await_contact":
        return "NAV_TRANSITION_WAIT", (), {
            "reason": "await_observed_contact", "next_edge": next_edge,
            "target_identity": player_identity(target)}
    if next_edge is None or not keys:
        return "NAV_HOLD", (), {
            "reason": "route_edge_has_no_safe_live_action",
            "source_surface": route.get("source"),
            "target_surface": route.get("target"),
            "target_identity": player_identity(target),
            "next_edge": next_edge}
    return ("NAV_RECOVERY" if route.get("partial") else "NAVIGATE"), keys, {
        "reason": "intermediate_hop_toward_target" if route.get("partial") else "geometry_route_next_edge",
        "source_surface": route.get("source"),
        "target_surface": route.get("target"),
        "target_identity": player_identity(target),
        "route_connected_to_target": connected,
        "route_length": len(route["path"]),
        "non_executable_edges": skipped,
        "next_edge": next_edge}
