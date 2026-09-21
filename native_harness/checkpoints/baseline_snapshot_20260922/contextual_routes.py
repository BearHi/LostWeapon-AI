"""Small map-context controllers whose every outcome is native-verified."""
from __future__ import annotations

from native_env import ACTIONS


def _result(verified, actions, states, demonstration, transitions, reason,
            stage, state):
    return {"native_verified": verified, "actions": actions, "states": states,
            "demonstration": demonstration, "transitions": transitions,
            "reason": reason, "stage": stage, "state": state}


def try_ladder_route(env, *, max_steps=512):
    """Compose approach, climb, and exit from raw ladder/endpoint geometry.

    Geometry selects targets only. Movement and completion are observed from
    the original Client transition, so this does not simulate ladder physics.
    """
    ladders = [(x, y) for tile, x, y in env.records if tile == 3]
    starts = list(env.planner.starts)
    goals = list(env.goals)
    if not ladders or not starts or not goals:
        return {"native_verified": False, "actions": [], "states": [],
                "demonstration": [], "transitions": [], "reason": "missing_geometry"}

    start = starts[0]
    goal = min(goals, key=lambda g: abs(g[0] - start[0]) + abs(g[1] - start[1]))
    ladder_x = min({x for x, _y in ladders},
                   key=lambda x: abs(x - start[0]) + abs(goal[0] - x))
    ladder_rows = [y for x, y in ladders if x == ladder_x]
    target_x = ladder_x * 32.0 + 16.0
    top_y = min(ladder_rows) * 32.0
    goal_x = goal[0] * 32.0

    obs, reset_info = env.reset()
    states = [reset_info["state"]]
    actions = []
    demonstration = []
    transitions = []
    stage = "approach"
    stagnant = 0
    last_pose = None
    for _ in range(min(int(max_steps), int(env.max_steps))):
        state = env.api.read_state()
        if stage == "approach" and abs(float(state["x"]) - target_x) <= 4.0:
            stage = "climb"
        if stage == "climb" and float(state["y"]) <= top_y:
            stage = "exit"

        if stage == "approach":
            keys = ("RIGHT",) if float(state["x"]) < target_x else ("LEFT",)
        elif stage == "climb":
            keys = ("UP",)
        else:
            direction = "RIGHT" if float(state["x"]) < goal_x else "LEFT"
            # At the top row the Client can still report ladder state. A lone
            # horizontal input is intentionally masked there; the upward
            # diagonal is the meaningful ladder-exit movement.
            keys = ((direction, "UP") if
                    state.get("38") == 0 and state.get("74") == 1 else
                    (direction,))
        action = ACTIONS.index(keys)
        if action not in env.valid_action_indices(state):
            return {"native_verified": False, "actions": actions, "states": states,
                    "demonstration": demonstration, "transitions": transitions,
                    "reason": "masked_action",
                    "stage": stage, "state": state}

        nxt, _reward, done, truncated, info = env.step(action)
        demonstration.append((obs.copy(), action))
        transitions.append((obs.copy(), action, nxt.copy(), bool(done or truncated)))
        actions.append(action)
        states.append(info["state"])
        obs = nxt
        if done:
            return {"native_verified": True, "actions": actions, "states": states,
                    "demonstration": demonstration, "transitions": transitions,
                    "reason": "goal_reached",
                    "stage": stage, "state": info["state"]}
        if truncated:
            break
        pose = (info["state"]["x"], info["state"]["y"], info["state"]["38"])
        stagnant = stagnant + 1 if pose == last_pose else 0
        last_pose = pose
        if stagnant >= 16:
            break
    return {"native_verified": False, "actions": actions, "states": states,
            "demonstration": demonstration, "transitions": transitions,
            "reason": "stalled_or_limit",
            "stage": stage, "state": states[-1]}


