"""Tests for spec 005 (look): player colours, the vision radius and the current area.

Unit tests against server/game.py first, then the WebSocket endpoint and the static page.
"""

import json
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.game import (
    EXPEL_COOLDOWN,
    MAX_PLAYERS,
    STEP,
    TICK_RATE,
    VISION_TILES,
    Game,
    GameError,
    load_map,
)
from server.main import app, game as shared_game

TILE = 32

# One big open hall, 30 x 16 tiles, with two named areas and a "corridor" between them.
# All ten spawn tiles are next to each other, so at the start everyone sees everyone.
LOOK_MAP = {
    "tile_size": TILE,
    "grid": ["#" * 30] + ["#" + "." * 28 + "#"] * 14 + ["#" * 30],
    "areas": [
        {"name": "West Hall", "x": 1, "y": 1, "w": 4, "h": 3, "color": "#3f6e8c"},
        {"name": "East Hall", "x": 10, "y": 1, "w": 5, "h": 3, "color": "#7a4f86"},
    ],
    "spawns": [[2, 2], [3, 2], [4, 2], [5, 2], [6, 2], [2, 3], [3, 3], [4, 3], [5, 3], [6, 3]],
}

RADIUS = VISION_TILES * TILE  # 192 px
PLAYER_KEYS = {"id", "name", "x", "y"}
COOLDOWN_TICKS = EXPEL_COOLDOWN * TICK_RATE


def lobby(count, seed=0):
    """A lobby with `count` players. players[0] joined first and is the host."""
    game = Game(LOOK_MAP, rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    return game, players


def playing(count=4, seed=0):
    """A started game. Returns the game, its examiners and its students (Player objects)."""
    game, players = lobby(count, seed)
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


def place(player, col, row):
    """Put a player on the centre of a tile."""
    player.x, player.y = (col + 0.5) * TILE, (row + 0.5) * TILE


def wait_ticks(game, ticks):
    for _ in range(ticks):
        game.step()


def expel_first_student(game, examiner, students):
    """The examiner expels students[0] where they stand. The game goes on (2 students left)."""
    wait_ticks(game, COOLDOWN_TICKS)
    examiner.x, examiner.y = students[0].x, students[0].y
    game.expel(examiner.id, students[0].id)
    return students[0]


def ids_in(snapshot):
    return sorted(p["id"] for p in snapshot["players"])


def colours_in_game(game):
    return {p.id: p.color for p in game.players.values()}


# --- Colours: accepted ----------------------------------------------------------


def test_first_players_get_the_lowest_colours():
    game, players = lobby(3)
    assert [p.color for p in players] == [0, 1, 2]


def test_ten_players_get_ten_different_colours():
    game, players = lobby(MAX_PLAYERS)
    colors = game.snapshot_for(players[0].id)["colors"]
    assert sorted(colors.values()) == list(range(10))


def test_colors_lists_exactly_the_players_in_the_snapshot():
    game, players = lobby(4)
    snapshot = game.snapshot_for(players[2].id)
    assert snapshot["colors"] == {p.id: p.color for p in players}
    assert sorted(snapshot["colors"]) == ids_in(snapshot)
    assert all(set(p) == PLAYER_KEYS for p in snapshot["players"])


def test_everyone_receives_the_same_colours():
    game, players = lobby(5)
    views = [game.snapshot_for(p.id)["colors"] for p in players]
    assert all(view == views[0] for view in views)


# --- Colours: rejected ----------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["", "x" * 17, "Ana!", "player 0", None],
    ids=["empty", "too long", "invalid character", "duplicate", "not text"],
)
def test_rejected_join_uses_no_colour(name):
    game, players = lobby(2)
    before = colours_in_game(game)
    with pytest.raises(GameError):
        game.join(name)
    assert colours_in_game(game) == before
    assert game.join("Next").color == 2


def test_eleventh_player_gets_no_colour():
    game, players = lobby(MAX_PLAYERS)
    before = colours_in_game(game)
    with pytest.raises(GameError, match="full"):
        game.join("Eleven")
    assert colours_in_game(game) == before


def test_join_while_playing_changes_no_colours():
    game, examiners, students = playing(4)
    before = colours_in_game(game)
    with pytest.raises(GameError, match="already running"):
        game.join("Late")
    assert colours_in_game(game) == before


# --- Colours: edge cases --------------------------------------------------------


