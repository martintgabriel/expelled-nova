"""Tests for spec 009: the Nova campus map.

First the real campus map (layout, areas, spawns, no dead ends, Auditorium seats, the
positions spec 008 keeps in the map), then validate_campus() with accepted, rejected and
edge cases, then the WebSocket welcome message.
"""

import copy
import math
from collections import deque

import pytest
from fastapi.testclient import TestClient

from server import game as game_rules
from server.game import MAX_PLAYERS, SPEED, Game, load_map
from server.main import app

TILE = 32
AREA_NAMES = {"Main Entrance", "Library", "Food Court", "Auditorium", "Student Services", "Courtyard"}
# Spec 011: furniture and plants no longer block walking, so they moved from the solid
# kinds to the floor kinds.
SOLID_KINDS = {"sea", "solar", "greenroof", "roof", "glasswall", "screen"}
FLOOR_KINDS = {
    "sand", "paving", "grass", "terrace", "pergola", "glassroof", "shopfloor", "seats", "beanbag",
    "counter", "shelf", "desk", "studytable", "table", "cafetable", "woodtable", "shopshelf",
    "foodcounter", "piano", "steps", "picnic", "tree",
}

# A small valid map: a 6 x 5 room with walls all around (columns/rows 0 and the last).
SMALL = {
    "tile_size": TILE,
    "grid": ["######", "#....#", "#....#", "#....#", "######"],
    "areas": [{"name": "Room", "x": 1, "y": 1, "w": 4, "h": 3, "color": "#3f6e8c"}],
    "spawns": [[1, 1]],
}


def centre(col, row):
    return (col + 0.5) * TILE, (row + 0.5) * TILE


def floor_tiles(campus):
    return {
        (col, row)
        for row, line in enumerate(campus["grid"])
        for col, tile in enumerate(line)
        if tile == "."
    }


def walk_distances(campus, start):
    """Walking distance in tiles (4 neighbours) from `start` to every reachable floor tile."""
    floor = floor_tiles(campus)
    dist = {tuple(start): 0}
    queue = deque([tuple(start)])
    while queue:
        col, row = queue.popleft()
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            tile = (col + dc, row + dr)
            if tile in floor and tile not in dist:
                dist[tile] = dist[(col, row)] + 1
                queue.append(tile)
    return dist


def with_decor(*entries, labels=None):
    campus = copy.deepcopy(SMALL)
    campus["decor"] = list(entries)
    if labels is not None:
        campus["labels"] = labels
    return campus


# --- Accepted: the real campus map --------------------------------------------------------


def test_the_campus_grid_is_42_by_43_with_walls_all_around():
    grid = load_map()["grid"]
    assert len(grid) == 43 and all(len(row) == 42 for row in grid)
    assert set("".join(grid)) <= {"#", "."}
    assert grid[0] == grid[-1] == "#" * 42
    assert all(row[0] == "#" and row[-1] == "#" for row in grid)


def test_the_campus_has_the_six_areas_and_two_courtyards_inside_the_grid():
    campus = load_map()
    names = [area["name"] for area in campus["areas"]]
    assert set(names) == AREA_NAMES
    assert names.count("Courtyard") == 2
    for area in campus["areas"]:
        assert 0 <= area["x"] and area["x"] + area["w"] <= 42
        assert 0 <= area["y"] and area["y"] + area["h"] <= 43


def test_every_floor_tile_is_reachable_from_the_first_spawn():
    campus = load_map()
    assert set(walk_distances(campus, campus["spawns"][0])) == floor_tiles(campus)


def test_there_are_no_dead_ends():
    campus = load_map()
    floor = floor_tiles(campus)
    dead = [
        (col, row)
        for col, row in floor
        if sum((col + dc, row + dr) in floor for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))) == 1
    ]
    assert dead == []


