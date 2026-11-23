"""The Segway security guard's route graph and movement math (spec 027).

Plain Python, no network code and (deliberately) no import of server.game: game.py imports
this module to build and drive the guard, so nothing here can import back. Every function
takes the plain numbers it needs (a tile size, a player's half-width) instead of a live Game,
so all of it is tested on its own, with a seeded random.Random wherever a result depends on it.
"""

import math


def build_route(campus, tile, player_half):
    """Parse, validate and return the map's "guard_route" as {id: {"x", "y", "connections"}}
    (pixel centres, a set of neighbour ids). None if the map has no guard_route at all (the
    small test maps of earlier specs).

    Raises ValueError with a short reason on anything broken: an id reused, a waypoint off
    the floor, a connection to an unknown id or not listed on both ends, a connection a
    player-sized square could not drive in a straight line, or a graph that is not all one
    piece. A broken map therefore fails at server start (validate_campus calls this too),
    not mid-game.
    """
    raw = campus.get("guard_route")
    if raw is None:
        return None
    grid = campus["grid"]
    waypoints = {}
    for entry in raw.get("waypoints", []):
        wid = entry.get("id")
        if not isinstance(wid, str) or not wid:
            raise ValueError("A guard waypoint needs a non-empty string id")
        if wid in waypoints:
            raise ValueError(f"Duplicate guard waypoint id: {wid!r}")
        x, y = entry.get("x"), entry.get("y")
        if type(x) is not int or type(y) is not int:
            raise ValueError(f"Guard waypoint {wid!r}: x and y must be whole numbers")
        px, py = (x + 0.5) * tile, (y + 0.5) * tile
        if _blocked(grid, tile, player_half, px, py):
            raise ValueError(f"Guard waypoint {wid!r} is not on a floor tile")
        connections = entry.get("connections", [])
        if not isinstance(connections, list) or not all(isinstance(c, str) for c in connections):
            raise ValueError(f"Guard waypoint {wid!r}: connections must be a list of ids")
        waypoints[wid] = {"x": px, "y": py, "connections": list(connections)}
    if not waypoints:
        raise ValueError("guard_route must have at least one waypoint")
    for wid, point in waypoints.items():
        for other in point["connections"]:
            if other not in waypoints:
                raise ValueError(f"Guard waypoint {wid!r} connects to unknown waypoint {other!r}")
            if wid not in waypoints[other]["connections"]:
                raise ValueError(f"Guard connection {wid!r}-{other!r} is not listed on both ends")
    for wid, point in waypoints.items():
        for other in point["connections"]:
            if not _drivable(grid, tile, player_half, point, waypoints[other]):
                raise ValueError(f"Guard connection {wid!r}-{other!r} is not drivable")
    if not _connected(waypoints):
        raise ValueError("guard_route's waypoint graph is not all connected")
    return waypoints


def _blocked(grid, tile, half, x, y):
    """Whether a player-sized square centred at (x, y) overlaps a wall or leaves the grid.

    The same check as Game.blocked(walls=True), kept standalone here so a map's guard_route
    can be validated before any Game exists.
    """
    left = math.floor((x - half) / tile)
    right = math.floor((x + half) / tile - 1e-9)
    top = math.floor((y - half) / tile)
    bottom = math.floor((y + half) / tile - 1e-9)
    for row in range(top, bottom + 1):
        for col in range(left, right + 1):
            if row < 0 or row >= len(grid) or col < 0 or col >= len(grid[row]):
                return True
            if grid[row][col] == "#":
                return True
    return False


def _drivable(grid, tile, half, a, b):
    """Whether a player-sized square can drive the straight line from a to b (pixel centres)
    without ever touching a blocked tile. Sampled every half pixel, which is far finer than
    a square can ever sidestep a wall corner."""
    dist = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
    steps = max(1, math.ceil(dist * 2))
    for i in range(steps + 1):
        t = i / steps
        x = a["x"] + (b["x"] - a["x"]) * t
        y = a["y"] + (b["y"] - a["y"]) * t
        if _blocked(grid, tile, half, x, y):
            return False
    return True


