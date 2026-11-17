"""Unit tests for the game rules in server/game.py (no network)."""

import dataclasses
import json
import math
import random
from collections import deque

import pytest

from server.game import (
    EXPEL_COOLDOWN,
    EXPEL_RANGE,
    MAX_MESSAGE_BYTES,
    MAX_PLAYERS,
    PLAYER_HALF,
    RATE_LIMIT,
    STEP,
    TICK_RATE,
    Game,
    GameError,
    RateLimiter,
    load_map,
    parse_message,
    validate_nickname,
)

# A small room surrounded by walls. Tiles are 32 px, so the floor spans
# x = 32..224 and y = 32..128. The spawn tile (2, 2) has its centre at (80, 80).
TEST_MAP = {
    "tile_size": 32,
    "grid": [
        "########",
        "#......#",
        "#......#",
        "#......#",
        "########",
    ],
    "areas": [],
    "spawns": [[2, 2]],
}

# Closest x a player can stand to the left wall (wall ends at x = 32).
LEFT_WALL_X = 32 + PLAYER_HALF


def new_game():
    return Game(TEST_MAP)


def state_of(game):
    """Everything about the players that a rejected action must not change."""
    return [(p.id, p.name, p.x, p.y, p.dx, p.dy) for p in game.players.values()]


# --- Join and nicknames -------------------------------------------------------


def test_join_places_player_on_spawn():
    game = new_game()
    player = game.join("Ana")
    assert player.name == "Ana"
    assert (player.x, player.y) == (80, 80)
    assert player.id in game.players


@pytest.mark.parametrize("name", ["A", "Ana 2", "x" * 16, "João", "Bea 99"])
def test_valid_nicknames_are_accepted(name):
    assert validate_nickname(name) == name


def test_nickname_surrounding_spaces_are_trimmed():
    assert validate_nickname("  Ana  ") == "Ana"


@pytest.mark.parametrize(
    "name",
    ["", "   ", "x" * 17, "Ana!", "<script>", "Ana\n", "Tab\tName", "Smile 🙂", "a_b"],
)
def test_invalid_nicknames_are_rejected(name):
    game = new_game()
    with pytest.raises(GameError):
        game.join(name)
    assert game.players == {}


@pytest.mark.parametrize("name", [None, 123, ["Ana"], {"name": "Ana"}])
def test_non_text_nicknames_are_rejected(name):
    game = new_game()
    with pytest.raises(GameError):
        game.join(name)
    assert game.players == {}


def test_duplicate_nickname_is_rejected():
    game = new_game()
    game.join("Ana")
    with pytest.raises(GameError, match="taken"):
        game.join("Ana")
    assert len(game.players) == 1


def test_duplicate_nickname_ignores_case_and_spaces():
    game = new_game()
    game.join("Ana")
    with pytest.raises(GameError, match="taken"):
        game.join(" ana ")
    assert len(game.players) == 1


def test_eleventh_player_is_rejected():
    game = new_game()
    for i in range(MAX_PLAYERS):
        game.join(f"Player {i}")
    with pytest.raises(GameError, match="full"):
        game.join("Eleven")
    assert len(game.players) == MAX_PLAYERS


def test_slot_and_nickname_are_free_again_after_leaving():
    game = new_game()
    players = [game.join(f"Player {i}") for i in range(MAX_PLAYERS)]
    game.leave(players[0].id)
    again = game.join("Player 0")
    assert again.id != players[0].id
    assert len(game.players) == MAX_PLAYERS


# --- Leaving ------------------------------------------------------------------


def test_disconnect_removes_player():
    game = new_game()
    ana = game.join("Ana")
    bea = game.join("Bea")
    game.leave(ana.id)
    assert ana.id not in game.players
    assert [p["id"] for p in game.snapshot()["players"]] == [bea.id]


def test_leaving_twice_or_unknown_id_is_harmless():
    game = new_game()
    ana = game.join("Ana")
    game.leave(ana.id)
    game.leave(ana.id)
    game.leave("nobody")
    assert game.players == {}


# --- Movement -----------------------------------------------------------------


@pytest.mark.parametrize(
    "dx, dy, expected",
    [(1, 0, (80 + STEP, 80)), (-1, 0, (80 - STEP, 80)), (0, 1, (80, 80 + STEP)), (0, -1, (80, 80 - STEP))],
)
def test_movement_at_fixed_speed(dx, dy, expected):
    game = new_game()
    player = game.join("Ana")
    game.set_input(player.id, {"type": "input", "dx": dx, "dy": dy})
    game.step()
    assert (player.x, player.y) == pytest.approx(expected)


