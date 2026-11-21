"""Tests for spec 008: fixes and remaining mechanics. One section per part."""

import copy
import dataclasses
import json
import os
import random

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import game as game_rules
from server import main as server_main
from server.game import PLAYER_HALF, SPEED, STEP, TICK_RATE, Game, GameError, load_map
from server.main import app

TILE = 32
PERIOD = 1 / TICK_RATE  # seconds between two ticks


# =====================================================================================
# Part 1: movement jitter at walls
# =====================================================================================
# The browser predicts its own character with the numbers and the map it receives in
# "welcome", in whole server ticks. So those numbers must be the server's own, the ticks
# must really be 1 / TICK_RATE apart, and the server's movement must give the same path
# for the same inputs.

# --- Accepted: the browser receives the server's movement constants ---------------------


def test_welcome_carries_the_servers_movement_constants_and_map(fresh_game):
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "name": "Ana"})
        welcome = ws.receive_json()
    assert welcome["type"] == "welcome"
    assert welcome["speed"] == SPEED
    assert welcome["tick_rate"] == TICK_RATE
    assert welcome["step"] == STEP == SPEED / TICK_RATE
    assert welcome["player_half"] == PLAYER_HALF
    assert welcome["map"] == fresh_game.campus == load_map()


def test_next_tick_is_one_tick_length_after_the_scheduled_time():
    assert server_main.next_tick_at(10.0, now=10.001) == pytest.approx(10.0 + PERIOD)


# --- Edge cases: late ticks ---------------------------------------------------------------


def test_a_tick_that_ran_late_is_made_up_by_a_shorter_wait():
    # The tick scheduled for 10.0 finished 10 ms after the next one was due. The next tick
    # stays on the timetable (it runs at once), so the one after is back on time.
    late = 10.0 + PERIOD + 0.010
    due = server_main.next_tick_at(10.0, now=late)
    assert due == pytest.approx(10.0 + PERIOD)
    assert server_main.next_tick_at(due, now=late) == pytest.approx(10.0 + 2 * PERIOD)


def test_a_few_ticks_behind_is_caught_up_but_a_long_pause_starts_a_new_timetable():
    behind = server_main.MAX_CATCH_UP_TICKS * PERIOD - 0.001  # just inside the limit
    assert server_main.next_tick_at(10.0, now=10.0 + PERIOD + behind) == pytest.approx(10.0 + PERIOD)
    # One second behind (e.g. the server was paused): no burst of 20 ticks at once.
    assert server_main.next_tick_at(10.0, now=11.05) == pytest.approx(11.05)


# --- Deterministic movement along and into walls (campus map) ----------------------------
# These guard the rule the browser repeats. The server's movement does not change in
# part 1, so they pass before and after it.

# They measure corners and doors of the spec 008 campus map, so they run on a frozen copy
# of that map (tests/maps/campus_spec008.json): spec 009 replaced the campus, not the rule.
SPEC008_MAP = load_map(os.path.join(os.path.dirname(__file__), "maps", "campus_spec008.json"))
LIBRARY_CORNER = (48, 48)  # centre of tile (1, 1): the wall is 6 px to the left and above
ABOVE_LIBRARY_DOOR = (176, 272)  # centre of tile (5, 8); the door below is columns 5-6
FLUSH = TILE + PLAYER_HALF  # 42: as close as a player gets to the wall at x or y = 32
LIBRARY_RIGHT = 12 * TILE - PLAYER_HALF  # 374: flush with the wall right of the Library
DOOR_JAMB = 7 * TILE - PLAYER_HALF  # 214: flush with the right side of the Library door

WALKS = {
    "into_a_wall": (LIBRARY_CORNER, [(-1, 0, 20)]),
    "into_a_corner": (LIBRARY_CORNER, [(-1, -1, 20)]),
    "along_a_wall": (LIBRARY_CORNER, [(1, -1, 80)]),
    "through_a_door": (ABOVE_LIBRARY_DOOR, [(0, 1, 30)]),
    "past_a_door_jamb": (ABOVE_LIBRARY_DOOR, [(1, 1, 15), (-1, 1, 15)]),  # stays in the door
}


def walk(start, script, others=0):
    """The position after every tick of one player who follows `script` on the campus.

    `script` is a list of (dx, dy, ticks). `others` more players walk around at random.
    """
    game = Game(SPEC008_MAP)
    player = game.join("Ana")
    player.x, player.y = start
    rng = random.Random(1)
    extras = [game.join(f"Other {i}") for i in range(others)]
    path = []
    for dx, dy, ticks in script:
        game.set_input(player.id, {"type": "input", "dx": dx, "dy": dy})
        for _ in range(ticks):
            for extra in extras:
                direction = {"dx": rng.choice([-1, 0, 1]), "dy": rng.choice([-1, 0, 1])}
                game.set_input(extra.id, {"type": "input", **direction})
            game.step()
            path.append((player.x, player.y))
    return path


@pytest.mark.parametrize("name", WALKS)
def test_the_same_inputs_give_exactly_the_same_path(name):
    start, script = WALKS[name]
    assert walk(start, script) == walk(start, script)


@pytest.mark.parametrize("name", WALKS)
def test_the_path_does_not_depend_on_other_players(name):
    start, script = WALKS[name]
    assert walk(start, script, others=9) == walk(start, script)


def test_walking_into_a_wall_ends_exactly_flush_and_stays_there():
    path = walk(*WALKS["into_a_wall"])
    assert path[0] == (FLUSH, 48)  # 6 px of the first 8 px step fit
    assert set(path) == {(FLUSH, 48)}


def test_walking_into_a_corner_stops_within_one_pixel_of_both_walls():
    x, y = walk(*WALKS["into_a_corner"])[-1]
    assert FLUSH <= x < FLUSH + 1
    assert FLUSH <= y < FLUSH + 1


def test_sliding_along_a_wall_never_changes_the_blocked_axis():
    path = walk(*WALKS["along_a_wall"])
    blocked_y = path[1][1]  # up against the top wall after two ticks
    assert FLUSH <= blocked_y < FLUSH + 1
    assert {y for _, y in path[1:]} == {blocked_y}
    xs = [x for x, _ in path]
    assert xs == sorted(xs)  # never a step back
    assert LIBRARY_RIGHT - 1 < xs[-1] <= LIBRARY_RIGHT  # stopped at the end of the wall


def test_walking_through_a_door_keeps_the_full_speed():
    path = walk(*WALKS["through_a_door"])
    assert path == [(176, 272 + STEP * tick) for tick in range(1, 31)]


def test_a_door_jamb_blocks_one_axis_only():
    path = walk(*WALKS["past_a_door_jamb"])
    down_right, down_left = path[:15], path[15:]
    assert DOOR_JAMB - 1 < down_right[-1][0] <= DOOR_JAMB  # x stopped by the jamb
    ys = [y for _, y in path]
    assert all(later > earlier for earlier, later in zip(ys, ys[1:]))  # y never stopped
    assert down_left[-1][0] < down_right[-1][0]  # free again when walking away from it


# --- Rejected -------------------------------------------------------------------------------


@pytest.mark.parametrize("dx", [-2, 2, "1", True, None, 0.5])
def test_an_invalid_input_next_to_a_wall_changes_nothing(dx):
    game = Game(load_map())
    player = game.join("Ana")
    player.x, player.y = FLUSH, 48
    game.set_input(player.id, {"type": "input", "dx": -1, "dy": 0})
    with pytest.raises(GameError, match="dx and dy must each be -1, 0 or 1"):
        game.set_input(player.id, {"type": "input", "dx": dx, "dy": 0})
    assert (player.x, player.y, player.dx, player.dy) == (FLUSH, 48, -1, 0)
    game.step()
    assert (player.x, player.y) == (FLUSH, 48)  # still walking into the wall: no movement


# =====================================================================================
# Part 2: no vote for yourself
# =====================================================================================

# One big open hall without an Auditorium and without a bell place: a meeting moves
# nobody, and everyone spawns on the same tile (within expel range of each other).
HALL_MAP = {
    "tile_size": TILE,
    "grid": ["#" * 30] + ["#" + "." * 28 + "#"] * 14 + ["#" * 30],
    "areas": [],
    "spawns": [[2, 2]],
}
SELF_VOTE = "You cannot vote for yourself"


