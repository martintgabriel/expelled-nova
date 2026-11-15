"""Unit tests for the game rules in server/game.py (no network)."""

import json
import math

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
