"""Whole-map scan plus local-context native skill chaining."""
from __future__ import annotations

from skill_replay import replay_candidate, restore_env_state, save_env_state
from transition_library import (extract_transitions, find_candidates, load_library,
                                save_transitions)
from local_skill_search import search_transition


def settle_on_surface(env, max_steps=64):
    """Use native NOOP ticks until the spawn reaches a scannable surface."""
    actions = []
    for _ in range(max_steps + 1):
        state = env.api.read_state()
        surface = env.planner.surface_for_player(state)
        if surface is not None:
            return {"status": "grounded", "state": state, "surface": surface,
                    "actions": actions}
        if len(actions) == max_steps:
            break
        _obs, _reward, terminated, truncated, _info = env.step(0)
        actions.append(0)
        if terminated or truncated:
            break
    return {"status": "no_ground_contact", "state": env.api.read_state(),
            "surface": None, "actions": actions}


def scan_state(env, state=None):
    state = state or env.api.read_state()
    surface = env.planner.surface_for_player(state)
    return {
        "state": state,
        "surface": surface,
        "targets": [] if surface is None else env.planner.candidate_targets(surface),
        "goal_surfaces": env.planner.goal_surfaces(),
    }


def try_known_transition(env, library, *, max_candidates=8, commit=True,
                         excluded_targets=(), progress=None):
    """Try context-ranked memories from the current surface via native branches."""
    scan = scan_state(env)
    source = scan["surface"]
    if source is None:
        return {"status": "needs_ground_contact", "attempts": []}
    state = scan["state"]
    start = float(state["x"]) / 32.0 - source.x0
    attempts = []
    excluded_targets = {tuple(value) for value in excluded_targets}
    for target in scan["targets"]:
        if (target.y, target.x0, target.x1) in excluded_targets:
            continue
        context = env.planner.transition_context(source, target)
        rows = find_candidates(
            library, source, target, action_repeat=env.action_repeat,
            start_from_left=start, start_tolerance=max(1.0, source.x1 - source.x0 + 1),
            context=context, state=state)
        approximate_match = False
        if not rows:
            # A one-tile height edit should reuse the closest known movement
            # as a native-validated seed instead of restarting randomly.
            rows = find_candidates(
                library, source, target, action_repeat=env.action_repeat,
                start_from_left=start,
                start_tolerance=max(1.0, source.x1 - source.x0 + 1),
                context=context, state=state, max_dy_error=1,
                max_gap_error=1, max_width_error=1)
            approximate_match = bool(rows)
        # Approximate geometry can expose many old variants.  Native replay of
        # every long variant is expensive, so rank them and adapt only the two
        # best before yielding to bounded local exploration.
        candidate_limit = min(max_candidates, 2) if approximate_match else max_candidates
        for row in rows[:candidate_limit]:
            if progress is not None:
                progress({"phase": "skill_replay", "target": [target.y, target.x0, target.x1],
                          "candidate_steps": int(row["steps"]),
                          "attempt": len(attempts) + 1})
            outer = save_env_state(env)
            wanted_x = (source.x0 + float(row["relative"]["start_from_left"])) * 32.0
            approach = []
            for _ in range(max(8, (source.x1 - source.x0 + 1) * 8)):
                current = env.api.read_state()
                if abs(float(current["x"]) - wanted_x) <= 24.0:
                    break
                action = 2 if current["x"] < wanted_x else 1
                _obs, _reward, terminated, truncated, info = env.step(action)
                approach.append(action)
                if (terminated or truncated or
                        env.planner.surface_for_player(info["state"]) != source):
                    break
            current = env.api.read_state()
            positioned = (abs(float(current["x"]) - wanted_x) <= 24.0 and
                          env.planner.surface_for_player(current) == source)
            if not positioned:
                restore_env_state(env, outer)
                attempts.append({"target": [target.y, target.x0, target.x1],
                                 "skill_steps": row["steps"], "approach_steps": len(approach),
                                 "native_verified": False, "reason": "entry_unreachable"})
                continue
            skill_start = env.api.read_state()
            result = replay_candidate(env, target, row, commit=commit)
            attempts.append({"target": [target.y, target.x0, target.x1],
                             "skill_steps": row["steps"],
                             "approach_steps": len(approach), **result})
            if result["native_verified"]:
                advanced = {"status": "advanced", "source": [source.y, source.x0, source.x1],
                        "target": [target.y, target.x0, target.x1],
                        "attempts": attempts, "actions": approach + result["actions"]}
                if approximate_match:
                    advanced.update({"adapted": True, "entry_state": skill_start,
                                     "skill_actions": result["actions"],
                                     "trace": result.get("trace", [])})
                return advanced
            # A remembered move can end just short when the entry velocity is
            # different. Search a tiny native-only continuation instead of
            # discarding the whole contextual skill or inventing physics.
            base_actions = list(result["actions"])
            tails = []
            for action in ([base_actions[-1]] if base_actions else []) + [0, 1, 2, 6, 7]:
                if action not in tails:
                    tails.append(action)
            # For a long near-miss, mutate only a few decisions around the
            # closest approach. This transfers a one-tile height change
            # without multiplying the entire sequence into a huge search.
            if len(base_actions) > 64:
                trace = result.get("trace", [])
                if trace:
                    target_x = (target.x0 + target.x1) * 16.0
                    target_y = target.y * 32.0
                    pivot = min(range(len(trace)), key=lambda index:
                                abs(trace[index]["x"] - target_x) +
                                2.0 * abs(trace[index]["y"] - target_y))
                    # Four high-value mutations keep a changed edge probe
                    # bounded; failure then returns to local exploration.
                    for lead in (8, 4):
                        start_index = max(0, pivot - lead)
                        for jump_action in (7, 3):
                            for span in (2,):
                                changed = list(base_actions)
                                changed[start_index:start_index + span] = [jump_action] * span
                                repaired = {**row, "actions_rle": [[action, 1]
                                                                     for action in changed]}
                                repair = replay_candidate(env, target, repaired, commit=commit)
                                if repair["native_verified"]:
                                    return {"status": "advanced",
                                            "source": [source.y, source.x0, source.x1],
                                            "target": [target.y, target.x0, target.x1],
                                            "attempts": attempts,
                                            "actions": approach + repair["actions"],
                                            "adapted": True, "entry_state": skill_start,
                                            "skill_actions": repair["actions"],
                                            "trace": repair["trace"]}
                restore_env_state(env, outer)
                continue
            for tail in tails:
                for count in range(1, 5):
                    repaired = {**row, "actions_rle": [[action, 1] for action in
                                                         base_actions + [tail] * count]}
                    repair = replay_candidate(env, target, repaired, commit=commit)
                    if repair["native_verified"]:
                        return {"status": "advanced", "source": [source.y, source.x0, source.x1],
                                "target": [target.y, target.x0, target.x1],
                                "attempts": attempts, "actions": approach + repair["actions"],
                                "adapted": True, "entry_state": skill_start,
                                "skill_actions": repair["actions"],
                                "trace": repair["trace"]}
            restore_env_state(env, outer)
    return {"status": "needs_new_exploration",
            "source": [source.y, source.x0, source.x1],
            "candidate_targets": [[v.y, v.x0, v.x1] for v in scan["targets"]
                                  if (v.y, v.x0, v.x1) not in excluded_targets],
            "attempts": attempts}