def try_water_route(env, *, max_steps=1024):
    """Follow a route through connected raw water cells with native feedback."""
    from collections import deque

    water = {(x, y) for tile, x, y in env.records if tile == 123}
    if not water or not env.planner.starts or not env.goals:
        return _result(False, [], [], [], [], "missing_geometry", "plan", {})
    start = env.planner.starts[0]
    goal = min(env.goals, key=lambda g: abs(g[0] - start[0]) + abs(g[1] - start[1]))
    cells = water | {start, goal}
    queue = deque([start]); previous = {start: None}
    while queue and goal not in previous:
        cell = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (cell[0] + dx, cell[1] + dy)
            if neighbor in cells and neighbor not in previous:
                previous[neighbor] = cell; queue.append(neighbor)
    if goal not in previous:
        return _result(False, [], [], [], [], "no_connected_water_path", "plan", {})
    path = []
    cell = goal
    while cell is not None:
        path.append(cell); cell = previous[cell]
    path.reverse()
    # Cell-by-cell targets fight the water's inertia and cause oscillation.
    # Keep only corners: they describe the corridor while allowing continuous
    # steering through each straight segment.
    if len(path) > 2:
        corners = [path[0]]
        old_direction = None
        for index in range(1, len(path)):
            direction = (path[index][0] - path[index - 1][0],
                         path[index][1] - path[index - 1][1])
            if old_direction is not None and direction != old_direction:
                corners.append(path[index - 1])
            old_direction = direction
        corners.append(path[-1])
        path = corners

    obs, reset_info = env.reset()
    states = [reset_info["state"]]; actions = []; demonstration = []; transitions = []
    # The injected spawn may begin one falling frame above the liquid. Wait
    # for the Client's own water-entry state before applying swim steering.
    for _ in range(64):
        state = env.api.read_state()
        if state.get("c0") == 21:
            break
        action = 0
        nxt, _reward, done, truncated, info = env.step(action)
        demonstration.append((obs.copy(), action))
        transitions.append((obs.copy(), action, nxt.copy(), bool(done or truncated)))
        actions.append(action); states.append(info["state"]); obs = nxt
        if done:
            return _result(True, actions, states, demonstration, transitions,
                           "goal_reached", "water_entry", info["state"])
        if truncated:
            return _result(False, actions, states, demonstration, transitions,
                           "entry_limit", "water_entry", info["state"])
    if env.api.read_state().get("c0") != 21:
        return _result(False, actions, states, demonstration, transitions,
                       "water_not_entered", "water_entry", states[-1])
    waypoint = 1; stagnant = 0; last_pose = None
    remaining = min(int(max_steps), int(env.max_steps)) - len(actions)
    for _ in range(max(0, remaining)):
        state = env.api.read_state()
        if waypoint >= len(path):
            target_cell = goal
        else:
            target_cell = path[waypoint]
        target_x = target_cell[0] * 32.0 + 16.0
        target_y = (target_cell[1] + 1) * 32.0
        dx = target_x - float(state["x"]); dy = target_y - float(state["y"])
        tolerance = 4.0 if waypoint >= len(path) - 1 else 20.0
        if abs(dx) <= tolerance and abs(dy) <= tolerance and waypoint < len(path) - 1:
            waypoint += 1
            continue
        horizontal = ("RIGHT" if dx > tolerance else
                      "LEFT" if dx < -tolerance else None)
        vertical = ("DOWN" if dy > tolerance else
                    "UP" if dy < -tolerance else None)
        keys = tuple(key for key in (horizontal, vertical) if key is not None)
        action = ACTIONS.index(keys)
        if action not in env.valid_action_indices(state):
            return _result(False, actions, states, demonstration, transitions,
                           "masked_action", f"waypoint_{waypoint}", state)
        nxt, _reward, done, truncated, info = env.step(action)
        demonstration.append((obs.copy(), action))
        transitions.append((obs.copy(), action, nxt.copy(), bool(done or truncated)))
        actions.append(action); states.append(info["state"]); obs = nxt
        if done:
            return _result(True, actions, states, demonstration, transitions,
                           "goal_reached", f"waypoint_{waypoint}", info["state"])
        if truncated:
            break
        pose = (info["state"]["x"], info["state"]["y"], info["state"]["38"])
        stagnant = stagnant + 1 if pose == last_pose else 0; last_pose = pose
        if stagnant >= 16:
            break
    return _result(False, actions, states, demonstration, transitions,
                   "stalled_or_limit", f"waypoint_{waypoint}", states[-1])