def test_diagonal_movement_is_not_faster():
    game = new_game()
    player = game.join("Ana")
    game.set_input(player.id, {"type": "input", "dx": 1, "dy": 1})
    game.step()
    distance = math.hypot(player.x - 80, player.y - 80)
    assert distance == pytest.approx(STEP)
    assert player.x > 80 and player.y > 80


def test_zero_input_stops_player():
    game = new_game()
    player = game.join("Ana")
    game.set_input(player.id, {"type": "input", "dx": 1, "dy": 0})
    game.step()
    game.set_input(player.id, {"type": "input", "dx": 0, "dy": 0})
    before = (player.x, player.y)
    game.step()
    assert (player.x, player.y) == before


def test_moving_into_wall_is_rejected_and_position_unchanged():
    game = new_game()
    player = game.join("Ana")
    player.x = LEFT_WALL_X  # standing right next to the left wall
    game.set_input(player.id, {"type": "input", "dx": -1, "dy": 0})
    game.step()
    assert (player.x, player.y) == (LEFT_WALL_X, 80)


def test_walking_towards_wall_stops_flush_and_never_enters():
    game = new_game()
    player = game.join("Ana")
    game.set_input(player.id, {"type": "input", "dx": -1, "dy": -1})
    for _ in range(100):
        game.step()
    # Top-left corner of the room: the hitbox is within 1 px of both walls
    # (moves are checked in pieces of at most 1 px) and never inside them.
    assert LEFT_WALL_X <= player.x < LEFT_WALL_X + 1
    assert 32 + PLAYER_HALF <= player.y < 32 + PLAYER_HALF + 1


def test_diagonal_into_wall_slides_along_it():
    game = new_game()
    player = game.join("Ana")
    player.x = LEFT_WALL_X
    game.set_input(player.id, {"type": "input", "dx": -1, "dy": 1})
    game.step()
    assert player.x == LEFT_WALL_X  # blocked axis unchanged
    assert player.y == pytest.approx(80 + STEP / math.sqrt(2))  # free axis moves


# --- Invalid input messages ---------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        {"type": "input", "dy": 0},
        {"type": "input", "dx": 0},
        {"type": "input", "dx": 2, "dy": 0},
        {"type": "input", "dx": "1", "dy": 0},
        {"type": "input", "dx": 0.5, "dy": 0},
        {"type": "input", "dx": True, "dy": 0},
        {"type": "input", "dx": None, "dy": 0},
        {"type": "input", "dx": 0, "dy": -2},
        {"type": "teleport", "dx": 1, "dy": 0},
        ["input", 1, 0],
        "input",
    ],
)
def test_invalid_input_is_rejected_without_state_change(message):
    game = new_game()
    player = game.join("Ana")
    game.set_input(player.id, {"type": "input", "dx": 1, "dy": 0})
    before = state_of(game)
    with pytest.raises(GameError):
        game.set_input(player.id, message)
    assert state_of(game) == before


def test_input_from_unknown_player_is_rejected():
    game = new_game()
    game.join("Ana")
    before = state_of(game)
    with pytest.raises(GameError):
        game.set_input("nobody", {"type": "input", "dx": 1, "dy": 0})
    assert state_of(game) == before


# --- Raw messages -------------------------------------------------------------


def test_parse_valid_messages():
    assert parse_message('{"type": "join", "name": "Ana"}', joined=False)["name"] == "Ana"
    assert parse_message('{"type": "input", "dx": 1, "dy": 0}', joined=True)["dx"] == 1


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "{",
        "[1, 2]",
        '"join"',
        "42",
        None,
        b'{"type": "join", "name": "Ana"}',
        '{"type": "hack"}',
        '{"name": "Ana"}',
        '{"type": 5}',
    ],
)
def test_malformed_messages_are_rejected(raw):
    with pytest.raises(GameError):
        parse_message(raw, joined=False)


def test_oversized_message_is_rejected():
    raw = json.dumps({"type": "join", "name": "x" * MAX_MESSAGE_BYTES})
    with pytest.raises(GameError, match="too long"):
        parse_message(raw, joined=False)


def test_input_before_join_is_rejected():
    with pytest.raises(GameError, match="Join"):
        parse_message('{"type": "input", "dx": 1, "dy": 0}', joined=False)


def test_second_join_is_rejected():
    with pytest.raises(GameError, match="already"):
        parse_message('{"type": "join", "name": "Ana"}', joined=True)


