"""Tests for spec 035: playtest bugfixes, campus names/layout and the new west-side games."""

import random
import re
from pathlib import Path

import pytest

from server import game as rules
from server import minigames
from server.game import FIRE_TICKS, SABOTAGE_COOLDOWN_TICKS, SPEED, TICK_RATE, Game, load_map

WEB = Path(__file__).resolve().parent.parent / "web"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def started(count=5, seed=0):
    game = Game(load_map(), rng=random.Random(seed))
    players = [game.join(f"P{i}") for i in range(count)]
    game.start(players[0].id)
    game.guard = None
    for _ in range(SABOTAGE_COOLDOWN_TICKS):
        game.step()
    return game, [p for p in players if p.role == "examiner"], [p for p in players if p.role == "student"]


def evacuate(game, player):
    area = next(s for s in game.campus["sabotages"] if s["kind"] == "fire")["assembly"]
    player.x, player.y = (area["x"] + 0.5) * game.tile, (area["y"] + 0.5) * game.tile


def test_the_fire_alarm_counts_every_living_player():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "fire")
    state = game.snapshot_for(students[0].id)["emergency"]
    assert state["evacuated"] == 0 and state["total"] == len(students) + 1
    evacuate(game, examiner)
    game.step()
    assert game.snapshot_for(students[0].id)["emergency"]["evacuated"] == 1


def test_examiners_staying_away_are_named_when_the_alarm_ends():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "fire")
    for student in students:
        evacuate(game, student)
    game.step()
    assert game.phase == "playing"
    for player in (examiner, *students):
        assert game.snapshot_for(player.id)["fire_missing"] == [examiner.id]
    for _ in range(8 * TICK_RATE):
        game.step()
    assert "fire_missing" not in game.snapshot_for(students[0].id)


def test_nobody_is_named_when_everyone_came():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "fire")
    for player in (examiner, *students):
        evacuate(game, player)
    game.step()
    assert game.snapshot_for(students[0].id)["fire_missing"] == []


def test_the_examiners_still_win_when_a_student_is_missing():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "fire")
    evacuate(game, examiner)
    for _ in range(FIRE_TICKS + 1):
        game.step()
    assert game.winner == "examiners"


def test_the_guard_sees_more_and_drives_a_little_slower():
    assert rules.GUARD_VISION_TILES == 6
    assert rules.GUARD_CONE_DEGREES == 100
    assert rules.GUARD_SPEED == 1.2 * SPEED  # spec 034 set the speed


def test_the_router_has_its_own_label_and_mark():
    script = read("main.js")
    assert '"fix lights"' not in script
    assert "Restart router" in script
    assert "Render.makeRouterMark(" in script and "makeRouterMark" in read("render.js")


def test_fixing_starts_with_a_lever_or_a_plug():
    script = read("main.js")
    assert "function openFixPanel(" in script
    body = script[script.index("function openFixPanel(") :]
    assert "lever" in body and "plug" in body
    assert 'id="fix-panel"' in read("index.html")


def test_the_waves_play_in_the_lobby_too():
    music = read("music.js")
    body = music[music.index("function updateWaves(") : music.index("\n  }\n", music.index("function updateWaves("))]
    assert '"lobby"' in body


def test_the_tray_is_a_drop_target():
    script = read("main.js")
    body = script[script.index("function renderTray(") : script.index("\n}\n", script.index("function renderTray("))]
    assert "pointerdown" in body and "tray-plate" in body
    assert ".tray-plate" in read("style.css")


# --- B. campus names and layout ---

TILE = 32


def centre(col, row):
    return (col + 0.5) * TILE, (row + 0.5) * TILE


def test_the_food_court_is_called_cafeteria_with_two_counters():
    campus = load_map()
    names = {a["name"] for a in campus["areas"]}
    assert "Cafeteria" in names and "Food Court" not in names
    texts = {label["text"] for label in campus["labels"]}
    assert {"Poke House", "The Cut", "Little Courtyard"} <= texts  # spec 036: "Poke House"
    assert "Shop" not in texts
    game = Game(campus)
    assert game.area_at(*centre(41, 12)) == "Cafeteria"


def test_the_little_courtyard_label_sits_on_floor():
    campus = load_map()
    label = next(l for l in campus["labels"] if l["text"] == "Little Courtyard")
    room = label["room"]
    assert (room["x"], room["y"], room["w"], room["h"]) == (7, 32, 8, 4)
    for row in range(room["y"], room["y"] + room["h"]):
        assert campus["grid"][row][room["x"] : room["x"] + room["w"]] == "." * room["w"]


def test_the_two_short_passages_are_closed():
    grid = load_map()["grid"]
    assert grid[13][9:11] == "##"
    assert grid[25][9:11] == "##"


def test_the_guard_no_longer_drives_through_them():
    route = {w["id"]: set(w["connections"]) for w in load_map()["guard_route"]["waypoints"]}
    assert "upper-courtyard" not in route["west-vent"]
    assert "west-south" not in route["lower-courtyard"]
    Game(load_map())  # the route still validates (drivable, connected)


def test_the_campus_map_draws_the_grass_and_render_has_the_nova_sign():
    source = (WEB / "campusmap.js").read_text(encoding="utf-8")
    assert "grass" in source and "GRASS" in source
    render = (WEB / "render.js").read_text(encoding="utf-8")
    assert "function makeNovaSign(" in render and '"NOVA"' in render
    assert "Render.makeNovaSign(" in (WEB / "main.js").read_text(encoding="utf-8")


