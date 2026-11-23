"""Tests for spec 027: the Segway security guard.

One section per part of the spec: map data, movement, vision, the catch rule, secrecy, the
cone's browser drawing and one end-to-end WebSocket check.
"""

import json
import math
import random
from collections import deque
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import game as rules
from server import guard
from server.game import (
    EXAMINER,
    GUARD_CONE_DEGREES,
    GUARD_MIN_START_TILES,
    GUARD_PAUSE_SECONDS,
    GUARD_STEP,
    GUARD_VISION_TILES,
    MEETING,
    PLAYER_HALF,
    PLAYING,
    SECURITY,
    STUDENT,
    TICK_RATE,
    Game,
    load_map,
)
from server.main import app

TILE = 32
WEB = Path(__file__).resolve().parents[1] / "web"


def centre(col, row):
    return (col + 0.5) * TILE, (row + 0.5) * TILE


# A small, open hall (rows/cols 1-5/1-10 are floor) with a branching guard route:
# A - B - C in a line, and B - D below it, so B is the only waypoint with more than one
# connection and A, C, D are dead ends.
HALL = {
    "tile_size": TILE,
    "grid": ["############"] + ["#" + "." * 10 + "#"] * 5 + ["############"],
    "areas": [],
    "spawns": [[1, 1]],
    "guard_route": {
        "waypoints": [
            {"id": "A", "x": 2, "y": 3, "connections": ["B"]},
            {"id": "B", "x": 5, "y": 3, "connections": ["A", "C", "D"]},
            {"id": "C", "x": 8, "y": 3, "connections": ["B"]},
            {"id": "D", "x": 5, "y": 5, "connections": ["B"]},
        ]
    },
}

# The same four waypoints, already in pixels, for the pure guard.py tests that need no map.
POINTS = {
    "A": {"x": 100.0, "y": 100.0, "connections": ["B"]},
    "B": {"x": 300.0, "y": 100.0, "connections": ["A", "C", "D"]},
    "C": {"x": 500.0, "y": 100.0, "connections": ["B"]},
    "D": {"x": 300.0, "y": 300.0, "connections": ["B"]},
}


def with_route(route, campus=HALL):
    """HALL with its guard_route replaced, everything else unchanged."""
    return {**campus, "guard_route": route}