def test_leaving_frees_the_colour_for_the_next_player():
    game, players = lobby(4)
    game.leave(players[1].id)  # had colour 1
    newcomer = game.join("Newcomer")
    assert newcomer.color == 1
    assert [players[0].color, players[2].color, players[3].color] == [0, 2, 3]


def test_lowest_free_colour_is_taken_first():
    game, players = lobby(5)
    game.leave(players[3].id)  # frees 3
    game.leave(players[1].id)  # frees 1
    assert game.join("First back").color == 1
    assert game.join("Second back").color == 3
    assert game.join("Brand new").color == 5


def test_colours_survive_start_expel_end_and_new_round():
    game, (examiner,), students = playing(4)
    before = colours_in_game(game)

    expel_first_student(game, examiner, students)
    assert colours_in_game(game) == before  # the ghost keeps their colour
    assert game.snapshot_for(students[0].id)["colors"] == before  # a ghost sees everyone

    wait_ticks(game, COOLDOWN_TICKS)
    examiner.x, examiner.y = students[1].x, students[1].y
    game.expel(examiner.id, students[1].id)
    assert game.phase == "ended"
    assert game.snapshot_for(students[2].id)["colors"] == before

    game.restart(game.host_id)
    assert game.phase == "lobby"
    assert game.snapshot_for(students[2].id)["colors"] == before


# --- Vision radius: accepted ----------------------------------------------------


def test_vision_radius_is_six_tiles():
    assert VISION_TILES == 6
    assert Game(LOOK_MAP).vision_radius == RADIUS
    assert Game(load_map()).vision_radius == 192


def test_living_player_sees_a_living_player_five_tiles_away():
    game, examiners, students = playing(4)
    viewer, other = students[0], students[1]
    place(viewer, 2, 2)
    place(other, 7, 2)
    snapshot = game.snapshot_for(viewer.id)
    seen = next(p for p in snapshot["players"] if p["id"] == other.id)
    assert (seen["x"], seen["y"]) == (other.x, other.y)
    assert snapshot["colors"][other.id] == other.color


def test_living_player_sees_a_failed_exam_within_the_radius():
    game, (examiner,), students = playing(4)
    ghost = expel_first_student(game, examiner, students)
    viewer = students[1]
    viewer.x, viewer.y = ghost.x + 5 * TILE, ghost.y
    (exam,) = game.snapshot_for(viewer.id)["failed_exams"]
    assert set(exam) == {"id", "x", "y"}
    assert (exam["x"], exam["y"]) == (ghost.x, ghost.y)


# --- Vision radius: rejected (not sent) -----------------------------------------


def test_living_player_does_not_receive_a_player_outside_the_radius():
    game, examiners, students = playing(4)
    viewer, other = students[0], students[1]
    place(viewer, 2, 2)
    place(other, 9, 2)  # 7 tiles away
    snapshot = game.snapshot_for(viewer.id)
    assert other.id not in ids_in(snapshot)
    assert other.id not in snapshot["colors"]
    assert other.name not in json.dumps(snapshot)
    # Vision is mutual: the other player does not receive the viewer either.
    assert viewer.id not in ids_in(game.snapshot_for(other.id))


def test_living_player_does_not_receive_a_failed_exam_outside_the_radius():
    game, (examiner,), students = playing(4)
    ghost = expel_first_student(game, examiner, students)
    viewer = students[1]
    viewer.x, viewer.y = ghost.x + 7 * TILE, ghost.y
    assert game.snapshot_for(viewer.id)["failed_exams"] == []
    assert len(game.failed_exams) == 1  # still there, just out of sight


def test_extra_fields_in_an_input_message_do_not_widen_vision():
    game, examiners, students = playing(4)
    viewer, other = students[0], students[1]
    place(viewer, 2, 2)
    place(other, 9, 2)
    message = {"type": "input", "dx": 0, "dy": 0, "vision": 9999, "vision_radius": 9999}
    try:
        game.set_input(viewer.id, message)
    except GameError:
        pass  # rejecting the whole message is fine too
    assert game.vision_radius == RADIUS
    assert other.id not in ids_in(game.snapshot_for(viewer.id))


# --- Vision radius: edge cases --------------------------------------------------


def test_exactly_at_the_radius_is_visible_one_pixel_further_is_not():
    game, examiners, students = playing(4)
    viewer, other = students[0], students[1]
    viewer.x, viewer.y = 100, 100
    other.x, other.y = 100 + RADIUS, 100
    assert other.id in ids_in(game.snapshot_for(viewer.id))
    other.x += 1
    assert other.id not in ids_in(game.snapshot_for(viewer.id))