def try_air_traverse_route(env, *, max_steps=1024, launch_margin_px=4.0,
                           launch_style="up", chute_pulse_period=None):
    """Traverse toward the goal; launch timing is a native-tested hypothesis."""
    if not env.planner.starts or not env.goals:
        return _result(False, [], [], [], [], "missing_geometry", "plan", {})
    start = env.planner.starts[0]
    goal = min(env.goals, key=lambda g: abs(g[0] - start[0]) + abs(g[1] - start[1]))
    direction = "RIGHT" if goal[0] > start[0] else "LEFT"
    if launch_style not in ("up", "roll"):
        raise ValueError(f"unknown launch style: {launch_style}")
    jump_keys = (direction, "DOWN" if launch_style == "roll" else "UP")
    chute_keys = (direction, "C")
    walk_keys = (direction,)

    obs, reset_info = env.reset()
    states = [reset_info["state"]]; actions = []; demonstration = []; transitions = []
    # Fresh injection can place the anchor one body-height above the start
    # tile. Let native gravity establish support before beginning the roll.
    start_surface = env.planner.surface_for_player(reset_info["state"])
    for _ in range(64):
        if start_surface is not None:
            break
        action = 0
        nxt, _reward, done, truncated, info = env.step(action)
        demonstration.append((obs.copy(), action))
        transitions.append((obs.copy(), action, nxt.copy(), bool(done or truncated)))
        actions.append(action); states.append(info["state"]); obs = nxt
        start_surface = env.planner.surface_for_player(info["state"])
    if start_surface is None:
        return _result(False, actions, states, demonstration, transitions,
                       "start_not_grounded", "settle", states[-1])
    stage = "approach"; left_start = False; maximum_distance = 0.0
    glide_ticks = 0
    start_x = float(reset_info["state"]["x"])
    goal_surface = env.planner.surface_below(goal)
    goal_x = goal[0] * 32.0 + 16.0
    edge_x = ((start_surface.x1 * 32.0) if direction == "RIGHT" else
              (start_surface.x0 * 32.0 + 32.0))
    remaining = min(int(max_steps), int(env.max_steps)) - len(actions)
    for _ in range(max(0, remaining)):
        state = env.api.read_state()
        surface = env.planner.surface_for_player(state)
        distance = abs(float(state["x"]) - start_x)
        maximum_distance = max(maximum_distance, distance)
        past_edge = (float(state["x"]) >= edge_x - launch_margin_px if direction == "RIGHT"
                     else float(state["x"]) <= edge_x + launch_margin_px)
        if stage == "approach" and past_edge:
            stage = "launch"
        if stage == "launch" and surface != start_surface:
            left_start = True
        # A jump initially rises. Pressing and holding C there misses the
        # later deployment edge, so keep jumping until native vertical motion
        # reports the descending half of the arc.
        if stage == "launch" and left_start and float(state.get("motion58", 0)) <= 0:
            stage = "glide"
        if stage == "glide" and left_start and surface is not None and surface != start_surface:
            stage = "landed"
        if stage == "landed" and surface is not None and surface != goal_surface:
            # A chain of small platforms needs another launch, not a walk
            # across empty space. This is selected from observed support.
            start_surface = surface
            edge_x = ((surface.x1 * 32.0) if direction == "RIGHT" else
                      (surface.x0 * 32.0 + 32.0))
            left_start = False
            glide_ticks = 0
            stage = "approach"
        if stage == "glide":
            glide_direction = (direction if
                               (float(state["x"]) < goal_x if direction == "RIGHT"
                                else float(state["x"]) > goal_x) else None)
            pulse_c = (chute_pulse_period is None or
                       glide_ticks % int(chute_pulse_period) == 0)
            keys = ((glide_direction, "C") if glide_direction else ("C",)) if pulse_c else (
                (glide_direction,) if glide_direction else ())
            glide_ticks += 1
        elif stage == "landed":
            keys = (("RIGHT",) if float(state["x"]) < goal_x else ("LEFT",))
        else:
            keys = walk_keys if stage == "approach" else jump_keys
        allowed = env.valid_action_indices(state)
        action = ACTIONS.index(keys)
        if action not in allowed and "C" in keys:
            # The local parachute-ban field does not prohibit steering.
            fallback = (glide_direction,) if glide_direction else ()
            action = ACTIONS.index(fallback)
        elif action not in allowed and stage == "launch":
            # Jump/roll bans are local. Try the other native launch mechanic.
            alternative = (direction, "DOWN" if launch_style == "up" else "UP")
            action = ACTIONS.index(alternative)
        if action not in allowed:
            return _result(False, actions, states, demonstration, transitions,
                           "masked_action", stage, state)
        nxt, _reward, done, truncated, info = env.step(action)
        demonstration.append((obs.copy(), action))
        transitions.append((obs.copy(), action, nxt.copy(), bool(done or truncated)))
        actions.append(action); states.append(info["state"]); obs = nxt
        if done:
            return _result(True, actions, states, demonstration, transitions,
                           "goal_reached", stage, info["state"])
        if truncated:
            break
        # A return to the spawn neighborhood after substantial travel is the
        # Client's own failed-attempt/reset signal.
        if maximum_distance > 128 and abs(float(info["state"]["x"]) - start_x) < 16:
            break
    return _result(False, actions, states, demonstration, transitions,
                   "reset_or_limit", stage, states[-1])


