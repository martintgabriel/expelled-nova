"""Unit tests for the game rules in server/game.py (no network)."""

import json
import math
import random

import pytest

from server.game import (
    MAX_MESSAGE_BYTES,
    MAX_PLAYERS,
    PLAYER_HALF,
    RATE_LIMIT,
    STEP,
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