def test_exam_exactly_at_the_radius_is_visible_one_pixel_further_is_not():
    game, (examiner,), students = playing(4)
    ghost = expel_first_student(game, examiner, students)
    viewer = students[1]
    viewer.x, viewer.y = ghost.x, ghost.y + RADIUS
    assert len(game.snapshot_for(viewer.id)["failed_exams"]) == 1
    viewer.y += 1
    assert game.snapshot_for(viewer.id)["failed_exams"] == []


def test_vision_is_a_circle_not_a_square():
    game, examiners, students = playing(4)
    viewer, other = students[0], students[1]
    place(viewer, 2, 2)
    place(other, 7, 2)  # 5 tiles right
    assert other.id in ids_in(game.snapshot_for(viewer.id))
    place(other, 2, 7)  # 5 tiles down
    assert other.id in ids_in(game.snapshot_for(viewer.id))
    place(other, 7, 7)  # 5 right and 5 down: about 7.1 tiles
    assert other.id not in ids_in(game.snapshot_for(viewer.id))


def test_player_always_sees_themself_even_alone():
    game, examiners, students = playing(4)
    viewer = students[0]
    place(viewer, 2, 2)
    for index, other in enumerate(p for p in game.players.values() if p is not viewer):
        place(other, 20 + index * 2, 12)
    snapshot = game.snapshot_for(viewer.id)
    assert ids_in(snapshot) == [viewer.id]
    assert snapshot["colors"] == {viewer.id: viewer.color}


def test_hidden_player_appears_when_walking_towards_them():
    game, examiners, students = playing(4)
    viewer, other = students[0], students[1]
    viewer.x, viewer.y = 100, 100
    other.x, other.y = 100 + RADIUS + STEP, 100  # one step too far
    assert other.id not in ids_in(game.snapshot_for(viewer.id))
    game.set_input(viewer.id, {"type": "input", "dx": 1, "dy": 0})
    game.step()
    assert other.id in ids_in(game.snapshot_for(viewer.id))


def test_ghost_sees_everyone_and_every_failed_exam_at_any_distance():
    game, (examiner,), students = playing(4)
    ghost = expel_first_student(game, examiner, students)
    place(ghost, 2, 2)
    place(examiner, 26, 2)
    place(students[1], 26, 13)
    place(students[2], 2, 13)
    snapshot = game.snapshot_for(ghost.id)
    assert ids_in(snapshot) == sorted(game.players)
    assert sorted(snapshot["colors"]) == sorted(game.players)
    assert len(snapshot["failed_exams"]) == 1
    # The living still do not receive the ghost, even when it stands next to them.
    place(ghost, 26, 3)
    assert ghost.id not in ids_in(game.snapshot_for(examiner.id))


def test_everyone_sees_everyone_in_the_lobby():
    game, players = lobby(4)
    for index, player in enumerate(players):
        place(player, 2 + index * 8, 2)
    for player in players:
        assert ids_in(game.snapshot_for(player.id)) == sorted(game.players)


def test_everyone_sees_everyone_after_the_end():
    game, (examiner,), students = playing(4)
    expel_first_student(game, examiner, students)
    wait_ticks(game, COOLDOWN_TICKS)
    examiner.x, examiner.y = students[1].x, students[1].y
    game.expel(examiner.id, students[1].id)
    assert game.phase == "ended"
    for index, player in enumerate(game.players.values()):
        place(player, 2 + index * 8, 2)
    for player_id in game.players:
        snapshot = game.snapshot_for(player_id)
        assert ids_in(snapshot) == sorted(game.players)
        assert len(snapshot["failed_exams"]) == 2


def test_fellow_examiner_out_of_sight_is_listed_but_not_located():
    game, (first, second), students = playing(7)
    place(first, 2, 2)
    place(second, 26, 13)
    snapshot = game.snapshot_for(first.id)
    assert snapshot["fellow_examiners"] == [second.id]
    assert second.id not in ids_in(snapshot)
    assert second.id not in snapshot["colors"]


# --- Current area ----------------------------------------------------------------


def test_area_at_returns_the_area_name_inside_an_area():
    game = Game(LOOK_MAP)
    assert game.area_at(2.5 * TILE, 2.5 * TILE) == "West Hall"
    assert game.area_at(12.5 * TILE, 2.5 * TILE) == "East Hall"