def try_vertical_spring_route(env, *, max_steps=512):
    """Find a raw4 launch, then steer toward the flag using native state."""
    springs = [(x, y) for tile, x, y in env.records if tile == 4]
    if not springs or not env.planner.starts or not env.goals:
        return _result(False, [], [], [], [], "missing_geometry", "plan", {})
    start = env.planner.starts[0]
    goal = min(env.goals, key=lambda g: abs(g[0] - start[0]) + abs(g[1] - start[1]))
    spring = min(springs, key=lambda s: abs(s[0] - start[0]) + abs(s[1] - start[1]))
    direction = "RIGHT" if spring[0] >= start[0] else "LEFT"
    goal_x = goal[0] * 32.0 + 16.0
    obs, reset_info = env.reset()
    states = [reset_info["state"]]; actions = []; demonstration = []; transitions = []

    def advance(action):
        nonlocal obs
        nxt, _reward, done, truncated, info = env.step(action)
        demonstration.append((obs.copy(), action))
        transitions.append((obs.copy(), action, nxt.copy(), bool(done or truncated)))
        actions.append(action); states.append(info["state"]); obs = nxt
        return done, truncated, info["state"]

    for _ in range(min(64, max_steps)):
        if env.planner.surface_for_player(env.api.read_state()) is not None:
            break
        done, truncated, state = advance(0)
        if done or truncated:
            return _result(done, actions, states, demonstration, transitions,
                           "early_end", "settle", state)
    if env.planner.surface_for_player(env.api.read_state()) is None:
        return _result(False, actions, states, demonstration, transitions,
                       "start_not_grounded", "settle", states[-1])

    launched = False
    for index in range(max(0, min(max_steps, env.max_steps) - len(actions))):
        state = env.api.read_state()
        if not launched:
            keys = (direction, "UP") if index == 0 else (direction,)
        elif abs(float(state["x"]) - goal_x) <= 4.0:
            keys = ()
        else:
            keys = ("RIGHT",) if float(state["x"]) < goal_x else ("LEFT",)
        action = ACTIONS.index(keys)
        if action not in env.valid_action_indices(state):
            return _result(False, actions, states, demonstration, transitions,
                           "masked_action", "steer" if launched else "approach", state)
        done, truncated, next_state = advance(action)
        if done:
            return _result(True, actions, states, demonstration, transitions,
                           "goal_reached", "steer" if launched else "approach", next_state)
        if truncated:
            break
        if not launched and float(next_state.get("motion58", 0)) > 1500:
            launched = True
        if float(next_state["x"]) < 0 or float(next_state["x"]) > env.width * 32:
            break
    return _result(False, actions, states, demonstration, transitions,
                   "spring_not_triggered" if not launched else "goal_not_reached",
                   "approach" if not launched else "steer", states[-1])