def test_every_spawn_is_its_own_floor_tile_in_the_main_entrance():
    campus = load_map()
    game = Game(campus)
    assert len({tuple(s) for s in campus["spawns"]}) == len(campus["spawns"]) >= MAX_PLAYERS
    for col, row in campus["spawns"]:
        assert campus["grid"][row][col] == "."
        assert game.area_at(*centre(col, row)) == "Main Entrance"


def test_each_courtyard_is_a_courtyard_and_spine_beach_and_plaza_are_corridors():
    game = Game(load_map())
    assert game.area_at(*centre(12, 14)) == "Courtyard"  # north courtyard
    assert game.area_at(*centre(12, 22)) == "Courtyard"  # south courtyard
    for col, row in [(24, 20), (1, 20), (30, 32)]:  # spine, beach, EDP Plaza
        assert not game.blocked(*centre(col, row))
        assert game.area_at(*centre(col, row)) is None


# Spec 011: a meeting no longer seats the players in the Auditorium. Everyone stands in a
# circle around the meeting table, so this test checks the circle instead of the seats.
def test_the_meeting_table_has_a_free_place_for_ten_players_who_do_not_overlap():
    game = Game(load_map())
    for index in range(MAX_PLAYERS):
        game.join(f"Player {index}")
    spots = game._meeting_spots()
    assert len(spots) == MAX_PLAYERS
    for x, y in spots:
        assert not game.blocked(x, y)
        assert game.area_at(x, y) != "Auditorium"
    for index, (x1, y1) in enumerate(spots):
        for x2, y2 in spots[index + 1 :]:
            assert max(abs(x1 - x2), abs(y1 - y2)) >= 2 * game_rules.PLAYER_HALF


def test_the_longest_walk_from_the_first_spawn_is_at_most_60_tiles():
    campus = load_map()
    longest = max(walk_distances(campus, campus["spawns"][0]).values())
    assert longest <= 60
    assert longest * TILE / SPEED <= 12  # seconds at the current speed


def test_bell_staff_doors_and_light_switch_are_free_reachable_floor_tiles():
    campus = load_map()
    game = Game(campus)
    reachable = walk_distances(campus, campus["spawns"][0])
    spawns = {tuple(s) for s in campus["spawns"]}
    tasks = {(t["x"], t["y"]) for t in campus["tasks"]}
    places = [tuple(campus["meeting_point"]), tuple(campus["light_switch"])]
    places += [(d["x"], d["y"]) for d in campus["staff_doors"]]
    for place in places:
        assert place in reachable, place
        assert place not in spawns and place not in tasks, place
    assert len(set(places)) == len(places)
    assert game.area_at(*centre(*campus["light_switch"])) == "Student Services"


def test_the_real_map_and_a_map_without_decor_and_labels_are_valid():
    game_rules.validate_campus(load_map())
    game_rules.validate_campus(copy.deepcopy(SMALL))


