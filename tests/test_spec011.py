"""Tests for spec 011: free movement, the meeting point, clear walls and clear glass.

One section per part of the spec. Drawing (web/render.js) is checked in a running game;
here only two small tests read the browser files.
"""

import math
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import game as game_rules
from server.game import STEP, Game, load_map
from server.main import app

TILE = 32
HALF = game_rules.PLAYER_HALF
WEB = Path(__file__).resolve().parents[1] / "web"


def centre(col, row):
    return (col + 0.5) * TILE, (row + 0.5) * TILE


def put(player, col, row, ox=0, oy=0):
    """Put a player on the centre of a tile, `ox`, `oy` pixels off it."""
    x, y = centre(col, row)
    player.x, player.y = x + ox, y + oy


def walker(campus, col, row, ox=0, oy=0):
    """A game in the lobby (walking works there) with one player on the given tile."""
    game = Game(campus)
    player = game.join("Ana")
    put(player, col, row, ox, oy)
    return game, player


def walk(game, player, dx, dy, ticks):
    """Hold a direction for some ticks. Returns the position after every tick."""
    game.set_input(player.id, {"type": "input", "dx": dx, "dy": dy})
    trail = []
    for _ in range(ticks):
        game.step()
        trail.append((player.x, player.y))
    return trail


def decor_tiles(campus, kinds):
    """Every (kind, col, row) of the map's decor entries of the given kinds."""
    return [
        (entry["kind"], col, row)
        for entry in campus["decor"]
        if entry["kind"] in kinds
        for row in range(entry["y"], entry["y"] + entry["h"])
        for col in range(entry["x"], entry["x"] + entry["w"])
    ]


# =====================================================================================
# Section 1: free movement
# =====================================================================================

# Furniture and small objects: drawn on the floor, walked over.
FURNITURE = [
    "counter", "shelf", "desk", "studytable", "table", "cafetable", "woodtable", "shopshelf",
    "foodcounter", "piano", "steps", "picnic", "tree",
]
# What still blocks walking, next to plain wall tiles.
STILL_SOLID = ["sea", "solar", "greenroof", "roof", "glasswall", "screen"]

# A wall across the room with a doorway of one tile on (3, 3).
#        col 0123456
DOOR_ROOM = {
    "tile_size": TILE,
    "grid": [
        "#######",
        "#.....#",
        "#.....#",
        "###.###",
        "#.....#",
        "#.....#",
        "#######",
    ],
    "areas": [],
    "spawns": [[1, 1]],
}
# The same room turned by a quarter: the doorway on (3, 3) is walked through sideways.
SIDE_DOOR_ROOM = dict(DOOR_ROOM, grid=["".join(column) for column in zip(*DOOR_ROOM["grid"])])


# --- Accepted: walking over furniture ---------------------------------------------------


def test_furniture_is_floor_decor_and_only_walls_glass_sea_roofs_and_screens_are_solid():
    assert game_rules.SOLID_DECOR == set(STILL_SOLID)
    assert set(FURNITURE) <= game_rules.FLOOR_DECOR
    assert not game_rules.SOLID_DECOR & game_rules.FLOOR_DECOR


def test_on_the_campus_every_piece_of_furniture_stands_on_a_floor_tile():
    campus = load_map()
    game = Game(campus)
    tiles = decor_tiles(campus, FURNITURE)
    assert {kind for kind, _, _ in tiles} >= {"table", "tree", "desk", "counter", "shelf", "piano"}
    for kind, col, row in tiles:
        assert campus["grid"][row][col] == ".", (kind, col, row)
        assert not game.blocked(*centre(col, row)), (kind, col, row)


@pytest.mark.parametrize(
    "what, start, furniture",
    [
        # Spec 015: the beach grew by 4 columns in the west, so every column here moved by 4.
        ("a table in the south Courtyard", (12, 23), (14, 23)),
        ("a tree in the north Courtyard", (10, 15), (12, 15)),
        ("a café table in the Food Court", (34, 14), (35, 14)),
        ("a desk in the Library", (33, 22), (36, 22)),
    ],
)
def test_a_player_walks_across_a_furniture_tile(what, start, furniture):
    campus = load_map()
    assert (furniture[0], furniture[1]) in {(c, r) for _, c, r in decor_tiles(campus, FURNITURE)}, what
    game, player = walker(campus, *start)
    walk(game, player, 1, 0, 30)
    assert player.x > (furniture[0] + 1) * TILE + HALF, what  # completely past the tile
    assert player.y == centre(*start)[1]  # in a straight line


@pytest.mark.parametrize("kind", FURNITURE)
def test_a_furniture_kind_on_a_floor_tile_is_valid_and_walkable(kind):
    campus = dict(DOOR_ROOM, decor=[{"kind": kind, "x": 3, "y": 1, "w": 1, "h": 1}])
    game_rules.validate_campus(campus)
    game, player = walker(campus, 1, 1)
    walk(game, player, 1, 0, 20)
    assert player.x == 6 * TILE - HALF  # walked over it, up to the far wall


# --- Rejected: what still blocks --------------------------------------------------------


