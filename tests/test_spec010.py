"""Tests for spec 010: line-of-sight vision like Among Us. One section per part.

Part 1 (the darkness covers the whole screen) is drawing only and has no tests here.
"""

import json
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import game as game_rules
from server.game import Game, GameError, load_map
from server.main import app

TILE = 32
WEB = Path(__file__).resolve().parents[1] / "web"

# =====================================================================================
# Part 2: only walls block sight
# =====================================================================================

# The two lists of the spec. Every solid decor kind blocks walking; only these block sight:
SIGHT_BLOCKING = ["roof", "greenroof", "solar", "shelf", "shopshelf", "screen"]
# ... and these do not:
SEE_THROUGH = [
    "sea", "glasswall", "counter", "foodcounter", "desk", "studytable", "table", "cafetable",
    "woodtable", "piano", "steps", "picnic", "tree",
]

# A corridor with something in its middle. The viewer stands on (3, 2), the target behind
# the obstacle on the same row. Everyone spawns on (1, 1).
#          col 01234567890
ONE_TILE = "#....#....#"  # one wall tile on (5, 2)


def room(middle_row=ONE_TILE, decor=()):
    return {
        "tile_size": TILE,
        "grid": ["###########", "#.........#", middle_row, "#.........#", "###########"],
        "areas": [],
        "spawns": [[1, 1]],
        "decor": list(decor),
    }


def on_tile(kind, col=5, row=2, w=1, h=1):
    return {"kind": kind, "x": col, "y": row, "w": w, "h": h}


def stand_at(player, col, row):
    player.x, player.y = (col + 0.5) * TILE, (row + 0.5) * TILE


def pair_in(campus, viewer_tile=(3, 2), target_tile=(7, 2), count=4):
    """A started game on `campus` with one living student on each of the two tiles."""
    game = Game(campus, rng=random.Random(0))
    players = [game.join(f"Player {i}") for i in range(count)]
    game.start(players[0].id)
    viewer, target = [p for p in players if p.role == "student"][:2]
    stand_at(viewer, *viewer_tile)
    stand_at(target, *target_tile)
    return game, viewer, target


def seen_ids(game, viewer):
    return {p["id"] for p in game.snapshot_for(viewer.id)["players"]}


def exam_behind(kind):
    """A failed exam on (7, 2) and a living student on (3, 2), with `kind` between them."""
    game = Game(room(decor=[on_tile(kind)]), rng=random.Random(0))
    players = [game.join(f"Player {i}") for i in range(5)]
    game.start(players[0].id)
    examiner = next(p for p in players if p.role == "examiner")
    ghost, viewer = [p for p in players if p.role == "student"][:2]
    stand_at(ghost, 7, 2)
    for _ in range(max(0, examiner.next_expel_tick - game.tick)):
        game.step()
    examiner.x, examiner.y = ghost.x, ghost.y
    game.expel(examiner.id, ghost.id)  # the failed exam lies on (7, 2)
    stand_at(examiner, 1, 1)
    stand_at(viewer, 3, 2)
    return game, viewer


# --- Accepted: seen across furniture, trees and the sea -------------------------------------


def test_the_sight_blocking_kinds_are_exactly_the_ones_of_the_spec():
    assert game_rules.SIGHT_DECOR == set(SIGHT_BLOCKING)
    assert game_rules.SIGHT_DECOR <= game_rules.SOLID_DECOR
    assert game_rules.SOLID_DECOR - game_rules.SIGHT_DECOR == set(SEE_THROUGH)


@pytest.mark.parametrize("kind", SEE_THROUGH)
def test_a_player_behind_low_decor_is_sent(kind):
    game, viewer, target = pair_in(room(decor=[on_tile(kind)]))
    assert target.id in seen_ids(game, viewer)
    assert viewer.id in seen_ids(game, target)  # in both directions


def test_a_failed_exam_behind_a_table_is_sent():
    game, viewer = exam_behind("table")
    assert len(game.snapshot_for(viewer.id)["failed_exams"]) == 1


def test_three_sea_tiles_in_a_row_do_not_block_sight():
    campus = room("#...###...#", decor=[on_tile("sea", col=4, w=3)])
    game, viewer, target = pair_in(campus)
    assert target.id in seen_ids(game, viewer)


@pytest.mark.parametrize(
    "viewer_tile, target_tile, between",
    [
        ((14, 16), (14, 18), "the Student Hall's glass wall"),
        ((23, 1), (23, 3), "a tree in the Main Entrance"),
        ((32, 21), (32, 23), "a desk in the Library"),
    ],
)
def test_on_the_campus_players_see_each_other_across_low_decor(viewer_tile, target_tile, between):
    game, viewer, target = pair_in(load_map(), viewer_tile, target_tile, count=5)
    assert target.id in seen_ids(game, viewer), between
    assert viewer.id in seen_ids(game, target), between


def test_the_welcome_message_carries_the_servers_sight_grid(fresh_game):
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "name": "Ana"})
        welcome = ws.receive_json()
    campus = load_map()
    assert welcome["sight_grid"] == fresh_game.sight == game_rules.sight_grid(campus)
    assert [len(row) for row in welcome["sight_grid"]] == [len(row) for row in campus["grid"]]
    assert welcome["map"] == campus  # the map itself is sent unchanged


