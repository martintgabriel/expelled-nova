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


# =====================================================================================
# Part 3: smooth line of sight
# =====================================================================================
# A target is visible if its centre is within the radius and a straight line from the
# viewer's centre reaches its centre or one of the four corners of its square without
# crossing a sight-blocking tile. Only touching a tile is not crossing it.

HALF = game_rules.PLAYER_HALF
RADIUS = game_rules.VISION_TILES * TILE  # 192 px
DARK_RADIUS = game_rules.LIGHTS_OUT_TILES * TILE  # 48 px

# A room with a short wall in the middle: column 5 (x 160..192), rows 3-5 (y 96..192).
# Everyone spawns on (1, 1).
WALL_ROOM = {
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

# Two wall tiles that only touch at one corner: (3, 2) and (4, 3) meet at (128, 96).
DIAGONAL_ROOM = {
    "tile_size": TILE,
    "grid": ["#######", "#.....#", "#..#..#", "#...#.#", "#.....#", "#######"],
    "areas": [],
    "spawns": [[1, 1]],
}

# One big open hall, 30 x 12 tiles of floor, with a light switch in a far corner.
OPEN_HALL = {
    "tile_size": TILE,
    "grid": ["#" * 32] + ["#" + "." * 30 + "#"] * 12 + ["#" * 32],
    "areas": [],
    "spawns": [[1, 1]],
    "light_switch": [29, 11],
}


def centre(col, row):
    return (col + 0.5) * TILE, (row + 0.5) * TILE


def clear_both_ways(game, x0, y0, x1, y1):
    """sight_clear() for a line, after checking that the direction does not matter."""
    result = game.sight_clear(x0, y0, x1, y1)
    assert game.sight_clear(x1, y1, x0, y0) == result
    return result


def round_with_ghost(campus=WALL_ROOM):
    """A started game with an examiner, a ghost and two living students. The failed exam
    lies on the spawn tile (1, 1)."""
    game = Game(campus, rng=random.Random(0))
    players = [game.join(f"Player {i}") for i in range(5)]
    game.start(players[0].id)
    examiner = next(p for p in players if p.role == "examiner")
    ghost, viewer, target = [p for p in players if p.role == "student"][:3]
    for _ in range(max(0, examiner.next_expel_tick - game.tick)):
        game.step()
    game.expel(examiner.id, ghost.id)
    return game, examiner, ghost, viewer, target


def lights_out_round():
    """A started game on OPEN_HALL in which the examiner has just turned off the lights."""
    game = Game(OPEN_HALL, rng=random.Random(0))
    players = [game.join(f"Player {i}") for i in range(5)]
    game.start(players[0].id)
    examiner = next(p for p in players if p.role == "examiner")
    students = [p for p in players if p.role == "student"]
    for _ in range(game_rules.SABOTAGE_COOLDOWN_TICKS):
        game.step()
    game.sabotage(examiner.id)
    return game, examiner, students


# --- Accepted: the line is clear, the target is sent ----------------------------------------


def test_a_line_over_open_floor_is_clear():
    game = Game(WALL_ROOM)
    assert clear_both_ways(game, *centre(1, 1), *centre(10, 1))
    assert clear_both_ways(game, *centre(2, 6), *centre(9, 7))
    assert game.sight_clear(100, 100, 100, 100)  # a line of no length


@pytest.mark.parametrize(
    "line",
    [
        (144, 112, 176, 80),  # through (160, 96), the wall's upper left corner
        (208, 112, 176, 80),  # through (192, 96), upper right
        (144, 176, 176, 208),  # through (160, 192), lower left
        (208, 176, 176, 208),  # through (192, 192), lower right
    ],
)
def test_a_line_that_only_touches_a_wall_corner_is_not_blocked(line):
    assert clear_both_ways(Game(WALL_ROOM), *line)


def test_a_line_through_the_point_where_two_walls_touch_diagonally_is_not_blocked():
    game = Game(DIAGONAL_ROOM)
    assert clear_both_ways(game, 112, 112, 144, 80)  # through (128, 96) only
    assert not clear_both_ways(game, 112, 113, 144, 81)  # one pixel lower: cuts tile (4, 3)
    assert not clear_both_ways(game, 112, 111, 144, 79)  # one pixel higher: cuts tile (3, 2)


def test_a_line_along_a_wall_face_is_clear():
    game = Game(WALL_ROOM)
    assert clear_both_ways(game, 160, 70, 160, 220)  # down the wall's left face
    assert clear_both_ways(game, 40, 32, 300, 32)  # along the border wall's inner face


def test_a_line_that_ends_on_a_wall_face_is_clear():
    assert clear_both_ways(Game(WALL_ROOM), 100, 144, 160, 144)


def test_a_player_whose_centre_is_hidden_but_one_corner_is_visible_is_sent():
    game, viewer, target = pair_in(WALL_ROOM, (3, 5), (7, 6))
    assert not game.sight_clear(viewer.x, viewer.y, target.x, target.y)  # the centre: hidden
    assert game.sight_clear(viewer.x, viewer.y, target.x - HALF, target.y + HALF)  # a corner
    snapshot = game.snapshot_for(viewer.id)
    seen = next(p for p in snapshot["players"] if p["id"] == target.id)
    assert seen == {"id": target.id, "name": target.name, "x": target.x, "y": target.y}
    assert snapshot["colors"][target.id] == target.color


def test_a_failed_exam_with_only_a_corner_in_sight_is_sent():
    game, examiner, ghost, viewer, target = round_with_ghost()
    exam = game.failed_exams[0]
    exam.x, exam.y = centre(7, 6)
    stand_at(viewer, 3, 5)
    assert not game.sight_clear(viewer.x, viewer.y, exam.x, exam.y)
    assert len(game.snapshot_for(viewer.id)["failed_exams"]) == 1


def test_a_hidden_player_appears_before_the_viewer_has_passed_the_end_of_the_wall():
    game, viewer, target = pair_in(WALL_ROOM, (3, 4), (7, 6))
    assert target.id not in seen_ids(game, viewer)
    game.set_input(viewer.id, {"type": "input", "dx": 0, "dy": 1})
    for _ in range(4):  # 32 px down, to the centre of (3, 5)
        game.step()
    assert viewer.y < 6 * TILE  # still beside the wall, which ends at y = 192
    assert target.id in seen_ids(game, viewer)


def test_exactly_at_the_radius_between_centres_is_visible():
    game, viewer, target = pair_in(OPEN_HALL, (2, 2), (8, 2))  # six tiles
    assert target.id in seen_ids(game, viewer)
    target.x, target.y = viewer.x, viewer.y + RADIUS
    assert target.id in seen_ids(game, viewer)


def test_a_ghost_sees_everyone_and_every_failed_exam_through_walls_and_at_any_distance():
    game, examiner, ghost, viewer, target = round_with_ghost()
    stand_at(ghost, 3, 4)
    stand_at(viewer, 7, 4)  # behind the wall
    stand_at(target, 10, 7)
    stand_at(examiner, 1, 7)
    snapshot = game.snapshot_for(ghost.id)
    assert {p["id"] for p in snapshot["players"]} == set(game.players)
    assert len(snapshot["failed_exams"]) == 1


def test_during_a_meeting_everyone_sees_everyone_through_walls():
    game, viewer, target = pair_in(WALL_ROOM, (3, 4), (7, 4))
    assert target.id not in seen_ids(game, viewer)
    game.bell(viewer.id)  # WALL_ROOM has no Auditorium and no bell place: nobody is moved
    assert game.phase == "meeting"
    for player in game.players.values():
        assert seen_ids(game, player) == set(game.players)


def test_in_the_lobby_and_after_the_end_walls_hide_nobody():
    game = Game(WALL_ROOM, rng=random.Random(0))
    players = [game.join(f"Player {i}") for i in range(4)]
    stand_at(players[0], 3, 4)
    stand_at(players[1], 7, 4)
    assert seen_ids(game, players[0]) == set(game.players)  # lobby
    game.start(players[0].id)
    game.leave(next(p for p in players if p.role == "examiner").id)  # the students win
    assert game.phase == "ended"
    for player in game.players.values():
        assert seen_ids(game, player) == set(game.players)


def test_with_the_lights_off_an_examiner_sees_as_far_as_before():
    game, examiner, students = lights_out_round()
    target = students[0]
    stand_at(examiner, 10, 5)
    target.x, target.y = examiner.x + RADIUS, examiner.y
    assert target.id in seen_ids(game, examiner)
    assert examiner.id not in seen_ids(game, target)  # the student does not see back
    assert game.snapshot_for(examiner.id)["vision_radius"] == RADIUS


# --- Rejected: the line is blocked, the target is not sent ----------------------------------


@pytest.mark.parametrize(
    "line",
    [
        (112, 144, 240, 144),  # straight through the wall
        (144, 80, 176, 112),  # through the corner (160, 96) and on into the wall
        (144, 112.01, 176, 80.01),  # a hundredth of a pixel inside the corner
        (150, 128, 200, 128),  # along the joint between two wall tiles, inside the wall
        (48, 48, -50, 48),  # out of the map: the border wall is in the way
    ],
)
def test_a_line_that_crosses_a_wall_tile_is_blocked(line):
    assert not clear_both_ways(Game(WALL_ROOM), *line)


def test_a_player_with_centre_and_all_corners_hidden_is_not_sent():
    game, viewer, target = pair_in(WALL_ROOM, (3, 4), (7, 4))
    for dx, dy in [(0, 0), (-HALF, -HALF), (HALF, -HALF), (-HALF, HALF), (HALF, HALF)]:
        assert not game.sight_clear(viewer.x, viewer.y, target.x + dx, target.y + dy)
    snapshot = game.snapshot_for(viewer.id)
    assert target.id not in {p["id"] for p in snapshot["players"]}
    assert target.id not in snapshot["colors"]
    assert target.name not in json.dumps(snapshot)
    assert viewer.id in seen_ids(game, viewer)  # a player always sees themself


def test_one_pixel_beyond_the_radius_is_not_sent_even_with_a_corner_inside_it():
    game, viewer, target = pair_in(OPEN_HALL, (2, 2), (8, 2))
    target.x += 1  # the centre is outside the radius, the two near corners are inside
    assert target.x - HALF - viewer.x < RADIUS
    assert target.id not in seen_ids(game, viewer)
    assert viewer.id not in seen_ids(game, target)


def test_with_the_lights_off_a_students_radius_shrinks():
    game, examiner, students = lights_out_round()
    viewer, target = students[0], students[1]
    stand_at(viewer, 10, 5)
    stand_at(target, 13, 5)  # three tiles away, nothing in between
    assert target.id not in seen_ids(game, viewer)
    target.x = viewer.x + DARK_RADIUS  # exactly at the reduced radius
    assert target.id in seen_ids(game, viewer)
    target.x += 1
    assert target.id not in seen_ids(game, viewer)
    assert game.snapshot_for(viewer.id)["vision_radius"] == DARK_RADIUS


def test_the_browser_no_longer_draws_tile_shadows_or_a_fixed_size_fog():
    code = (WEB / "main.js").read_text(encoding="utf-8") + (WEB / "render.js").read_text(encoding="utf-8")
    # "function lineBetween": our own tile line. Phaser's drawing call g.lineBetween() stays.
    gone = ("drawShadows", "makeFog", "FOG_TEXTURE_SIZE", "visibleTiles", "function lineBetween", "drawLitTiles")
    for name in gone:
        assert name not in code, name


# --- Edge cases -----------------------------------------------------------------------------


def test_where_the_viewer_stands_on_their_tile_now_matters():
    game, viewer, target = pair_in(WALL_ROOM, (3, 5), (7, 6))
    viewer.y = 5 * TILE + 1  # the top of tile (3, 5): the wall still covers the target
    assert target.id not in seen_ids(game, viewer)
    viewer.y = 5.5 * TILE  # the middle of the same tile: a corner of the target shows
    assert target.id in seen_ids(game, viewer)


def test_centre_lines_between_floor_tiles_are_the_same_in_both_directions_on_the_campus():
    campus = load_map()
    game = Game(campus)
    floor = [
        (col, row)
        for row, line in enumerate(campus["grid"])
        for col, tile in enumerate(line)
        if tile == "."
    ]
    reach = game_rules.VISION_TILES
    for a in floor:
        for b in floor:
            if a < b and abs(a[0] - b[0]) <= reach and abs(a[1] - b[1]) <= reach:
                there = game.sight_clear(*centre(*a), *centre(*b))
                assert game.sight_clear(*centre(*b), *centre(*a)) == there, (a, b)


def test_on_the_campus_the_next_room_is_hidden_and_the_doorway_is_not():
    game, viewer, target = pair_in(load_map(), (29, 21), (29, 15), count=5)  # Library, Food Court
    assert target.id not in seen_ids(game, viewer)
    stand_at(target, 27, 21)  # in the Library's doorway to the spine, same row
    assert target.id in seen_ids(game, viewer)