def lobby(count=4, seed=0, campus=None):
    game = Game(campus if campus is not None else HALL, rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    return game, players


def playing(count=4, seed=0, campus=None):
    game, players = lobby(count, seed, campus)
    game.start(players[0].id)
    examiners = [p for p in players if p.role == EXAMINER]
    students = [p for p in players if p.role == STUDENT]
    return game, examiners, students


def clear_cooldown(game, examiner):
    for _ in range(examiner.next_expel_tick - game.tick):
        game.step()


# =====================================================================================
# Map data
# =====================================================================================


def test_every_waypoint_of_the_campus_route_lies_on_a_floor_tile():
    campus = load_map()
    route = guard.build_route(campus, TILE, PLAYER_HALF)
    game = Game(campus)
    for point in route.values():
        assert not game.blocked(point["x"], point["y"])


def test_every_connection_of_the_campus_route_is_drivable():
    campus = load_map()
    route = guard.build_route(campus, TILE, PLAYER_HALF)
    game = Game(campus)
    for wid, point in route.items():
        for other_id in point["connections"]:
            other = route[other_id]
            distance = math.hypot(other["x"] - point["x"], other["y"] - point["y"])
            steps = max(1, int(distance))
            for i in range(steps + 1):
                t = i / steps
                x = point["x"] + (other["x"] - point["x"]) * t
                y = point["y"] + (other["y"] - point["y"]) * t
                assert not game.blocked(x, y), (wid, other_id)


def test_the_campus_routes_graph_is_connected():
    campus = load_map()
    route = guard.build_route(campus, TILE, PLAYER_HALF)
    start = next(iter(route))
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbour in route[current]["connections"]:
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    assert seen == set(route)


def test_every_connection_is_listed_on_both_ends_on_the_campus():
    campus = load_map()
    route = guard.build_route(campus, TILE, PLAYER_HALF)
    for wid, point in route.items():
        for other_id in point["connections"]:
            assert wid in route[other_id]["connections"], (wid, other_id)


def test_every_campus_area_has_a_waypoint_inside_its_own_rectangle():
    campus = load_map()
    route = guard.build_route(campus, TILE, PLAYER_HALF)
    for area in campus["areas"]:
        col_range = range(area["x"], area["x"] + area["w"])
        row_range = range(area["y"], area["y"] + area["h"])
        assert any(
            math.floor(point["x"] / TILE) in col_range and math.floor(point["y"] / TILE) in row_range
            for point in route.values()
        ), area["name"]


def test_a_map_with_no_guard_route_builds_none():
    small = {k: v for k, v in HALL.items() if k != "guard_route"}
    assert guard.build_route(small, TILE, PLAYER_HALF) is None
    rules.validate_campus(small)  # no guard_route at all: nothing to check, still valid


def test_the_real_map_and_the_test_hall_are_valid():
    rules.validate_campus(load_map())
    rules.validate_campus(HALL)


@pytest.mark.parametrize(
    "route, reason",
    [
        ({"waypoints": [{"id": "A", "x": 0, "y": 0, "connections": []}]}, "floor"),
        (
            {
                "waypoints": [
                    {"id": "A", "x": 2, "y": 3, "connections": ["B"]},
                    {"id": "B", "x": 5, "y": 3, "connections": []},  # does not list A back
                ]
            },
            "both ends",
        ),
        (
            {
                "waypoints": [
                    {"id": "A", "x": 2, "y": 3, "connections": ["B"]},
                    {"id": "B", "x": 5, "y": 3, "connections": ["A"]},
                    {"id": "C", "x": 8, "y": 3, "connections": []},  # reachable from nobody
                ]
            },
            "connected",
        ),
        (
            {"waypoints": [{"id": "A", "x": 2, "y": 3, "connections": ["ghost"]}]},
            "unknown",
        ),
        ({"waypoints": []}, "at least one"),
        (
            {"waypoints": [{"id": "A", "x": 2.5, "y": 3, "connections": []}]},
            "whole numbers",
        ),
        (
            {"waypoints": [{"id": "", "x": 2, "y": 3, "connections": []}]},
            "non-empty",
        ),
        (
            {
                "waypoints": [
                    {"id": "A", "x": 2, "y": 3, "connections": []},
                    {"id": "A", "x": 5, "y": 3, "connections": []},
                ]
            },
            "Duplicate",
        ),
    ],
)
def test_a_broken_guard_route_is_rejected(route, reason):
    with pytest.raises(ValueError, match=reason):
        rules.validate_campus(with_route(route))


def test_a_broken_guard_route_fails_at_game_construction_too():
    broken = with_route({"waypoints": [{"id": "A", "x": 0, "y": 0, "connections": []}]})
    with pytest.raises(ValueError, match="floor"):
        Game(broken)


# Two rooms (cols 1-2 and cols 4-6) separated by a wall column (col 3): a straight line
# between a waypoint in each is on the floor at both ends but drives straight through a wall.
TWO_ROOMS = {
    "tile_size": TILE,
    "grid": ["########", "#..#...#", "#..#...#", "#..#...#", "########"],
    "areas": [],
    "spawns": [[1, 1]],
}


def test_a_connection_straight_through_a_wall_is_rejected():
    broken = {
        **TWO_ROOMS,
        "guard_route": {
            "waypoints": [
                {"id": "A", "x": 1, "y": 2, "connections": ["B"]},
                {"id": "B", "x": 5, "y": 2, "connections": ["A"]},
            ]
        },
    }
    with pytest.raises(ValueError, match="drivable"):
        rules.validate_campus(broken)


# =====================================================================================
# Movement (pure server.guard functions, no Game needed)
# =====================================================================================


def test_choosing_the_next_waypoint_never_immediately_backtracks_unless_it_is_a_dead_end():
    rng = random.Random(0)
    for _ in range(200):
        assert guard.choose_next(POINTS, "B", "A", rng) in ("C", "D")
    for _ in range(20):
        assert guard.choose_next(POINTS, "A", "B", rng) == "B"  # A's only connection is B
        assert guard.choose_next(POINTS, "C", "B", rng) == "B"
        assert guard.choose_next(POINTS, "D", "B", rng) == "B"


def test_two_different_seeds_choose_a_different_first_ten_waypoints():
    def path(seed):
        rng = random.Random(seed)
        g = guard.start_guard(POINTS, rng, ["B"])
        route = [g.current]
        for _ in range(2000):  # enough ticks to reach 10 arrivals at GUARD_STEP per tick
            guard.step_guard(g, POINTS, GUARD_STEP, 0.0, (1, 1), TICK_RATE, (0.1, 40), rng, 0)
            if len(route) < 10 and g.current != route[-1]:
                route.append(g.current)
            if len(route) >= 10:
                break
        return route

    assert path(1) != path(2)


def test_driving_advances_by_exactly_guard_step_per_tick_and_stays_on_the_line():
    rng = random.Random(0)
    g = guard.GuardState(x=100.0, y=100.0, facing=0.0, current="A", target="C")
    POINTS_LINE = {
        "A": {"x": 100.0, "y": 100.0, "connections": ["C"]},
        "C": {"x": 100.0 + GUARD_STEP * 50, "y": 100.0, "connections": ["A"]},
    }
    for _ in range(40):  # well short of arriving
        before = (g.x, g.y)
        guard.step_guard(g, POINTS_LINE, GUARD_STEP, 0.0, (1, 1), TICK_RATE, (0.1, 40), rng, 0)
        moved = math.hypot(g.x - before[0], g.y - before[1])
        assert moved == pytest.approx(GUARD_STEP)
        assert g.y == pytest.approx(100.0)  # never leaves the straight line


def test_arriving_within_one_step_snaps_exactly_onto_the_target_without_overshoot():
    rng = random.Random(0)
    target = POINTS["A"]
    g = guard.GuardState(x=target["x"] - GUARD_STEP / 2, y=target["y"], facing=0.0, current="B", target="A")
    guard.step_guard(g, POINTS, GUARD_STEP, 0.0, (1, 1), TICK_RATE, (0.1, 40), rng, 0)
    assert (g.x, g.y) == (target["x"], target["y"])


def test_a_pause_lasts_a_whole_number_of_seconds_and_the_facing_sweeps():
    rng = random.Random(0)
    target = POINTS["A"]
    g = guard.GuardState(x=target["x"] - 1, y=target["y"], facing=0.3, current="B", target="A")
    guard.step_guard(g, POINTS, GUARD_STEP, 1.0, (2, 2), TICK_RATE, (0.3, 40), rng, 100)  # pause_chance 1.0
    assert g.paused
    seconds = (g.pause_until_tick - 100) / TICK_RATE
    assert seconds == 2 and seconds == int(seconds)
    position = (g.x, g.y)
    facings = set()
    for tick in range(101, g.pause_until_tick):
        guard.step_guard(g, POINTS, GUARD_STEP, 1.0, (2, 2), TICK_RATE, (0.3, 40), rng, tick)
        assert (g.x, g.y) == position  # he does not move while paused
        facings.add(round(g.facing, 6))
    assert len(facings) > 1  # the facing actually sweeps
    guard.step_guard(g, POINTS, GUARD_STEP, 0.0, (2, 2), TICK_RATE, (0.3, 40), rng, g.pause_until_tick)
    assert not g.paused  # departs once the pause is over


@pytest.mark.parametrize("seconds", GUARD_PAUSE_SECONDS)
def test_guard_pause_seconds_constant_is_one_to_three_inclusive(seconds):
    assert 1 <= seconds <= 3


# =====================================================================================
# Movement through a live Game
# =====================================================================================


def test_the_guard_does_not_exist_in_the_lobby_or_once_the_game_has_ended():
    game, players = lobby()
    assert game.guard is None
    game.start(players[0].id)
    assert game.guard is not None
    game.leave(next(p.id for p in players if p.role == EXAMINER))  # students win
    assert game.phase == "ended"
    assert game.guard is None


def test_step_does_not_move_the_guard_during_a_meeting_and_he_resumes_after():
    game, examiners, students = playing()
    # HALL has no meeting_point, so the button can be pressed from anywhere.
    game.call_meeting(students[0].id)
    assert game.phase == MEETING
    before = (game.guard.x, game.guard.y, game.guard.facing)
    for _ in range(50):
        game.step()
    assert (game.guard.x, game.guard.y, game.guard.facing) == before
    for _ in range(rules.MEETING_TICKS + rules.RESULT_TICKS + 5):
        game.step()
    assert game.phase == PLAYING
    # He picked up driving again at some point (position or facing moved from where he paused).
    moved = False
    for _ in range(50):
        game.step()
        if (game.guard.x, game.guard.y) != before[:2]:
            moved = True
            break
    assert moved


def test_the_guard_is_always_on_a_drivable_never_blocked_position():
    game, _, _ = playing(campus=load_map(), count=4)
    for _ in range(400):
        game.step()
        assert not game.blocked(game.guard.x, game.guard.y)


def test_the_guards_starting_waypoint_is_far_enough_from_every_spawn_on_the_real_map():
    for seed in range(5):
        game, _, _ = playing(campus=load_map(), count=4, seed=seed)
        spawn_centres = [centre(*s) for s in game.campus["spawns"]]
        distance = min(math.hypot(game.guard.x - sx, game.guard.y - sy) for sx, sy in spawn_centres)
        assert distance >= GUARD_MIN_START_TILES * TILE


# =====================================================================================
# Vision
# =====================================================================================


def test_seen_by_guard_requires_range_angle_and_a_clear_line():
    game, _, _ = playing()
    # Spec 035: his view grew to 6 tiles, so he stands further left to keep the far point
    # inside this small hall (it was centre(5, 3) with a 4-tile view).
    game.guard.x, game.guard.y = centre(2, 3)
    game.guard.facing = 0.0  # facing straight along +x

    within_cone_and_range = (game.guard.x + GUARD_VISION_TILES * TILE - 1, game.guard.y)
    assert game._seen_by_guard(*within_cone_and_range)

    too_far = (game.guard.x + GUARD_VISION_TILES * TILE + 1, game.guard.y)
    assert not game._seen_by_guard(*too_far)

    behind = (game.guard.x - TILE, game.guard.y)
    assert not game._seen_by_guard(*behind)

    half = math.radians(GUARD_CONE_DEGREES) / 2
    just_outside_angle = (
        game.guard.x + math.cos(half + 0.1) * TILE,
        game.guard.y + math.sin(half + 0.1) * TILE,
    )
    assert not game._seen_by_guard(*just_outside_angle)


def test_the_guard_sees_through_no_wall_blocked_lights_or_not():
    wall_hall = {
        **TWO_ROOMS,
        "guard_route": {
            "waypoints": [
                {"id": "A", "x": 1, "y": 2, "connections": ["B"]},
                {"id": "B", "x": 1, "y": 1, "connections": ["A"]},
            ]
        },
    }
    game, _, _ = playing(campus=wall_hall)
    game.guard.x, game.guard.y = centre(1, 2)
    game.guard.facing = 0.0
    target = centre(5, 2)  # behind the wall column at col 3
    assert not game._seen_by_guard(*target)
    game.lights_on = False  # spec 027: never shrunk by the lights
    assert not game._seen_by_guard(*target)


# =====================================================================================
# The catch rule
# =====================================================================================


def test_an_examiner_seen_expelling_starts_a_security_meeting_naming_them():
    game, (examiner,), students = playing()
    target = students[0]
    clear_cooldown(game, examiner)
    examiner.x, examiner.y = target.x, target.y = centre(2, 2)
    game.guard.x, game.guard.y = centre(2, 2)
    game.guard.facing = 0.0
    game.expel(examiner.id, target.id)
    assert game.phase == MEETING
    assert game.meeting.reason == SECURITY
    assert game.meeting.caught == examiner.id


def test_only_the_student_inside_the_cone_still_catches_the_examiner():
    game, (examiner,), students = playing()
    target = students[0]
    clear_cooldown(game, examiner)
    gx, gy = centre(2, 2)
    game.guard.x, game.guard.y, game.guard.facing = gx, gy, 0.0  # facing +x
    target.x, target.y = gx + TILE, gy  # one tile ahead: inside the cone and the radius
    examiner.x, examiner.y = gx + TILE, gy - 40  # 40 px from the target, but behind the guard's cone
    assert not game._seen_by_guard(examiner.x, examiner.y)
    assert game._seen_by_guard(target.x, target.y)
    assert math.hypot(examiner.x - target.x, examiner.y - target.y) <= rules.EXPEL_RANGE
    game.expel(examiner.id, target.id)
    assert game.meeting is not None and game.meeting.reason == SECURITY
    assert game.meeting.caught == examiner.id


def test_an_expel_the_guard_does_not_see_proceeds_as_usual():
    game, (examiner,), students = playing()
    target = students[0]
    clear_cooldown(game, examiner)
    examiner.x, examiner.y = target.x, target.y = centre(2, 2)
    game.guard.x, game.guard.y = centre(9, 2)  # far away
    game.guard.facing = math.pi  # facing away too
    game.expel(examiner.id, target.id)
    assert game.phase == PLAYING
    assert game.meeting is None


def test_a_game_ending_expel_seen_by_the_guard_sets_security_witnessed():
    game, (examiner,), students = playing()
    for student in students[1:]:
        student.alive = False  # simulate earlier expels: only one student left alive
    last = students[0]
    clear_cooldown(game, examiner)
    examiner.x, examiner.y = last.x, last.y = centre(2, 2)
    game.guard.x, game.guard.y = centre(2, 2)
    game.guard.facing = 0.0
    game.expel(examiner.id, last.id)
    assert game.phase == "ended"
    assert game.winner == rules.EXAMINERS_WIN
    assert game.snapshot_for(examiner.id)["security_witnessed"] is True


def test_the_same_game_ending_expel_unseen_leaves_security_witnessed_false():
    game, (examiner,), students = playing()
    for student in students[1:]:
        student.alive = False
    last = students[0]
    clear_cooldown(game, examiner)
    examiner.x, examiner.y = last.x, last.y = centre(2, 2)
    game.guard.x, game.guard.y = centre(9, 2)
    game.expel(examiner.id, last.id)
    assert game.phase == "ended"
    assert game.snapshot_for(examiner.id)["security_witnessed"] is False


def test_a_fellow_examiners_role_is_never_leaked_by_a_security_catch():
    game, players = lobby(count=6, seed=3)
    game.examiner_setting = 2
    game.start(players[0].id)
    examiners = [p for p in game.players.values() if p.role == EXAMINER]
    students = [p for p in game.players.values() if p.role == STUDENT]
    caught, other_examiner = examiners
    target = students[0]
    clear_cooldown(game, caught)
    caught.x, caught.y = target.x, target.y = centre(2, 2)
    game.guard.x, game.guard.y = centre(2, 2)
    game.guard.facing = 0.0
    game.expel(caught.id, target.id)
    assert game.meeting.caught == caught.id
    snapshot = game.snapshot_for(students[1].id)
    assert "examiner" not in json.dumps(snapshot)  # no role, of either examiner
    assert snapshot["meeting"]["caught"] == caught.id  # the one deliberate exception to R2
    assert other_examiner.id not in (snapshot["meeting"]["caught"],)


# =====================================================================================
# Secrecy
# =====================================================================================


def test_a_living_players_snapshot_has_no_guard_key_when_out_of_their_own_sight():
    game, examiners, students = playing(campus=load_map())
    viewer = students[0]
    viewer.x, viewer.y = centre(2, 2)
    game.guard.x, game.guard.y = viewer.x + 10 * TILE, viewer.y  # far outside their own sight
    assert "guard" not in game.snapshot_for(viewer.id)


def test_a_living_players_snapshot_has_the_guard_key_when_in_their_own_sight():
    game, examiners, students = playing(campus=load_map())
    viewer = students[0]
    viewer.x, viewer.y = centre(2, 2)
    game.guard.x, game.guard.y = viewer.x + TILE, viewer.y
    assert game.snapshot_for(viewer.id)["guard"]["x"] == round(game.guard.x, 1)


@pytest.mark.parametrize("phase_setup", ["ghost", "lobby", "meeting", "ended"])
def test_the_guard_key_always_shows_regardless_of_distance_outside_playing(phase_setup):
    game, examiners, students = playing()
    far_x = centre(2, 2)[0] + 50 * TILE
    if phase_setup == "ghost":
        viewer = students[0]
        viewer.alive = False
        game.guard.x, game.guard.y = far_x, centre(2, 2)[1]
        assert "guard" in game.snapshot_for(viewer.id)
    elif phase_setup == "lobby":
        game2, players2 = lobby()
        assert game2.guard is None  # no guard at all in the lobby: nothing to show
    elif phase_setup == "meeting":
        game.call_meeting(students[0].id)
        game.guard.x, game.guard.y = far_x, centre(2, 2)[1]
        assert "guard" in game.snapshot_for(students[0].id)
    elif phase_setup == "ended":
        game.leave(examiners[0].id)
        assert game.phase == "ended"
        # The guard does not exist once the round has ended: nothing to show either.
        assert "guard" not in game.snapshot_for(students[0].id)


def test_no_snapshot_ever_carries_the_waypoint_graph_or_the_guards_internal_state():
    game, examiners, students = playing(campus=load_map())
    game.guard.x, game.guard.y = centre(2, 2)
    students[0].x, students[0].y = centre(2, 2)
    for player_id in game.players:
        blob = json.dumps(game.snapshot_for(player_id))
        for forbidden in ("connections", "waypoint", "target", "pause_until_tick", "came_from"):
            assert forbidden not in blob


def test_player_entries_stay_exactly_id_name_x_y_with_a_guard_present():
    game, _, _ = playing(campus=load_map())
    snapshot = game.snapshot(see_ghosts=True)
    for entry in snapshot["players"]:
        assert set(entry) == {"id", "name", "x", "y"}


def test_welcome_map_never_carries_the_guard_route():
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "name": "Ana"})
        welcome = ws.receive_json()
    assert "guard_route" not in welcome["map"]
    assert "guard_vision_radius" in welcome
    assert welcome["guard_cone_degrees"] == GUARD_CONE_DEGREES