def test_load_map_checks_the_map(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(game_rules, "validate_campus", lambda campus: calls.append(campus))
    load_map()
    assert len(calls) == 1


def test_every_decor_kind_on_the_campus_is_known_and_solid_kinds_cover_only_walls():
    campus = load_map()
    for entry in campus["decor"]:
        assert entry["kind"] in SOLID_KINDS | FLOOR_KINDS, entry
        if entry["kind"] in SOLID_KINDS:
            for row in range(entry["y"], entry["y"] + entry["h"]):
                for col in range(entry["x"], entry["x"] + entry["w"]):
                    assert campus["grid"][row][col] == "#", entry


def test_the_campus_labels_name_the_halls_and_the_beach():
    texts = {label["text"] for label in load_map()["labels"]}
    assert {"Hall B", "Student Hall", "Hall D", "Hall E", "Beach"} <= texts


# --- Rejected: validate_campus ----------------------------------------------------------------


@pytest.mark.parametrize(
    "entry, reason",
    [
        ({"kind": "lava", "x": 0, "y": 0, "w": 1, "h": 1}, "kind"),
        ({"kind": "tree", "x": 0, "y": 0, "h": 1}, "w"),
        ({"kind": "tree", "x": 0, "y": 0, "w": 0, "h": 1}, "w"),
        ({"kind": "tree", "x": 0, "y": 0, "w": 1.5, "h": 1}, "whole"),
        ({"kind": "tree", "x": 0, "y": 0, "w": True, "h": 1}, "whole"),
        ({"kind": "sea", "x": 5, "y": 0, "w": 2, "h": 1}, "outside"),  # past the right edge
        ({"kind": "sea", "x": 0, "y": 4, "w": 1, "h": 2}, "outside"),  # past the bottom edge
        ({"kind": "sea", "x": -1, "y": 0, "w": 1, "h": 1}, "outside"),
        # Spec 011: a tree is furniture now and belongs on a floor tile; a roof is still solid.
        ({"kind": "roof", "x": 2, "y": 2, "w": 1, "h": 1}, "floor"),  # a solid kind on a floor tile
        ({"kind": "tree", "x": 0, "y": 0, "w": 1, "h": 1}, "wall"),  # furniture on a wall tile
    ],
)
def test_a_broken_decor_entry_is_rejected(entry, reason):
    with pytest.raises(ValueError, match=reason):
        game_rules.validate_campus(with_decor(entry))


@pytest.mark.parametrize(
    "label, reason",
    [
        ({"text": "", "x": 1, "y": 1}, "text"),
        ({"text": "x" * 25, "x": 1, "y": 1}, "text"),
        ({"text": 7, "x": 1, "y": 1}, "text"),
        ({"text": "Beach", "x": 6, "y": 1}, "outside"),
        ({"text": "Beach", "x": 1, "y": -0.5}, "outside"),
        ({"text": "Beach", "x": "1", "y": 1}, "number"),
    ],
)
def test_a_broken_label_is_rejected(label, reason):
    with pytest.raises(ValueError, match=reason):
        game_rules.validate_campus(with_decor(labels=[label]))


def test_a_broken_map_file_fails_when_it_is_loaded(tmp_path):
    broken = with_decor({"kind": "lava", "x": 0, "y": 0, "w": 1, "h": 1})
    path = tmp_path / "campus.json"
    path.write_text(__import__("json").dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError, match="kind"):
        load_map(path)


# --- Edge cases -------------------------------------------------------------------------------


def test_a_floor_kind_may_span_wall_tiles():
    game_rules.validate_campus(with_decor({"kind": "paving", "x": 0, "y": 0, "w": 6, "h": 5}))


def test_a_solid_kind_on_the_last_wall_column_and_row_is_valid():
    game_rules.validate_campus(with_decor({"kind": "sea", "x": 5, "y": 4, "w": 1, "h": 1}))


def test_a_label_with_24_characters_and_on_the_edge_is_valid():
    game_rules.validate_campus(with_decor(labels=[{"text": "x" * 24, "x": 0, "y": 4.9}]))


def test_decor_never_changes_who_can_walk_where():
    campus = load_map()
    bare = {key: value for key, value in campus.items() if key not in ("decor", "labels")}
    with_look, without = Game(campus), Game(bare)
    for col, row in floor_tiles(campus) | {(0, 0), (12, 23), (28, 37)}:
        assert with_look.blocked(*centre(col, row)) == without.blocked(*centre(col, row))


# --- WebSocket ----------------------------------------------------------------------------------


def test_welcome_carries_the_decor_and_the_labels(fresh_game):
    campus = load_map()
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "name": "Ana"})
        welcome = ws.receive_json()
    assert welcome["type"] == "welcome"
    assert len(welcome["map"]["decor"]) == len(campus["decor"])
    assert welcome["map"]["labels"] == campus["labels"]
    assert math.isclose(len(welcome["map"]["grid"]), 43)
