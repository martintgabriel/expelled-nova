"""Tests for spec 021: the Cafeteria tray and Beach surfing mini-games."""

import random

import pytest

from server import minigames
from server.game import TICK_RATE, Game, GameError, load_map

TRAY = ["Main course", "Soup", "Drink", "Dessert", "Pay"]


def tray(seed=0):
    return minigames.make_challenge("tray", random.Random(seed), 0, TICK_RATE)


def answer(challenge, value, seed=1):
    minigames.validate_value(challenge["kind"], value)
    return minigames.apply_answer(challenge, value, random.Random(seed), 0, TICK_RATE)


# --- tray ------------------------------------------------------------------------------------


def test_tray_is_a_kind_with_a_limit_and_a_note():
    assert "tray" in minigames.KINDS
    assert minigames.TIME_LIMITS["tray"] == 30
    assert minigames.TIMEOUT_NOTES["tray"] == "The cafeteria closed."


def test_a_tray_shows_the_five_items_shuffled():
    challenge = tray()
    assert sorted(challenge["items"]) == sorted(TRAY)
    assert challenge["next"] == 0
    assert challenge["deadline_tick"] == 30 * TICK_RATE
    assert len({tuple(tray(seed)["items"]) for seed in range(10)}) > 1


def test_tapping_the_line_in_order_fills_the_tray():
    challenge = tray()
    for step, item in enumerate(TRAY):
        done, note = answer(challenge, challenge["items"].index(item))
        assert note is None
        assert done == (step == 4)


def test_a_wrong_item_sends_you_to_the_back_of_the_queue():
    challenge = tray()
    answer(challenge, challenge["items"].index("Main course"))
    done, note = answer(challenge, challenge["items"].index("Pay"))
    assert (done, note) == (False, "Wrong order. Back of the queue.")
    assert challenge["next"] == 0


@pytest.mark.parametrize("value", [-1, 5, "0", 1.0, True, None, [0]])
def test_an_invalid_tray_value_is_rejected(value):
    with pytest.raises(ValueError):
        minigames.validate_value("tray", value)


def test_the_tray_view_shows_items_and_progress():
    challenge = tray()
    view = minigames.public_view(challenge, 0, TICK_RATE)
    assert view == {"kind": "tray", "items": challenge["items"], "next": 0, "order": TRAY}


# --- surf ------------------------------------------------------------------------------------


def surf(tick=0):
    return minigames.make_challenge("surf", random.Random(0), tick, TICK_RATE)


def press(challenge, tick):
    minigames.validate_value("surf", True)
    return minigames.apply_answer(challenge, True, random.Random(0), tick, TICK_RATE)


CREST = 20  # a tick inside the riding window of every wave cycle


def test_surf_is_a_kind_with_a_limit_and_a_note():
    assert "surf" in minigames.KINDS
    assert minigames.TIME_LIMITS["surf"] == 25
    assert minigames.TIMEOUT_NOTES["surf"] == "The waves are gone. Flat sea."
    low, high = minigames.SURF_CREST
    assert low <= CREST < high and minigames.SURF_PERIOD == 40


def test_three_waves_ridden_on_the_crest_finish_the_task():
    challenge = surf(tick=100)
    results = [press(challenge, 100 + CREST + i * minigames.SURF_PERIOD) for i in range(3)]
    assert results == [(False, None), (False, None), (True, None)]


def test_standing_up_off_the_crest_is_a_wipeout_and_starts_again():
    challenge = surf()
    press(challenge, CREST)
    done, note = press(challenge, minigames.SURF_PERIOD + 2)
    assert (done, note) == (False, "Wipeout! Paddle back out.")
    assert challenge["rides"] == 0


@pytest.mark.parametrize("value", [False, 1, "yes", None, [True]])
def test_an_invalid_surf_value_is_rejected(value):
    with pytest.raises(ValueError):
        minigames.validate_value("surf", value)


def test_the_surf_view_shows_the_wave_phase():
    challenge = surf(tick=10)
    view = minigames.public_view(challenge, 10 + 45, TICK_RATE)
    assert view == {"kind": "surf", "phase": 5, "period": 40, "crest": [15, 25], "rides": 0, "goal": 3}


# --- On the campus -----------------------------------------------------------------------------


def test_both_tasks_are_on_the_campus_on_walkable_tiles():
    campus = load_map()
    tasks = {t["id"]: t for t in campus["tasks"]}
    assert (tasks["tray"]["area"], tasks["tray"]["x"], tasks["tray"]["y"], tasks["tray"]["minigame"]) == (
        "Cafeteria", 41, 12, "tray")
    assert (tasks["surf"]["area"], tasks["surf"]["x"], tasks["surf"]["y"], tasks["surf"]["minigame"]) == (
        "Beach", 3, 17, "surf")  # playtest: the middle of the beach
    for task in (tasks["tray"], tasks["surf"]):
        assert campus["grid"][task["y"]][task["x"]] == "."
        assert task["joke"]


def test_a_player_can_play_the_tray_task_to_the_end():
    campus = load_map()
    for seed in range(200):
        game = Game(campus, rng=random.Random(seed))
        players = [game.join(f"P{i}") for i in range(4)]
        game.start(players[0].id)
        student = next((p for p in players if p.role == "student" and "tray" in p.tasks), None)
        if student:
            break
    task = next(t for t in campus["tasks"] if t["id"] == "tray")
    student.x, student.y = (task["x"] + 0.5) * 32, (task["y"] + 0.5) * 32
    game.task(student.id, "tray")
    for item in TRAY:
        game.task_input(student.id, "tray", student.challenge["items"].index(item))
    assert "tray" in student.tasks_done
    with pytest.raises(GameError):
        game.task_input(student.id, "tray", 0)


def test_the_surf_sea_takes_the_panel_width():
    # Bug fix (23 Nov): the panel centres its content, so without its own width the sea
    # (whose children are all absolutely positioned) shrank to 0 px and no wave was visible.
    from pathlib import Path
    import re

    style = (Path(__file__).resolve().parent.parent / "web" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.surf-sea \{([^}]*)\}", style).group(1)
    assert "width: 100%" in rule