@pytest.mark.parametrize(
    "what, start, direction, stopped_at",
    [
        # Spec 015: the beach grew by 4 columns in the west, so every column here moved by 4. The sea is still column 0.
        ("a wall of the Main Entrance", (20, 4), (-1, 0), (20 * TILE + HALF, None)),
        ("a glass pane of the Student Hall", (18, 16), (0, 1), (None, 17 * TILE - HALF)),
        ("the sea", (1, 20), (-1, 0), (1 * TILE + HALF, None)),
        ("the roof of the Gym", (34, 28), (1, 0), (35 * TILE - HALF, None)),
        ("the Auditorium screen", (34, 36), (0, 1), (None, 37 * TILE - HALF)),
    ],
)
def test_walls_glass_the_sea_roofs_and_screens_still_block(what, start, direction, stopped_at):
    game, player = walker(load_map(), *start)
    walk(game, player, *direction, 12)
    x, y = centre(*start)
    assert (player.x, player.y) == (stopped_at[0] or x, stopped_at[1] or y), what


@pytest.mark.parametrize("kind", STILL_SOLID)
def test_a_solid_kind_on_a_floor_tile_is_rejected(kind):
    campus = dict(DOOR_ROOM, decor=[{"kind": kind, "x": 3, "y": 1, "w": 1, "h": 1}])
    with pytest.raises(ValueError, match="floor"):
        game_rules.validate_campus(campus)


# --- Sliding: diagonal moves ------------------------------------------------------------


def at_wall(value, wall):
    """A diagonal step has no whole number of pixels: it stops less than 1 px before a wall."""
    return wall - 1 < value <= wall


def test_moving_diagonally_into_a_wall_slides_along_it():
    game, player = walker(DOOR_ROOM, 1, 2)
    trail = walk(game, player, 1, 1, 4)
    assert at_wall(player.y, 3 * TILE - HALF)  # against the wall below
    xs = [x for x, _ in trail]
    assert xs == sorted(xs) and xs[-1] > xs[0]  # and still moving along it


def test_moving_diagonally_past_a_corner_slides_along_the_wall_and_through_the_doorway():
    game, player = walker(DOOR_ROOM, 1, 2)
    walk(game, player, 1, 1, 45)
    # Along the wall, round the corner of the doorway, through it, into the far corner.
    assert at_wall(player.x, 6 * TILE - HALF) and at_wall(player.y, 6 * TILE - HALF)


def test_moving_diagonally_into_an_inside_corner_stops_flush_in_it():
    game, player = walker(DOOR_ROOM, 4, 2)
    walk(game, player, 1, 1, 20)
    assert at_wall(player.x, 6 * TILE - HALF) and at_wall(player.y, 3 * TILE - HALF)


# --- Sliding: a straight walk into the corner of a doorway ---------------------------------


@pytest.mark.parametrize("off", [-16, -11, -7, 7, 11, 16])
def test_a_straight_walk_slips_through_a_doorway_without_precise_aiming(off):
    # More than 6 px off the middle, the player's square does not fit the doorway any more.
    game, player = walker(DOOR_ROOM, 3, 2, ox=off)
    walk(game, player, 0, 1, 20)
    assert player.y == 6 * TILE - HALF  # through the doorway, at the far wall
    assert 3 * TILE + HALF <= player.x <= 4 * TILE - HALF  # moved just into line with it


@pytest.mark.parametrize("off", [-16, -9, 9, 16])
@pytest.mark.parametrize("direction", [1, -1])
def test_a_sideways_doorway_works_the_same_in_both_directions(off, direction):
    start_col = 2 if direction == 1 else 4
    game, player = walker(SIDE_DOOR_ROOM, start_col, 3, oy=off)
    walk(game, player, direction, 0, 20)
    assert player.x == (6 * TILE - HALF if direction == 1 else TILE + HALF)
    assert 3 * TILE + HALF <= player.y <= 4 * TILE - HALF


def test_sliding_round_a_corner_is_never_faster_than_walking_and_never_enters_a_wall():
    game, player = walker(DOOR_ROOM, 3, 2, ox=16)
    before = (player.x, player.y)
    for after in walk(game, player, 0, 1, 20):
        assert abs(after[0] - before[0]) + abs(after[1] - before[1]) <= STEP + 1e-9
        assert not game.blocked(*after)
        before = after


def test_the_slide_reaches_exactly_as_far_as_the_corner_slide():
    reach = game_rules.CORNER_SLIDE
    assert reach == HALF  # half a player: whoever is at least half in front of a gap slips in
    # The square sticks out `reach` px over the wall next to the doorway: it slides ...
    game, player = walker(DOOR_ROOM, 3, 2, ox=6 + reach)
    walk(game, player, 0, 1, 20)
    assert player.y == 6 * TILE - HALF
    # ... one pixel more and the wall stops the player like any wall.
    game, player = walker(DOOR_ROOM, 3, 2, ox=6 + reach + 1)
    start_x = player.x
    walk(game, player, 0, 1, 20)
    assert (player.x, player.y) == (start_x, 3 * TILE - HALF)


