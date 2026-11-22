"""Tests for spec 015: host hand-over, the bigger beach, vents like the original.

One section per part of the spec that touches server/game.py. Drawing and the story look
(web/) are checked in a running game; a few tests read the files in web/ to guard what the
page must keep (the M shortcut, the how-to-play panel, element ids).
"""

import copy
import dataclasses
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import game as game_rules
from server.game import TICK_RATE, Game, GameError, load_map
from server.main import app

TILE = 32
WEB = Path(__file__).resolve().parent.parent / "web"

# A plain hall without tasks, vents or a meeting point: enough for the host rules.
HALL_MAP = {
    "tile_size": TILE,
    "grid": [
        "############",
        "#..........#",
        "#..........#",
        "#..........#",
        "############",
    ],
    "areas": [{"name": "Hall", "x": 1, "y": 1, "w": 10, "h": 3, "color": "#888888"}],
    "spawns": [[col, row] for row in (1, 2, 3) for col in range(1, 11)],
}


def lobby(count, campus=None, seed=0):
    """A lobby with `count` players. players[0] joined first and is the host."""
    game = Game(copy.deepcopy(campus or HALL_MAP), rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    return game, players


def state_of(game):
    """Everything a rejected action must leave unchanged."""
    return copy.deepcopy(
        {
            "phase": game.phase,
            "host": game.host_id,
            "winner": game.winner,
            "lights_on": game.lights_on,
            "meeting": game.meeting,
            "failed_exams": game.failed_exams,
            "vent_open": getattr(game, "vent_open", None),
            "next_sabotage_tick": game.next_sabotage_tick,
            "players": {pid: dataclasses.asdict(p) for pid, p in game.players.items()},
        }
    )


def assert_rejected(game, action, reason):
    """The action raises GameError with exactly `reason` and changes nothing."""
    before = state_of(game)
    with pytest.raises(GameError) as error:
        action()
    assert str(error.value) == reason
    assert state_of(game) == before


def host_seen_by_all(game):
    hosts = {game.snapshot_for(pid)["host"] for pid in game.players}
    assert len(hosts) == 1
    return hosts.pop()


def receive_until(ws, predicate, limit=5 * TICK_RATE):
    """Read messages until one matches, or fail after `limit` messages."""
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


# =====================================================================================
# Section 1: host hand-over (make_host)
# =====================================================================================

# --- Accepted ---------------------------------------------------------------------------------


def test_the_host_makes_another_player_host_in_the_lobby():
    game, players = lobby(4)
    game.make_host(players[0].id, players[2].id)
    assert game.host_id == players[2].id
    assert host_seen_by_all(game) == players[2].id  # every browser learns it
    assert game.phase == "lobby" and list(game.players) == [p.id for p in players]


def test_the_host_is_stored_and_no_longer_the_first_in_join_order():
    game, players = lobby(4)
    game.make_host(players[0].id, players[3].id)
    # The first player is still in the game, but is not the host any more.
    assert_rejected(game, lambda: game.start(players[0].id), "Only the host can start the game")
    game.start(players[3].id)
    assert game.phase == "playing"
    assert host_seen_by_all(game) == players[3].id


def test_the_new_host_can_hand_over_again_and_the_old_one_cannot():
    game, players = lobby(4)
    game.make_host(players[0].id, players[1].id)
    assert_rejected(
        game, lambda: game.make_host(players[0].id, players[2].id), "Only the host can hand over"
    )
    game.make_host(players[1].id, players[0].id)  # and back
    assert game.host_id == players[0].id


def test_the_handed_over_host_keeps_the_role_for_the_next_round():
    game, players = lobby(4)
    game.make_host(players[0].id, players[2].id)
    game.start(players[2].id)
    game._end(game_rules.STUDENTS_WIN)
    assert_rejected(
        game, lambda: game.restart(players[0].id), "Only the host can start a new round"
    )
    game.restart(players[2].id)
    assert game.phase == "lobby" and game.host_id == players[2].id


# --- Rejected: each leaves the whole state unchanged -------------------------------------------


def make_host_by_a_non_host():
    game, players = lobby(4)
    return game, lambda: game.make_host(players[1].id, players[2].id)


def make_host_by_a_non_host_for_themselves():
    # The sender is checked first: a non-host learns nothing else.
    game, players = lobby(4)
    return game, lambda: game.make_host(players[1].id, players[1].id)


def make_host_for_oneself():
    game, players = lobby(4)
    return game, lambda: game.make_host(players[0].id, players[0].id)


def make_host_for_an_unknown_player():
    game, players = lobby(4)
    return game, lambda: game.make_host(players[0].id, "p99")


def make_host_for_a_player_who_left():
    game, players = lobby(4)
    game.leave(players[3].id)
    return game, lambda: game.make_host(players[0].id, players[3].id)


def make_host_by_an_unknown_player():
    game, players = lobby(4)
    return game, lambda: game.make_host("nobody", players[1].id)


def make_host_while_playing():
    game, players = lobby(4)
    game.start(players[0].id)
    return game, lambda: game.make_host(players[0].id, players[1].id)


def make_host_during_a_meeting():
    game, players = lobby(4)
    game.start(players[0].id)
    game.call_meeting(players[0].id)  # HALL_MAP has no meeting point: called from anywhere
    assert game.phase == "meeting"
    return game, lambda: game.make_host(players[0].id, players[1].id)


def make_host_after_the_end():
    game, players = lobby(4)
    game.start(players[0].id)
    game._end(game_rules.STUDENTS_WIN)
    return game, lambda: game.make_host(players[0].id, players[1].id)


@pytest.mark.parametrize(
    "case, reason",
    [
        (make_host_by_a_non_host, "Only the host can hand over"),
        (make_host_by_a_non_host_for_themselves, "Only the host can hand over"),
        (make_host_for_oneself, "You are already the host"),
        (make_host_for_an_unknown_player, "Unknown target"),
        (make_host_for_a_player_who_left, "Unknown target"),
        (make_host_by_an_unknown_player, "Unknown player"),
        (make_host_while_playing, "The host can only change in the lobby"),
        (make_host_during_a_meeting, "The host can only change in the lobby"),
        (make_host_after_the_end, "The host can only change in the lobby"),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_make_host_changes_nothing(case, reason):
    game, action = case()
    assert_rejected(game, action, reason)


# None stands for a missing field: server/main.py passes message.get("target").
@pytest.mark.parametrize("target", [3, None, True, ["p2"], {"id": "p2"}])
def test_a_make_host_target_that_is_not_a_string_is_rejected(target):
    game, players = lobby(4)
    assert_rejected(
        game, lambda: game.make_host(players[0].id, target), "Target must be a player id"
    )


# --- The host leaving: the player who has been in the game longest takes over ------------------


def test_a_handed_over_host_leaving_passes_the_host_to_the_longest_present_player():
    game, players = lobby(4)
    game.make_host(players[0].id, players[2].id)
    game.leave(players[2].id)
    assert host_seen_by_all(game) == players[0].id  # the longest in the game, not the next in line


def test_the_first_host_leaving_still_passes_the_host_on_as_before():
    game, players = lobby(4)
    game.leave(players[0].id)
    assert host_seen_by_all(game) == players[1].id


def test_a_non_host_leaving_keeps_a_handed_over_host():
    game, players = lobby(4)
    game.make_host(players[0].id, players[3].id)
    game.leave(players[0].id)
    game.leave(players[1].id)
    assert host_seen_by_all(game) == players[3].id


def test_the_host_leaving_during_a_round_passes_the_host_on():
    game, players = lobby(5)
    game.make_host(players[0].id, players[4].id)
    game.start(players[4].id)
    game.leave(players[4].id)
    assert game.host_id == players[0].id


def test_an_empty_game_has_no_host_and_the_next_player_becomes_host():
    game, players = lobby(2)
    game.make_host(players[0].id, players[1].id)
    game.leave(players[1].id)
    game.leave(players[0].id)
    assert game.host_id is None
    newcomer = game.join("Newcomer")
    assert game.host_id == newcomer.id


# --- Messages ---------------------------------------------------------------------------------


def test_make_host_messages_are_parsed_after_joining_and_rejected_before():
    raw = '{"type": "make_host", "target": "p2"}'
    assert game_rules.parse_message(raw, joined=True) == {"type": "make_host", "target": "p2"}
    with pytest.raises(GameError, match="Join the game first"):
        game_rules.parse_message(raw, joined=False)


def test_make_host_over_the_websocket(fresh_game):
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
            ids = []
            for ws, name in ((a, "Ada"), (b, "Bo")):
                ws.send_json({"type": "join", "name": name})
                ids.append(receive_until(ws, lambda m: m["type"] == "welcome")["id"])

            b.send_json({"type": "make_host", "target": ids[1]})  # not the host
            error = receive_until(b, lambda m: m["type"] == "error")
            assert error["reason"] == "Only the host can hand over"

            a.send_json({"type": "make_host"})  # no target
            error = receive_until(a, lambda m: m["type"] == "error")
            assert error["reason"] == "Target must be a player id"

            a.send_json({"type": "make_host", "target": ids[1]})
            for ws in (a, b):
                state = receive_until(ws, lambda m: m["type"] == "state" and m["host"] == ids[1])
                assert state["phase"] == "lobby"
            assert fresh_game.host_id == ids[1]


# --- The page: meeting shortcut and "How to play" (checked by hand, guarded here) --------------


def test_the_page_has_the_m_shortcut_and_the_how_to_play_panel():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    script = (WEB / "main.js").read_text(encoding="utf-8")
    assert 'id="help-button"' in page and 'id="help-panel"' in page and 'id="help-close"' in page
    assert ">M</kbd>" in page  # the key badge on the meeting button
    assert "tryMeeting" in script and "make_host" in script


# =====================================================================================
# Section 2: the bigger beach with surfboards (server/campus.json)
# =====================================================================================

OFFSET = 4  # columns added in the west; every coordinate of the old map moved by this
BEACH_COLS = range(1, 6)  # five tiles of sand between the sea (column 0) and the campus
BEACH_ROWS = range(9, 36)
# The campus before this spec (spec 011 and 013), to check that everything moved together.
OLD_SPAWNS = [[18, 4], [20, 4], [22, 4], [24, 4], [26, 4], [19, 6], [21, 6], [23, 6], [25, 6], [27, 6]]
OLD_AREAS = {
    "Main Entrance": (16, 1, 14, 6),
    "Student Services": (31, 1, 9, 6),
    "Food Court": (28, 9, 11, 7),
    "Library": (28, 18, 10, 8),
    "Auditorium": (23, 38, 13, 4),
}
OLD_STATIONS = [(33, 22), (35, 3), (20, 3), (37, 20), (30, 40), (24, 6), (19, 23)]


def centre(col, row):
    return (col + 0.5) * TILE, (row + 0.5) * TILE


def reachable_tiles(campus):
    """Every floor tile a living player can walk to from the first spawn (4 neighbours)."""
    grid = campus["grid"]
    seen, todo = set(), [tuple(campus["spawns"][0])]
    while todo:
        col, row = todo.pop()
        inside = 0 <= row < len(grid) and 0 <= col < len(grid[row])
        if (col, row) in seen or not inside or grid[row][col] != ".":
            continue
        seen.add((col, row))
        todo += [(col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1)]
    return seen


def decor_tiles(campus, kind):
    return {
        (col, row)
        for entry in campus["decor"]
        if entry["kind"] == kind
        for row in range(entry["y"], entry["y"] + entry["h"])
        for col in range(entry["x"], entry["x"] + entry["w"])
    }


def stations(campus):
    """Every task place of the map as (col, row), multi-step tasks included."""
    return [(s["x"], s["y"]) for task in campus["tasks"] for s in task.get("steps", [task])]


def test_the_map_grew_by_four_columns_and_keeps_its_height():
    grid = load_map()["grid"]
    assert len(grid) == 43
    assert {len(line) for line in grid} == {42 + OFFSET}


def test_every_coordinate_moved_east_by_the_same_offset():
    campus = load_map()
    assert campus["spawns"] == [[col + OFFSET, row] for col, row in OLD_SPAWNS]
    assert campus["meeting_point"] == [24 + OFFSET, 21]
    assert campus["light_switch"] == [39 + OFFSET, 6]
    assert stations(campus) == [(col + OFFSET, row) for col, row in OLD_STATIONS]
    areas = {a["name"]: (a["x"], a["y"], a["w"], a["h"]) for a in campus["areas"] if a["name"] != "Courtyard"}
    assert areas == {name: (x + OFFSET, y, w, h) for name, (x, y, w, h) in OLD_AREAS.items()}
    courtyards = [(a["x"], a["y"], a["w"], a["h"]) for a in campus["areas"] if a["name"] == "Courtyard"]
    assert courtyards == [(3 + OFFSET, 14, 20, 3), (3 + OFFSET, 22, 20, 3)]


def test_the_beach_is_five_tiles_of_walkable_sand_reachable_from_the_spawn():
    campus = load_map()
    reachable = reachable_tiles(campus)
    sand = decor_tiles(campus, "sand")
    game = Game(campus)
    for row in BEACH_ROWS:
        for col in BEACH_COLS:
            assert campus["grid"][row][col] == ".", (col, row)
            assert (col, row) in sand, (col, row)
            assert (col, row) in reachable, (col, row)
            assert not game.blocked(*centre(col, row))
    assert len(BEACH_COLS) == 5


def test_the_sea_lies_west_north_and_south_of_the_beach_and_blocks_walking():
    campus = load_map()
    sea = decor_tiles(campus, "sea")
    game = Game(campus)
    west = [(0, row) for row in range(43)]
    north = [(col, 8) for col in BEACH_COLS]
    south = [(col, 36) for col in BEACH_COLS]
    for col, row in west + north + south:
        assert campus["grid"][row][col] == "#", (col, row)
        assert (col, row) in sea, (col, row)
        assert game.blocked(*centre(col, row))
        assert game.sight[row][col] == "."  # one can look across the water


@pytest.mark.parametrize("row", [9, 20, 35])
def test_a_walk_across_the_beach_ends_at_the_water(row):
    campus = load_map()
    game = Game(campus)
    player = game.join("Surfer")
    player.x, player.y = centre(5, row)
    game.set_input(player.id, {"type": "input", "dx": -1, "dy": 0})
    for _ in range(60):
        game.step()
    assert (player.x, player.y) == (TILE + game_rules.PLAYER_HALF, centre(5, row)[1])  # flush with the sea
    for _ in range(20):  # walking on changes nothing: the sea blocks
        game.step()
    assert player.x == TILE + game_rules.PLAYER_HALF


def test_the_beach_opens_onto_the_campus_in_several_places():
    grid = load_map()["grid"]
    openings = [row for row in BEACH_ROWS if grid[row][6] == "."]
    # Hall B, both Courtyards, Hall D and the lawn path, as before the beach grew.
    assert openings == [9, 10, 11, 15, 23, 27, 28, 29, 34, 35]


def test_surfboards_are_floor_decor_on_the_sand():
    campus = load_map()
    assert "surfboard" in game_rules.FURNITURE_DECOR  # walked over, like all furniture
    boards = decor_tiles(campus, "surfboard")
    assert len(boards) >= 4
    assert boards <= {(col, row) for row in BEACH_ROWS for col in BEACH_COLS}
    assert not boards & set(map(tuple, campus["spawns"]))


def test_walking_over_a_surfboard_is_possible():
    campus = load_map()
    game = Game(campus)
    player = game.join("Surfer")
    col, row = sorted(decor_tiles(campus, "surfboard"))[0]
    player.x, player.y = centre(col, row)
    assert not game.blocked(player.x, player.y)


def test_the_beach_is_labelled_carcavelos_beach():
    labels = {label["text"]: label for label in load_map()["labels"]}
    assert "Beach" not in labels
    beach = labels["Carcavelos Beach"]
    assert 1 <= beach["x"] <= 6 and 9 <= beach["y"] <= 35


# =====================================================================================
# Section 3: vents like the original game
# =====================================================================================
# The four vents replace the staff doors of spec 008, part 6 (the rule changed): a living
# examiner climbs into a vent, is hidden from everyone while inside, moves between the
# vents and climbs out. The old staff-door tests in tests/test_spec008.py went with the rule.

VENT_SECONDS = 3  # cooldown before climbing in again after climbing out
VENT_TICKS = VENT_SECONDS * TICK_RATE
INSIDE = "Leave the vent first"
NOT_ON_A_VENT = "You are not standing on a vent"
NOT_INSIDE = "You are not inside a vent"
EXAMINERS_ONLY = "Only examiners can use vents"
CORNERS = ["lecture-hall", "student-services", "south-lawn", "plaza"]  # NW, NE, SW, SE


def vents():
    """The campus vents by id."""
    return {vent["id"]: vent for vent in load_map()["vents"]}


def vent_centre(vent_id):
    vent = vents()[vent_id]
    return centre(vent["x"], vent["y"])


def stand_on(player, vent_id, dx=0, dy=0):
    """Put a player on the centre of a vent's tile, or `dx`, `dy` pixels from it."""
    x, y = vent_centre(vent_id)
    player.x, player.y = x + dx, y + dy


def stand_at(player, col, row):
    player.x, player.y = centre(col, row)


def started(count=5, campus=None, seed=0):
    """A started round on the campus. Returns the game, its examiners and its students."""
    game, players = lobby(count, campus or load_map(), seed)
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


def inside(count=5, vent_id="lecture-hall"):
    """A started round whose first examiner has climbed into `vent_id`."""
    game, examiners, students = started(count)
    stand_on(examiners[0], vent_id)
    game.enter_vent(examiners[0].id)
    return game, examiners, students


def wait(game, ticks):
    for _ in range(ticks):
        game.step()


def at_table(game, player):
    player.x, player.y = centre(*game.campus["meeting_point"])


def seen_ids(game, viewer):
    return [p["id"] for p in game.snapshot_for(viewer.id)["players"]]


def make_ghost(game, examiner, student):
    """The examiner expels the student right now (cooldown skipped, standing together)."""
    examiner.next_expel_tick = game.tick
    student.x, student.y = examiner.x, examiner.y
    game.expel(examiner.id, student.id)
    return student


# --- Accepted: climbing in --------------------------------------------------------------------


@pytest.mark.parametrize("vent_id", CORNERS)
def test_a_living_examiner_on_a_vent_climbs_in(vent_id):
    game, (examiner,), students = started()
    stand_on(examiner, vent_id)
    others = [(p.x, p.y) for p in students]
    game.enter_vent(examiner.id)
    assert examiner.vent == vent_id
    assert game.snapshot_for(examiner.id)["vent"] == vent_id
    assert game.phase == "playing" and examiner.alive
    assert [(p.x, p.y) for p in students] == others  # nobody else moved


@pytest.mark.parametrize("dx, dy", [(-16, -16), (15, 15), (-16, 15), (15, -16)])
def test_anywhere_on_the_vents_tile_counts_and_the_examiner_sits_on_its_centre(dx, dy):
    game, (examiner,), _ = started()
    stand_on(examiner, "plaza", dx, dy)  # the corners of the tile
    game.enter_vent(examiner.id)
    assert (examiner.x, examiner.y) == vent_centre("plaza")  # where the camera sits


def test_climbing_in_stops_walking_and_cancels_a_running_task():
    game, (examiner,), _ = started()
    stand_on(examiner, "plaza")
    game.set_input(examiner.id, {"type": "input", "dx": 1, "dy": 0})
    examiner.doing, examiner.challenge = examiner.tasks[0], {"kind": "card"}
    game.enter_vent(examiner.id)
    assert (examiner.dx, examiner.dy) == (0, 0)
    assert examiner.doing is None and examiner.challenge is None
    wait(game, 5)
    assert (examiner.x, examiner.y) == vent_centre("plaza")


def test_only_an_examiner_learns_about_their_own_vent_and_cooldown():
    game, (examiner,), students = started()
    state = game.snapshot_for(examiner.id)
    assert state["vent"] is None and state["vent_cooldown"] == 0  # ready at the start
    assert "door_cooldown" not in state  # the staff doors are gone
    for student in students:
        own = game.snapshot_for(student.id)
        assert "vent" not in own and "vent_cooldown" not in own


# --- Rejected: climbing in; each leaves the whole state unchanged -------------------------------


def enter_by_a_student():
    game, _, students = started()
    stand_on(students[0], "plaza")
    return game, lambda: game.enter_vent(students[0].id)


def enter_by_a_student_somewhere():
    # The sender is checked first: a student learns nothing about vents by trying.
    game, _, students = started()
    return game, lambda: game.enter_vent(students[0].id)


def enter_by_a_ghost_student():
    game, (examiner,), students = started()
    ghost = make_ghost(game, examiner, students[0])
    stand_on(ghost, "plaza")
    return game, lambda: game.enter_vent(ghost.id)


def enter_by_a_ghost_examiner():
    game, (first, second), students = started(7)
    at_table(game, students[0])
    game.call_meeting(students[0].id)
    for player in [p for p in game.players.values() if p.alive]:
        game.vote(player.id, "skip" if player is first else first.id)
    wait(game, 1 + game_rules.RESULT_TICKS)
    assert first.alive is False and game.phase == "playing"
    stand_on(first, "plaza")
    return game, lambda: game.enter_vent(first.id)


def enter_off_a_vent():
    game, (examiner,), _ = started()  # still on the spawn in the Main Entrance
    return game, lambda: game.enter_vent(examiner.id)


def enter_one_pixel_beside_the_tile():
    game, (examiner,), _ = started()
    stand_on(examiner, "plaza", dx=-17)  # the tile is 16 px to each side of its centre
    return game, lambda: game.enter_vent(examiner.id)


def enter_during_the_cooldown():
    game, (examiner,), _ = inside(vent_id="plaza")
    game.leave_vent(examiner.id)
    return game, lambda: game.enter_vent(examiner.id)


def enter_during_a_meeting():
    game, (examiner,), students = started()
    at_table(game, students[0])
    game.call_meeting(students[0].id)
    stand_on(examiner, "plaza")
    return game, lambda: game.enter_vent(examiner.id)


def enter_in_the_lobby():
    game, players = lobby(4, load_map())
    stand_on(players[0], "plaza")
    return game, lambda: game.enter_vent(players[0].id)


def enter_after_the_end():
    game, (examiner,), students = started(4)
    make_ghost(game, examiner, students[0])
    make_ghost(game, examiner, students[1])  # the examiners win
    assert game.phase == "ended"
    stand_on(examiner, "plaza")
    return game, lambda: game.enter_vent(examiner.id)


def enter_while_already_inside():
    game, (examiner,), _ = inside()
    return game, lambda: game.enter_vent(examiner.id)


def enter_by_an_unknown_player():
    game, _, _ = started()
    return game, lambda: game.enter_vent("nobody")


def enter_on_a_map_without_vents():
    game, (examiner,), _ = started(4, campus=HALL_MAP)
    return game, lambda: game.enter_vent(examiner.id)


@pytest.mark.parametrize(
    "case, reason",
    [
        (enter_by_a_student, EXAMINERS_ONLY),
        (enter_by_a_student_somewhere, EXAMINERS_ONLY),
        (enter_by_a_ghost_student, "Ghosts cannot use vents"),
        (enter_by_a_ghost_examiner, "Ghosts cannot use vents"),
        (enter_off_a_vent, NOT_ON_A_VENT),
        (enter_one_pixel_beside_the_tile, NOT_ON_A_VENT),
        (enter_during_the_cooldown, "Vent cooldown: 3 s left"),
        (enter_during_a_meeting, "Meeting in progress"),
        (enter_in_the_lobby, "The game has not started yet"),
        (enter_after_the_end, "Game is over"),
        (enter_while_already_inside, "You are already inside a vent"),
        (enter_by_an_unknown_player, "Unknown player"),
        (enter_on_a_map_without_vents, NOT_ON_A_VENT),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_climbing_in_changes_nothing(case, reason):
    game, action = case()
    assert_rejected(game, action, reason)


# --- Moving between vents while inside ----------------------------------------------------------


@pytest.mark.parametrize("destination", ["student-services", "south-lawn", "plaza"])
def test_an_examiner_inside_moves_to_another_vent_at_once(destination):
    game, (examiner,), _ = inside(vent_id="lecture-hall")
    game.move_vent(examiner.id, destination)
    assert examiner.vent == destination
    assert (examiner.x, examiner.y) == vent_centre(destination)  # the camera follows
    assert game.snapshot_for(examiner.id)["vent"] == destination
    assert game.snapshot_for(examiner.id)["area"] == game.area_at(*vent_centre(destination))


def test_moving_between_vents_has_no_cooldown():
    game, (examiner,), _ = inside(vent_id="lecture-hall")
    for destination in ["plaza", "south-lawn", "student-services", "lecture-hall"]:
        game.move_vent(examiner.id, destination)  # all in the same tick
    assert examiner.vent == "lecture-hall"
    assert game.snapshot_for(examiner.id)["vent_cooldown"] == 0


def move_without_being_inside():
    game, (examiner,), _ = started()
    stand_on(examiner, "plaza")  # on a vent, but not in it
    return game, lambda: game.move_vent(examiner.id, "south-lawn")


def move_to_an_unknown_vent():
    game, (examiner,), _ = inside()
    return game, lambda: game.move_vent(examiner.id, "no-such-vent")


def move_to_the_vent_you_are_in():
    game, (examiner,), _ = inside(vent_id="plaza")
    return game, lambda: game.move_vent(examiner.id, "plaza")


def move_by_a_student():
    game, _, students = started()
    return game, lambda: game.move_vent(students[0].id, "plaza")


def move_during_a_meeting():
    game, (examiner,), students = inside()
    at_table(game, students[0])
    game.call_meeting(students[0].id)
    return game, lambda: game.move_vent(examiner.id, "plaza")


@pytest.mark.parametrize(
    "case, reason",
    [
        (move_without_being_inside, NOT_INSIDE),
        (move_to_an_unknown_vent, "Unknown vent"),
        (move_to_the_vent_you_are_in, "You are already at this vent"),
        (move_by_a_student, EXAMINERS_ONLY),
        (move_during_a_meeting, "Meeting in progress"),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_moving_between_vents_changes_nothing(case, reason):
    game, action = case()
    assert_rejected(game, action, reason)


# None stands for a missing field: server/main.py passes message.get("to").
@pytest.mark.parametrize("destination", [2, None, True, ["plaza"], {"id": "plaza"}])
def test_a_vent_destination_that_is_not_a_string_is_rejected(destination):
    game, (examiner,), _ = inside()
    assert_rejected(game, lambda: game.move_vent(examiner.id, destination), "Destination must be a vent id")


# --- Climbing out ---------------------------------------------------------------------------------


def test_leaving_places_the_examiner_on_the_vent_they_are_in():
    game, (examiner,), students = inside(vent_id="lecture-hall")
    game.move_vent(examiner.id, "plaza")
    game.leave_vent(examiner.id)
    assert examiner.vent is None
    assert (examiner.x, examiner.y) == vent_centre("plaza")
    assert not game.blocked(examiner.x, examiner.y)
    assert game.snapshot_for(examiner.id)["vent"] is None
    stand_at(students[0], vents()["plaza"]["x"] - 2, vents()["plaza"]["y"])
    assert examiner.id in seen_ids(game, students[0])  # visible again
    game.set_input(examiner.id, {"type": "input", "dx": -1, "dy": 0})  # and walking again
    wait(game, 1)
    assert examiner.x == vent_centre("plaza")[0] - game_rules.STEP


def leave_without_being_inside():
    game, (examiner,), _ = started()
    stand_on(examiner, "plaza")
    return game, lambda: game.leave_vent(examiner.id)


def leave_by_a_student():
    game, _, students = started()
    return game, lambda: game.leave_vent(students[0].id)


def leave_by_an_unknown_player():
    game, _, _ = started()
    return game, lambda: game.leave_vent("nobody")


@pytest.mark.parametrize(
    "case, reason",
    [
        (leave_without_being_inside, NOT_INSIDE),
        (leave_by_a_student, EXAMINERS_ONLY),
        (leave_by_an_unknown_player, "Unknown player"),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_climbing_out_changes_nothing(case, reason):
    game, action = case()
    assert_rejected(game, action, reason)


def test_the_cooldown_after_climbing_out_ends_after_exactly_three_seconds():
    game, (examiner,), students = inside(vent_id="plaza")
    game.leave_vent(examiner.id)
    assert game.snapshot_for(examiner.id)["vent_cooldown"] == VENT_SECONDS
    wait(game, TICK_RATE)
    assert game.snapshot_for(examiner.id)["vent_cooldown"] == VENT_SECONDS - 1
    wait(game, VENT_TICKS - TICK_RATE - 1)
    assert_rejected(game, lambda: game.enter_vent(examiner.id), "Vent cooldown: 1 s left")
    wait(game, 1)
    game.enter_vent(examiner.id)  # exactly 3 seconds later
    assert examiner.vent == "plaza"
    for student in students:
        assert "vent_cooldown" not in game.snapshot_for(student.id)


def test_a_new_round_resets_vents_and_cooldowns():
    game, (examiner,), students = inside(4, vent_id="plaza")
    game.leave_vent(examiner.id)
    make_ghost(game, examiner, students[0])
    make_ghost(game, examiner, students[1])  # the examiners win
    game.restart(game.host_id)
    assert examiner.vent is None and examiner.next_vent_tick == 0
    assert game.vent_open == {}
    assert "vent_cooldown" not in game.snapshot_for(examiner.id)  # no roles in the lobby


# --- While inside: invisible to everyone else ---------------------------------------------------


def test_an_examiner_inside_is_in_nobody_elses_snapshot():
    game, (first, second), students = started(7)
    ghost = make_ghost(game, first, students[0])
    stand_on(first, "plaza")
    col, row = vents()["plaza"]["x"], vents()["plaza"]["y"]
    stand_at(students[1], col - 1, row)  # right next to the vent
    stand_at(second, col - 2, row)  # the fellow examiner too
    stand_at(ghost, col - 1, row - 1)  # and a ghost, who normally sees everyone
    watchers = [students[1], second, ghost]
    assert all(first.id in seen_ids(game, watcher) for watcher in watchers)
    game.enter_vent(first.id)
    for watcher in game.players.values():
        if watcher is first:
            continue
        state = game.snapshot_for(watcher.id)
        assert first.id not in [p["id"] for p in state["players"]], watcher.name
        assert first.id not in state["colors"]
        assert state.get("vent") is None  # never another player's vent
    own = game.snapshot_for(first.id)
    assert first.id in [p["id"] for p in own["players"]]  # the own browser still gets itself
    assert students[1].id in [p["id"] for p in own["players"]]  # and sees out of the vent


def test_the_vent_of_a_player_inside_is_never_sent_to_others_while_moving():
    game, (first, second), students = started(7)
    stand_on(first, "lecture-hall")
    game.enter_vent(first.id)
    for destination in ["plaza", "south-lawn"]:
        game.move_vent(first.id, destination)
        col, row = vents()[destination]["x"], vents()[destination]["y"]
        stand_at(students[0], col + (1 if destination == "south-lawn" else -1), row)
        state = game.snapshot_for(students[0].id)
        assert first.id not in [p["id"] for p in state["players"]]
        assert state["open_vents"] == []  # moving inside opens no hatch
        assert destination not in str({k: v for k, v in state.items() if k != "area"})


def test_the_plain_snapshot_leaves_out_players_inside_a_vent():
    game, (examiner,), students = inside()
    assert examiner.id not in [p["id"] for p in game.snapshot()["players"]]
    assert examiner.id not in [p["id"] for p in game.snapshot(see_ghosts=True)["players"]]


# --- While inside: every other action is rejected -----------------------------------------------


def walking_inside():
    game, (examiner,), _ = inside()
    return game, lambda: game.set_input(examiner.id, {"type": "input", "dx": 1, "dy": 0})


def expelling_inside():
    game, (examiner,), students = inside()
    students[0].x, students[0].y = examiner.x + 20, examiner.y  # within reach
    examiner.next_expel_tick = game.tick  # no cooldown in the way
    return game, lambda: game.expel(examiner.id, students[0].id)


def reporting_inside():
    game, (first, second), students = started(7)
    stand_on(first, "plaza")
    stand_on(second, "plaza")
    make_ghost(game, second, students[0])  # a failed exam on the vent
    game.enter_vent(first.id)
    return game, lambda: game.report(first.id, game.failed_exams[0].id)


def calling_a_meeting_inside():
    game, (examiner,), _ = started(campus=dict(load_map(), meeting_point=[44, 36]))  # table on the plaza vent
    stand_on(examiner, "plaza")
    game.enter_vent(examiner.id)
    return game, lambda: game.call_meeting(examiner.id)


def doing_a_task_inside():
    campus = copy.deepcopy(load_map())
    for task in campus["tasks"]:  # every task place on the plaza vent
        for station in task.get("steps", [task]):
            station["x"], station["y"] = 44, 36
    game, (examiner,), _ = started(campus=campus)
    stand_on(examiner, "plaza")
    game.enter_vent(examiner.id)
    return game, lambda: game.task(examiner.id, examiner.tasks[0])


def sabotaging_inside():
    game, (examiner,), _ = inside()
    wait(game, game_rules.SABOTAGE_COOLDOWN_TICKS)  # the lights are ready
    return game, lambda: game.sabotage(examiner.id)


@pytest.mark.parametrize(
    "case",
    [walking_inside, expelling_inside, reporting_inside, calling_a_meeting_inside, doing_a_task_inside, sabotaging_inside],
    ids=lambda value: value.__name__,
)
def test_inside_a_vent_every_other_action_is_rejected(case):
    game, action = case()
    assert_rejected(game, action, INSIDE)


def test_the_same_actions_work_again_after_climbing_out():
    game, (examiner,), students = inside()
    students[0].x, students[0].y = examiner.x + 20, examiner.y
    examiner.next_expel_tick = game.tick
    game.leave_vent(examiner.id)
    game.expel(examiner.id, students[0].id)
    assert students[0].alive is False


def test_stopping_is_always_accepted_inside_a_vent():
    # A browser that sends "stop" right after climbing in must not get an error.
    game, (examiner,), _ = inside()
    game.set_input(examiner.id, {"type": "input", "dx": 0, "dy": 0})
    assert (examiner.dx, examiner.dy) == (0, 0) and examiner.vent == "lecture-hall"


# --- A meeting takes everyone out of the vents ---------------------------------------------------


@pytest.mark.parametrize("how", ["button", "report"])
def test_a_meeting_takes_the_examiner_out_and_places_them_at_the_table(how):
    game, (first, second), students = started(7)
    stand_on(first, "south-lawn")
    game.enter_vent(first.id)
    if how == "button":
        at_table(game, students[1])
        game.call_meeting(students[1].id)
    else:
        make_ghost(game, second, students[0])
        students[1].x, students[1].y = students[0].x, students[0].y  # next to the failed exam
        game.report(students[1].id, game.failed_exams[0].id)
    assert game.phase == "meeting" and first.vent is None
    table_x, table_y = centre(*game.campus["meeting_point"])
    distance = ((first.x - table_x) ** 2 + (first.y - table_y) ** 2) ** 0.5
    assert distance == pytest.approx(game_rules.MEETING_CIRCLE)  # like everyone else
    for player in game.players.values():
        state = game.snapshot_for(player.id)
        assert first.id in [p["id"] for p in state["players"]]  # everyone sees them again
        assert state["open_vents"] == []
    assert game.snapshot_for(first.id)["vent"] is None
    assert game.snapshot_for(first.id)["vent_cooldown"] == 0  # being taken out starts no cooldown


def test_the_end_of_the_game_takes_the_examiner_out():
    game, (examiner,), students = inside(vent_id="plaza")
    game._end(game_rules.STUDENTS_WIN)
    assert examiner.vent is None
    assert examiner.id in seen_ids(game, students[0])


# --- Others see the hatch move, never who is inside ----------------------------------------------


def test_players_within_vision_see_the_hatch_open_and_close():
    game, (examiner,), students = started()
    near, far = students[0], students[1]
    col, row = vents()["plaza"]["x"], vents()["plaza"]["y"]
    stand_at(near, col - 3, row)
    stand_at(far, 28, 4)  # in the Main Entrance
    stand_on(examiner, "plaza")
    assert game.snapshot_for(near.id)["open_vents"] == []
    game.enter_vent(examiner.id)
    assert game.snapshot_for(near.id)["open_vents"] == ["plaza"]
    assert game.snapshot_for(far.id)["open_vents"] == []  # out of sight: nothing
    assert game.snapshot_for(examiner.id)["open_vents"] == ["plaza"]
    wait(game, game_rules.VENT_OPEN_TICKS - 1)
    assert game.snapshot_for(near.id)["open_vents"] == ["plaza"]
    wait(game, 1)
    assert game.snapshot_for(near.id)["open_vents"] == []  # closed again

    game.leave_vent(examiner.id)
    assert game.snapshot_for(near.id)["open_vents"] == ["plaza"]
    wait(game, game_rules.VENT_OPEN_TICKS)
    assert game.snapshot_for(near.id)["open_vents"] == []


def test_a_hatch_behind_a_wall_is_not_sent_and_a_ghost_sees_every_hatch():
    game, (examiner,), students = started()
    ghost = make_ghost(game, examiner, students[0])
    stand_at(ghost, 28, 4)  # far away: ghosts see the whole map
    # In the north Courtyard, four tiles south of the vent: within the vision radius, but
    # the wall of lecture hall B on (7, 13) is in the way.
    stand_at(students[1], 7, 14)
    stand_on(examiner, "lecture-hall")
    game.enter_vent(examiner.id)
    assert game.snapshot_for(ghost.id)["open_vents"] == ["lecture-hall"]
    assert game.snapshot_for(students[1].id)["open_vents"] == []


def test_the_open_hatch_names_only_the_vent():
    game, (examiner,), students = started()
    col, row = vents()["plaza"]["x"], vents()["plaza"]["y"]
    stand_at(students[0], col - 3, row)
    stand_on(examiner, "plaza")
    game.enter_vent(examiner.id)
    state = game.snapshot_for(students[0].id)
    assert state["open_vents"] == ["plaza"]
    assert examiner.id not in str(state["open_vents"])
    assert examiner.id not in [p["id"] for p in state["players"]]


# --- Messages -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, parsed",
    [
        ('{"type": "vent_enter"}', {"type": "vent_enter"}),
        ('{"type": "vent_move", "to": "plaza"}', {"type": "vent_move", "to": "plaza"}),
        ('{"type": "vent_leave"}', {"type": "vent_leave"}),
    ],
)
def test_vent_messages_are_parsed_after_joining_and_rejected_before(raw, parsed):
    assert game_rules.parse_message(raw, joined=True) == parsed
    with pytest.raises(GameError, match="Join the game first"):
        game_rules.parse_message(raw, joined=False)


def test_the_old_staff_door_message_is_unknown_now():
    with pytest.raises(GameError, match="Unknown message type"):
        game_rules.parse_message('{"type": "door", "to": "library"}', joined=True)


def test_vents_over_the_websocket(fresh_game):
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
                assert welcome["map"]["vents"] == load_map()["vents"]
                assert "staff_doors" not in welcome["map"]
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

            stand_on(student, "plaza")
            student_ws.send_json({"type": "vent_enter"})
            error = receive_until(student_ws, lambda m: m["type"] == "error")
            assert error["reason"] == EXAMINERS_ONLY

            examiner_ws.send_json({"type": "vent_enter"})  # from the spawn
            error = receive_until(examiner_ws, lambda m: m["type"] == "error")
            assert error["reason"] == NOT_ON_A_VENT

            stand_on(examiner, "plaza")
            student.x, student.y = examiner.x - 64, examiner.y  # two tiles away, watching
            examiner_ws.send_json({"type": "vent_enter"})
            own = receive_until(examiner_ws, lambda m: m["type"] == "state" and m.get("vent") == "plaza")
            assert own["area"] is None  # the plaza is a corridor
            hidden = receive_until(
                student_ws,
                lambda m: m["type"] == "state" and examiner.id not in [p["id"] for p in m["players"]],
            )
            assert "vent" not in hidden and "vent_cooldown" not in hidden

            examiner_ws.send_json({"type": "vent_move"})  # no destination
            error = receive_until(examiner_ws, lambda m: m["type"] == "error")
            assert error["reason"] == "Destination must be a vent id"

            examiner_ws.send_json({"type": "vent_move", "to": "student-services"})
            moved = receive_until(
                examiner_ws, lambda m: m["type"] == "state" and m.get("vent") == "student-services"
            )
            assert moved["area"] == "Student Services"

            examiner_ws.send_json({"type": "vent_leave"})
            out = receive_until(
                examiner_ws, lambda m: m["type"] == "state" and m.get("vent") is None and m["vent_cooldown"] > 0
            )
            x, y = vent_centre("student-services")
            me = next(p for p in out["players"] if p["id"] == examiner.id)
            assert (me["x"], me["y"]) == (x, y)
            assert out["vent_cooldown"] == VENT_SECONDS


# --- The map --------------------------------------------------------------------------------------


def test_the_campus_has_exactly_four_vents_one_per_corner_quadrant():
    campus = load_map()
    assert "staff_doors" not in campus  # replaced by the vents
    found = campus["vents"]
    assert len(found) == 4
    assert len({vent["id"] for vent in found}) == 4 and len({(v["x"], v["y"]) for v in found}) == 4
    floor = [(c, r) for r, line in enumerate(campus["grid"]) for c, tile in enumerate(line) if tile == "."]
    # The middle of the walkable map: between its outermost floor tiles.
    middle_col = (min(c for c, _ in floor) + max(c for c, _ in floor)) / 2
    middle_row = (min(r for _, r in floor) + max(r for _, r in floor)) / 2
    quadrants = {(vent["x"] > middle_col, vent["y"] > middle_row): vent["id"] for vent in found}
    assert quadrants == {
        (False, False): "lecture-hall",  # north-west
        (True, False): "student-services",  # north-east
        (False, True): "south-lawn",  # south-west
        (True, True): "plaza",  # south-east
    }
    for vent in found:
        assert set(vent) == {"id", "name", "x", "y"}
        assert vent["id"] and vent["name"]
        # Near its corner: in the outer third of the walkable map on both axes.
        assert abs(vent["x"] - middle_col) > (max(c for c, _ in floor) - middle_col) / 3, vent["id"]
        assert abs(vent["y"] - middle_row) > (max(r for _, r in floor) - middle_row) / 3, vent["id"]


def test_every_place_of_the_game_is_reachable_from_the_first_spawn():
    campus = load_map()
    reachable = reachable_tiles(campus)
    places = {f"spawn {index}": tuple(spawn) for index, spawn in enumerate(campus["spawns"])}
    places.update({f"task place {index}": tile for index, tile in enumerate(stations(campus))})
    places.update({f"vent {vent['id']}": (vent["x"], vent["y"]) for vent in campus["vents"]})
    places["light switch"] = tuple(campus["light_switch"])
    places["meeting point"] = tuple(campus["meeting_point"])
    assert len(places) == 10 + 7 + 4 + 2
    for name, tile in places.items():
        assert tile in reachable, name
    assert len(set(places.values())) == len(places)  # no two share a tile


def test_vents_are_free_floor_tiles_away_from_the_meeting_table():
    campus = load_map()
    game = Game(campus)
    table_x, table_y = centre(*campus["meeting_point"])
    for vent in campus["vents"]:
        x, y = centre(vent["x"], vent["y"])
        assert campus["grid"][vent["y"]][vent["x"]] == ".", vent["id"]
        assert not game.blocked(x, y), vent["id"]
        assert ((x - table_x) ** 2 + (y - table_y) ** 2) ** 0.5 > game_rules.MEETING_TABLE_RADIUS + TILE


def test_the_page_draws_vents_and_sends_the_vent_messages():
    script = (WEB / "main.js").read_text(encoding="utf-8")
    render = (WEB / "render.js").read_text(encoding="utf-8")
    page = (WEB / "index.html").read_text(encoding="utf-8")
    for message in ("vent_enter", "vent_move", "vent_leave"):
        assert f'type: "{message}"' in script
    assert 'type: "door"' not in script and "staff_doors" not in script + render
    assert "makeVent" in render and "open_vents" in script
    assert 'id="door-action-button"' in page and 'id="door-buttons"' in page  # ids kept