# =====================================================================================
# The browser's wall-clipped cone (structural, like the spec 010/018 identifier checks)
# =====================================================================================


def test_render_js_builds_the_guard_cone_from_the_shared_ray_casting_helper():
    code = (WEB / "render.js").read_text(encoding="utf-8")
    # The one per-ray wall-intersection routine, shared by the player's own lit area
    # (castRays) and the guard's cone (castGuardCone): not two independent raycasters.
    assert code.count("function castFromAngles") == 1
    assert "castFromAngles(near, x, y, reach, angles)" in code  # castRays's own call
    assert "function castGuardCone" in code
    assert "castFromAngles(near, x, y, reach" in code.split("function castGuardCone", 1)[1]
    assert "function drawGuardCone" in code
    assert "function makeGuard(" in code


def test_welcome_carries_the_guard_vision_fields_the_browser_reads():
    code = (WEB / "main.js").read_text(encoding="utf-8")
    assert "guard_vision_radius" in code
    assert "guard_cone_degrees" in code


# =====================================================================================
# One WebSocket test
# =====================================================================================


def receive_until(ws, predicate, limit=200):
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def test_a_player_in_the_guards_sight_receives_him_over_the_websocket(fresh_game):
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            clients = [a, b, c, d]
            ids = []
            for ws, name in zip(clients, ["Ada", "Bo", "Cy", "Di"]):
                ws.send_json({"type": "join", "name": name})
                welcome = receive_until(ws, lambda m: m["type"] == "welcome")
                ids.append(welcome["id"])
            a.send_json({"type": "start"})
            for ws in clients:
                receive_until(ws, lambda m: m["type"] == "state" and m["phase"] == "playing")

            assert fresh_game.guard is not None
            me = fresh_game.players[ids[0]]
            me.x, me.y = fresh_game.guard.x, fresh_game.guard.y - TILE

            state = receive_until(
                a, lambda m: m["type"] == "state" and "guard" in m, limit=400
            )
            assert set(state["guard"]) == {"x", "y", "facing", "paused"}
            mine = next(p for p in state["players"] if p["id"] == ids[0])
            seen_distance = math.hypot(state["guard"]["x"] - mine["x"], state["guard"]["y"] - mine["y"])
            assert seen_distance <= GUARD_VISION_TILES * TILE
