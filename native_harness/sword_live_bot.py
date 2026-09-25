"""Foreground-only stage07 PRACTICE baseline live controller.

F8 toggles control, Shift yields to manual input, and F9 emergency-stops.
The controller reads Client memory but injects only ordinary keyboard events
while the selected Client remains the foreground process.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import struct
import time

from human_play_recorder import KEYS, foreground_pid
from live_state import Reader
from sword_live_state import read_room_snapshot, require_supported_client
from sword_practice_runtime import SwordPracticeRecorder
from combat_live_trace import _runtime_player_row, _event_json
from sword_live_navigation import (OpponentBehaviorWindows, choose_target,
                                   decide_live_action, needs_parachute_recovery,
                                   LiveRouteProgressGuard,
                                   parachute_glide_action, player_identity)
from sword_combat_experience import AdaptiveDodgeMemory
from sword_demonstration import demonstration_sample
from sword_fight_learning import SwordFightLearningRecorder
from sword_navigation_graph import Stage07RouteGraph
from sword_stage07_world import (OBJECTIVE_WIND_LEAF_COUNT,
                                 load_stage07_static_world)

u = C.WinDLL("user32", use_last_error=True)
u.GetAsyncKeyState.argtypes = [C.c_int]
u.GetAsyncKeyState.restype = C.c_short
u.keybd_event.argtypes = [W.BYTE, W.BYTE, W.DWORD, C.c_size_t]
u.keybd_event.restype = None
F8, F9, SHIFT = 0x77, 0x78, 0x10
KEYUP = 0x0002
CONTROL_KEYS = {key: KEYS[key] for key in
                ("LEFT", "RIGHT", "UP", "DOWN", "C", "Z",
                 "1", "2", "3", "4")}


def down(vk: int) -> bool:
    return bool(u.GetAsyncKeyState(vk) & 0x8000)


class KeyOutput:
    """Track injected keys and always send matching key-up edges."""
    def __init__(self):
        self.held: set[str] = set()
        self.events: list[dict] = []

    def set(self, keys, reason="action_update"):
        wanted = set(keys)
        for key in sorted(self.held - wanted):
            u.keybd_event(CONTROL_KEYS[key], 0, KEYUP, 0)
            self.events.append({"key": key, "edge": "key_up", "reason": reason})
        for key in wanted - self.held:
            u.keybd_event(CONTROL_KEYS[key], 0, 0, 0)
            self.events.append({"key": key, "edge": "key_down", "reason": reason})
        self.held = wanted

    def release_all_keys(self, reason="release_all"):
        self.set((), reason=reason)

    def take_events(self):
        events, self.events = self.events, []
        return events


def acquire_reader(wait_seconds: float):
    deadline = time.perf_counter() + wait_seconds
    while time.perf_counter() < deadline:
        pid = foreground_pid()
        if pid:
            try:
                return pid, Reader(pid)
            except (OSError, StopIteration, RuntimeError):
                pass
        time.sleep(0.1)
    raise TimeoutError("Client.exe was not selected in the foreground before timeout")


def read_tick(reader: Reader):
    snapshot = read_room_snapshot(reader)
    # Preserve the raw live wind-object count; do not infer wind force from
    # parachute motion alone.
    snapshot["global_wind_leaf_count_raw"] = reader.get(
        OBJECTIVE_WIND_LEAF_COUNT, "I")[0]
    return snapshot


def runtime_stage07_match(reader, map_size, expected_collision):
    """Require live collision bytes to match the hash-pinned stage07 parse."""
    if tuple(map_size) != (60, 60):
        return False, {"reason": "wrong_map_dimensions", "map_size": list(map_size)}
    try:
        grid_pointer = reader.get(0x08952E4C, "I")[0]
        if grid_pointer < 0x10000:
            return False, {"reason": "invalid_runtime_collision_pointer",
                           "pointer": grid_pointer}
        raw = reader.read(grid_pointer, 60 * 60 * 2)
        runtime_grid = struct.unpack("<3600H", raw)
    except (OSError, RuntimeError, ValueError, struct.error) as exc:
        return False, {"reason": "runtime_collision_read_failed",
                       "detail": f"{type(exc).__name__}: {exc}"}
    if tuple(expected_collision) != runtime_grid:
        mismatches = [index for index, (expected, actual) in
                      enumerate(zip(expected_collision, runtime_grid))
                      if expected != actual]
        return False, {"reason": "runtime_collision_differs_from_stage07",
                       "mismatch_count": len(mismatches),
                       "first_mismatch": ([mismatches[0] % 60,
                                           mismatches[0] // 60]
                                          if mismatches else None)}
    return True, {"reason": "exact_stage07_runtime_collision_match",
                  "collision_cells": len(runtime_grid)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("logs/sword_live_bot.jsonl"))
    parser.add_argument("--experience-state", type=Path,
                        default=Path("logs/sword_combat_experience.json"))
    parser.add_argument("--seconds", type=float, default=300)
    parser.add_argument("--until-stopped", action="store_true",
                        help="run until F9 or Ctrl+C instead of the --seconds timeout")
    parser.add_argument("--wait-seconds", type=float, default=60)
    parser.add_argument("--decision-ms", type=float, default=50)
    parser.add_argument("--act", action="store_true",
                        help="permit ordinary keyboard events after F8 is armed")
    parser.add_argument("--record-demonstration", action="store_true",
                        help="record human v9 input/state samples; F8 starts/pauses capture, no bot input")
    parser.add_argument("--fight-learning-output", type=Path,
                        default=Path("logs/sword_fight_learning.jsonl"),
                        help="append time-aligned, scored duel transitions while the bot controls")
    args = parser.parse_args()
    if args.record_demonstration and args.act:
        parser.error("record-demonstration and act are mutually exclusive")
    if not 10 <= args.decision_ms <= 100:
        parser.error("decision-ms must be between 10 and 100")
    pid, reader = acquire_reader(args.wait_seconds)
    try:
        require_supported_client(reader)
        static_world = load_stage07_static_world()
        route_graph = Stage07RouteGraph(static_world)
    except Exception:
        reader.close()
        raise
    output = KeyOutput()
    recorder = SwordPracticeRecorder(session_id=f"sword-live-{pid}-{int(time.time())}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.fight_learning_output.parent.mkdir(parents=True, exist_ok=True)
    experience_memory = AdaptiveDodgeMemory(args.experience_state)
    fight_learning = SwordFightLearningRecorder(recorder.session_id)
    deadline = None if args.until_stopped else time.perf_counter() + args.seconds
    started = time.perf_counter()
    tick = 0
    observed_slots: set[int] = set()
    observed_identities: set[str] = set()
    previous_direction = None
    sticky_target_identity = None
    previous_logged_target = None
    opponent_windows = OpponentBehaviorWindows(window_seconds=5.0)
    route_progress_guard = LiveRouteProgressGuard()
    navigation_context = None
    last_navigation_game_ms = None
    navigation_outcome_counts = Counter()
    previous_local_y = None
    desired_weapon_slot = None
    last_weapon_switch_at = float("-inf")
    parachute_attempts = 0
    last_parachute_pulse_at = float("-inf")
    last_map_check = float("-inf")
    map_verified = False
    map_verification = {"reason": "not_checked"}
    verified_room_index = None
    map_check_interval = 2.0
    enabled = False
    key_edges = {F8: False, F9: False}
    last_game_ms = None
    termination_reason = "timeout"
    event_counts = Counter()
    mode_counts = Counter()
    try:
        # Session ids delimit runs; append so restarting the always-on bot
        # continues accumulating live evidence instead of erasing earlier runs.
        with ExitStack() as streams:
            stream = streams.enter_context(args.output.open("a", encoding="utf-8", buffering=1))
            fight_stream = streams.enter_context(
                args.fight_learning_output.open("a", encoding="utf-8", buffering=1))
            print(json.dumps({"type": "ready", "pid": pid,
                              "controls": "F8 arm/pause, Shift manual override, F9 emergency stop",
                              "act_enabled": args.act,
                              "record_demonstration": args.record_demonstration,
                              "fight_learning_output": str(args.fight_learning_output),
                              "run_mode": "until_stopped" if args.until_stopped else "timed",
                              "route_graph_nodes": len(route_graph.nodes),
                              "experience_state": str(args.experience_state),
                              "experience_updates_loaded": experience_memory.data["updates"],
                              "experience_trials_loaded": experience_memory.data["trials"],
                              "experience_load_error": experience_memory.load_error,
                              "note": "Only sends input while this Client is foreground; fight scores require a two-player duel."}), flush=True)
            while deadline is None or time.perf_counter() < deadline:
                t0 = time.perf_counter()
                pressed = {vk: down(vk) for vk in key_edges}
                toggled = {vk: pressed[vk] and not key_edges[vk] for vk in key_edges}
                key_edges = pressed
                if toggled[F9]:
                    termination_reason = "emergency_stop_f9"
                    break
                if toggled[F8]:
                    enabled = not enabled
                    output.release_all_keys("resume_hotkey" if enabled else "pause_hotkey")
                focused = foreground_pid() == pid
                if not focused:
                    enabled = False
                    output.release_all_keys("focus_loss")
                manual_override = down(SHIFT) or any(
                    down(vk) for key, vk in CONTROL_KEYS.items()
                    if key not in output.held)
                if manual_override:
                    output.release_all_keys("manual_override")
                # Keep recording while paused, unfocused, or under manual
                # override; only the keyboard output is gated by those states.
                read_started = time.perf_counter()
                human_keys_before = ([key for key, vk in CONTROL_KEYS.items() if down(vk)]
                                     if args.record_demonstration and enabled and focused else [])
                snapshot = read_tick(reader)
                human_keys_after = ([key for key, vk in CONTROL_KEYS.items() if down(vk)]
                                    if args.record_demonstration and enabled and foreground_pid() == pid else [])
                demonstration_focused = focused and foreground_pid() == pid
                demonstration_read_finished = time.perf_counter()
                observation_read_ms = (time.perf_counter() - read_started) * 1000
                players = snapshot["room_slots"]
                local_slot = snapshot["local_room_slot"]
                last_game_ms = game_ms = snapshot["game_ms"]
                own = next((p for p in players if p["room_slot"] == local_slot), None)
                now = time.perf_counter()
                prior_local_y = previous_local_y
                if own is not None:
                    previous_local_y = float(own["pos"][1])
                map_check_ms = 0.0
                if (now - last_map_check >= map_check_interval or
                        snapshot["room_index"] != verified_room_index):
                    map_check_started = time.perf_counter()
                    old_map_verified = map_verified
                    map_verified, map_verification = runtime_stage07_match(
                        reader, snapshot["map_size"],
                        static_world["runtime"]["collision_grid"])
                    last_map_check = now
                    verified_room_index = snapshot["room_index"]
                    map_check_ms = (time.perf_counter() - map_check_started) * 1000
                    if map_verified != old_map_verified or tick == 0:
                        stream.write(json.dumps({
                            "type": "stage07_map_verification",
                            "tick": tick, "room_index": verified_room_index,
                            "verified": map_verified,
                            "evidence": map_verification},
                            separators=(",", ":")) + "\n")
                decision_started = time.perf_counter()
                opponent_behavior, preferred_target_identity, \
                    incoming_attack_candidates = opponent_windows.update(
                        now, own, players, local_slot)
                own_roll_state = (own.get("state") or {}) if own else {}
                roll_can_act = bool(
                    args.act and enabled and focused and not manual_override and
                    map_verified and snapshot["room_slot_limit_raw"] > 0 and
                    local_slot is not None and own is not None and
                    own.get("hp", 0) > 0 and
                    own_roll_state.get("0x74", -1) != 1 and
                    own_roll_state.get("0xdc", 0) == 0)
                adaptation_decision = experience_memory.plan(
                    now, own, incoming_attack_candidates,
                    can_act=roll_can_act, players=players,
                    local_slot=local_slot)
                adaptation_decision["control_available"] = roll_can_act
                target = choose_target(players, local_slot, own,
                                       sticky_target_identity,
                                       preferred_identity=preferred_target_identity)
                if target is not None:
                    sticky_target_identity = player_identity(target)
                elif not any(player_identity(row) == sticky_target_identity
                             and row.get("present", True) for row in players):
                    sticky_target_identity = None
                current_navigation_context = (snapshot["room_index"], local_slot,
                                              player_identity(own) if own else None,
                                              map_verified)
                if current_navigation_context != navigation_context:
                    route_progress_guard.reset()
                    navigation_context = current_navigation_context
                navigation_control_available = bool(
                    args.act and enabled and focused and not manual_override and
                    map_verified and snapshot["room_slot_limit_raw"] > 0)
                navigation_feedback = None
                game_tick_advanced = game_ms != last_navigation_game_ms
                if game_ms != last_navigation_game_ms or not navigation_control_available:
                    navigation_feedback = route_progress_guard.observe(
                        now, own, graph=route_graph, target=target,
                        control_available=navigation_control_available)
                last_navigation_game_ms = game_ms
                if navigation_feedback:
                    navigation_outcome_counts[navigation_feedback["status"]] += 1
                    stream.write(json.dumps({
                        "type": ("navigation_edge_rejected" if
                                 navigation_feedback["status"] == "failed" else
                                 "navigation_transition_outcome"),
                        "tick": tick, "game_ms": game_ms, **navigation_feedback},
                        ensure_ascii=False, separators=(",", ":")) + "\n")
                excluded_route_edges = route_progress_guard.excluded_edges(
                    now, graph=route_graph, target=target)
                mode, requested, navigation = decide_live_action(
                    route_graph, own, target, now=now, started=started,
                    previous_direction=previous_direction,
                    map_verified=map_verified,
                    excluded_edges=excluded_route_edges,
                    active_edge=route_progress_guard.continuation_edge())
                if target is not None and own is not None and own.get("hp", 0) > 0:
                    # Controlled per-bout weapon sampling: the current live
                    # baseline has no evidence-backed tactical weapon policy.
                    # Start at slot 1, then advance only after the recorder
                    # confirms a complete PRACTICE reset/refill boundary.
                    if desired_weapon_slot is None:
                        desired_weapon_slot = 1
                    if (map_verified and own.get("weapon") != desired_weapon_slot
                            and now - last_weapon_switch_at >= 0.35):
                        mode = "WEAPON_PROBE"
                        requested = (str(desired_weapon_slot),)
                        navigation = {
                            **navigation,
                            "weapon_probe": "per_bout_slot_sweep",
                            "reason": "select_next_measured_weapon_slot",
                            "desired_weapon_slot": desired_weapon_slot,
                            "observed_weapon_slot": own.get("weapon"),
                        }
                        last_weapon_switch_at = now

                # Keep the selected participant through their HP-zero frame:
                # choose_target intentionally removes dead opponents from policy.
                scoring_target = target
                if scoring_target is None and sticky_target_identity is not None:
                    scoring_target = next((row for row in players
                        if row.get("present", True) and
                        player_identity(row) == sticky_target_identity and
                        row.get("room_slot") != local_slot), None)

                chute_state = (own.get("state") or {}) if own else {}
                chute_dc = chute_state.get("0xdc", 0)
                chute_recovery = {
                    "needed": False,
                    "attempts_this_fall": parachute_attempts,
                    "dc_raw": chute_dc,
                }
                chute_pulse_requested = False
                if (own is None or chute_dc != 0 or
                        (chute_state.get("0x38", 0) != 9)):
                    parachute_attempts = 0
                if map_verified and needs_parachute_recovery(
                        route_graph, own, previous_y=prior_local_y):
                    chute_recovery["needed"] = True
                    if (parachute_attempts < 3 and
                            now - last_parachute_pulse_at >= 0.25):
                        # Pulse C while preserving horizontal steering. The
                        # next observation must show DC before we call it a
                        # successful parachute deployment.
                        requested = tuple(dict.fromkeys((*requested, "C")))
                        mode = "PARACHUTE_RECOVERY"
                        navigation = {
                            **navigation,
                            "parachute_recovery": "falling_without_support_below",
                            "parachute_observed_yet": False,
                        }
                        chute_pulse_requested = True
                        chute_recovery["pulse_sent_requested"] = True
                    else:
                        chute_recovery["pulse_sent_requested"] = False
                    chute_recovery["attempts_this_fall"] = parachute_attempts
                elif own is not None and chute_dc != 0:
                    chute_recovery["observed_nonzero_dc"] = True

                # A deployed parachute is a distinct traversal mode. The
                # ordinary route edge may request UP for a ladder or jump;
                # carrying that vertical input through DC=1 kept a confirmed
                # glide rising instead of giving it a passive landing chance.
                parachute_glide = {"active": False, "dc_raw": chute_dc}
                if (own is not None and own.get("hp", 0) > 0 and
                        chute_dc != 0 and
                        (own.get("state") or {}).get("0x74", -1) != 1):
                    requested, glide = parachute_glide_action(
                        own, target, navigation, previous_direction)
                    mode = "PARACHUTE_GLIDE"
                    navigation = {**navigation, "parachute_glide": glide}
                    parachute_glide = {"active": True, "dc_raw": chute_dc,
                                       **glide}

                # Keep delayed-roll experiments interpretable: do not let a
                # route, attack, or weapon key interfere during the selected
                # 100/180 ms timing interval.
                if adaptation_decision.get("status") == "timing_wait":
                    requested = ()
                    mode = "COMBAT_ADAPTATION_WAIT"
                    navigation = {**navigation,
                                  "adaptive_dodge": adaptation_decision}

                defensive_roll = {"candidate": None, "requested": False,
                                  "timing_memory": adaptation_decision}
                if incoming_attack_candidates:
                    roll_candidate = min(incoming_attack_candidates,
                                         key=lambda row: row["distance"])
                    defensive_roll["candidate"] = roll_candidate
                if adaptation_decision.get("keys"):
                    requested = tuple(adaptation_decision["keys"])
                    mode = "COMBAT_ADAPTIVE_EVADE"
                    navigation = {
                        **navigation,
                        "defensive_reaction": "learned_roll_timing_trial",
                        "adaptive_dodge": adaptation_decision,
                    }
                    defensive_roll["requested"] = True
                route_decision_ms = (time.perf_counter() - decision_started) * 1000
                if "LEFT" in requested or "RIGHT" in requested:
                    previous_direction = "LEFT" if "LEFT" in requested else "RIGHT"
                action_requested = tuple(requested)
                # Fail closed for unsupported room, map, or local-slot evidence.
                safe_context = (snapshot["room_slot_limit_raw"] > 0 and
                                tuple(snapshot["map_size"]) == (60, 60) and
                                local_slot is not None and own is not None and
                                map_verified)
                if not safe_context:
                    requested, mode = (), "WAIT_UNVERIFIED_CONTEXT"
                mode_counts[mode] += 1
                sent = bool(args.act and enabled and focused and not manual_override
                            and safe_context)
                if sent and chute_pulse_requested:
                    parachute_attempts += 1
                    last_parachute_pulse_at = now
                    chute_recovery["attempts_this_fall"] = parachute_attempts
                if sent:
                    output.set(requested)
                else:
                    output.release_all_keys("output_gated")
                route_progress_guard.record_action(
                    now, own, navigation.get("next_edge"),
                    graph=route_graph, target=target, keys=requested,
                    sent=sent and mode in ("NAVIGATE", "NAV_RECOVERY", "NAV_TRANSITION_WAIT"))
                eligible_duel_opponents = [row for row in players
                    if row.get("room_slot") != local_slot and row.get("present", True)
                    and row.get("policy_targetable") is True]
                scored_sample = fight_learning.observe(
                    game_ms=game_ms, room_index=snapshot["room_index"],
                    local_slot=local_slot, own=own, target=scoring_target,
                    eligible_opponent_count=len(eligible_duel_opponents),
                    active_player_count=sum(bool(row.get("present", True))
                                            for row in players),
                    controlled=bool(args.act and enabled and focused and
                                    not manual_override and safe_context),
                    mode=mode, keys_sent=list(requested) if sent else [])
                if scored_sample:
                    if scored_sample.get("transition"):
                        fight_stream.write(json.dumps(
                            scored_sample["transition"], separators=(",", ":")) + "\n")
                    if scored_sample.get("outcome"):
                        fight_stream.write(json.dumps(
                            scored_sample["outcome"], separators=(",", ":")) + "\n")
                control_cycle_ms = (time.perf_counter() - t0) * 1000

                runtime_players = [_runtime_player_row(row) for row in players]
                observed_slots.update(row["room_slot"] for row in players)
                observed_identities.update(row["identity_key"] for row in players)
                environment = {
                    "game_ms": game_ms, "room_index": snapshot["room_index"],
                    "room_count": snapshot["room_count"],
                    "room_count_raw": snapshot["room_count_raw"],
                    "room_slot_limit_raw": snapshot["room_slot_limit_raw"],
                    "participant_count": snapshot["participant_count"],
                    "local_global_user_index": snapshot["local_global_user_index"],
                    "local_slot": local_slot,
                    "slot_to_global_user_index": snapshot["slot_to_global_user_index"],
                    "room_double_damage": snapshot["room_double_damage"],
                    "global_wind_leaf_count_raw": snapshot[
                        "global_wind_leaf_count_raw"],
                    "map_size": list(snapshot["map_size"]),
                }
                events = recorder.record_tick(tick, runtime_players,
                                              inputs={"requested": list(requested),
                                                      "sent": list(requested) if sent else []},
                                              environment=environment)
                experience_updates = experience_memory.resolve(
                    now, own, players, local_slot, events,
                    list(requested) if sent else [])
                weapon_cycle_events = []
                for event in events:
                    event_counts[event.kind] += 1
                    if (event.kind == "hp_refill" and event.slot == local_slot and
                            event.payload.get("before_hp", 1) <= 0 <
                            event.payload.get("after_hp", 0)):
                        prior_weapon = desired_weapon_slot
                        cycle_from = (prior_weapon if prior_weapon is not None else
                                      (own.get("weapon") if own and own.get("weapon") else 1))
                        desired_weapon_slot = (
                            int(cycle_from) % 4) + 1
                        weapon_cycle_events.append({
                            "event": "advance_after_local_hp_zero_refill",
                            "hp_before": event.payload.get("before_hp"),
                            "hp_after": event.payload.get("after_hp"),
                            "from_desired_slot": prior_weapon,
                            "to_desired_slot": desired_weapon_slot,
                        })
                observation = {
                    "local_slot": local_slot,
                    "own": _compact_player(own),
                    "players": [_compact_player(p) for p in players],
                    "policy_targetable_opponents": [
                        _compact_player(p) for p in players
                        if p["room_slot"] != local_slot and
                        p.get("present", True) and
                        p.get("policy_targetable") is True and p["hp"] > 0],
                    "jaja_opponents_excluded_by_policy": [
                        _compact_player(p) for p in players
                        if p["room_slot"] != local_slot and p["jaja_state"]],
                }
                if tick == 0:
                    stream.write(json.dumps({
                        "type": "local_player_identity",
                        "session_id": recorder.session_id,
                        "room_slot": own["room_slot"] if own else None,
                        "global_user_index": own["global_user_index"] if own else None,
                        "nickname": own["nickname"] if own else None,
                        "nickname_raw": own["nickname_raw"] if own else None,
                        "peer_identity_raw": own["peer_identity_raw"] if own else None,
                    }, ensure_ascii=False, separators=(",", ":")) + "\n")
                current_target_identity = (player_identity(target)
                                           if target is not None else None)
                if current_target_identity != previous_logged_target:
                    stream.write(json.dumps({
                        "type": "target_selection_changed", "tick": tick,
                        "game_ms": game_ms,
                        "previous_target_identity": previous_logged_target,
                        "target_identity": current_target_identity,
                        "target_room_slot": target["room_slot"] if target else None,
                        "reason": "eligible_target_roster_update"},
                        ensure_ascii=False, separators=(",", ":")) + "\n")
                    previous_logged_target = current_target_identity
                stream.write(json.dumps({
                    "type": "control_tick", "session_id": recorder.session_id,
                    "tick": tick, "game_ms": game_ms, "mode": mode,
                    "room_index": snapshot["room_index"],
                    "room_count": snapshot["room_count"],
                    "room_count_raw": snapshot["room_count_raw"],
                    "room_slot_limit_raw": snapshot["room_slot_limit_raw"],
                    "participant_count": snapshot["participant_count"],
                    "room_double_damage": snapshot["room_double_damage"],
                    "global_wind_leaf_count_raw": snapshot[
                        "global_wind_leaf_count_raw"],
                    "local_global_user_index": snapshot["local_global_user_index"],
                    "observation": observation,
                    "navigation": navigation,
                    "navigation_feedback": navigation_feedback,
                    "navigation_excluded_edges": [list(edge) for edge in excluded_route_edges],
                    "observation_read_ms": round(observation_read_ms, 3),
                    "map_check_ms": round(map_check_ms, 3),
                    "route_decision_ms": round(route_decision_ms, 3),
                    "control_cycle_ms": round(control_cycle_ms, 3),
                    "stage07_map_verified": map_verified,
                    "stage07_map_verification": map_verification,
                    "selected_target": target["room_slot"] if target else None,
                    "selected_target_identity": ({
                        "room_slot": target["room_slot"],
                        "global_user_index": target["global_user_index"],
                        "nickname": target["nickname"],
                    } if target else None),
                    "action_requested": list(action_requested),
                    "action_sent": list(requested) if sent else [],
                    "key_events": output.take_events(),
                    "keys_held": sorted(output.held),
                    "armed": bool(args.act and enabled),
                    "focused": focused,
                    "manual_override": manual_override,
                    "human_demonstration": (demonstration_sample(
                        armed=enabled, focused=demonstration_focused,
                        map_verified=map_verified, own=own,
                        before_keys=human_keys_before, after_keys=human_keys_after,
                        sample_started=read_started - started,
                        sample_finished=demonstration_read_finished - started,
                        game_tick_advanced=game_tick_advanced)
                        if args.record_demonstration else None),
                    "jaja_state": own.get("jaja_state") if own else None,
                    "native_damage_eligible": own.get("native_damage_eligible") if own else None,
                    "native_targetable": own.get("native_targetable") if own else None,
                    "policy_targetable": own.get("policy_targetable") if own else None,
                    "selected_target_policy_eligible": target is not None,
                    "weapon_policy": {
                        "mode": "per_bout_slot_sweep",
                        "desired_slot": desired_weapon_slot,
                        "observed_slot": own.get("weapon") if own else None,
                        "acknowledged": (desired_weapon_slot is not None and own is not None
                                         and own.get("weapon") == desired_weapon_slot),
                        "cycle_events": weapon_cycle_events,
                    },
                    "opponent_behavior_window": {
                        "window_seconds": 5.0,
                        "players": opponent_behavior,
                        "preferred_target_identity": preferred_target_identity,
                        "current_incoming_attack_candidates": incoming_attack_candidates,
                    },
                    "defensive_roll": defensive_roll,
                    "combat_adaptation": {
                        "decision": adaptation_decision,
                        "updates": experience_updates,
                        "persistent_updates": experience_memory.data["updates"],
                        "persistent_trials": experience_memory.data["trials"],
                        "state_file": str(args.experience_state),
                        "load_error": experience_memory.load_error,
                        "persistence_error": experience_memory.persistence_error,
                    },
                    "fight_learning_sample": ({
                        "transition_recorded": bool(scored_sample),
                        "bot_controlled": bool(args.act and enabled and focused and
                                                not manual_override and safe_context),
                        "score_counts": dict(fight_learning.counts),
                    }),
                    "parachute_recovery": chute_recovery,
                    "parachute_glide": parachute_glide,
                    "runtime_events": [_event_json(event) for event in events],
                }, ensure_ascii=False, separators=(",", ":")) + "\n")
                tick += 1
                time.sleep(max(0.0, args.decision_ms / 1000 - (time.perf_counter() - t0)))
            if deadline is not None and time.perf_counter() >= deadline:
                termination_reason = "timeout"
    except KeyboardInterrupt:
        termination_reason = "keyboard_interrupt"
    except Exception as exc:
        termination_reason = f"exception:{type(exc).__name__}"
        raise
    finally:
        output.release_all_keys(f"shutdown:{termination_reason}")
        final_key_events = output.take_events()
        reader.close()
        with args.output.open("a", encoding="utf-8", buffering=1) as stream:
            stream.write(json.dumps({"type": "runtime_summary", "summary": {
                "session_id": recorder.session_id, "total_ticks": tick,
                 "duration": time.perf_counter() - started,
                 "observed_slots": sorted(observed_slots),
                 "observed_identities": sorted(observed_identities),
                 "event_counts": dict(event_counts), "mode_counts": dict(mode_counts),
                 "navigation_outcome_counts": dict(navigation_outcome_counts),
                 "map_verified_at_end": map_verified,
                 "last_map_verification": map_verification,
                 "last_game_ms": last_game_ms,
                "combat_adaptation_updates": experience_memory.data["updates"],
                "combat_adaptation_trials": experience_memory.data["trials"],
                "combat_adaptation_state_file": str(args.experience_state),
                "combat_adaptation_persistence_error": experience_memory.persistence_error,
                "fight_learning_counts": dict(fight_learning.counts),
                "fight_learning_output": str(args.fight_learning_output),
                "termination_reason": termination_reason,
                "final_key_events": final_key_events,
                "final_keys_held": sorted(output.held),
                "capture_status": "complete" if termination_reason == "timeout" else "partial",
                "finalized": True,
            }}, ensure_ascii=False, separators=(",", ":")) + "\n")


def _compact_player(row):
    if row is None:
        return None
    adapted = _runtime_player_row(row)
    return {"room_slot": row["room_slot"],
            "global_user_index": row["global_user_index"],
            "nickname": row["nickname"],
            "peer_identity_raw": row["peer_identity_raw"],
            "physics_address": row["physics_address"],
            "pos": row["pos"], "hp": row["hp"], "weapon": row["weapon"],
            "speed_stat": row["speed_stat"],
            "defense_stat": row["defense_stat"],
            "jump_stat": row["jump_stat"], "state": row["state"],
            "jaja_state": adapted.get("jaja_state"),
            "native_damage_eligible": adapted.get("native_damage_eligible"),
            "native_targetable": adapted.get("native_targetable"),
            "policy_targetable": adapted.get("policy_targetable")}


if __name__ == "__main__":
    main()