def _connected(waypoints):
    """Whether a breadth-first walk from any one waypoint reaches every other."""
    start = next(iter(waypoints))
    seen = {start}
    queue = [start]
    while queue:
        current = queue.pop()
        for neighbour in waypoints[current]["connections"]:
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return seen == set(waypoints)


class GuardState:
    """The guard's live position and the route bookkeeping that never leaves the server.

    `x`, `y`: pixel centre, like a player's. `facing`: radians, the heading he last drove (or,
    while paused, sweeps around). `current`/`target`: waypoint ids. `came_from`: the waypoint
    he just left, so choose_next() does not send him straight back along it. `paused`/
    `pause_until_tick`/`sweep_base`: set only while he stands at a waypoint waiting.
    """

    __slots__ = (
        "x", "y", "facing", "current", "target", "came_from",
        "paused", "pause_until_tick", "sweep_base",
    )

    def __init__(self, x, y, facing, current, target, came_from=None):
        self.x = x
        self.y = y
        self.facing = facing
        self.current = current
        self.target = target
        self.came_from = came_from
        self.paused = False
        self.pause_until_tick = 0
        self.sweep_base = facing


def choose_next(waypoints, at_id, came_from, rng):
    """Among the waypoints `at_id` connects to, pick one at random, excluding the one just
    come from unless it is the only connection (a dead end, where it is the one candidate)."""
    options = [c for c in waypoints[at_id]["connections"] if c != came_from]
    if not options:
        options = list(waypoints[at_id]["connections"])
    return rng.choice(options)


def start_guard(waypoints, rng, start_ids):
    """Place the guard at a random waypoint from `start_ids` (the caller has already picked
    out the ones far enough from every spawn) and send him towards a first target, chosen the
    same way as any other arrival."""
    start_id = rng.choice(list(start_ids))
    target_id = choose_next(waypoints, start_id, None, rng)
    x, y = waypoints[start_id]["x"], waypoints[start_id]["y"]
    tx, ty = waypoints[target_id]["x"], waypoints[target_id]["y"]
    facing = math.atan2(ty - y, tx - x)
    return GuardState(x=x, y=y, facing=facing, current=start_id, target=target_id, came_from=None)


def step_guard(guard, waypoints, step_px, pause_chance, pause_ticks, tick_rate, sweep, rng, tick):
    """Advance the guard by one tick. Mutates and returns `guard`.

    `pause_ticks` is (min_seconds, max_seconds), both inclusive. `sweep` is
    (amplitude_radians, period_ticks) for the head-sweep while paused.
    """
    if guard.paused:
        if tick >= guard.pause_until_tick:
            guard.paused = False
        else:
            amplitude, period = sweep
            guard.facing = guard.sweep_base + amplitude * math.sin(2 * math.pi * tick / period)
            return guard
    point = waypoints[guard.target]
    dx, dy = point["x"] - guard.x, point["y"] - guard.y
    distance = math.hypot(dx, dy)
    if distance <= step_px:
        guard.x, guard.y = point["x"], point["y"]
        arrived, came_from = guard.target, guard.current
        guard.current, guard.came_from = arrived, came_from
        if rng.random() < pause_chance:
            low, high = pause_ticks
            seconds = rng.randint(low, high)
            guard.paused = True
            guard.pause_until_tick = tick + seconds * tick_rate
            guard.sweep_base = guard.facing
        else:
            guard.target = choose_next(waypoints, arrived, came_from, rng)
            next_point = waypoints[guard.target]
            guard.facing = math.atan2(next_point["y"] - guard.y, next_point["x"] - guard.x)
    else:
        guard.facing = math.atan2(dy, dx)
        guard.x += dx / distance * step_px
        guard.y += dy / distance * step_px
    return guard