# --- C. new west-side games ---

def make(kind, seed=0, tick=0):
    return minigames.make_challenge(kind, random.Random(seed), tick, TICK_RATE)


def answer(challenge, value, tick):
    minigames.validate_value(challenge["kind"], value)
    return minigames.apply_answer(challenge, value, random.Random(1), tick, TICK_RATE)


# --- beer -----------------------------------------------------------------------------------


def test_beer_basics():
    assert minigames.TIME_LIMITS["beer"] == 20
    assert minigames.TIMEOUT_NOTES["beer"] == "Last call. The bar closed."
    challenge = make("beer")
    assert minigames.public_view(challenge, 0, TICK_RATE) == {"kind": "beer", "beers": 0, "sips": 0, "goal": 3, "per_beer": 8}


def test_three_beers_of_eight_quick_sips_finish():
    challenge = make("beer")
    results = [answer(challenge, True, i * 5) for i in range(24)]
    assert results[-1] == (True, None)
    assert all(done is False for done, _ in results[:-1])


def test_a_long_pause_lets_the_beer_go_warm():
    challenge = make("beer")
    for i in range(5):
        answer(challenge, True, i * 5)
    done, note = answer(challenge, True, 20 + minigames.BEER_WARM_TICKS + 1)
    assert (done, note) == (False, "Too slow. It got warm.")
    assert challenge["sips"] == 0 and challenge["beers"] == 0


@pytest.mark.parametrize("value", [False, 1, "sip", None])
def test_an_invalid_sip_is_rejected(value):
    with pytest.raises(ValueError):
        minigames.validate_value("beer", value)


# --- frisbee ---------------------------------------------------------------------------------


def in_air(challenge, i):
    return challenge["start_tick"] + challenge["gulls"][i]["spawn"] + 1


def test_frisbee_basics():
    assert minigames.TIME_LIMITS["frisbee"] == 15
    assert minigames.TIMEOUT_NOTES["frisbee"] == "The others went to class."
    challenge = make("frisbee")
    assert len(challenge["gulls"]) == 5
    view = minigames.public_view(challenge, 0, TICK_RATE)
    assert view["kind"] == "frisbee" and view["goal"] == 3


def test_three_catches_finish():
    challenge = make("frisbee")
    results = [answer(challenge, i, in_air(challenge, i)) for i in range(3)]
    assert results == [(False, None), (False, None), (True, None)]


def test_three_drops_fail():
    challenge = make("frisbee")
    third = challenge["gulls"][2]
    landed = challenge["start_tick"] + third["spawn"] + third["fly"]
    assert minigames.failure(challenge, landed - 1) is None
    assert minigames.failure(challenge, landed) == "You dropped too many."


@pytest.mark.parametrize("value", [-1, 5, "0", True])
def test_an_invalid_frisbee_is_rejected(value):
    with pytest.raises(ValueError):
        minigames.validate_value("frisbee", value)


# --- seat ----------------------------------------------------------------------------------------


def free_at(challenge, tick):
    return minigames.public_view(challenge, tick, TICK_RATE)["free"]


def test_seat_basics():
    assert minigames.TIME_LIMITS["seat"] == 20
    assert minigames.TIMEOUT_NOTES["seat"] == "The lecture started without you."
    challenge = make("seat")
    view = minigames.public_view(challenge, 0, TICK_RATE)
    assert set(view) == {"kind", "free", "seats", "sits", "goal", "next_in"}
    assert view["seats"] == 12 and view["goal"] == 3 and 0 <= view["free"] < 12


def test_the_free_seat_moves_every_period():
    challenge = make("seat")
    frees = {free_at(challenge, i * minigames.SEAT_PERIOD) for i in range(12)}
    assert len(frees) > 1


def test_three_free_seats_finish_and_a_taken_one_is_awkward():
    challenge = make("seat")
    tick = 0
    taken = next(s for s in range(12) if s != free_at(challenge, tick))
    assert answer(challenge, taken, tick) == (False, "Taken. Awkward.")
    results = []
    for i in range(3):
        tick = i * minigames.SEAT_PERIOD
        results.append(answer(challenge, free_at(challenge, tick), tick))
    assert results == [(False, None), (False, None), (True, None)]


@pytest.mark.parametrize("value", [-1, 12, "3", 2.0, False])
def test_an_invalid_seat_is_rejected(value):
    with pytest.raises(ValueError):
        minigames.validate_value("seat", value)


# --- campus ------------------------------------------------------------------------------------


def test_the_campus_places():
    campus = load_map()
    tasks = {t["id"]: t for t in campus["tasks"]}
    expected = {
        "surf": ("Beach", 3, 17, "surf"),
        "beer": ("Beach", 3, 33, "beer"),
        "frisbee": ("Little Courtyard", 10, 34, "frisbee"),
        "seat": ("Lecture hall B", 9, 10, "seat"),  # playtest: the chair stands in Lecture hall B
    }
    for task_id, (area, x, y, kind) in expected.items():
        task = tasks[task_id]
        assert (task["area"], task["x"], task["y"], task["minigame"]) == (area, x, y, kind)
        assert campus["grid"][y][x] == "."
        assert task["joke"]