def test_walking_straight_into_the_face_of_a_wall_does_not_move_the_player():
    game, player = walker(DOOR_ROOM, 1, 2)
    walk(game, player, 0, 1, 5)
    at_the_wall = (player.x, player.y)
    assert at_the_wall == (centre(1, 2)[0], 3 * TILE - HALF)
    walk(game, player, 0, 1, 20)
    assert (player.x, player.y) == at_the_wall  # no sideways drift along a plain wall


def test_a_player_who_does_not_walk_is_never_moved_by_the_slide():
    game, player = walker(DOOR_ROOM, 3, 2, ox=16, oy=6)  # touching the wall next to the doorway
    start = (player.x, player.y)
    walk(game, player, 0, 0, 10)
    assert (player.x, player.y) == start


def test_a_ghost_still_walks_straight_through_the_wall_next_to_a_doorway():
    game, player = walker(DOOR_ROOM, 3, 2, ox=16)
    player.alive = False
    start_x = player.x
    walk(game, player, 0, 1, 12)
    assert player.x == start_x and player.y > 4 * TILE


# --- Sliding: every doorway of the campus ---------------------------------------------------


def campus_doorways(campus):
    """Every gap of one tile: (tile, (dx, dy)) for both directions through it.

    A floor tile with a wall on both sides and floor before and behind it.
    """
    grid = campus["grid"]

    def floor(col, row):
        return 0 <= row < len(grid) and 0 <= col < len(grid[0]) and grid[row][col] == "."

    found = []
    for row in range(len(grid)):
        for col in range(len(grid[0])):
            if not floor(col, row):
                continue
            if not floor(col - 1, row) and not floor(col + 1, row) and floor(col, row - 1) and floor(col, row + 1):
                found += [((col, row), (0, 1)), ((col, row), (0, -1))]
            if not floor(col, row - 1) and not floor(col, row + 1) and floor(col - 1, row) and floor(col + 1, row):
                found += [((col, row), (1, 0)), ((col, row), (-1, 0))]
    return found


def test_walking_through_every_doorway_of_the_campus_works_without_precise_aiming():
    campus = load_map()
    doorways = campus_doorways(campus)
    # Spec 015: the beach is five tiles wide now and no path of one-tile gaps any more
    # (it alone had 34 of the 38). What is left are its two openings to the Courtyards.
    assert len(doorways) >= 4
    tried = 0
    for (col, row), (dx, dy) in doorways:
        for off in (-16, -11, -8, 0, 8, 11, 16):
            # Start on the tile in front of the doorway, `off` px to the side of its middle.
            game, player = walker(campus, col - dx, row - dy, ox=off * abs(dy), oy=off * abs(dx))
            if game.blocked(player.x, player.y):
                continue  # a wall next to the start tile: nobody can stand that far off
            tried += 1
            walk(game, player, dx, dy, 16)
            behind = centre(col + dx, row + dy)
            progress = (player.x - behind[0]) * dx + (player.y - behind[1]) * dy
            assert progress >= 0, f"stuck at doorway {(col, row)} going {(dx, dy)}, {off} px off"
    assert tried > len(doorways)  # not only the straight walks


# --- The browser predicts with the same rule ------------------------------------------------


def test_welcome_carries_the_corner_slide_for_the_browsers_prediction(fresh_game):
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "name": "Ana"})
        welcome = ws.receive_json()
    assert welcome["corner_slide"] == game_rules.CORNER_SLIDE
    assert welcome["player_half"] == HALF and welcome["step"] == STEP


def test_the_browser_slides_with_the_servers_corner_slide():
    script = (WEB / "main.js").read_text(encoding="utf-8")
    assert "welcome.corner_slide" in script
    assert "Game._slide()" in script  # the "REPEATS SERVER RULE" note names the server's rule


# =====================================================================================
# Section 2: a meeting point instead of a bell
# =====================================================================================

TOO_FAR = "Too far from the meeting table"

# A corridor three tiles high with a meeting point on (5, 2): too tight for the whole circle.
TIGHT_MAP = {
    "tile_size": TILE,
    "grid": ["###########", "#.........#", "#.........#", "#.........#", "###########"],
    "areas": [],
    "spawns": [[1, 1], [2, 1], [3, 1], [7, 1], [8, 1], [9, 1], [1, 3], [2, 3], [8, 3], [9, 3]],
    "meeting_point": [5, 2],
}
# The same corridor without a meeting point, like the small maps of earlier specs.
NO_TABLE_MAP = {key: value for key, value in TIGHT_MAP.items() if key != "meeting_point"}