def try_diagonal_spring_route(env, *, max_steps=300, runup_ticks=8):
    """Back up, face the spring, roll into it, then steer by native position."""
    springs = [(x, y) for tile, x, y in env.records if tile in (5, 6)]
    if not springs or not env.planner.starts or not env.goals:
        return _result(False, [], [], [], [], "missing_geometry", "plan", {})
    if env.action_repeat != 1:
        return _result(False, [], [], [], [], "requires_one_tick_actions", "plan", {})
    start = env.planner.starts[0]
    goal = min(env.goals, key=lambda g: abs(g[0] - start[0]) + abs(g[1] - start[1]))
    spring = min(springs, key=lambda s: abs(s[0] - start[0]) + abs(s[1] - start[1]))
    direction = "RIGHT" if spring[0] >= start[0] else "LEFT"
    opposite = "LEFT" if direction == "RIGHT" else "RIGHT"
    goal_x = goal[0] * 32.0 + 16.0
    obs, reset_info = env.reset()
    states = [reset_info["state"]]; actions = []; demonstration = []; transitions = []

    def advance(action):
        nonlocal obs
        nxt, _reward, done, truncated, info = env.step(action)
        demonstration.append((obs.copy(), action))
        transitions.append((obs.copy(), action, nxt.copy(), bool(done or truncated)))
        actions.append(action); states.append(info["state"]); obs = nxt
        return done, truncated, info["state"]

    for _ in range(min(64, max_steps)):
        if env.planner.surface_for_player(env.api.read_state()) is not None:
            break
        done, truncated, state = advance(0)
        if done or truncated:
            return _result(done, actions, states, demonstration, transitions,
                           "early_end", "settle", state)
    if env.planner.surface_for_player(env.api.read_state()) is None:
        return _result(False, actions, states, demonstration, transitions,
                       "start_not_grounded", "settle", states[-1])

    for key in [opposite] * int(runup_ticks) + [direction]:
        done, truncated, state = advance(ACTIONS.index((key,)))
        if done or truncated:
            return _result(done, actions, states, demonstration, transitions,
                           "early_end", "runup", state)
    launched = False
    start_x = float(reset_info["state"]["x"])
    for _ in range(max(0, min(max_steps, env.max_steps) - len(actions))):
        state = env.api.read_state()
        if not launched:
            keys = (direction, "DOWN")
        elif abs(float(state["x"]) - goal_x) <= 4.0:
            keys = ()
        else:
            keys = ("RIGHT",) if float(state["x"]) < goal_x else ("LEFT",)
        action = ACTIONS.index(keys)
        if action not in env.valid_action_indices(state):
            return _result(False, actions, states, demonstration, transitions,
                           "masked_action", "steer" if launched else "roll", state)
        done, truncated, next_state = advance(action)
        if done:
            return _result(True, actions, states, demonstration, transitions,
                           "goal_reached", "steer" if launched else "roll", next_state)
        if truncated:
            break
        if not launched and float(next_state.get("motion58", 0)) >= 1000:
            launched = True
        if not launched and len(actions) > runup_ticks + 20 and (
                abs(float(next_state["x"]) - start_x) < 16 and
                abs(float(states[-2]["x"]) - start_x) > 128):
            break
    return _result(False, actions, states, demonstration, transitions,
                   "spring_not_triggered" if not launched else "goal_not_reached",
                   "roll" if not launched else "steer", states[-1])