# --- Rate limit ---------------------------------------------------------------


def test_messages_up_to_the_limit_are_accepted():
    limiter = RateLimiter()
    assert all(limiter.allow(i * 0.01) for i in range(RATE_LIMIT))


def test_messages_above_the_limit_are_rejected():
    limiter = RateLimiter()
    for i in range(RATE_LIMIT):
        limiter.allow(i * 0.01)
    assert limiter.allow(0.5) is False
    assert limiter.allow(0.9) is False


def test_rate_limit_recovers_after_one_second():
    limiter = RateLimiter()
    for i in range(RATE_LIMIT):
        limiter.allow(i * 0.01)
    assert limiter.allow(0.5) is False
    assert limiter.allow(1.0) is True


def test_steady_traffic_below_the_limit_is_never_rejected():
    limiter = RateLimiter()
    # 20 messages per second for 5 seconds.
    assert all(limiter.allow(i * 0.05) for i in range(100))


# --- Campus map data ----------------------------------------------------------


def test_campus_map_is_valid():
    campus = load_map()
    grid = campus["grid"]
    width = len(grid[0])
    assert all(len(row) == width for row in grid), "grid must be rectangular"
    assert set("".join(grid)) <= {"#", "."}
    assert grid[0] == "#" * width and grid[-1] == "#" * width
    assert all(row[0] == "#" and row[-1] == "#" for row in grid), "border must be walls"

    names = {area["name"] for area in campus["areas"]}
    assert names == {
        "Main Entrance",
        "Library",
        "Food Court",
        "Auditorium",
        "Student Services",
        "Courtyard",
    }
    for area in campus["areas"]:
        assert 0 <= area["x"] and area["x"] + area["w"] <= width
        assert 0 <= area["y"] and area["y"] + area["h"] <= len(grid)

    assert len(campus["spawns"]) >= MAX_PLAYERS
    for col, row in campus["spawns"]:
        assert grid[row][col] == "."


def test_every_campus_spawn_is_free_to_stand_on():
    game = Game(load_map())
    for i in range(MAX_PLAYERS):
        player = game.join(f"Player {i}")
        assert not game.blocked(player.x, player.y)


# --- Map connectivity: flood fill (review of spec 001) -------------------------


def reachable_tiles(game, start):
    """Every floor tile reachable from `start` (col, row), walking the 4 neighbours."""
    visited = {start}
    queue = deque([start])
    while queue:
        col, row = queue.popleft()
        for dc, dr in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            tile = (col + dc, row + dr)
            if tile in visited:
                continue
            if game.blocked(*game._tile_centre(*tile)):
                continue
            visited.add(tile)
            queue.append(tile)
    return visited


def area_floor_tiles(game, area):
    return [
        (col, row)
        for row in range(area["y"], area["y"] + area["h"])
        for col in range(area["x"], area["x"] + area["w"])
        if not game.blocked(*game._tile_centre(col, row))
    ]


def assert_every_spawn_and_area_is_reachable(game):
    """Every spawn point, and at least one floor tile of every area, is reachable from
    the first spawn point. Walks the floor (4 neighbours), checking each tile centre
    with Game.blocked(), so it holds for any map, not just the real campus."""
    reached = reachable_tiles(game, tuple(game.campus["spawns"][0]))
    for col, row in game.campus["spawns"]:
        assert (col, row) in reached, f"spawn {(col, row)} is unreachable"
    for area in game.campus["areas"]:
        floor = area_floor_tiles(game, area)
        assert floor, f"{area['name']} has no floor tile"
        assert any(tile in reached for tile in floor), f"{area['name']} is unreachable"


def test_every_campus_spawn_and_area_is_reachable_from_the_first_spawn():
    assert_every_spawn_and_area_is_reachable(Game(load_map()))


# A small room (columns 1-3) with a second, walled-off room (columns 5-6) that has
# no door: the same check must find it unreachable, so we know it really detects this.
CLOSED_ROOM_MAP = {
    "tile_size": 32,
    "grid": [
        "########",
        "#...#..#",
        "#...#..#",
        "########",
    ],
    "areas": [{"name": "Sealed Room", "x": 5, "y": 1, "w": 2, "h": 2, "color": "#000000"}],
    "spawns": [[1, 1]],
}


def test_flood_fill_detects_a_walled_off_room():
    game = Game(CLOSED_ROOM_MAP)
    with pytest.raises(AssertionError, match="Sealed Room"):
        assert_every_spawn_and_area_is_reachable(game)


# --- Lobby, host and secret roles (spec 002) ----------------------------------