def chain_known_transitions(env, library, *, max_edges=32, explore_unknown=False,
                            search_depth=32, beam_width=16, library_path=None,
                            source_map_sha256="unknown", source_episode=-1,
                            progress=None):
    """Compose only native-verified edges; stop cleanly at the first unknown context."""
    settled = settle_on_surface(env)
    actions = list(settled["actions"])
    edges = []
    if settled["status"] != "grounded":
        return {"status": settled["status"], "actions": actions, "edges": edges}
    visited = {(settled["surface"].y, settled["surface"].x0, settled["surface"].x1)}
    for _ in range(max_edges):
        state = env.api.read_state()
        if env.reached_goal(state):
            return {"status": "goal_reached", "actions": actions, "edges": edges}
        result = try_known_transition(env, library, commit=True,
                                      excluded_targets=visited, progress=progress)
        if result["status"] != "advanced":
            if explore_unknown and result["status"] == "needs_new_exploration":
                profile = env.planner.mechanic_profile()
                if profile["mode"] != "platform":
                    return {**result, "status": "needs_mechanic_search",
                            "mechanic_profile": profile,
                            "actions": actions, "edges": edges}
                learned = None
                # Search only the best goal-directed unknown edge per visit.
                # Trying every nearby platform makes an unsuccessful local
                # probe look like a hung training process.
                for target_shape in result.get("candidate_targets", [])[:1]:
                    target = next(surface for surface in env.planner.surfaces
                                  if [surface.y, surface.x0, surface.x1] == target_shape)
                    entry_state = env.api.read_state()
                    learned = search_transition(env, target, max_depth=search_depth,
                                                beam_width=beam_width, commit=True,
                                                progress=progress)
                    if learned["native_verified"]:
                        transitions = extract_transitions(
                            env.planner, [entry_state] + learned.get("trace", []),
                            learned["actions"])
                        saved_count = 0
                        if library_path is not None and transitions:
                            saved_count = save_transitions(
                                library_path, transitions,
                                action_repeat=env.action_repeat,
                                source_map_sha256=source_map_sha256,
                                source_episode=source_episode,
                                verification="native_branch_verified_landing")
                            refreshed = load_library(library_path)
                            library.clear(); library.update(refreshed)
                        actions.extend(learned["actions"])
                        edges.append({"source": result["source"], "target": target_shape,
                                      "steps": learned["steps"],
                                      "native_verified": True, "new_skill": True,
                                      "saved_skills": saved_count})
                        visited.add(tuple(target_shape))
                        break
                if learned and learned["native_verified"]:
                    continue
                return {**result, "status": "local_search_failed",
                        "search": learned, "actions": actions, "edges": edges}
            return {**result, "actions": actions, "edges": edges}
        actions.extend(result["actions"])
        saved_count = 0
        if result.get("adapted") and library_path is not None:
            transitions = extract_transitions(
                env.planner, [result["entry_state"]] + result.get("trace", []),
                result["skill_actions"])
            if transitions:
                saved_count = save_transitions(
                    library_path, transitions,
                    action_repeat=env.action_repeat,
                    source_map_sha256=source_map_sha256,
                    source_episode=source_episode,
                    verification="native_branch_adapted_landing")
                refreshed = load_library(library_path)
                library.clear(); library.update(refreshed)
        edges.append({"source": result["source"], "target": result["target"],
                      "steps": len(result["actions"]), "native_verified": True,
                      "adapted": bool(result.get("adapted")),
                      "saved_skills": saved_count})
        visited.add(tuple(result["target"]))
    status = "goal_reached" if env.reached_goal(env.api.read_state()) else "edge_limit"
    return {"status": status, "actions": actions, "edges": edges}
