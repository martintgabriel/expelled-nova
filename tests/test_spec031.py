"""Tests for spec 031: the nata mini-game (shoo the seagulls off your pastel)."""

import random

import pytest

from server import minigames
from server.game import TICK_RATE, Game, load_map


def make(seed=0, tick=0):
    return minigames.make_challenge("nata", random.Random(seed), tick, TICK_RATE)


def shoo(challenge, gull, tick):
    minigames.validate_value("nata", gull)
    return minigames.apply_answer(challenge, gull, random.Random(0), tick, TICK_RATE)


def in_air(challenge, gull):
    g = challenge["gulls"][gull]
    return challenge["start_tick"] + g["spawn"] + 1


def test_the_flight_plan():
    challenge = make()
    gulls = challenge["gulls"]
    assert len(gulls) == 8
    for i, gull in enumerate(gulls):
        assert gull["spawn"] == minigames.NATA_FIRST + i * minigames.NATA_GAP
        assert gull["fly"] == minigames.NATA_FLY - i * 2
        assert gull["from"] in range(8)
        assert gull["shooed"] is False
    assert minigames.TIME_LIMITS["nata"] == 15
    assert minigames.TIMEOUT_NOTES["nata"] == "Too slow. The seagulls won."
    last = gulls[-1]
    assert last["spawn"] + last["fly"] < 15 * TICK_RATE


def test_a_seagull_in_the_air_can_be_shooed_once():
    challenge = make()
    assert shoo(challenge, 0, in_air(challenge, 0)) == (False, None)
    assert challenge["gulls"][0]["shooed"] is True
    assert shoo(challenge, 0, in_air(challenge, 0) + 1) == (False, None)
    assert sum(g["shooed"] for g in challenge["gulls"]) == 1


def test_a_seagull_not_yet_flying_or_already_landed_cannot_be_shooed():
    challenge = make()
    gull = challenge["gulls"][3]
    assert shoo(challenge, 3, challenge["start_tick"]) == (False, None)
    landed = challenge["start_tick"] + gull["spawn"] + gull["fly"]
    assert shoo(challenge, 3, landed) == (False, None)
    assert gull["shooed"] is False


def test_six_shooed_seagulls_finish_the_task():
    challenge = make()
    results = [shoo(challenge, i, in_air(challenge, i)) for i in range(6)]
    assert results == [(False, None)] * 5 + [(True, None)]


def test_two_bites_fail_and_one_does_not():
    challenge = make()
    g0, g1 = challenge["gulls"][0], challenge["gulls"][1]
    after_first = challenge["start_tick"] + g0["spawn"] + g0["fly"]
    assert minigames.failure(challenge, after_first) is None
    after_second = challenge["start_tick"] + g1["spawn"] + g1["fly"]
    assert minigames.failure(challenge, after_second) == "A seagull took your pastel."


def test_other_kinds_never_fail_on_their_own():
    challenge = minigames.make_challenge("card", random.Random(0), 0, TICK_RATE)
    assert minigames.failure(challenge, 10**6) is None


@pytest.mark.parametrize("value", [-1, 8, "0", 1.0, True, None])
def test_an_invalid_seagull_number_is_rejected(value):
    with pytest.raises(ValueError):
        minigames.validate_value("nata", value)


def test_the_view_shows_the_plan_and_the_age():
    challenge = make(tick=100)
    challenge["gulls"][0]["shooed"] = True
    view = minigames.public_view(challenge, 130, TICK_RATE)
    assert view["kind"] == "nata"
    assert view["age"] == 30
    assert view["goal"] == 6 and view["shooed"] == 1 and view["bites"] == 0
    assert view["gulls"] == [dict(g) for g in challenge["gulls"]]


def test_the_game_loop_ends_the_challenge_at_two_bites():
    campus = load_map()
    for seed in range(300):
        game = Game(campus, rng=random.Random(seed))
        players = [game.join(f"P{i}") for i in range(4)]
        game.start(players[0].id)
        student = next((p for p in players if p.role == "student" and "nata" in p.tasks), None)
        if student:
            break
    task = next(t for t in campus["tasks"] if t["id"] == "nata")
    student.x, student.y = (task["x"] + 0.5) * 32, (task["y"] + 0.5) * 32
    game.task(student.id, "nata")
    assert student.challenge["kind"] == "nata"
    g1 = student.challenge["gulls"][1]
    for _ in range(g1["spawn"] + g1["fly"] + 1):
        game.step()
    assert student.challenge is None and student.doing is None
    assert student.task_note == "A seagull took your pastel."
    assert "nata" not in student.tasks_done


def test_the_campus_nata_task_uses_the_new_game():
    task = next(t for t in load_map()["tasks"] if t["id"] == "nata")
    assert task["minigame"] == "nata"