# A player entry in a snapshot may only hold these keys (never a role).
PLAYER_KEYS = {"id", "name", "x", "y"}


def game_with(count, seed=0):
    """A lobby with `count` players and a seeded random generator. players[0] joined first."""
    game = Game(TEST_MAP, rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    return game, players


def roles_of(game):
    """Each player's own role, as their own snapshot shows it."""
    return {pid: game.snapshot_for(pid)["role"] for pid in game.players}


def examiners_of(game):
    return sorted(pid for pid, role in roles_of(game).items() if role == "examiner")


def host_seen_by_all(game):
    """The host id; every player's snapshot must show the same one."""
    hosts = {game.snapshot_for(pid)["host"] for pid in game.players}
    assert len(hosts) == 1
    return hosts.pop()


def assert_rejected_without_change(game, action, reason):
    """The action raises GameError with `reason` and changes neither phase nor roles."""
    phase, roles = game.phase, roles_of(game)
    with pytest.raises(GameError, match=reason):
        action()
    assert game.phase == phase
    assert roles_of(game) == roles


# Accepted actions


def test_new_game_is_in_lobby_and_first_player_is_host():
    game, players = game_with(3)
    assert game.phase == "lobby"
    for player in players:
        snapshot = game.snapshot_for(player.id)
        assert snapshot["phase"] == "lobby"
        assert snapshot["host"] == players[0].id
        assert snapshot["role"] is None


def test_host_starts_with_four_players():
    game, players = game_with(4)
    game.start(players[0].id)
    assert game.phase == "playing"
    assert sorted(roles_of(game).values()) == ["examiner", "student", "student", "student"]


@pytest.mark.parametrize(
    "count, examiners", [(4, 1), (5, 1), (6, 1), (7, 2), (8, 2), (9, 2), (10, 2)]
)
def test_number_of_examiners_depends_on_player_count(count, examiners):
    game, players = game_with(count)
    game.start(players[0].id)
    roles = list(roles_of(game).values())
    assert roles.count("examiner") == examiners
    assert roles.count("student") == count - examiners


def test_roles_are_random_but_fixed_by_the_seed():
    def examiners_for(seed):
        game, players = game_with(4, seed)
        game.start(players[0].id)
        return examiners_of(game)

    assert examiners_for(1) == examiners_for(1)
    # Not always the same player (e.g. not simply the first or the last to join).
    assert len({tuple(examiners_for(seed)) for seed in range(20)}) > 1


def test_players_can_move_while_playing():
    game, players = game_with(4)
    game.start(players[0].id)
    player = players[1]
    start_x = player.x
    game.set_input(player.id, {"type": "input", "dx": 1, "dy": 0})
    game.step()
    assert player.x == pytest.approx(start_x + STEP)


def test_start_message_is_accepted_after_joining():
    assert parse_message('{"type": "start"}', joined=True) == {"type": "start"}


# Rejected actions: each leaves phase and roles unchanged


def test_start_from_non_host_is_rejected():
    game, players = game_with(4)
    assert_rejected_without_change(game, lambda: game.start(players[1].id), "Only the host")
    assert game.phase == "lobby"


def test_start_with_three_players_is_rejected():
    game, players = game_with(3)
    assert_rejected_without_change(game, lambda: game.start(players[0].id), "at least 4 players")
    assert game.phase == "lobby"


def test_second_start_while_playing_is_rejected():
    game, players = game_with(7)
    game.start(players[0].id)
    assert_rejected_without_change(game, lambda: game.start(players[0].id), "already running")
    assert game.phase == "playing"


def test_start_from_unknown_player_is_rejected():
    game, _ = game_with(4)
    assert_rejected_without_change(game, lambda: game.start("nobody"), "Unknown player")


def test_join_while_playing_is_rejected():
    game, players = game_with(4)
    game.start(players[0].id)
    before = state_of(game)
    assert_rejected_without_change(game, lambda: game.join("Late"), "already running")
    assert state_of(game) == before


def test_start_before_joining_is_rejected():
    with pytest.raises(GameError, match="Join"):
        parse_message('{"type": "start"}', joined=False)


def test_snapshot_for_unknown_player_is_rejected():
    game, _ = game_with(2)
    with pytest.raises(GameError):
        game.snapshot_for("nobody")


# Host changes and edge cases


def test_host_leaving_in_lobby_passes_host_on():
    game, players = game_with(5)
    game.leave(players[0].id)
    assert host_seen_by_all(game) == players[1].id
    game.start(players[1].id)
    assert game.phase == "playing"


def test_host_leaving_while_playing_passes_host_on():
    game, players = game_with(5)
    game.start(players[0].id)
    roles = roles_of(game)
    game.leave(players[0].id)
    del roles[players[0].id]
    assert host_seen_by_all(game) == players[1].id
    assert game.phase == "playing"
    assert roles_of(game) == roles


def test_non_host_leaving_keeps_the_host():
    game, players = game_with(4)
    game.leave(players[2].id)
    assert host_seen_by_all(game) == players[0].id


def test_host_order_follows_join_time_not_nickname():
    game, (first, second, third) = game_with(3)
    game.leave(second.id)
    game.join(second.name)  # same nickname again, but now the newest player
    game.leave(first.id)
    assert host_seen_by_all(game) == third.id


def test_start_is_rejected_again_when_a_player_leaves_the_lobby():
    game, players = game_with(4)
    game.leave(players[3].id)
    assert_rejected_without_change(game, lambda: game.start(players[0].id), "at least 4 players")


def test_last_player_leaving_returns_the_game_to_lobby():
    game, players = game_with(4)
    game.start(players[0].id)
    for player in players:
        game.leave(player.id)
    assert game.phase == "lobby"
    newcomer = game.join("Newcomer")
    snapshot = game.snapshot_for(newcomer.id)
    assert snapshot["host"] == newcomer.id
    assert snapshot["role"] is None


# Secret roles: nobody learns another player's role


def test_student_snapshot_contains_no_other_role():
    game, players = game_with(4)
    game.start(players[0].id)
    student = next(pid for pid, role in roles_of(game).items() if role == "student")
    snapshot = game.snapshot_for(student)
    assert snapshot["role"] == "student"
    assert "fellow_examiners" not in snapshot
    assert len(snapshot["players"]) == 4
    assert all(set(p) == PLAYER_KEYS for p in snapshot["players"])
    assert "examiner" not in json.dumps(snapshot)


def test_examiner_snapshot_lists_fellow_examiner_and_no_student_roles():
    game, players = game_with(7)
    game.start(players[0].id)
    first, second = examiners_of(game)
    for me, fellow in [(first, second), (second, first)]:
        snapshot = game.snapshot_for(me)
        assert snapshot["role"] == "examiner"
        assert snapshot["fellow_examiners"] == [fellow]
        assert all(set(p) == PLAYER_KEYS for p in snapshot["players"])
        assert "student" not in json.dumps(snapshot)


def test_single_examiner_has_no_fellow_examiners():
    game, players = game_with(4)
    game.start(players[0].id)
    (examiner,) = examiners_of(game)
    assert game.snapshot_for(examiner)["fellow_examiners"] == []


def test_shared_snapshot_contains_no_roles():
    game, players = game_with(7)
    game.start(players[0].id)
    text = json.dumps(game.snapshot())
    assert "examiner" not in text
    assert "student" not in text


# --- Expel, ghosts, game end and new round (spec 003) -------------------------

# In TEST_MAP all players stand on the one spawn tile (80, 80), so everyone starts
# within expel range of everyone else.
COOLDOWN_TICKS = EXPEL_COOLDOWN * TICK_RATE


def playing(count=4, seed=0):
    """A started game. Returns the game, its examiners and its students (Player objects)."""
    game, players = game_with(count, seed)
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


def ready_game(count=4):
    """A started game in which the examiners' first cooldown is just over."""
    game, examiners, students = playing(count)
    wait_ticks(game, COOLDOWN_TICKS)
    return game, examiners, students


def examiners_won():
    """4 players: the examiner expels two students, so the game ends with an examiner win."""
    game, (examiner,), students = ready_game(4)
    game.expel(examiner.id, students[0].id)
    wait_ticks(game, COOLDOWN_TICKS)
    game.expel(examiner.id, students[1].id)
    return game, [examiner], students


def wait_ticks(game, ticks):
    for _ in range(ticks):
        game.step()


def place(player, x, y=80):
    player.x, player.y = x, y


def full_state(game):
    """Everything a rejected expel, move or restart must leave unchanged."""
    return (
        game.phase,
        game.winner,
        [dataclasses.asdict(p) for p in game.players.values()],
        [dataclasses.asdict(e) for e in game.failed_exams],
    )


def ids_in(snapshot):
    return sorted(p["id"] for p in snapshot["players"])


# Accepted actions


def test_examiner_expels_student_in_range_after_cooldown():
    game, (examiner,), students = ready_game(4)
    target = students[0]
    place(target, 100, 90)  # about 22 px from the examiner at (80, 80)
    game.expel(examiner.id, target.id)
    assert target.alive is False
    assert game.phase == "playing"  # 1 examiner, 2 living students
    (exam,) = game.failed_exams
    assert (exam.x, exam.y) == (100, 90)
    assert exam.id not in game.players  # its own id, not the player's
    assert game.snapshot_for(examiner.id)["expel_cooldown"] == EXPEL_COOLDOWN


def test_expel_exactly_when_cooldown_ends_is_accepted():
    game, (examiner,), students = playing(4)
    wait_ticks(game, COOLDOWN_TICKS)  # exactly 20 seconds of ticks
    game.expel(examiner.id, students[0].id)
    assert students[0].alive is False


def test_expel_at_exactly_expel_range_is_accepted():
    game, (examiner,), students = ready_game(4)
    place(examiner, 80)
    place(students[0], 80 + EXPEL_RANGE)
    game.expel(examiner.id, students[0].id)
    assert students[0].alive is False


def test_cooldown_restarts_after_an_expel():
    game, (examiner,), students = ready_game(5)
    game.expel(examiner.id, students[0].id)
    with pytest.raises(GameError, match="Cooldown"):
        game.expel(examiner.id, students[1].id)
    wait_ticks(game, COOLDOWN_TICKS - 1)
    with pytest.raises(GameError, match="Cooldown"):
        game.expel(examiner.id, students[1].id)
    game.step()
    game.expel(examiner.id, students[1].id)
    assert students[1].alive is False
    assert game.phase == "playing"  # 1 examiner, 2 living students


def test_examiner_snapshot_shows_cooldown_seconds_left():
    game, (examiner,), students = playing(4)
    assert game.snapshot_for(examiner.id)["expel_cooldown"] == EXPEL_COOLDOWN
    wait_ticks(game, COOLDOWN_TICKS - 1)
    assert game.snapshot_for(examiner.id)["expel_cooldown"] == 1  # one tick left: rounded up
    game.step()
    assert game.snapshot_for(examiner.id)["expel_cooldown"] == 0
    for student in students:
        assert "expel_cooldown" not in game.snapshot_for(student.id)


def test_ghost_keeps_moving_and_walls_still_block():
    game, (examiner,), students = ready_game(4)
    ghost = students[0]
    game.expel(examiner.id, ghost.id)
    game.set_input(ghost.id, {"type": "input", "dx": 1, "dy": 0})
    game.step()
    assert ghost.x == pytest.approx(80 + STEP)
    place(ghost, LEFT_WALL_X)
    game.set_input(ghost.id, {"type": "input", "dx": -1, "dy": 0})
    game.step()
    assert (ghost.x, ghost.y) == (LEFT_WALL_X, 80)


def test_expel_and_restart_messages_are_parsed_after_joining():
    assert parse_message('{"type": "expel", "target": "p2"}', joined=True)["target"] == "p2"
    assert parse_message('{"type": "restart"}', joined=True) == {"type": "restart"}


@pytest.mark.parametrize("raw", ['{"type": "expel", "target": "p2"}', '{"type": "restart"}'])
def test_expel_and_restart_before_joining_are_rejected(raw):
    with pytest.raises(GameError, match="Join"):
        parse_message(raw, joined=False)


# Rejected expels: each case returns (game, sender id, target) ready for one expel


def one_tick_before_cooldown_ends():
    game, examiners, students = playing(4)
    wait_ticks(game, COOLDOWN_TICKS - 1)
    return game, examiners[0].id, students[0].id


def out_of_range():
    game, examiners, students = ready_game(4)
    place(examiners[0], 80)
    place(students[0], 80 + EXPEL_RANGE + 1)
    return game, examiners[0].id, students[0].id


def target_is_fellow_examiner():
    game, examiners, _ = ready_game(7)
    return game, examiners[0].id, examiners[1].id


def target_is_self():
    game, examiners, _ = ready_game(4)
    return game, examiners[0].id, examiners[0].id


def target_is_ghost():
    game, examiners, students = ready_game(4)
    game.expel(examiners[0].id, students[0].id)
    wait_ticks(game, COOLDOWN_TICKS)
    return game, examiners[0].id, students[0].id


def sender_is_student():
    game, _, students = ready_game(4)
    return game, students[0].id, students[1].id


def sender_is_ghost_student():
    game, examiners, students = ready_game(4)
    game.expel(examiners[0].id, students[0].id)
    return game, students[0].id, students[1].id


def sender_is_ghost_examiner():
    # Examiners only become ghosts by vote (spec 006); set it directly here.
    game, examiners, students = ready_game(7)
    examiners[0].alive = False
    return game, examiners[0].id, students[0].id


def in_lobby():
    game, players = game_with(4)
    return game, players[0].id, players[1].id


def in_ended():
    game, examiners, students = examiners_won()
    wait_ticks(game, COOLDOWN_TICKS)
    return game, examiners[0].id, students[2].id


def unknown_target():
    game, examiners, _ = ready_game(4)
    return game, examiners[0].id, "nobody"


def unknown_sender():
    game, _, students = ready_game(4)
    return game, "nobody", students[0].id


@pytest.mark.parametrize(
    "case, reason",
    [
        (one_tick_before_cooldown_ends, "Cooldown"),
        (out_of_range, "Too far away"),
        (target_is_fellow_examiner, "Cannot expel an examiner"),
        (target_is_self, "Cannot expel an examiner"),
        (target_is_ghost, "Already expelled"),
        (sender_is_student, "Only examiners can expel"),
        (sender_is_ghost_student, "Ghosts cannot expel"),
        (sender_is_ghost_examiner, "Ghosts cannot expel"),
        (in_lobby, "not started"),
        (in_ended, "Game is over"),
        (unknown_target, "Unknown target"),
        (unknown_sender, "Unknown player"),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_expel_changes_nothing(case, reason):
    game, sender, target = case()
    before = full_state(game)
    with pytest.raises(GameError, match=reason):
        game.expel(sender, target)
    assert full_state(game) == before


@pytest.mark.parametrize("target", [2, None, True, ["p2"], {"id": "p2"}])
def test_expel_target_that_is_not_a_string_is_rejected(target):
    game, examiners, _ = ready_game(4)
    before = full_state(game)
    with pytest.raises(GameError, match="Target must be a player id"):
        game.expel(examiners[0].id, target)
    assert full_state(game) == before


def test_movement_in_ended_is_rejected():
    game, _, students = examiners_won()
    before = full_state(game)
    with pytest.raises(GameError, match="Game is over"):
        game.set_input(students[2].id, {"type": "input", "dx": 1, "dy": 0})
    assert full_state(game) == before


# Simultaneous actions


def test_two_expels_of_the_same_student_in_one_tick_first_wins():
    game, (first, second), students = ready_game(7)
    target = students[0]
    game.expel(first.id, target.id)
    with pytest.raises(GameError, match="Already expelled"):
        game.expel(second.id, target.id)  # same tick: no step() in between
    assert len(game.failed_exams) == 1
    assert game.snapshot_for(second.id)["expel_cooldown"] == 0  # unchanged


# Winning


def test_examiners_win_when_they_equal_the_living_students():
    game, (examiner,), students = ready_game(4)
    game.expel(examiner.id, students[0].id)
    assert game.phase == "playing"  # 1 examiner, 2 living students
    wait_ticks(game, COOLDOWN_TICKS)
    game.expel(examiner.id, students[1].id)
    assert game.phase == "ended"  # 1 examiner, 1 living student
    assert game.snapshot_for(examiner.id)["winner"] == "examiners"


def test_students_win_when_the_only_examiner_leaves():
    game, (examiner,), students = playing(4)
    game.leave(examiner.id)
    assert game.phase == "ended"
    for student in students:
        assert game.snapshot_for(student.id)["winner"] == "students"


def test_one_of_two_examiners_leaving_keeps_the_game_running():
    game, (first, second), _ = playing(7)
    game.leave(first.id)
    assert game.phase == "playing"
    assert "winner" not in game.snapshot_for(second.id)


def test_student_leaving_can_give_the_examiners_the_win():
    game, (examiner,), students = ready_game(4)
    game.expel(examiner.id, students[0].id)  # 1 examiner, 2 living students
    game.leave(students[1].id)  # 1 examiner, 1 living student
    assert game.phase == "ended"
    assert game.snapshot_for(examiner.id)["winner"] == "examiners"


def test_everyone_leaving_after_an_expel_leaves_a_clean_lobby():
    game, (examiner,), students = ready_game(4)
    game.expel(examiner.id, students[0].id)
    for player_id in list(game.players):
        game.leave(player_id)
    assert game.phase == "lobby"
    newcomer = game.join("Newcomer")
    snapshot = game.snapshot_for(newcomer.id)
    assert snapshot["failed_exams"] == []
    assert snapshot["alive"] is True
    assert "winner" not in snapshot


def test_nobody_keeps_walking_when_the_game_ends():
    game, (examiner,), students = ready_game(4)
    game.expel(examiner.id, students[0].id)
    wait_ticks(game, COOLDOWN_TICKS)
    walker = students[2]
    game.set_input(walker.id, {"type": "input", "dx": 1, "dy": 0})
    game.expel(examiner.id, students[1].id)  # examiners win
    before = (walker.x, walker.y)
    game.step()
    assert (walker.x, walker.y) == before


# Snapshots: who sees ghosts, failed exams and roles


def test_living_player_does_not_see_ghosts_but_sees_the_failed_exam():
    game, (examiner,), students = ready_game(4)
    ghost = students[0]
    game.expel(examiner.id, ghost.id)
    for player in [examiner, students[1], students[2]]:
        snapshot = game.snapshot_for(player.id)
        assert snapshot["alive"] is True
        assert ids_in(snapshot) == sorted([examiner.id, students[1].id, students[2].id])
        assert [set(e) for e in snapshot["failed_exams"]] == [{"id", "x", "y"}]
        assert (snapshot["failed_exams"][0]["x"], snapshot["failed_exams"][0]["y"]) == (80, 80)


def test_ghost_sees_everyone():
    game, (examiner,), students = ready_game(4)
    ghost = students[0]
    game.expel(examiner.id, ghost.id)
    snapshot = game.snapshot_for(ghost.id)
    assert snapshot["alive"] is False
    assert ids_in(snapshot) == sorted(game.players)
    assert snapshot["ghosts"] == [ghost.id]
    assert len(snapshot["failed_exams"]) == 1


def test_no_snapshot_shows_other_roles_before_the_end():
    game, examiners, students = ready_game(7)
    game.expel(examiners[0].id, students[0].id)  # one ghost in the game
    for player_id, player in game.players.items():
        snapshot = game.snapshot_for(player_id)
        assert "roles" not in snapshot
        assert "winner" not in snapshot
        assert all(set(p) == PLAYER_KEYS for p in snapshot["players"])
        if player.role == "student":
            assert "examiner" not in json.dumps(snapshot)


def test_all_roles_and_the_winner_are_shown_at_the_end():
    game, _, students = examiners_won()
    roles = {p.id: p.role for p in game.players.values()}
    for player_id in game.players:
        snapshot = game.snapshot_for(player_id)
        assert snapshot["phase"] == "ended"
        assert snapshot["winner"] == "examiners"
        assert snapshot["roles"] == roles
        assert ids_in(snapshot) == sorted(game.players)  # ghosts included
        assert sorted(snapshot["ghosts"]) == sorted([students[0].id, students[1].id])


# New round


def test_host_starts_a_new_round_after_the_end():
    game, _, _ = examiners_won()
    ids = list(game.players)
    host = ids[0]
    for player in game.players.values():
        place(player, 150, 100)  # away from the spawn point
    game.restart(host)
    assert game.phase == "lobby"
    assert list(game.players) == ids  # the same players stay
    spawn_points = {((col + 0.5) * 32, (row + 0.5) * 32) for col, row in TEST_MAP["spawns"]}
    for player in game.players.values():
        assert (player.x, player.y) in spawn_points
        snapshot = game.snapshot_for(player.id)
        assert snapshot["role"] is None
        assert snapshot["alive"] is True
        assert snapshot["failed_exams"] == []
        assert "winner" not in snapshot and "roles" not in snapshot
        assert ids_in(snapshot) == sorted(ids)

    game.start(host)
    (examiner,) = [p for p in game.players.values() if p.role == "examiner"]
    assert game.snapshot_for(examiner.id)["expel_cooldown"] == EXPEL_COOLDOWN


def restart_by_non_host_in_ended():
    game, _, _ = examiners_won()
    return game, list(game.players)[1]


def restart_by_host_in_lobby():
    game, players = game_with(4)
    return game, players[0].id


def restart_by_host_while_playing():
    game, _, _ = playing(4)
    return game, game.host_id


def restart_by_unknown_player():
    game, _, _ = examiners_won()
    return game, "nobody"


@pytest.mark.parametrize(
    "case, reason",
    [
        (restart_by_non_host_in_ended, "Only the host"),
        (restart_by_host_in_lobby, "not over"),
        (restart_by_host_while_playing, "not over"),
        (restart_by_unknown_player, "Unknown player"),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_restart_changes_nothing(case, reason):
    game, sender = case()
    before = full_state(game)
    with pytest.raises(GameError, match=reason):
        game.restart(sender)
    assert full_state(game) == before