def round_on(campus=None, count=4, seed=0):
    """A started game. Returns the game, its examiners and its students."""
    game = Game(campus or load_map(), rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


def table_centre(campus=None):
    return centre(*(campus or load_map())["meeting_point"])


def at_table(player, dx=0, dy=0):
    """Put a player on the middle of the campus meeting table, or `dx`, `dy` px next to it."""
    x, y = table_centre()
    player.x, player.y = x + dx, y + dy


def reach():
    """How far from the table's middle a meeting can be called: its radius plus the range."""
    return game_rules.MEETING_TABLE_RADIUS + game_rules.MEETING_RANGE


def end_meeting(game):
    """Everyone skips; the meeting runs to its end."""
    for player in [p for p in game.players.values() if p.alive]:
        game.vote(player.id, "skip")
    for _ in range(game_rules.RESULT_TICKS + 1):
        game.step()
    assert game.phase == "playing"


def everything(game):
    """What a rejected call must leave unchanged, including what every player receives."""
    return (
        game.phase,
        [vars(p).copy() for p in game.players.values()],
        game.meeting,
        {player_id: game.snapshot_for(player_id) for player_id in game.players},
    )


# --- Accepted: the meeting point and calling a meeting -------------------------------------


def test_the_campus_has_a_meeting_point_in_the_middle_of_the_map_and_no_bell():
    campus = load_map()
    assert "bell" not in campus
    col, row = campus["meeting_point"]
    assert type(col) is int and type(row) is int
    assert campus["grid"][row][col] == "."
    # Spec 015: 4 columns of beach were added in the west only, so the middle of the
    # buildings lies 2 columns east of the middle of the grid.
    assert abs(col + 0.5 - (len(campus["grid"][0]) + 4) / 2) <= 4
    assert abs(row + 0.5 - len(campus["grid"]) / 2) <= 4


def test_the_meeting_range_is_about_one_and_a_half_tiles_from_the_table_edge():
    assert game_rules.MEETING_RANGE == 1.5 * TILE
    assert TILE <= game_rules.MEETING_TABLE_RADIUS <= 1.5 * TILE  # a table of 2 to 3 tiles


def test_calling_a_meeting_at_the_table_starts_a_meeting():
    game, _, students = round_on()
    caller = students[0]
    at_table(caller, dx=50)  # standing next to the table
    game.call_meeting(caller.id)
    assert game.phase == "meeting"
    meeting = game.snapshot_for(students[1].id)["meeting"]
    assert (meeting["reason"], meeting["called_by"]) == ("button", caller.id)
    for player in game.players.values():
        assert game.snapshot_for(player.id)["meeting_used"] is (player is caller)


@pytest.mark.parametrize("direction", [(1, 0), (-1, 0), (0, 1), (0, -1)])
def test_calling_from_exactly_the_range_from_the_table_edge_is_accepted(direction):
    game, _, students = round_on()
    at_table(students[0], dx=direction[0] * reach(), dy=direction[1] * reach())
    game.call_meeting(students[0].id)
    assert game.phase == "meeting"


def test_an_examiner_can_call_a_meeting_too():
    game, (examiner,), _ = round_on()
    at_table(examiner)
    game.call_meeting(examiner.id)
    assert game.snapshot_for(examiner.id)["meeting"]["called_by"] == examiner.id


def test_a_report_still_works_anywhere_and_does_not_use_up_the_meeting_call():
    game, (examiner,), students = round_on(count=5)
    victim, reporter = students[0], students[1]
    # Spec 015: the beach grew by 4 columns in the west, so every column here moved by 4.
    put(victim, 41, 23)  # in the Library, far from the meeting table
    for _ in range(examiner.next_expel_tick - game.tick):
        game.step()
    put(examiner, 41, 23)
    game.expel(examiner.id, victim.id)
    put(reporter, 41, 24)
    game.report(reporter.id, game.failed_exams[0].id)
    assert game.snapshot_for(reporter.id)["meeting"]["reason"] == "report"
    assert game.snapshot_for(reporter.id)["meeting_used"] is False


def test_a_new_round_gives_everyone_their_meeting_call_back():
    game, (examiner,), students = round_on()
    at_table(students[0])
    game.call_meeting(students[0].id)
    game.leave(examiner.id)  # the students win
    assert game.phase == "ended"
    game.restart(game.host_id)
    assert all(game.snapshot_for(p)["meeting_used"] is False for p in game.players)


def test_a_map_without_a_meeting_point_calls_anywhere_and_moves_nobody():
    game, _, students = round_on(NO_TABLE_MAP)
    before = [(p.x, p.y) for p in game.players.values()]
    game.call_meeting(students[0].id)
    assert game.phase == "meeting"
    assert [(p.x, p.y) for p in game.players.values()] == before


# --- Rejected: far away, and the limits of specs 006 and 008 --------------------------------


def call_from_the_spawn():
    game, _, students = round_on()
    return game, students[0]


def call_one_pixel_beyond_the_range():
    game, _, students = round_on()
    at_table(students[0], dx=reach() + 1)
    return game, students[0]


def call_by_a_ghost_at_the_table():
    game, _, students = round_on(count=5)
    students[0].alive = False
    at_table(students[0])
    return game, students[0]


def second_call_at_the_table():
    game, _, students = round_on()
    at_table(students[0])
    game.call_meeting(students[0].id)
    end_meeting(game)  # everyone stands around the table now
    return game, students[0]


def call_in_the_lobby():
    game = Game(load_map())
    players = [game.join(f"Player {i}") for i in range(4)]
    at_table(players[0])
    return game, players[0]


def call_during_a_meeting():
    game, _, students = round_on()
    at_table(students[0])
    game.call_meeting(students[0].id)
    return game, students[1]  # stands at the table too


def call_after_the_end():
    game, (examiner,), students = round_on()
    game.leave(examiner.id)
    at_table(students[0])
    return game, students[0]


@pytest.mark.parametrize(
    "case, reason",
    [
        (call_from_the_spawn, TOO_FAR),
        (call_one_pixel_beyond_the_range, TOO_FAR),
        (call_by_a_ghost_at_the_table, "Ghosts cannot call a meeting"),
        (second_call_at_the_table, "You have already called a meeting"),
        (call_in_the_lobby, "The game has not started yet"),
        (call_during_a_meeting, "A meeting is already running"),
        (call_after_the_end, "Game is over"),
    ],
)
def test_a_rejected_meeting_call_changes_nothing(case, reason):
    game, caller = case()
    before = everything(game)
    with pytest.raises(game_rules.GameError, match=reason):
        game.call_meeting(caller.id)
    assert everything(game) == before


def test_an_unknown_player_cannot_call_a_meeting():
    game, _, _ = round_on()
    with pytest.raises(game_rules.GameError, match="Unknown player"):
        game.call_meeting("p99")
    assert game.phase == "playing"


def test_a_call_rejected_for_distance_is_not_used_up():
    game, _, students = round_on()
    with pytest.raises(game_rules.GameError, match=TOO_FAR):
        game.call_meeting(students[0].id)
    at_table(students[0])
    game.call_meeting(students[0].id)
    assert game.phase == "meeting"


def test_the_bell_is_gone_from_the_messages():
    assert "bell" not in game_rules.MESSAGE_TYPES and "meeting" in game_rules.MESSAGE_TYPES
    assert game_rules.parse_message('{"type": "meeting"}', joined=True) == {"type": "meeting"}
    with pytest.raises(game_rules.GameError, match="Unknown message type"):
        game_rules.parse_message('{"type": "bell"}', joined=True)
    with pytest.raises(game_rules.GameError, match="Join the game first"):
        game_rules.parse_message('{"type": "meeting"}', joined=False)


# --- Meeting positions: a circle around the table ---------------------------------------------


def around_the_table(game, campus=None):
    """Every player's place seen from the table's middle: (distance, angle in degrees)."""
    cx, cy = table_centre(campus)
    return [
        (math.hypot(p.x - cx, p.y - cy), math.degrees(math.atan2(p.y - cy, p.x - cx)) % 360)
        for p in game.players.values()
    ]


@pytest.mark.parametrize("count", [4, 5, 6, 7, 8, 9, 10])
def test_at_a_meeting_start_everyone_stands_around_the_table_without_overlapping(count):
    game, _, students = round_on(count=count)
    students[1].alive = False  # ghosts are placed too
    for player in game.players.values():
        player.dx = 1
    at_table(students[0])
    game.call_meeting(students[0].id)
    players = list(game.players.values())
    places = around_the_table(game)
    for player, (distance, _) in zip(players, places):
        assert distance == pytest.approx(game_rules.MEETING_CIRCLE), player.name
        assert not game.blocked(player.x, player.y), player.name  # a free floor spot
        assert game.area_at(player.x, player.y) != "Auditorium"
        assert (player.dx, player.dy) == (0, 0)
    # Evenly spaced, in join order, the first player north of the table.
    angles = [angle for _, angle in places]
    assert angles[0] == pytest.approx(270)
    for index, angle in enumerate(angles):
        assert (angle - 270) % 360 == pytest.approx(index * 360 / count, abs=1e-6)
    # Nobody overlaps: two 20 px squares are apart in x or in y.
    for i, a in enumerate(players):
        for b in players[i + 1:]:
            assert max(abs(a.x - b.x), abs(a.y - b.y)) >= 2 * HALF, (a.name, b.name)


def test_the_meeting_circle_stands_outside_the_table_and_within_calling_range():
    assert game_rules.MEETING_CIRCLE >= game_rules.MEETING_TABLE_RADIUS + HALF  # not on the table
    assert game_rules.MEETING_CIRCLE <= game_rules.MEETING_TABLE_RADIUS + game_rules.MEETING_RANGE


@pytest.mark.parametrize("count", range(1, 11))
def test_on_the_campus_every_place_of_the_circle_is_free_for_any_number_of_players(count):
    game = Game(load_map())
    for index in range(count):
        game.join(f"Player {index}")
    spots = game._meeting_spots()
    assert len(spots) == count and None not in spots


def test_the_snapshots_carry_the_new_places_and_everyone_sees_everyone():
    game, _, students = round_on(count=10)
    at_table(students[0])
    game.call_meeting(students[0].id)
    snapshot = game.snapshot_for(students[3].id)
    assert len(snapshot["players"]) == 10
    for entry, player in zip(snapshot["players"], game.players.values()):
        assert (entry["x"], entry["y"]) == (round(player.x, 1), round(player.y, 1))


def test_after_the_meeting_everyone_walks_on_from_the_table():
    game, _, students = round_on()
    at_table(students[0])
    game.call_meeting(students[0].id)
    end_meeting(game)
    walker_ = students[2]
    start = (walker_.x, walker_.y)
    walk(game, walker_, 0, -1, 3)
    assert walker_.y == start[1] - 3 * STEP and walker_.x == start[0]


def test_on_a_tight_map_a_player_whose_place_is_in_a_wall_stays_where_they_are():
    game, _, students = round_on(TIGHT_MAP, count=4)
    before = {p.id: (p.x, p.y) for p in game.players.values()}
    students[0].x, students[0].y = table_centre(TIGHT_MAP)
    before[students[0].id] = (students[0].x, students[0].y)
    game.call_meeting(students[0].id)
    players = list(game.players.values())
    # Places: north, east, south, west of the table. The corridor is 3 tiles high, so the
    # places north and south lie in the walls; east and west are free.
    places = around_the_table(game, TIGHT_MAP)
    assert (players[0].x, players[0].y) == before[players[0].id]
    assert (players[2].x, players[2].y) == before[players[2].id]
    assert places[1] == pytest.approx((game_rules.MEETING_CIRCLE, 0))
    assert places[3] == pytest.approx((game_rules.MEETING_CIRCLE, 180))
    assert all(not game.blocked(p.x, p.y) for p in players)


# --- Over the WebSocket and in the browser files ----------------------------------------------


def receive_until(ws, wanted):
    for _ in range(200):
        message = ws.receive_json()
        if wanted(message):
            return message
    raise AssertionError("the expected message never came")


def test_meeting_over_websocket_is_rejected_far_away_and_accepted_at_the_table(fresh_game):
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
                assert welcome["meeting_range"] == game_rules.MEETING_RANGE
                assert welcome["meeting_table_radius"] == game_rules.MEETING_TABLE_RADIUS
                assert welcome["map"]["meeting_point"] == load_map()["meeting_point"]
                assert "bell_range" not in welcome and "bell" not in welcome["map"]
                ids.append(welcome["id"])
            a.send_json({"type": "start"})
            receive_until(a, lambda m: m["type"] == "state" and m["phase"] == "playing")

            a.send_json({"type": "bell"})  # the old message
            assert receive_until(a, lambda m: m["type"] == "error")["reason"] == "Unknown message type"

            a.send_json({"type": "meeting"})  # from the spawn in the Main Entrance
            assert receive_until(a, lambda m: m["type"] == "error")["reason"] == TOO_FAR
            state = receive_until(a, lambda m: m["type"] == "state")
            assert (state["phase"], state["meeting_used"]) == ("playing", False)
            assert "bell_used" not in state

            at_table(fresh_game.players[ids[0]])
            a.send_json({"type": "meeting"})
            state = receive_until(b, lambda m: m["type"] == "state" and m["phase"] == "meeting")
            assert (state["meeting"]["reason"], state["meeting"]["called_by"]) == ("button", ids[0])
            assert len(state["players"]) == 4


def test_no_bell_is_left_in_the_server_the_map_and_the_browser():
    root = WEB.parent
    for path in ["server/game.py", "server/main.py", "server/campus.json", "web/index.html",
                 "web/main.js", "web/render.js", "web/style.css"]:
        assert "bell" not in (root / path).read_text(encoding="utf-8").lower(), path


def test_the_browser_draws_a_meeting_table_and_offers_to_call_a_meeting():
    render = (WEB / "render.js").read_text(encoding="utf-8")
    assert "makeMeetingPoint" in render and '"MEETING"' in render
    assert "Call a meeting" in (WEB / "index.html").read_text(encoding="utf-8")
    script = (WEB / "main.js").read_text(encoding="utf-8")
    assert '{ type: "meeting" }' in script and "welcome.meeting_range" in script


# =====================================================================================
# Section 3: clear walls, clear glass
# =====================================================================================
# The server's rule: opaque walls (plain wall tiles, roofs, screens) block sight and
# walking. Glass blocks walking only. Furniture stands on floor tiles and blocks neither.

OPAQUE = ["roof", "greenroof", "solar", "screen"]

# A corridor with one wall tile on (5, 2) between a viewer on (3, 2) and a target on (7, 2).
PILLAR_ROOM = {
    "tile_size": TILE,
    "grid": ["###########", "#.........#", "#....#....#", "#.........#", "###########"],
    "areas": [],
    "spawns": [[1, 1]],
}


def two_students(campus, viewer_tile=(3, 2), target_tile=(7, 2), count=5):
    """A started game with one living student on each of the two tiles."""
    game, _, students = round_on(campus, count=count)
    put(students[0], *viewer_tile)
    put(students[1], *target_tile)
    return game, students[0], students[1]


def sees(game, viewer, target):
    return target.id in {p["id"] for p in game.snapshot_for(viewer.id)["players"]}


def test_glass_does_not_block_sight_but_still_blocks_walking():
    campus = dict(PILLAR_ROOM, decor=[{"kind": "glasswall", "x": 5, "y": 2, "w": 1, "h": 1}])
    game, viewer, target = two_students(campus)
    assert sees(game, viewer, target) and sees(game, target, viewer)
    put(viewer, 4, 2)
    walk(game, viewer, 1, 0, 10)
    assert viewer.x == 5 * TILE - HALF  # stopped at the pane


def test_an_opaque_wall_blocks_sight_and_walking():
    game, viewer, target = two_students(PILLAR_ROOM)
    assert not sees(game, viewer, target) and not sees(game, target, viewer)
    put(viewer, 4, 2)
    walk(game, viewer, 1, 0, 10)
    assert viewer.x == 5 * TILE - HALF


@pytest.mark.parametrize("kind", OPAQUE)
def test_roofs_and_screens_are_opaque_like_plain_walls(kind):
    campus = dict(PILLAR_ROOM, decor=[{"kind": kind, "x": 5, "y": 2, "w": 1, "h": 1}])
    game, viewer, target = two_students(campus)
    assert not sees(game, viewer, target)


@pytest.mark.parametrize("kind", FURNITURE + ["beanbag"])
def test_furniture_between_two_players_never_blocks_sight(kind):
    campus = dict(DOOR_ROOM, decor=[{"kind": kind, "x": 3, "y": 1, "w": 1, "h": 1}])
    game, viewer, target = two_students(campus, (1, 1), (5, 1))
    assert sees(game, viewer, target) and sees(game, target, viewer)


def test_the_sight_split_is_opaque_walls_against_glass_and_sea():
    assert game_rules.SIGHT_DECOR == set(OPAQUE)
    assert game_rules.SOLID_DECOR - game_rules.SIGHT_DECOR == {"glasswall", "sea"}


@pytest.mark.parametrize(
    "viewer_tile, target_tile, what",
    [
        # Spec 015: the beach grew by 4 columns in the west, so every column here moved by 4.
        ((18, 16), (18, 18), "from the north Courtyard into the Student Hall"),
        ((20, 22), (20, 20), "from the south Courtyard into the Student Hall"),
        ((20, 16), (20, 22), "through both glass walls of the Student Hall"),
        ((36, 18), (36, 20), "across the bookshelf in the Library"),
    ],
)
def test_on_the_campus_players_see_each_other_through_glass_and_over_furniture(viewer_tile, target_tile, what):
    game, viewer, target = two_students(load_map(), viewer_tile, target_tile)
    assert sees(game, viewer, target) and sees(game, target, viewer), what


@pytest.mark.parametrize(
    "viewer_tile, target_tile, what",
    [
        # Spec 015: the beach grew by 4 columns in the west, so every column here moved by 4.
        ((29, 19), (32, 19), "the wall between the spine and the Library"),
        ((33, 1), (35, 1), "the wall between the Main Entrance and Student Services"),
        ((34, 36), (34, 38), "the Auditorium's front wall with its screen"),
        ((16, 11), (16, 14), "the green roof between Hall B and the north Courtyard"),
    ],
)
def test_on_the_campus_opaque_walls_hide_players(viewer_tile, target_tile, what):
    game, viewer, target = two_students(load_map(), viewer_tile, target_tile)
    assert not sees(game, viewer, target) and not sees(game, target, viewer), what


def test_the_campus_sight_grid_opens_exactly_glass_and_sea():
    campus = load_map()
    see_through = {(c, r) for _, c, r in decor_tiles(campus, ["glasswall", "sea"])}
    opaque = {(c, r) for _, c, r in decor_tiles(campus, OPAQUE)}
    assert see_through and not see_through & opaque
    sight = game_rules.sight_grid(campus)
    for row, line in enumerate(campus["grid"]):
        for col, tile in enumerate(line):
            blocks = tile == "#" and (col, row) not in see_through
            assert (sight[row][col] == "#") == blocks, (col, row)


def test_the_browser_keeps_walls_out_of_the_light_and_out_of_the_darkness():
    render = (WEB / "render.js").read_text(encoding="utf-8")
    assert "one tile deep" not in render  # the light no longer shines into walls
    assert "glass facade" not in render  # walls no longer show windows
    assert "wallRects" in render  # the wall tiles the darkness leaves out
    assert "drawGlassPane" in render  # glass is a thin pane of its own


# =====================================================================================
# Section 4: the map check
# =====================================================================================


def walkable_from(campus, start):
    """Every tile a living player can stand on that is reachable from `start` (4 neighbours)."""
    game = Game(campus)
    seen, todo = set(), [tuple(start)]
    while todo:
        col, row = todo.pop()
        if (col, row) in seen or game.blocked(*centre(col, row)):
            continue
        seen.add((col, row))
        todo += [(col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1)]
    return seen


def is_floor(campus, col, row):
    grid = campus["grid"]
    return 0 <= row < len(grid) and 0 <= col < len(grid[0]) and grid[row][col] == "."


def test_every_place_of_the_game_can_be_reached_from_the_first_spawn():
    campus = load_map()
    reachable = walkable_from(campus, campus["spawns"][0])
    places = {f"spawn {index}": tuple(spawn) for index, spawn in enumerate(campus["spawns"])}
    station_count = 0
    for task in campus["tasks"]:
        stations = task.get("steps") or [task]
        station_count += len(stations)
        for index, station in enumerate(stations):
            label = f"task {task['id']}" if len(stations) == 1 else f"task {task['id']} step {index + 1}"
            places[label] = (station["x"], station["y"])
    # Spec 015: the four vents replaced the four staff doors (map key "vents").
    places.update({f"vent {vent['id']}": (vent["x"], vent["y"]) for vent in campus["vents"]})
    places["light switch"] = tuple(campus["light_switch"])
    places["meeting point"] = tuple(campus["meeting_point"])
    assert len(places) == 10 + station_count + 4 + 2
    for name, tile in places.items():
        assert tile in reachable, name
    # ... and so can every floor tile and every piece of furniture.
    floor = {(c, r) for r, line in enumerate(campus["grid"]) for c, tile in enumerate(line) if tile == "."}
    assert reachable == floor


def test_no_wall_tile_stands_alone_on_the_campus():
    campus = load_map()
    alone = [
        (col, row)
        for row, line in enumerate(campus["grid"])
        for col, tile in enumerate(line)
        if tile == "#" and all(is_floor(campus, col + dc, row + dr) for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    ]
    assert alone == []


def test_every_glass_pane_is_a_thin_wall_between_two_walkable_sides():
    campus = load_map()
    glass = {(c, r) for _, c, r in decor_tiles(campus, ["glasswall"])}
    assert len(glass) >= 10
    for col, row in glass:
        across_rows = is_floor(campus, col, row - 1) and is_floor(campus, col, row + 1)
        across_cols = is_floor(campus, col - 1, row) and is_floor(campus, col + 1, row)
        assert across_rows != across_cols, (col, row)  # floor on both sides, one tile thin
        # Part of a pane, not a single glass tile in the middle of a room.
        neighbours = [(col - 1, row), (col + 1, row)] if across_rows else [(col, row - 1), (col, row + 1)]
        assert any(tile in glass for tile in neighbours), (col, row)


@pytest.mark.parametrize(
    "what, tiles",
    [
        # Spec 015: the beach grew by 4 columns in the west, so every column here moved by 4.
        ("lecture hall B to the north Courtyard", [(9, 13), (10, 13)]),
        ("Hall B to the north Courtyard, west", [(18, 12), (19, 12), (18, 13), (19, 13)]),
        ("Hall B to the north Courtyard, east", [(23, 12), (24, 12), (23, 13), (24, 13)]),
        ("the south Courtyard to lecture hall D", [(9, 25), (10, 25)]),
        ("the south Courtyard to Hall D", [(23, 25), (24, 25), (23, 26), (24, 26)]),
        ("Hall D to Hall E", [(21, r) for r in range(30, 34)] + [(22, r) for r in range(30, 34)]),
        ("the spine to the Food Court", [(30, 11), (31, 11), (30, 12), (31, 12), (30, 13), (31, 13)]),
        ("the meeting point to the Library", [(31, 21), (31, 22)]),
        ("the Main Entrance to Student Services", [(34, 3), (34, 4)]),
        ("the plaza to the Auditorium", [(38, 37), (39, 37)]),
    ],
)
def test_the_doorways_between_the_parts_of_the_campus_are_at_least_two_tiles_wide(what, tiles):
    campus = load_map()
    assert all(is_floor(campus, col, row) for col, row in tiles), what


def test_the_way_from_the_main_entrance_into_student_services_is_a_straight_walk():
    # Before, a standing screen on (28, 2-5) stood in front of this door.
    # Spec 015: the beach grew by 4 columns in the west, so every column here moved by 4.
    game, player = walker(load_map(), 30, 3)
    walk(game, player, 1, 0, 30)
    assert game.area_at(player.x, player.y) == "Student Services"


def test_the_screens_of_the_campus_hang_on_walls():
    campus = load_map()
    screens = decor_tiles(campus, ["screen"])
    # Spec 015: the beach grew by 4 columns in the west, so every column here moved by 4.
    assert {(c, r) for _, c, r in screens} >= {(31, 37), (34, 5)}
    screen_tiles = {(c, r) for _, c, r in screens}
    for entry in campus["decor"]:
        if entry["kind"] != "screen":
            continue
        tiles = [
            (col, row)
            for row in range(entry["y"], entry["y"] + entry["h"])
            for col in range(entry["x"], entry["x"] + entry["w"])
        ]
        # Every screen continues a wall: one of its tiles touches a wall tile that is no
        # screen. A screen standing free in a room would be a wall of its own.
        around = {(c + dc, r + dr) for c, r in tiles for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))}
        assert any(campus["grid"][r][c] == "#" for c, r in around - screen_tiles), entry


def test_the_meeting_table_does_not_cover_furniture_or_a_task_place():
    campus = load_map()
    cx, cy = table_centre()
    occupied = [(c, r) for _, c, r in decor_tiles(campus, FURNITURE + ["beanbag"])]
    occupied += [
        (station["x"], station["y"])
        for task in campus["tasks"]
        for station in task.get("steps", [task])
    ]
    # Spec 015: the vents replaced the staff doors.
    occupied += [(vent["x"], vent["y"]) for vent in campus["vents"]] + [tuple(campus["light_switch"])]
    for col, row in occupied:
        x, y = centre(col, row)
        assert math.hypot(x - cx, y - cy) > game_rules.MEETING_TABLE_RADIUS + TILE / 2, (col, row)