def started(count=4, seed=0, campus=HALL_MAP):
    """A started game. Returns the game, its examiners and its students (Player objects)."""
    game = Game(campus, rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


def full_state(game):
    """Everything a rejected action must leave unchanged, including what every player sees."""
    return (
        game.phase,
        game.winner,
        [dataclasses.asdict(p) for p in game.players.values()],
        [dataclasses.asdict(e) for e in game.failed_exams],
        copy.deepcopy(game.meeting),  # votes and timer
        {player_id: game.snapshot_for(player_id) for player_id in game.players},
    )


def assert_rejected(game, action, reason):
    before = full_state(game)
    with pytest.raises(GameError, match=reason):
        action()
    assert full_state(game) == before


def meeting_of(game, player):
    return game.snapshot_for(player.id)["meeting"]


# --- Rejected -------------------------------------------------------------------------------


def test_a_student_voting_for_themself_is_rejected_and_nothing_changes():
    game, _, students = started(4)
    game.bell(students[0].id)
    me = students[1]
    assert_rejected(game, lambda: game.vote(me.id, me.id), SELF_VOTE)
    assert meeting_of(game, me)["my_vote"] is None
    assert meeting_of(game, students[0])["voted"] == []


def test_an_examiner_voting_for_themself_is_rejected_and_nothing_changes():
    game, (examiner,), students = started(4)
    game.bell(students[0].id)
    assert_rejected(game, lambda: game.vote(examiner.id, examiner.id), SELF_VOTE)


def test_a_self_vote_after_other_votes_does_not_touch_them():
    game, (examiner,), students = started(4)
    game.bell(students[0].id)
    game.vote(students[0].id, students[1].id)
    game.vote(examiner.id, "skip")
    assert_rejected(game, lambda: game.vote(students[1].id, students[1].id), SELF_VOTE)
    assert meeting_of(game, students[2])["voted"] == sorted([students[0].id, examiner.id])


# --- Accepted: the rejected vote is not used up -----------------------------------------------


@pytest.mark.parametrize("choice", ["another player", "skip"])
def test_after_a_rejected_self_vote_the_player_can_still_vote(choice):
    game, (examiner,), students = started(4)
    game.bell(students[0].id)
    me = students[1]
    with pytest.raises(GameError, match=SELF_VOTE):
        game.vote(me.id, me.id)
    target = examiner.id if choice == "another player" else "skip"
    game.vote(me.id, target)
    assert meeting_of(game, me)["my_vote"] == target
    assert meeting_of(game, examiner)["voted"] == [me.id]


def test_everyone_else_can_still_vote_a_player_out():
    game, (examiner,), students = started(4)
    game.bell(students[0].id)
    for student in students:
        game.vote(student.id, examiner.id)
    with pytest.raises(GameError, match=SELF_VOTE):
        game.vote(examiner.id, examiner.id)
    game.vote(examiner.id, "skip")
    game.step()
    result = meeting_of(game, students[0])["result"]
    assert (result["votes"][examiner.id], result["skips"], result["surfing"]) == (3, 1, examiner.id)
    assert examiner.alive is False


# --- Edge cases -------------------------------------------------------------------------------


def test_a_ghost_voting_for_itself_is_told_that_ghosts_cannot_vote():
    # The sender is checked before the target, as with every other action.
    game, (examiner,), students = started(5)
    ghost = students[0]
    for _ in range(examiner.next_expel_tick - game.tick):
        game.step()
    game.expel(examiner.id, ghost.id)
    game.bell(students[1].id)
    assert_rejected(game, lambda: game.vote(ghost.id, ghost.id), "Ghosts cannot vote")


def test_a_self_vote_during_the_result_is_told_that_voting_has_closed():
    game, _, students = started(4)
    game.bell(students[0].id)
    for player in list(game.players.values()):
        game.vote(player.id, "skip")
    game.step()  # the voting closes
    assert_rejected(game, lambda: game.vote(students[1].id, students[1].id), "Voting has closed")


def test_a_self_vote_after_having_voted_is_told_that_the_vote_is_cast():
    game, (examiner,), students = started(4)
    game.bell(students[0].id)
    game.vote(students[1].id, examiner.id)
    assert_rejected(game, lambda: game.vote(students[1].id, students[1].id), "You have already voted")


def test_a_rejected_self_vote_does_not_close_the_voting():
    game, (examiner,), students = started(4)
    game.bell(students[0].id)
    me = students[1]
    for voter in [examiner, students[0], students[2]]:
        game.vote(voter.id, "skip")
    with pytest.raises(GameError, match=SELF_VOTE):
        game.vote(me.id, me.id)
    game.step()
    assert meeting_of(game, me)["result"] is None  # still waiting for this player
    game.vote(me.id, "skip")
    game.step()
    assert meeting_of(game, me)["result"] == {
        "votes": {player_id: 0 for player_id in game.players},
        "skips": 4,
        "surfing": None,
    }


# --- Over the WebSocket -----------------------------------------------------------------------


def receive_until(ws, predicate, limit=5 * TICK_RATE):
    """Read messages until one matches, or fail after `limit` messages."""
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def in_meeting(message):
    return message["type"] == "state" and message["phase"] == "meeting"


def test_self_vote_over_websocket_gets_an_error_and_the_player_can_vote_again(fresh_game):
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            ids = []
            for ws, name in zip([a, b, c, d], ["Ada", "Bo", "Cy", "Di"]):
                ws.send_json({"type": "join", "name": name})
                ids.append(receive_until(ws, lambda m: m["type"] == "welcome")["id"])
            a.send_json({"type": "start"})
            receive_until(a, lambda m: m["type"] == "state" and m["phase"] == "playing")
            # At the bell (part 4).
            ringer = fresh_game.players[ids[0]]
            go_to_bell(ringer)
            a.send_json({"type": "bell"})
            receive_until(a, in_meeting)

            a.send_json({"type": "vote", "target": ids[0]})
            error = receive_until(a, lambda m: m["type"] == "error")
            assert error["reason"] == SELF_VOTE
            still_open = receive_until(a, in_meeting)["meeting"]
            assert (still_open["my_vote"], still_open["voted"]) == (None, [])

            a.send_json({"type": "vote", "target": ids[1]})
            voted = receive_until(a, lambda m: in_meeting(m) and m["meeting"]["my_vote"])
            assert voted["meeting"]["my_vote"] == ids[1]


# =====================================================================================
# Part 3: ghosts pass through walls
# =====================================================================================

# Two rooms with a wall (column 4, x = 128..160) between them. Everyone spawns on tile
# (2, 2), centre (80, 80). The map is 320 x 160 px.
WALL_MAP = {
    "tile_size": TILE,
    "grid": [
        "##########",
        "#...#....#",
        "#...#....#",
        "#...#....#",
        "##########",
    ],
    "areas": [],
    "spawns": [[2, 2]],
}
MAP_WIDTH, MAP_HEIGHT = 10 * TILE, 5 * TILE
BEFORE_WALL = 4 * TILE - PLAYER_HALF  # 118: where the wall stops a living player


def make_ghost(game, examiner, student):
    """The examiner waits for the cooldown and expels the student where they stand."""
    for _ in range(max(0, examiner.next_expel_tick - game.tick)):
        game.step()
    examiner.x, examiner.y = student.x, student.y
    game.expel(examiner.id, student.id)
    return student


def hold(game, player, dx, dy, ticks):
    """The player's position after every tick of holding one direction."""
    game.set_input(player.id, {"type": "input", "dx": dx, "dy": dy})
    path = []
    for _ in range(ticks):
        game.step()
        path.append((player.x, player.y))
    return path


def on_wall_tile(game, x, y):
    return game.grid[int(y // TILE)][int(x // TILE)] == "#"


# --- Accepted ---------------------------------------------------------------------------------


def test_a_ghost_walks_through_a_wall_at_full_speed():
    game, (examiner,), students = started(4, campus=WALL_MAP)
    ghost = make_ghost(game, examiner, students[0])
    path = hold(game, ghost, 1, 0, 14)
    assert path == [(80 + STEP * tick, 80) for tick in range(1, 15)]  # never slowed down
    assert any(on_wall_tile(game, x, y) for x, y in path)  # the centre was inside the wall
    assert not game.blocked(*path[-1])  # and out again, in the other room


def test_a_ghost_can_float_over_the_border_wall():
    game, (examiner,), students = started(4, campus=WALL_MAP)
    ghost = make_ghost(game, examiner, students[0])
    x, y = hold(game, ghost, 0, -1, 20)[-1]
    assert (x, y) == (80, PLAYER_HALF)
    assert on_wall_tile(game, x, y)


# --- Rejected (blocked) -----------------------------------------------------------------------


def test_a_living_player_is_still_blocked_by_the_same_wall():
    game, _, students = started(4, campus=WALL_MAP)
    path = hold(game, students[1], 1, 0, 14)
    assert path[-1] == (BEFORE_WALL, 80)
    assert not any(on_wall_tile(game, x, y) for x, y in path)


@pytest.mark.parametrize(
    "dx, dy", [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
)
def test_a_ghost_never_leaves_the_map(dx, dy):
    game, (examiner,), students = started(4, campus=WALL_MAP)
    ghost = make_ghost(game, examiner, students[0])
    for x, y in hold(game, ghost, dx, dy, 100):
        assert PLAYER_HALF <= x <= MAP_WIDTH - PLAYER_HALF
        assert PLAYER_HALF <= y <= MAP_HEIGHT - PLAYER_HALF
    # Held for 100 ticks, the ghost stands within one pixel of the map edge it walked to.
    if dx == 1:
        assert MAP_WIDTH - PLAYER_HALF - 1 < ghost.x
    if dx == -1:
        assert ghost.x < PLAYER_HALF + 1
    if dy == 1:
        assert MAP_HEIGHT - PLAYER_HALF - 1 < ghost.y
    if dy == -1:
        assert ghost.y < PLAYER_HALF + 1


def test_blocked_without_walls_only_knows_the_map_edge():
    game = Game(WALL_MAP)
    in_the_wall = (4.5 * TILE, 80)
    assert game.blocked(*in_the_wall)  # the default is unchanged: walls block
    assert not game.blocked(*in_the_wall, walls=False)
    assert game.blocked(PLAYER_HALF - 1, 80, walls=False)
    assert game.blocked(MAP_WIDTH - PLAYER_HALF + 1, 80, walls=False)
    assert game.blocked(80, MAP_HEIGHT - PLAYER_HALF + 1, walls=False)
    assert not game.blocked(MAP_WIDTH - PLAYER_HALF, MAP_HEIGHT - PLAYER_HALF, walls=False)


# --- Edge cases -------------------------------------------------------------------------------


def test_a_player_expelled_while_pressed_against_a_wall_passes_it_from_the_next_tick():
    game, (examiner,), students = started(4, campus=WALL_MAP)
    student = students[0]
    for _ in range(examiner.next_expel_tick - game.tick):
        game.step()
    assert hold(game, student, 1, 0, 10)[-1] == (BEFORE_WALL, 80)  # alive: stopped by the wall
    examiner.x, examiner.y = student.x, student.y
    game.expel(examiner.id, student.id)
    assert (student.x, student.y) == (BEFORE_WALL, 80)  # the expel itself moves nobody
    game.step()
    assert (student.x, student.y) == (BEFORE_WALL + STEP, 80)


def test_a_ghost_slides_along_the_map_edge():
    game, (examiner,), students = started(4, campus=WALL_MAP)
    ghost = make_ghost(game, examiner, students[0])
    hold(game, ghost, 0, -1, 20)  # up to the top edge
    path = hold(game, ghost, 1, -1, 5)
    assert {y for _, y in path} == {PLAYER_HALF}  # the blocked axis does not change
    assert path[-1][0] == pytest.approx(80 + 5 * STEP / 2**0.5)  # the free axis moves


def test_a_ghost_inside_a_wall_is_seated_in_the_auditorium_when_a_meeting_starts():
    game, (examiner,), students = started(5, campus=load_map())
    ghost = make_ghost(game, examiner, students[0])
    ghost.x, ghost.y = 27.5 * TILE, 17.5 * TILE  # in the wall between Food Court and Library
    assert game.blocked(ghost.x, ghost.y)
    ringer = students[1]
    go_to_bell(ringer)  # part 4: the bell
    game.bell(ringer.id)
    assert game.area_at(ghost.x, ghost.y) == "Auditorium"
    assert not game.blocked(ghost.x, ghost.y)


def test_after_a_new_round_the_former_ghost_is_blocked_by_walls_again():
    game, (examiner,), students = started(4, campus=WALL_MAP)
    ghost = make_ghost(game, examiner, students[0])
    hold(game, ghost, 1, 0, 6)  # into the wall
    assert on_wall_tile(game, ghost.x, ghost.y)
    make_ghost(game, examiner, students[1])  # 1 examiner, 1 student: the examiners win
    assert game.phase == "ended"
    game.restart(game.host_id)
    assert (ghost.alive, ghost.x, ghost.y) == (True, 80, 80)  # back on the spawn, not in a wall
    assert hold(game, ghost, 1, 0, 14)[-1] == (BEFORE_WALL, 80)


# =====================================================================================
# Part 4: the bell rings only at one place
# =====================================================================================

BELL_RANGE = 48  # px from the player's centre to the bell's tile centre, about 1.5 tiles
TOO_FAR = "Too far from the bell"


def bell_centre():
    """The centre of the campus bell's tile, in pixels."""
    col, row = load_map()["bell"]
    return (col + 0.5) * TILE, (row + 0.5) * TILE


def go_to_bell(player, dx=0, dy=0):
    """Put a player on the bell, or `dx`, `dy` pixels next to it."""
    x, y = bell_centre()
    player.x, player.y = x + dx, y + dy


def skip_meeting(game):
    """Every living player skips; the meeting runs to its end."""
    for player in [p for p in game.players.values() if p.alive]:
        game.vote(player.id, "skip")
    game.step()  # the voting closes
    for _ in range(game_rules.RESULT_SECONDS * TICK_RATE):
        game.step()


# --- Accepted ---------------------------------------------------------------------------------


def test_ringing_next_to_the_bell_starts_a_meeting():
    game, _, students = started(5, campus=load_map())
    ringer = students[0]
    go_to_bell(ringer)
    game.bell(ringer.id)
    assert game.phase == "meeting"
    meeting = meeting_of(game, students[1])
    assert (meeting["reason"], meeting["called_by"]) == ("bell", ringer.id)
    assert game.snapshot_for(ringer.id)["bell_used"] is True


@pytest.mark.parametrize("dx, dy", [(BELL_RANGE, 0), (-BELL_RANGE, 0), (0, BELL_RANGE), (0, -BELL_RANGE)])
def test_ringing_from_exactly_the_bell_range_is_accepted(dx, dy):
    game, _, students = started(5, campus=load_map())
    go_to_bell(students[0], dx, dy)
    game.bell(students[0].id)
    assert game.phase == "meeting"


def test_an_examiner_can_ring_the_bell_too():
    game, (examiner,), _ = started(5, campus=load_map())
    go_to_bell(examiner)
    game.bell(examiner.id)
    assert game.phase == "meeting"


def test_a_bell_rejected_for_distance_is_not_used_up():
    game, _, students = started(5, campus=load_map())
    ringer = students[0]
    with pytest.raises(GameError, match=TOO_FAR):
        game.bell(ringer.id)  # still on the spawn in the Main Entrance
    assert game.snapshot_for(ringer.id)["bell_used"] is False
    go_to_bell(ringer)
    game.bell(ringer.id)
    assert game.phase == "meeting"


# --- Rejected: each leaves the whole state unchanged ---------------------------------------------


def bell_from_the_spawn():
    game, _, students = started(5, campus=load_map())
    return game, lambda: game.bell(students[0].id)


def bell_one_pixel_beyond_the_range():
    game, _, students = started(5, campus=load_map())
    go_to_bell(students[0], dx=BELL_RANGE + 1)
    return game, lambda: game.bell(students[0].id)


def bell_from_a_corner_of_the_square_around_it():
    # 34 px right and 34 px down is about 48.1 px away: the range is a circle.
    game, _, students = started(5, campus=load_map())
    go_to_bell(students[0], dx=34, dy=34)
    return game, lambda: game.bell(students[0].id)


def ghost_at_the_bell():
    game, (examiner,), students = started(5, campus=load_map())
    ghost = make_ghost(game, examiner, students[0])
    go_to_bell(ghost)
    return game, lambda: game.bell(ghost.id)


def second_time_at_the_bell():
    game, _, students = started(5, campus=load_map())
    go_to_bell(students[0])
    game.bell(students[0].id)
    skip_meeting(game)
    go_to_bell(students[0])
    return game, lambda: game.bell(students[0].id)


def second_time_far_from_the_bell():
    game, _, students = started(5, campus=load_map())
    go_to_bell(students[0])
    game.bell(students[0].id)
    skip_meeting(game)  # everyone is in the Auditorium now, far from the bell
    return game, lambda: game.bell(students[0].id)


def at_the_bell_in_the_lobby():
    game = Game(load_map())
    players = [game.join(f"Player {i}") for i in range(4)]
    go_to_bell(players[0])
    return game, lambda: game.bell(players[0].id)


def at_the_bell_during_a_meeting():
    game, _, students = started(5, campus=load_map())
    go_to_bell(students[0])
    game.bell(students[0].id)
    go_to_bell(students[1])
    return game, lambda: game.bell(students[1].id)


def at_the_bell_after_the_end():
    game, (examiner,), students = started(4, campus=load_map())
    make_ghost(game, examiner, students[0])
    make_ghost(game, examiner, students[1])  # the examiners win
    go_to_bell(students[2])
    return game, lambda: game.bell(students[2].id)


@pytest.mark.parametrize(
    "case, reason",
    [
        (bell_from_the_spawn, TOO_FAR),
        (bell_one_pixel_beyond_the_range, TOO_FAR),
        (bell_from_a_corner_of_the_square_around_it, TOO_FAR),
        (ghost_at_the_bell, "Ghosts cannot ring the bell"),
        (second_time_at_the_bell, "You have already rung the bell"),
        (second_time_far_from_the_bell, "You have already rung the bell"),
        (at_the_bell_in_the_lobby, "The game has not started yet"),
        (at_the_bell_during_a_meeting, "A meeting is already running"),
        (at_the_bell_after_the_end, "Game is over"),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_bell_changes_nothing(case, reason):
    game, action = case()
    assert_rejected(game, action, reason)


# --- Edge cases: the map data and what the browser receives ---------------------------------------


def test_the_bell_range_is_about_one_and_a_half_tiles():
    assert game_rules.BELL_RANGE == BELL_RANGE == 1.5 * TILE


def test_the_campus_bell_is_a_floor_tile_in_the_middle_of_the_map():
    campus = load_map()
    game = Game(campus)
    col, row = campus["bell"]
    assert type(col) is int and type(row) is int
    assert campus["grid"][row][col] == "."
    assert not game.blocked(*bell_centre())
    assert game.area_at(*bell_centre()) == "Courtyard"
    assert abs(col - len(campus["grid"][0]) / 2) <= 3
    assert abs(row - len(campus["grid"]) / 2) <= 3


def test_the_campus_bell_can_be_reached_from_the_first_spawn():
    campus = load_map()
    game = Game(campus)
    seen, todo = set(), [tuple(campus["spawns"][0])]
    while todo:  # flood fill over the floor tiles (4 neighbours)
        col, row = todo.pop()
        if (col, row) in seen or game.blocked((col + 0.5) * TILE, (row + 0.5) * TILE):
            continue
        seen.add((col, row))
        todo += [(col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1)]
    assert tuple(campus["bell"]) in seen


def test_a_map_without_a_bell_place_rings_anywhere():
    # The small test maps have no "bell": like a map without an Auditorium, they still work.
    game, _, students = started(4)  # HALL_MAP
    students[0].x, students[0].y = 26.5 * TILE, 13.5 * TILE
    game.bell(students[0].id)
    assert game.phase == "meeting"


def test_bell_over_websocket_is_rejected_far_away_and_accepted_at_the_bell(fresh_game):
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            ids = []
            for ws, name in zip([a, b, c, d], ["Ada", "Bo", "Cy", "Di"]):
                ws.send_json({"type": "join", "name": name})
                welcome = receive_until(ws, lambda m: m["type"] == "welcome")
                assert welcome["bell_range"] == BELL_RANGE
                assert welcome["map"]["bell"] == load_map()["bell"]
                ids.append(welcome["id"])
            a.send_json({"type": "start"})
            receive_until(a, lambda m: m["type"] == "state" and m["phase"] == "playing")

            a.send_json({"type": "bell"})  # from the spawn in the Main Entrance
            assert receive_until(a, lambda m: m["type"] == "error")["reason"] == TOO_FAR
            state = receive_until(a, lambda m: m["type"] == "state")
            assert (state["phase"], state["bell_used"]) == ("playing", False)

            go_to_bell(fresh_game.players[ids[0]])
            a.send_json({"type": "bell"})
            meeting = receive_until(b, in_meeting)["meeting"]
            assert (meeting["reason"], meeting["called_by"]) == ("bell", ids[0])


# =====================================================================================
# Not a part of spec 008: browsers must re-check the page's files on every load
# =====================================================================================
# Found while checking part 4: a browser combined the new main.js with an old cached
# render.js and the map stayed blank. The files in web/ belong together, so the server
# tells browsers to ask on every load whether a file has changed ("Cache-Control:
# no-cache"). An unchanged file is answered with a short "304 Not Modified".

PAGE_FILES = ["/", "/index.html", "/main.js", "/render.js", "/controls.js", "/style.css", "/vendor/phaser.min.js"]


def site(folder):
    """A tiny app that serves `folder` the way server/main.py serves web/."""
    small_app = FastAPI()
    small_app.mount("/", server_main.FreshStaticFiles(directory=folder, html=True))
    return TestClient(small_app)


# --- Accepted ---------------------------------------------------------------------------------


@pytest.mark.parametrize("path", PAGE_FILES)
def test_every_file_of_the_page_must_be_rechecked_by_the_browser(path):
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["etag"]  # what the browser sends back to ask "still the same?"


def test_an_unchanged_file_is_answered_with_not_modified_and_no_body():
    with TestClient(app) as client:
        first = client.get("/render.js")
        again = client.get("/render.js", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["cache-control"] == "no-cache"  # keeps asking the next time too


def test_a_changed_file_is_sent_again_in_full(tmp_path):
    script = tmp_path / "render.js"
    script.write_text("const Render = 1;")
    os.utime(script, (1_000, 1_000))
    client = site(tmp_path)
    old = client.get("/render.js")
    assert old.text == "const Render = 1;"

    script.write_text("const Render = 2; // with makeBell")  # a deploy changes the file
    os.utime(script, (2_000, 2_000))
    new = client.get("/render.js", headers={"If-None-Match": old.headers["etag"]})
    assert new.status_code == 200
    assert new.text == "const Render = 2; // with makeBell"
    assert new.headers["etag"] != old.headers["etag"]
    assert new.headers["cache-control"] == "no-cache"


# --- Rejected ---------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/missing.js", "/vendor/missing.js", "/%2e%2e/server/game.py"])
def test_a_file_that_is_not_part_of_the_page_is_still_not_found(path):
    with TestClient(app) as client:
        assert client.get(path).status_code == 404


def test_the_page_files_still_cannot_be_written():
    with TestClient(app) as client:
        assert client.post("/main.js", content="alert(1)").status_code == 405


# --- Edge cases -------------------------------------------------------------------------------


def test_the_other_endpoints_keep_working():
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/qr.svg").headers["content-type"] == "image/svg+xml"


def test_an_etag_from_another_file_does_not_count_as_unchanged():
    with TestClient(app) as client:
        other = client.get("/main.js").headers["etag"]
        response = client.get("/render.js", headers={"If-None-Match": other})
    assert response.status_code == 200
    assert "makeBell" in response.text


# =====================================================================================
# Part 6: staff doors
# =====================================================================================

DOOR_SECONDS = 3
DOOR_TICKS = DOOR_SECONDS * TICK_RATE
NOT_ON_A_DOOR = "You are not standing on a staff door"


def doors():
    """The campus staff doors by id."""
    return {door["id"]: door for door in load_map()["staff_doors"]}


def door_centre(door_id):
    door = doors()[door_id]
    return (door["x"] + 0.5) * TILE, (door["y"] + 0.5) * TILE


def stand_on(player, door_id, dx=0, dy=0):
    """Put a player on the centre of a staff door's tile, or `dx`, `dy` pixels from it."""
    x, y = door_centre(door_id)
    player.x, player.y = x + dx, y + dy


def stand_at(player, col, row):
    player.x, player.y = (col + 0.5) * TILE, (row + 0.5) * TILE


def vote_out(game, ringer, target):
    """A meeting in which everyone else votes for `target`; it runs to its end."""
    go_to_bell(ringer)
    game.bell(ringer.id)
    for player in [p for p in game.players.values() if p.alive]:
        game.vote(player.id, "skip" if player is target else target.id)
    game.step()
    for _ in range(game_rules.RESULT_SECONDS * TICK_RATE):
        game.step()


def sees(game, viewer, other):
    return other.id in [p["id"] for p in game.snapshot_for(viewer.id)["players"]]


# --- Accepted ---------------------------------------------------------------------------------


@pytest.mark.parametrize("destination", ["food-court", "student-services", "main-entrance"])
def test_an_examiner_on_a_staff_door_travels_to_the_chosen_door(destination):
    game, (examiner,), students = started(5, campus=load_map())
    stand_on(examiner, "library")
    others = [(p.x, p.y) for p in students]
    game.use_door(examiner.id, destination)
    assert (examiner.x, examiner.y) == door_centre(destination)
    assert not game.blocked(examiner.x, examiner.y)
    assert game.phase == "playing" and examiner.alive
    assert [(p.x, p.y) for p in students] == others  # nobody else moved


@pytest.mark.parametrize("dx, dy", [(-16, -16), (15, 15), (-16, 15), (15, -16)])
def test_anywhere_on_the_doors_tile_counts_as_standing_on_it(dx, dy):
    game, (examiner,), _ = started(5, campus=load_map())
    stand_on(examiner, "library", dx, dy)  # the corners of the tile
    game.use_door(examiner.id, "food-court")
    assert (examiner.x, examiner.y) == door_centre("food-court")


def test_the_door_cooldown_is_shown_to_the_examiner_only():
    game, (examiner,), students = started(5, campus=load_map())
    assert game.snapshot_for(examiner.id)["door_cooldown"] == 0  # ready at the start
    stand_on(examiner, "library")
    game.use_door(examiner.id, "food-court")
    assert game.snapshot_for(examiner.id)["door_cooldown"] == DOOR_SECONDS
    for _ in range(TICK_RATE):
        game.step()
    assert game.snapshot_for(examiner.id)["door_cooldown"] == DOOR_SECONDS - 1
    for student in students:
        assert "door_cooldown" not in game.snapshot_for(student.id)


def test_an_examiner_can_travel_on_from_the_destination_after_the_cooldown():
    game, (examiner,), _ = started(5, campus=load_map())
    stand_on(examiner, "library")
    game.use_door(examiner.id, "food-court")
    for _ in range(DOOR_TICKS):
        game.step()
    game.use_door(examiner.id, "main-entrance")
    assert (examiner.x, examiner.y) == door_centre("main-entrance")


# --- Rejected: each leaves the whole state unchanged ---------------------------------------------


def door_by_a_student():
    game, _, students = started(5, campus=load_map())
    stand_on(students[0], "library")
    return game, lambda: game.use_door(students[0].id, "food-court")


def unknown_door_by_a_student_somewhere():
    # The sender is checked first: a student learns nothing about doors by trying.
    game, _, students = started(5, campus=load_map())
    return game, lambda: game.use_door(students[0].id, "no-such-door")


def door_by_a_ghost_examiner():
    game, (first, second), students = started(7, campus=load_map())
    vote_out(game, students[0], first)
    assert first.alive is False and game.phase == "playing"
    stand_on(first, "library")
    return game, lambda: game.use_door(first.id, "food-court")


def door_during_a_meeting():
    game, (examiner,), students = started(5, campus=load_map())
    go_to_bell(students[0])
    game.bell(students[0].id)
    stand_on(examiner, "library")
    return game, lambda: game.use_door(examiner.id, "food-court")


def door_in_the_lobby():
    game = Game(load_map())
    players = [game.join(f"Player {i}") for i in range(4)]
    stand_on(players[0], "library")
    return game, lambda: game.use_door(players[0].id, "food-court")


def door_after_the_end():
    game, (examiner,), students = started(4, campus=load_map())
    make_ghost(game, examiner, students[0])
    make_ghost(game, examiner, students[1])  # the examiners win
    stand_on(examiner, "library")
    return game, lambda: game.use_door(examiner.id, "food-court")


def door_from_the_spawn():
    game, (examiner,), _ = started(5, campus=load_map())
    return game, lambda: game.use_door(examiner.id, "food-court")


def door_one_pixel_beside_the_tile():
    game, (examiner,), _ = started(5, campus=load_map())
    stand_on(examiner, "library", dx=-17)  # the tile is 16 px to each side of its centre
    return game, lambda: game.use_door(examiner.id, "food-court")


def door_to_an_unknown_destination():
    game, (examiner,), _ = started(5, campus=load_map())
    stand_on(examiner, "library")
    return game, lambda: game.use_door(examiner.id, "no-such-door")


def door_to_the_door_you_stand_on():
    game, (examiner,), _ = started(5, campus=load_map())
    stand_on(examiner, "library")
    return game, lambda: game.use_door(examiner.id, "library")


def door_during_the_cooldown():
    game, (examiner,), _ = started(5, campus=load_map())
    stand_on(examiner, "library")
    game.use_door(examiner.id, "food-court")
    return game, lambda: game.use_door(examiner.id, "library")


def door_by_an_unknown_player():
    game, _, _ = started(5, campus=load_map())
    return game, lambda: game.use_door("nobody", "library")


def door_on_a_map_without_doors():
    game, (examiner,), _ = started(4)  # HALL_MAP
    return game, lambda: game.use_door(examiner.id, "library")


@pytest.mark.parametrize(
    "case, reason",
    [
        (door_by_a_student, "Only examiners can use staff doors"),
        (unknown_door_by_a_student_somewhere, "Only examiners can use staff doors"),
        (door_by_a_ghost_examiner, "Ghosts cannot use staff doors"),
        (door_during_a_meeting, "Meeting in progress"),
        (door_in_the_lobby, "The game has not started yet"),
        (door_after_the_end, "Game is over"),
        (door_from_the_spawn, NOT_ON_A_DOOR),
        (door_one_pixel_beside_the_tile, NOT_ON_A_DOOR),
        (door_to_an_unknown_destination, "Unknown staff door"),
        (door_to_the_door_you_stand_on, "You are already at this door"),
        (door_during_the_cooldown, "Staff door cooldown: 3 s left"),
        (door_by_an_unknown_player, "Unknown player"),
        (door_on_a_map_without_doors, NOT_ON_A_DOOR),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_staff_door_changes_nothing(case, reason):
    game, action = case()
    assert_rejected(game, action, reason)


# None stands for a missing field: server/main.py passes message.get("to").
@pytest.mark.parametrize("destination", [2, None, True, ["library"], {"id": "library"}])
def test_a_destination_that_is_not_a_string_is_rejected(destination):
    game, (examiner,), _ = started(5, campus=load_map())
    stand_on(examiner, "library")
    reason = "Destination must be a staff door id"
    assert_rejected(game, lambda: game.use_door(examiner.id, destination), reason)


def test_door_messages_are_parsed_after_joining_and_rejected_before():
    raw = '{"type": "door", "to": "library"}'
    assert game_rules.parse_message(raw, joined=True) == {"type": "door", "to": "library"}
    with pytest.raises(GameError, match="Join the game first"):
        game_rules.parse_message(raw, joined=False)


# --- Edge cases -------------------------------------------------------------------------------


def test_the_door_cooldown_ends_after_exactly_three_seconds():
    game, (examiner,), _ = started(5, campus=load_map())
    stand_on(examiner, "library")
    game.use_door(examiner.id, "food-court")
    for _ in range(DOOR_TICKS - 1):
        game.step()
    assert_rejected(
        game, lambda: game.use_door(examiner.id, "library"), "Staff door cooldown: 1 s left"
    )
    game.step()
    game.use_door(examiner.id, "library")  # exactly 3 seconds later
    assert (examiner.x, examiner.y) == door_centre("library")


def test_others_see_the_examiner_vanish_and_appear_only_within_their_vision():
    game, (examiner,), students = started(5, campus=load_map())
    at_origin, at_destination, far_away, ghost = students
    make_ghost(game, examiner, ghost)
    stand_on(examiner, "library")
    stand_at(at_origin, 34, 25)  # two tiles from the Library door, same room
    stand_at(at_destination, 36, 15)  # two tiles from the Food Court door, same room
    stand_at(far_away, 24, 4)  # in the Main Entrance, far from both
    stand_at(ghost, 20, 22)

    before = [sees(game, viewer, examiner) for viewer in students]
    assert before == [True, False, False, True]
    game.use_door(examiner.id, "food-court")
    after = [sees(game, viewer, examiner) for viewer in students]
    assert after == [False, True, False, True]
    # Whoever sees the examiner receives the new position, nothing else about the journey.
    seen = next(p for p in game.snapshot_for(at_destination.id)["players"] if p["id"] == examiner.id)
    assert seen == {"id": examiner.id, "name": examiner.name, "x": examiner.x, "y": examiner.y}


def test_a_new_round_resets_the_door_cooldown():
    game, (examiner,), students = started(4, campus=load_map())
    stand_on(examiner, "library")
    game.use_door(examiner.id, "food-court")
    make_ghost(game, examiner, students[0])
    make_ghost(game, examiner, students[1])  # the examiners win
    game.restart(game.host_id)
    assert examiner.next_door_tick == 0
    assert "door_cooldown" not in game.snapshot_for(examiner.id)  # no roles in the lobby


def test_the_campus_has_three_or_four_staff_doors_on_reachable_floor_tiles():
    campus = load_map()
    game = Game(campus)
    staff_doors = campus["staff_doors"]
    assert 3 <= len(staff_doors) <= 4
    assert len({door["id"] for door in staff_doors}) == len(staff_doors)  # one network, unique ids
    assert len({(door["x"], door["y"]) for door in staff_doors}) == len(staff_doors)
    seen, todo = set(), [tuple(campus["spawns"][0])]
    while todo:  # flood fill over the floor tiles (4 neighbours)
        col, row = todo.pop()
        if (col, row) in seen or game.blocked((col + 0.5) * TILE, (row + 0.5) * TILE):
            continue
        seen.add((col, row))
        todo += [(col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1)]
    taken = [campus["bell"]] + campus["spawns"] + [[t["x"], t["y"]] for t in campus["tasks"]]
    for door in staff_doors:
        assert set(door) == {"id", "name", "x", "y"}
        assert door["id"] and door["name"]
        assert campus["grid"][door["y"]][door["x"]] == ".", door["id"]
        assert (door["x"], door["y"]) in seen, door["id"]
        assert [door["x"], door["y"]] not in taken, door["id"]  # not on a bell, spawn or task


def test_a_staff_door_over_the_websocket(fresh_game):
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
                assert welcome["map"]["staff_doors"] == load_map()["staff_doors"]
                ids.append(welcome["id"])
            a.send_json({"type": "start"})
            roles = [
                receive_until(ws, lambda m: m["type"] == "state" and m["phase"] == "playing")["role"]
                for ws in clients
            ]
            examiner_ws = clients[roles.index("examiner")]
            examiner = fresh_game.players[ids[roles.index("examiner")]]
            student_ws = clients[roles.index("student")]
            student = fresh_game.players[ids[roles.index("student")]]

            stand_on(student, "library")
            student_ws.send_json({"type": "door", "to": "food-court"})
            error = receive_until(student_ws, lambda m: m["type"] == "error")
            assert error["reason"] == "Only examiners can use staff doors"

            examiner_ws.send_json({"type": "door", "to": "food-court"})  # from the spawn
            error = receive_until(examiner_ws, lambda m: m["type"] == "error")
            assert error["reason"] == NOT_ON_A_DOOR

            stand_on(examiner, "library")
            examiner_ws.send_json({"type": "door", "to": "food-court"})
            x, y = door_centre("food-court")
            arrived = receive_until(
                examiner_ws,
                lambda m: m["type"] == "state"
                and any(p["id"] == examiner.id and (p["x"], p["y"]) == (x, y) for p in m["players"]),
            )
            assert arrived["door_cooldown"] == DOOR_SECONDS
            assert arrived["area"] == "Food Court"


# =====================================================================================
# Part 7: vision blocked by walls
# =====================================================================================

# A room with a short wall in the middle (column 5, rows 3-5). Everyone spawns on (1, 1).
#   col 0123456789..
SIGHT_MAP = {
    "tile_size": TILE,
    "grid": [
        "############",
        "#..........#",
        "#..........#",
        "#....#.....#",
        "#....#.....#",
        "#....#.....#",
        "#..........#",
        "#..........#",
        "############",
    ],
    "areas": [],
    "spawns": [[1, 1]],
}


def seen_ids(game, viewer):
    return {p["id"] for p in game.snapshot_for(viewer.id)["players"]}


def pair_at(viewer_tile, target_tile, count=4):
    """A started game on SIGHT_MAP with one student on each of the two tiles."""
    game, examiners, students = started(count, campus=SIGHT_MAP)
    viewer, target = students[0], students[1]
    stand_at(viewer, *viewer_tile)
    stand_at(target, *target_tile)
    return game, viewer, target


# --- Accepted: visible ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "viewer_tile, target_tile",
    [
        ((3, 1), (7, 1)),  # open space above the wall
        ((3, 6), (7, 6)),  # past the lower end of the wall
        ((4, 4), (4, 7)),  # along the wall
        ((4, 3), (4, 2)),  # neighbouring tiles
        ((4, 2), (5, 2)),  # next to the wall's upper end
        ((6, 4), (9, 4)),  # both on the same side of the wall
    ],
)
def test_a_target_with_no_wall_on_the_line_is_visible(viewer_tile, target_tile):
    game, viewer, target = pair_at(viewer_tile, target_tile)
    assert target.id in seen_ids(game, viewer)
    assert viewer.id in seen_ids(game, target)  # vision is mutual


def test_two_players_on_the_same_tile_see_each_other():
    game, viewer, target = pair_at((4, 4), (4, 4))
    target.x += 10  # the same tile, not the same spot
    assert target.id in seen_ids(game, viewer)


def test_a_ghost_sees_through_walls():
    game, (examiner,), students = started(5, campus=SIGHT_MAP)
    ghost, target = students[0], students[1]
    make_ghost(game, examiner, ghost)  # the failed exam lies on the spawn tile (1, 1)
    stand_at(ghost, 3, 4)
    stand_at(target, 7, 4)  # behind the wall
    stand_at(examiner, 9, 7)
    snapshot = game.snapshot_for(ghost.id)
    assert {p["id"] for p in snapshot["players"]} == set(game.players)
    assert len(snapshot["failed_exams"]) == 1


def test_in_a_meeting_everyone_sees_everyone_through_walls():
    game, viewer, target = pair_at((3, 4), (7, 4))
    assert target.id not in seen_ids(game, viewer)
    game.bell(viewer.id)  # SIGHT_MAP has no Auditorium: nobody is moved
    assert seen_ids(game, viewer) == seen_ids(game, target) == set(game.players)


def test_in_the_lobby_and_after_the_end_walls_hide_nobody():
    game = Game(SIGHT_MAP, rng=random.Random(0))
    players = [game.join(f"Player {i}") for i in range(4)]
    stand_at(players[0], 3, 4)
    stand_at(players[1], 7, 4)
    assert seen_ids(game, players[0]) == set(game.players)  # lobby
    game.start(players[0].id)
    examiner = next(p for p in players if p.role == "examiner")
    game.leave(examiner.id)  # the students win
    assert game.phase == "ended"
    for player in game.players.values():
        assert seen_ids(game, player) == set(game.players)


# --- Rejected: not sent -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "viewer_tile, target_tile",
    [
        ((3, 4), (7, 4)),  # straight through the wall
        ((4, 4), (6, 4)),  # right next to it on both sides
        ((4, 4), (6, 6)),  # around the lower corner
        ((4, 2), (6, 4)),  # around the upper corner
        ((2, 3), (7, 5)),  # a slanted line through the wall
    ],
)
def test_a_target_behind_a_wall_within_the_radius_is_not_sent(viewer_tile, target_tile):
    game, viewer, target = pair_at(viewer_tile, target_tile)
    snapshot = game.snapshot_for(viewer.id)
    assert target.id not in {p["id"] for p in snapshot["players"]}
    assert target.id not in snapshot["colors"]
    assert target.name not in json.dumps(snapshot)
    assert viewer.id not in seen_ids(game, target)  # mutual
    assert viewer.id in seen_ids(game, viewer)  # a player always sees themself


def test_a_failed_exam_behind_a_wall_is_not_sent():
    game, (examiner,), students = started(5, campus=SIGHT_MAP)
    ghost, viewer = students[0], students[1]
    stand_at(ghost, 7, 4)
    make_ghost(game, examiner, ghost)  # the failed exam lies on (7, 4)
    stand_at(viewer, 3, 4)
    assert game.snapshot_for(viewer.id)["failed_exams"] == []
    stand_at(viewer, 7, 6)  # same side, two tiles below
    assert len(game.snapshot_for(viewer.id)["failed_exams"]) == 1
    assert len(game.failed_exams) == 1


def test_extra_fields_in_a_message_do_not_let_a_browser_see_through_walls():
    game, viewer, target = pair_at((3, 4), (7, 4))
    message = {"type": "input", "dx": 0, "dy": 0, "walls": False, "see_ghosts": True, "viewer": None}
    try:
        game.set_input(viewer.id, message)
    except GameError:
        pass  # rejecting the whole message is fine too
    assert target.id not in seen_ids(game, viewer)


# --- Edge cases -------------------------------------------------------------------------------


@pytest.mark.parametrize("dx, dy", [(-15, -15), (15, 15), (-15, 15), (15, -15)])
def test_where_a_player_stands_on_their_tile_does_not_matter(dx, dy):
    game, viewer, target = pair_at((3, 4), (7, 4))
    target.x += dx
    target.y += dy
    viewer.x -= dx
    viewer.y -= dy
    assert target.id not in seen_ids(game, viewer)


def test_the_radius_still_applies_where_no_wall_is_in_the_way():
    game, viewer, target = pair_at((1, 1), (7, 1))  # six tiles: exactly the radius
    assert target.id in seen_ids(game, viewer)
    stand_at(target, 8, 1)  # seven tiles
    assert target.id not in seen_ids(game, viewer)


# Changed by spec 010, part 3: the viewer starts one tile higher, on (3, 4) instead of
# (3, 5). From (3, 5) a corner of the target already shows past the end of the wall, and a
# visible corner is now enough to be seen.
def test_a_hidden_player_appears_when_the_viewer_walks_past_the_end_of_the_wall():
    game, viewer, target = pair_at((3, 4), (7, 6))
    assert target.id not in seen_ids(game, viewer)
    game.set_input(viewer.id, {"type": "input", "dx": 0, "dy": 1})
    for _ in range(8):  # 64 px down: onto row 6, below the wall
        game.step()
    assert target.id in seen_ids(game, viewer)


def test_on_the_campus_a_player_in_the_next_room_is_hidden_and_one_in_the_doorway_is_not():
    game, _, students = started(5, campus=load_map())
    viewer, target = students[0], students[1]
    stand_at(viewer, 29, 21)  # Library, west side
    stand_at(target, 29, 15)  # Food Court: 6 tiles away, behind the wall between the rooms
    assert target.id not in seen_ids(game, viewer)
    stand_at(target, 27, 21)  # in the Library's doorway to the spine, same row
    assert target.id in seen_ids(game, viewer)


# Removed by spec 010, part 3 (the rule changed: vision no longer goes from tile to tile):
# - test_vision_between_tiles_is_the_same_in_both_directions_everywhere_on_the_campus:
#   there are no sets of visible tiles any more. Its successor in tests/test_spec010.py is
#   test_centre_lines_between_floor_tiles_are_the_same_in_both_directions_on_the_campus.
# - test_the_visible_tiles_of_a_tile_are_worked_out_only_once: nothing is kept per tile
#   any more; every line of sight is worked out when it is needed.


# =====================================================================================
# Part 8: lights sabotage
# =====================================================================================

SABOTAGE_TICKS = 30 * TICK_RATE  # the cooldown
FIX_TICKS = 3 * TICK_RATE  # how long a student holds the light switch
SWITCH_RANGE = 48  # px from the player's centre to the centre of the switch's tile
NORMAL_RADIUS = 6 * TILE  # 192 px
DARK_RADIUS = 1.5 * TILE  # 48 px: what a student sees while the lights are off

# One big open hall with a light switch on tile (20, 10) and one task right next to it,
# so a student standing on the task tile is within reach of both.
LIGHT_MAP = {
    "tile_size": TILE,
    "grid": ["#" * 30] + ["#" + "." * 28 + "#"] * 14 + ["#" * 30],
    "areas": [{"name": "Hall", "x": 1, "y": 1, "w": 28, "h": 14, "color": "#3f6e8c"}],
    "spawns": [[2, 2]],
    "light_switch": [20, 10],
    "tasks": [
        {"id": "desk", "title": "Desk", "area": "Hall", "x": 21, "y": 10, "seconds": 5, "joke": "Done"}
    ],
}


def lights_round(count=5, seed=0):
    """A started game on LIGHT_MAP in which the sabotage cooldown from the start is over."""
    game, examiners, students = started(count, seed, LIGHT_MAP)
    for _ in range(SABOTAGE_TICKS):
        game.step()
    return game, examiners, students


def dark_round(count=5, seed=0):
    """The same, and the first examiner has just turned off the lights."""
    game, examiners, students = lights_round(count, seed)
    game.sabotage(examiners[0].id)
    return game, examiners, students


def go_to_switch(player, dx=0, dy=0):
    player.x, player.y = 20.5 * TILE + dx, 10.5 * TILE + dy


def lights(game):
    """`lights_on` as every player receives it (it must be the same for all)."""
    values = {game.snapshot_for(player_id)["lights_on"] for player_id in game.players}
    assert len(values) == 1
    return values.pop()


def fixing(game, student):
    return game.snapshot_for(student.id)["fixing"]


# --- Accepted ---------------------------------------------------------------------------------


def test_a_living_examiner_turns_off_the_lights_after_the_cooldown():
    game, (examiner,), students = lights_round()
    assert lights(game) is True
    game.sabotage(examiner.id)
    assert lights(game) is False
    assert game.phase == "playing"


def test_a_student_fixes_the_lights_by_staying_at_the_switch_for_exactly_three_seconds():
    game, _, students = dark_round()
    student = students[0]
    go_to_switch(student)
    game.fix(student.id)
    assert fixing(game, student) == {"seconds_left": 3}
    for _ in range(FIX_TICKS - 1):
        game.step()
    assert lights(game) is False  # one tick earlier: not yet
    assert fixing(game, student) == {"seconds_left": 1}
    game.step()
    assert lights(game) is True
    assert fixing(game, student) is None


@pytest.mark.parametrize("dx, dy", [(SWITCH_RANGE, 0), (-SWITCH_RANGE, 0), (0, SWITCH_RANGE), (0, -SWITCH_RANGE)])
def test_the_lights_can_be_fixed_from_exactly_the_switch_range(dx, dy):
    game, _, students = dark_round()
    go_to_switch(students[0], dx, dy)
    game.fix(students[0].id)
    for _ in range(FIX_TICKS):
        game.step()
    assert lights(game) is True


def test_walking_around_within_reach_of_the_switch_does_not_cancel():
    game, _, students = dark_round()
    student = students[0]
    go_to_switch(student)
    game.fix(student.id)
    for tick in range(FIX_TICKS):
        direction = 1 if tick % 6 < 3 else -1  # at most 24 px from the switch
        game.set_input(student.id, {"type": "input", "dx": direction, "dy": 0})
        game.step()
    assert lights(game) is True


def test_when_two_students_fix_the_first_to_finish_turns_the_lights_on_for_both():
    game, _, students = dark_round()
    go_to_switch(students[0])
    game.fix(students[0].id)
    for _ in range(20):
        game.step()
    go_to_switch(students[1])
    game.fix(students[1].id)  # one second later
    for _ in range(FIX_TICKS - 20):
        game.step()
    assert lights(game) is True
    assert fixing(game, students[0]) is None and fixing(game, students[1]) is None


def test_the_examiner_sees_the_sabotage_cooldown_and_students_do_not():
    game, (examiner,), students = started(5, campus=LIGHT_MAP)
    assert game.snapshot_for(examiner.id)["sabotage_cooldown"] == 30
    for _ in range(TICK_RATE):
        game.step()
    assert game.snapshot_for(examiner.id)["sabotage_cooldown"] == 29
    for student in students:
        snapshot = game.snapshot_for(student.id)
        assert "sabotage_cooldown" not in snapshot
        assert snapshot["fixing"] is None
    assert "fixing" not in game.snapshot_for(examiner.id)


# --- Rejected: each leaves the whole state unchanged ---------------------------------------------


def sabotage_by_a_student():
    game, _, students = lights_round()
    return game, lambda: game.sabotage(students[0].id)


def sabotage_by_a_ghost_examiner():
    game, (first, second), students = started(7, campus=LIGHT_MAP)
    game.bell(students[0].id)
    for player in list(game.players.values()):
        game.vote(player.id, "skip" if player is first else first.id)
    game.step()
    for _ in range(game_rules.RESULT_SECONDS * TICK_RATE + SABOTAGE_TICKS):
        game.step()  # the result, then the cooldown after the meeting
    assert first.alive is False and game.phase == "playing"
    return game, lambda: game.sabotage(first.id)


def sabotage_during_the_first_cooldown():
    game, (examiner,), _ = started(5, campus=LIGHT_MAP)
    return game, lambda: game.sabotage(examiner.id)


def sabotage_during_a_meeting():
    game, (examiner,), students = lights_round()
    game.bell(students[0].id)
    return game, lambda: game.sabotage(examiner.id)


def sabotage_in_the_lobby():
    game = Game(LIGHT_MAP)
    players = [game.join(f"Player {i}") for i in range(4)]
    return game, lambda: game.sabotage(players[0].id)


def sabotage_after_the_end():
    game, (examiner,), students = lights_round(4)
    make_ghost(game, examiner, students[0])
    examiner.next_expel_tick = game.tick
    make_ghost(game, examiner, students[1])  # the examiners win
    return game, lambda: game.sabotage(examiner.id)


def sabotage_while_the_lights_are_off():
    game, (examiner,), _ = dark_round()
    return game, lambda: game.sabotage(examiner.id)


def sabotage_by_the_other_examiner_while_the_lights_are_off():
    game, (first, second), _ = dark_round(7)
    return game, lambda: game.sabotage(second.id)


def sabotage_by_an_unknown_player():
    game, _, _ = lights_round()
    return game, lambda: game.sabotage("nobody")


def sabotage_on_a_map_without_a_switch():
    game, (examiner,), _ = started(4)  # HALL_MAP: nobody could turn the lights back on
    for _ in range(SABOTAGE_TICKS):
        game.step()
    return game, lambda: game.sabotage(examiner.id)


def fix_by_an_examiner():
    game, (examiner,), _ = dark_round()
    go_to_switch(examiner)
    return game, lambda: game.fix(examiner.id)


def fix_by_a_ghost_student():
    game, (examiner,), students = lights_round()
    make_ghost(game, examiner, students[0])
    game.sabotage(examiner.id)
    go_to_switch(students[0])
    return game, lambda: game.fix(students[0].id)


def fix_while_the_lights_are_on():
    game, _, students = lights_round()
    go_to_switch(students[0])
    return game, lambda: game.fix(students[0].id)


def fix_one_pixel_out_of_reach():
    game, _, students = dark_round()
    go_to_switch(students[0], dx=SWITCH_RANGE + 1)
    return game, lambda: game.fix(students[0].id)


def fix_from_the_spawn():
    game, _, students = dark_round()
    return game, lambda: game.fix(students[0].id)


def fix_while_already_fixing():
    game, _, students = dark_round()
    go_to_switch(students[0])
    game.fix(students[0].id)
    return game, lambda: game.fix(students[0].id)


def fix_while_doing_a_task():
    game, _, students = dark_round()
    students[0].x, students[0].y = 21.5 * TILE, 10.5 * TILE  # on the task, next to the switch
    game.task(students[0].id, "desk")
    return game, lambda: game.fix(students[0].id)


def task_while_fixing():
    game, _, students = dark_round()
    students[0].x, students[0].y = 21.5 * TILE, 10.5 * TILE
    game.fix(students[0].id)
    return game, lambda: game.task(students[0].id, "desk")


def fix_during_a_meeting():
    game, _, students = dark_round()
    game.bell(students[1].id)
    go_to_switch(students[0])
    return game, lambda: game.fix(students[0].id)


def fix_in_the_lobby():
    game = Game(LIGHT_MAP)
    players = [game.join(f"Player {i}") for i in range(4)]
    go_to_switch(players[0])
    return game, lambda: game.fix(players[0].id)


def fix_after_the_end():
    game, (examiner,), students = dark_round(4)
    make_ghost(game, examiner, students[0])
    examiner.next_expel_tick = game.tick
    make_ghost(game, examiner, students[1])  # the examiners win
    go_to_switch(students[2])
    return game, lambda: game.fix(students[2].id)


def fix_by_an_unknown_player():
    game, _, _ = dark_round()
    return game, lambda: game.fix("nobody")


@pytest.mark.parametrize(
    "case, reason",
    [
        (sabotage_by_a_student, "Only examiners can turn off the lights"),
        (sabotage_by_a_ghost_examiner, "Ghosts cannot turn off the lights"),
        (sabotage_during_the_first_cooldown, "Lights cooldown: 30 s left"),
        (sabotage_during_a_meeting, "Meeting in progress"),
        (sabotage_in_the_lobby, "The game has not started yet"),
        (sabotage_after_the_end, "Game is over"),
        (sabotage_while_the_lights_are_off, "The lights are already off"),
        (sabotage_by_the_other_examiner_while_the_lights_are_off, "The lights are already off"),
        (sabotage_by_an_unknown_player, "Unknown player"),
        (sabotage_on_a_map_without_a_switch, "This map has no light switch"),
        (fix_by_an_examiner, "Only students can fix the lights"),
        (fix_by_a_ghost_student, "Ghosts cannot fix the lights"),
        (fix_while_the_lights_are_on, "The lights are on"),
        (fix_one_pixel_out_of_reach, "Too far from the light switch"),
        (fix_from_the_spawn, "Too far from the light switch"),
        (fix_while_already_fixing, "You are already fixing the lights"),
        (fix_while_doing_a_task, "You are already doing a task"),
        (task_while_fixing, "You are fixing the lights"),
        (fix_during_a_meeting, "Meeting in progress"),
        (fix_in_the_lobby, "The game has not started yet"),
        (fix_after_the_end, "Game is over"),
        (fix_by_an_unknown_player, "Unknown player"),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_lights_action_changes_nothing(case, reason):
    game, action = case()
    assert_rejected(game, action, reason)


@pytest.mark.parametrize("raw", ['{"type": "sabotage"}', '{"type": "fix"}'])
def test_sabotage_and_fix_messages_are_parsed_after_joining_and_rejected_before(raw):
    assert game_rules.parse_message(raw, joined=True) == json.loads(raw)
    with pytest.raises(GameError, match="Join the game first"):
        game_rules.parse_message(raw, joined=False)


# --- Edge cases: reduced vision ---------------------------------------------------------------


def test_with_the_lights_off_a_student_sees_only_one_and_a_half_tiles():
    game, (examiner,), students = dark_round()
    viewer, target = students[0], students[1]
    stand_at(viewer, 10, 5)
    stand_at(target, 13, 5)  # three tiles away
    assert target.id not in seen_ids(game, viewer)
    assert viewer.id not in seen_ids(game, target)
    target.x = viewer.x + DARK_RADIUS  # exactly at the reduced radius: visible
    assert target.id in seen_ids(game, viewer)
    target.x += 1  # one pixel further: not
    assert target.id not in seen_ids(game, viewer)
    assert game.snapshot_for(viewer.id)["vision_radius"] == DARK_RADIUS
    assert viewer.id in seen_ids(game, viewer)  # a player always sees themself


def test_with_the_lights_off_examiners_and_ghosts_see_as_before():
    game, (examiner,), students = lights_round()
    ghost, target = students[0], students[1]
    make_ghost(game, examiner, ghost)
    game.sabotage(examiner.id)
    stand_at(examiner, 10, 5)
    stand_at(target, 13, 5)  # three tiles from the examiner
    stand_at(ghost, 25, 12)
    assert target.id in seen_ids(game, examiner)
    assert examiner.id not in seen_ids(game, target)  # the student does not see back
    assert game.snapshot_for(examiner.id)["vision_radius"] == NORMAL_RADIUS
    assert seen_ids(game, ghost) == set(game.players)


def test_with_the_lights_off_a_student_does_not_receive_a_failed_exam_three_tiles_away():
    game, (examiner,), students = lights_round()
    ghost, viewer = students[0], students[1]
    stand_at(ghost, 13, 5)
    make_ghost(game, examiner, ghost)  # the failed exam lies on (13, 5)
    stand_at(viewer, 10, 5)
    stand_at(examiner, 10, 5)
    assert len(game.snapshot_for(viewer.id)["failed_exams"]) == 1  # lights on
    game.sabotage(examiner.id)
    assert game.snapshot_for(viewer.id)["failed_exams"] == []
    assert len(game.snapshot_for(examiner.id)["failed_exams"]) == 1


def test_fixing_the_lights_gives_students_their_full_vision_back():
    game, _, students = dark_round()
    viewer, target, fixer = students[0], students[1], students[2]
    stand_at(viewer, 10, 5)
    stand_at(target, 13, 5)
    go_to_switch(fixer)
    game.fix(fixer.id)
    for _ in range(FIX_TICKS):
        game.step()
    assert target.id in seen_ids(game, viewer)
    assert game.snapshot_for(viewer.id)["vision_radius"] == NORMAL_RADIUS


def test_the_lobby_has_no_lights_fields():
    game = Game(LIGHT_MAP)
    player = game.join("Ana")
    assert not {"lights_on", "vision_radius", "fixing", "sabotage_cooldown"} & set(game.snapshot_for(player.id))


# --- Edge cases: cancelling, cooldown, meeting, new round -----------------------------------------


def test_moving_away_from_the_switch_cancels_and_the_fix_starts_again_from_zero():
    game, _, students = dark_round()
    student = students[0]
    go_to_switch(student)
    game.fix(student.id)
    for _ in range(FIX_TICKS - 1):
        game.step()  # almost done
    go_to_switch(student, dx=SWITCH_RANGE + 1)
    game.step()  # out of reach: cancelled
    assert fixing(game, student) is None and lights(game) is False
    for _ in range(FIX_TICKS):
        game.step()
    assert lights(game) is False  # nothing finishes on its own
    go_to_switch(student)
    game.fix(student.id)
    for _ in range(FIX_TICKS - 1):
        game.step()
    assert lights(game) is False  # the first attempt does not count
    game.step()
    assert lights(game) is True


def test_being_expelled_cancels_the_fix():
    game, (examiner,), students = dark_round()
    student = students[0]
    go_to_switch(student)
    game.fix(student.id)
    for _ in range(20):
        game.step()
    examiner.x, examiner.y = student.x, student.y
    game.expel(examiner.id, student.id)
    assert student.fix_done_tick is None
    for _ in range(FIX_TICKS):
        game.step()
    assert lights(game) is False


def test_the_first_sabotage_is_possible_exactly_thirty_seconds_after_the_start():
    game, (examiner,), _ = started(5, campus=LIGHT_MAP)
    for _ in range(SABOTAGE_TICKS - 1):
        game.step()
    assert_rejected(game, lambda: game.sabotage(examiner.id), "Lights cooldown: 1 s left")
    game.step()
    game.sabotage(examiner.id)
    assert lights(game) is False


def test_the_cooldown_restarts_when_the_lights_are_fixed():
    game, (examiner,), students = dark_round()
    go_to_switch(students[0])
    game.fix(students[0].id)
    for _ in range(FIX_TICKS):
        game.step()
    assert_rejected(game, lambda: game.sabotage(examiner.id), "Lights cooldown: 30 s left")
    for _ in range(SABOTAGE_TICKS - 1):
        game.step()
    assert_rejected(game, lambda: game.sabotage(examiner.id), "Lights cooldown: 1 s left")
    game.step()
    game.sabotage(examiner.id)
    assert lights(game) is False


def test_a_meeting_turns_the_lights_back_on_and_cancels_a_running_fix():
    game, (examiner,), students = dark_round()
    go_to_switch(students[0])
    game.fix(students[0].id)
    for _ in range(20):
        game.step()
    game.bell(students[1].id)
    assert lights(game) is True
    assert fixing(game, students[0]) is None
    skip_meeting(game)
    assert game.phase == "playing" and lights(game) is True
    # The cooldown is a full 30 seconds from the end of the meeting.
    for _ in range(SABOTAGE_TICKS - 1):
        game.step()
    assert_rejected(game, lambda: game.sabotage(examiner.id), "Lights cooldown: 1 s left")
    game.step()
    game.sabotage(examiner.id)
    assert lights(game) is False


def test_a_new_round_starts_with_the_lights_on_and_a_fresh_cooldown():
    game, (examiner,), students = dark_round(4)
    go_to_switch(students[2])
    game.fix(students[2].id)
    make_ghost(game, examiner, students[0])
    examiner.next_expel_tick = game.tick
    make_ghost(game, examiner, students[1])  # the examiners win, in the dark
    assert game.phase == "ended"
    assert students[2].fix_done_tick is None  # nothing keeps running after the end
    game.restart(game.host_id)
    assert game.lights_on is True
    game.start(game.host_id)
    assert lights(game) is True
    new_examiner = next(p for p in game.players.values() if p.role == "examiner")
    assert game.snapshot_for(new_examiner.id)["sabotage_cooldown"] == 30


def test_nothing_in_any_snapshot_shows_who_turned_off_the_lights():
    def everyone_receives(saboteur_index):
        game, examiners, _ = lights_round(7)
        game.sabotage(examiners[saboteur_index].id)
        return {player_id: game.snapshot_for(player_id) for player_id in game.players}

    assert everyone_receives(0) == everyone_receives(1)


def test_the_campus_light_switch_is_a_free_floor_tile_in_student_services():
    campus = load_map()
    game = Game(campus)
    col, row = campus["light_switch"]
    assert type(col) is int and type(row) is int
    assert campus["grid"][row][col] == "."
    assert game.area_at((col + 0.5) * TILE, (row + 0.5) * TILE) == "Student Services"
    taken = [campus["bell"]] + campus["spawns"]
    taken += [[t["x"], t["y"]] for t in campus["tasks"]] + [[d["x"], d["y"]] for d in campus["staff_doors"]]
    assert [col, row] not in taken
    # No task place is within reach of the switch, so one key can serve both.
    for task in campus["tasks"]:
        assert max(abs(task["x"] - col), abs(task["y"] - row)) * TILE > 2 * SWITCH_RANGE, task["id"]


def test_the_lights_constants():
    assert game_rules.SABOTAGE_COOLDOWN == 30
    assert game_rules.FIX_SECONDS == 3
    assert game_rules.SWITCH_RANGE == SWITCH_RANGE
    assert game_rules.LIGHTS_OUT_TILES == 1.5


def test_lights_out_and_fix_over_the_websocket(fresh_game):
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
                assert welcome["switch_range"] == SWITCH_RANGE
                assert welcome["lights_out_radius"] == DARK_RADIUS
                assert welcome["map"]["light_switch"] == load_map()["light_switch"]
                ids.append(welcome["id"])
            a.send_json({"type": "start"})
            roles = [
                receive_until(ws, lambda m: m["type"] == "state" and m["phase"] == "playing")["role"]
                for ws in clients
            ]
            examiner_ws = clients[roles.index("examiner")]
            student_ws = clients[roles.index("student")]
            student = fresh_game.players[ids[roles.index("student")]]

            student_ws.send_json({"type": "sabotage"})
            error = receive_until(student_ws, lambda m: m["type"] == "error")
            assert error["reason"] == "Only examiners can turn off the lights"
            examiner_ws.send_json({"type": "sabotage"})
            error = receive_until(examiner_ws, lambda m: m["type"] == "error")
            assert error["reason"].startswith("Lights cooldown")

            fresh_game.next_sabotage_tick = fresh_game.tick  # skip the cooldown
            examiner_ws.send_json({"type": "sabotage"})
            for ws in clients:
                dark = receive_until(ws, lambda m: m["type"] == "state" and not m["lights_on"])
                expected = DARK_RADIUS if dark["role"] == "student" else NORMAL_RADIUS
                assert dark["vision_radius"] == expected

            col, row = load_map()["light_switch"]
            student.x, student.y = (col + 0.5) * TILE, (row + 0.5) * TILE  # skip the walk
            student_ws.send_json({"type": "fix"})
            running = receive_until(student_ws, lambda m: m["type"] == "state" and m["fixing"])
            assert running["fixing"]["seconds_left"] == 3
            student.fix_done_tick = fresh_game.tick + 2  # skip the waiting
            for ws in clients:
                receive_until(ws, lambda m: m["type"] == "state" and m["lights_on"])