def test_area_at_edges_of_an_area():
    game = Game(LOOK_MAP)  # West Hall covers the tiles x 1-4, y 1-3
    assert game.area_at(1 * TILE, 1 * TILE) == "West Hall"  # first pixel of the first tile
    assert game.area_at(5 * TILE - 0.1, 4 * TILE - 0.1) == "West Hall"  # last tile
    assert game.area_at(5 * TILE, 2.5 * TILE) is None  # one tile to the right
    assert game.area_at(2.5 * TILE, 4 * TILE) is None  # one tile below
    assert game.area_at(1 * TILE - 0.1, 2.5 * TILE) is None  # the wall on the left


def test_area_at_is_none_in_a_corridor():
    game = Game(LOOK_MAP)
    assert game.area_at(7.5 * TILE, 2.5 * TILE) is None


def test_snapshot_area_follows_the_players_own_position():
    game, players = lobby(2)
    walker, other = players
    assert game.snapshot_for(walker.id)["area"] == "West Hall"  # the spawn tile
    place(walker, 7, 2)
    assert game.snapshot_for(walker.id)["area"] is None
    place(walker, 12, 2)
    assert game.snapshot_for(walker.id)["area"] == "East Hall"
    assert game.snapshot_for(other.id)["area"] == "West Hall"  # each player gets their own


def test_every_campus_spawn_is_in_the_main_entrance():
    game = Game(load_map())
    for index in range(MAX_PLAYERS):
        player = game.join(f"Player {index}")
        assert game.snapshot_for(player.id)["area"] == "Main Entrance"


# --- Over the real WebSocket endpoint ---------------------------------------------

TWO_SECONDS = 2 * TICK_RATE


def receive_until(ws, predicate, limit=TWO_SECONDS):
    """Read messages until one matches, or fail after `limit` messages."""
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def join(ws, name, **extra):
    ws.send_json({"type": "join", "name": name, **extra})
    return receive_until(ws, lambda m: m["type"] in ("welcome", "error"))


def test_clients_receive_server_colours_and_cannot_pick_their_own():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
            welcome_a = join(a, "Alice", color=7)  # the extra field is ignored
            assert welcome_a["type"] == "welcome"
            assert welcome_a["vision_radius"] == VISION_TILES * welcome_a["map"]["tile_size"]
            welcome_b = join(b, "Bob", color=7)
            a_id, b_id = welcome_a["id"], welcome_b["id"]

            def both(m):
                return m["type"] == "state" and len(m["players"]) == 2

            state_a = receive_until(a, both)
            state_b = receive_until(b, both)
            assert state_a["colors"] == state_b["colors"] == {a_id: 0, b_id: 1}
            assert state_a["area"] == "Main Entrance"


def test_player_far_away_disappears_from_a_living_players_state():
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            clients = [a, b, c, d]
            ids = [join(ws, name)["id"] for ws, name in zip(clients, ["Olga", "Paul", "Quin", "Rosa"])]
            a.send_json({"type": "start"})
            for ws in clients:
                receive_until(ws, lambda m: m["type"] == "state" and m["phase"] == "playing", limit=100)

            # Skip the long walk: put the last player into the Library, far from the entrance.
            far_id = ids[3]
            far = shared_game.players[far_id]
            far.x, far.y = 2.5 * TILE, 2.5 * TILE

            near_view = receive_until(
                a,
                lambda m: m["type"] == "state" and far_id not in [p["id"] for p in m["players"]],
                limit=100,
            )
            assert far_id not in near_view["colors"]
            assert sorted(p["id"] for p in near_view["players"]) == sorted(ids[:3])

            far_view = receive_until(
                d,
                lambda m: m["type"] == "state" and [p["id"] for p in m["players"]] == [far_id],
                limit=100,
            )
            assert far_view["area"] == "Library"
            assert far_view["colors"] == {far_id: 3}


# --- The static page ----------------------------------------------------------------

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}


def test_render_js_is_served_and_loaded_between_phaser_and_main():
    with TestClient(app) as client:
        assert client.get("/render.js").status_code == 200
        page = client.get("/").text
        phaser = page.index('src="vendor/phaser.min.js"')
        render = page.index('src="render.js"')
        main = page.index('src="main.js"')
        assert phaser < render < main


def test_web_folder_contains_no_image_files():
    """Everything is drawn in code (spec 005): no downloaded or exported pictures."""
    images = [str(p.relative_to(WEB_DIR)) for p in WEB_DIR.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES]
    assert images == []