def test_the_browser_works_with_the_servers_sight_grid():
    assert "sight_grid" in (WEB / "main.js").read_text(encoding="utf-8")


# --- Rejected: not sent ---------------------------------------------------------------------


@pytest.mark.parametrize("kind", SIGHT_BLOCKING)
def test_a_player_behind_a_roof_a_shelf_or_a_screen_is_not_sent(kind):
    game, viewer, target = pair_in(room(decor=[on_tile(kind)]))
    snapshot = game.snapshot_for(viewer.id)
    assert target.id not in {p["id"] for p in snapshot["players"]}
    assert target.id not in snapshot["colors"]
    assert target.name not in json.dumps(snapshot)
    assert viewer.id not in seen_ids(game, target)


def test_a_player_behind_a_plain_wall_tile_is_not_sent():
    game, viewer, target = pair_in(room())
    assert target.id not in seen_ids(game, viewer)
    assert viewer.id not in seen_ids(game, target)


def test_a_failed_exam_behind_a_roof_is_not_sent():
    game, viewer = exam_behind("roof")
    assert game.snapshot_for(viewer.id)["failed_exams"] == []
    assert len(game.failed_exams) == 1  # still there, just out of sight


@pytest.mark.parametrize(
    "viewer_tile, target_tile, between",
    [
        ((30, 36), (30, 38), "the Auditorium screen in its front wall"),
        ((27, 3), (29, 3), "the standing screen in the Main Entrance"),
        ((32, 18), (32, 20), "a bookshelf in the Library"),
    ],
)
def test_on_the_campus_screens_and_shelves_hide_players(viewer_tile, target_tile, between):
    game, viewer, target = pair_in(load_map(), viewer_tile, target_tile, count=5)
    assert target.id not in seen_ids(game, viewer), between
    assert viewer.id not in seen_ids(game, target), between


@pytest.mark.parametrize("kind", SEE_THROUGH + SIGHT_BLOCKING)
def test_every_solid_decor_kind_still_blocks_walking(kind):
    game, viewer, _ = pair_in(room(decor=[on_tile(kind)]), viewer_tile=(4, 2))
    assert game.blocked((5 + 0.5) * TILE, (2 + 0.5) * TILE)
    game.set_input(viewer.id, {"type": "input", "dx": 1, "dy": 0})
    for _ in range(10):
        game.step()
    assert viewer.x == 5 * TILE - game_rules.PLAYER_HALF  # flush against the tile, not in it


def test_extra_fields_in_a_message_do_not_let_a_browser_see_through_a_roof():
    game, viewer, target = pair_in(room(decor=[on_tile("roof")]))
    message = {"type": "input", "dx": 0, "dy": 0, "sight_grid": [], "sight": False}
    try:
        game.set_input(viewer.id, message)
    except GameError:
        pass  # rejecting the whole message is fine too
    assert target.id not in seen_ids(game, viewer)


def test_a_sight_grid_in_the_join_message_is_ignored(fresh_game):
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "name": "Ana", "sight_grid": ["."]})
        welcome = ws.receive_json()
    assert welcome["sight_grid"] == fresh_game.sight == game_rules.sight_grid(load_map())


# --- Edge cases -----------------------------------------------------------------------------


def test_on_a_map_without_decor_every_wall_blocks_sight():
    campus = room()
    del campus["decor"]
    assert game_rules.sight_grid(campus) == campus["grid"]


def test_a_tile_with_low_and_tall_decor_blocks_sight():
    for kinds in (("table", "roof"), ("roof", "table")):
        game, viewer, target = pair_in(room(decor=[on_tile(kind) for kind in kinds]))
        assert target.id not in seen_ids(game, viewer), kinds


def test_floor_decor_painted_around_a_wall_tile_does_not_open_it():
    game, viewer, target = pair_in(room(decor=[on_tile("grass", col=4, w=3)]))
    assert target.id not in seen_ids(game, viewer)


def test_a_wall_behind_a_table_still_blocks_sight():
    campus = room("#....##...#", decor=[on_tile("table")])  # table on (5, 2), wall on (6, 2)
    game, viewer, target = pair_in(campus, target_tile=(8, 2))
    assert target.id not in seen_ids(game, viewer)


def test_the_campus_sight_grid_marks_walls_roofs_shelves_and_screens_only():
    campus = load_map()
    grid, sight = campus["grid"], game_rules.sight_grid(campus)
    assert [len(row) for row in sight] == [len(row) for row in grid]
    for row, line in enumerate(sight):
        for col, tile in enumerate(line):
            assert tile in "#."
            assert tile == "." or grid[row][col] == "#", (col, row)  # only walls block sight
    blocks = {(2, 0): "plain wall", (31, 28): "Gym roof", (30, 19): "bookshelf", (27, 37): "screen"}
    opens = {(0, 0): "sea", (23, 2): "tree", (10, 23): "table", (13, 17): "glass wall", (24, 4): "floor"}
    for (col, row), what in blocks.items():
        assert sight[row][col] == "#", what
    for (col, row), what in opens.items():
        assert sight[row][col] == ".", what
