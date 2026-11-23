"""Tests for spec 024: the print_file, cert_file and chat mini-games."""

import random

import pytest

from server import minigames
from server.game import TICK_RATE, load_map


def make(kind, seed=0):
    return minigames.make_challenge(kind, random.Random(seed), 0, TICK_RATE)


def answer(challenge, value, seed=1):
    minigames.validate_value(challenge["kind"], value)
    return minigames.apply_answer(challenge, value, random.Random(seed), 0, TICK_RATE)


def right_option(challenge):
    if challenge["kind"] == "chat":
        return challenge["options"].index(challenge["correct"])
    return challenge["options"].index(challenge["request"])


# --- print_file and cert_file --------------------------------------------------------------


@pytest.mark.parametrize("kind, rounds", [("print_file", 3), ("cert_file", 2)])
def test_a_file_challenge_shows_a_request_and_four_options(kind, rounds):
    challenge = make(kind)
    assert challenge["round"] == 1 and challenge["rounds"] == rounds
    assert len(challenge["options"]) == len(set(challenge["options"])) == 4
    assert challenge["request"] in challenge["options"]
    assert minigames.TIME_LIMITS[kind] == 30
    assert minigames.TIMEOUT_NOTES[kind] == "The printer went to sleep."


@pytest.mark.parametrize("kind, rounds", [("print_file", 3), ("cert_file", 2)])
def test_picking_the_right_file_every_round_finishes(kind, rounds):
    challenge = make(kind)
    results = [answer(challenge, right_option(challenge), seed) for seed in range(rounds)]
    assert results == [(False, None)] * (rounds - 1) + [(True, None)]


@pytest.mark.parametrize("kind", ["print_file", "cert_file"])
def test_a_wrong_file_starts_again(kind):
    challenge = make(kind)
    answer(challenge, right_option(challenge))
    wrong = next(i for i, name in enumerate(challenge["options"]) if name != challenge["request"])
    assert answer(challenge, wrong) == (False, "Wrong file. You printed 40 pages of it.")
    assert challenge["round"] == 1


@pytest.mark.parametrize("kind", ["print_file", "cert_file"])
@pytest.mark.parametrize("value", [-1, 4, "0", 1.0, True, None])
def test_an_invalid_file_value_is_rejected(kind, value):
    with pytest.raises(ValueError):
        minigames.validate_value(kind, value)


def test_the_file_view_shows_what_the_player_needs():
    challenge = make("print_file")
    view = minigames.public_view(challenge, 0, TICK_RATE)
    assert view == {
        "kind": "print_file",
        "request": challenge["request"],
        "options": challenge["options"],
        "round": 1,
        "rounds": 3,
    }


# --- chat ---------------------------------------------------------------------------------


def test_a_chat_starts_at_the_first_line_with_three_replies():
    challenge = make("chat")
    assert challenge["step"] == 0 and challenge["steps"] == 3
    assert len(challenge["options"]) == len(set(challenge["options"])) == 3
    assert challenge["correct"] in challenge["options"]
    assert minigames.TIME_LIMITS["chat"] == 45
    assert minigames.TIMEOUT_NOTES["chat"] == "The Helpdesk closed for lunch."


def test_three_right_replies_finish_the_conversation():
    challenge = make("chat")
    results = [answer(challenge, right_option(challenge), seed) for seed in range(3)]
    assert results == [(False, None), (False, None), (True, None)]


def test_a_wrong_reply_starts_the_conversation_again():
    challenge = make("chat")
    answer(challenge, right_option(challenge))
    wrong = next(i for i, text in enumerate(challenge["options"]) if text != challenge["correct"])
    assert answer(challenge, wrong) == (False, "Não percebi. Outra vez, por favor.")
    assert challenge["step"] == 0


@pytest.mark.parametrize("value", [-1, 3, "1", 0.0, False, None])
def test_an_invalid_chat_value_is_rejected(value):
    with pytest.raises(ValueError):
        minigames.validate_value("chat", value)


def test_the_chat_view_never_says_which_reply_is_right():
    challenge = make("chat")
    view = minigames.public_view(challenge, 0, TICK_RATE)
    assert "correct" not in view
    assert set(view) == {"kind", "line", "want", "options", "step", "steps"}
    assert view["options"] == challenge["options"]


def test_every_conversation_has_three_complete_lines():
    for conversation in minigames.CONVERSATIONS:
        assert len(conversation) == 3
        for line in conversation:
            assert set(line) == {"desk", "want", "reply"}
            assert all(line.values())


# --- On the campus ----------------------------------------------------------------------------


def test_the_campus_uses_the_new_kinds():
    tasks = {t["id"]: t for t in load_map()["tasks"]}
    assert tasks["print"]["minigame"] == "print_file"
    assert tasks["helpdesk"]["minigame"] == "chat"
    assert tasks["certificate"]["steps"][0]["minigame"] == "cert_file"
    kinds = [s.get("minigame") for t in tasks.values() for s in t.get("steps", [t])]
    assert "paper_jam" not in kinds and "translate" not in kinds
