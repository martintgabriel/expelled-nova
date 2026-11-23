"""Tests for spec 018 (playtest fixes, part 1): cooldown, tasks per player count, the
examiner setting and the ballots after a vote."""

import json
import random

import pytest
from fastapi.testclient import TestClient

from server import game as rules
from server.game import TICK_RATE, Game, GameError, load_map, parse_message
from server.main import app

TILE = 32
HALL_MAP = {
    "tile_size": TILE,
    "grid": ["#" * 30] + ["#" + "." * 28 + "#"] * 14 + ["#" * 30],
    "areas": [],
    "spawns": [[2, 2]],
}


def lobby(count, seed=0, campus=None):
    game = Game(campus or load_map(), rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    return game, players


def playing(count=4, seed=0, campus=None):
    game, players = lobby(count, seed, campus)
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


# --- 1. Expel cooldown -----------------------------------------------------------------


def test_the_expel_cooldown_is_30_seconds():
    assert rules.EXPEL_COOLDOWN == 30
    assert rules.EXPEL_COOLDOWN_TICKS == 30 * TICK_RATE


def test_an_examiner_cannot_expel_before_30_seconds():
    game, examiners, students = playing(4, campus=HALL_MAP)
    examiner, student = examiners[0], students[0]
    for _ in range(25 * TICK_RATE):
        game.step()
    examiner.x, examiner.y = student.x, student.y
    with pytest.raises(GameError, match="Cooldown"):
        game.expel(examiner.id, student.id)
    assert student.alive


# --- 2. Tasks per player count -----------------------------------------------------------


@pytest.mark.parametrize(
    "count, tasks", [(4, 3), (5, 3), (6, 4), (7, 4), (8, 5), (9, 5), (10, 5)]
)
def test_tasks_per_player_grows_with_the_player_count(count, tasks):
    assert rules.tasks_per_player(count) == tasks


@pytest.mark.parametrize("count", [4, 6, 8, 10])
def test_every_player_is_dealt_tasks_per_player_different_tasks(count):
    game, examiners, students = playing(count)
    expected = min(rules.tasks_per_player(count), len(game.tasks))
    for player in (*examiners, *students):
        assert len(set(player.tasks)) == len(player.tasks) == expected


def test_a_small_map_deals_what_it_has():
    two = {
        **HALL_MAP,
        "tasks": [
            {"id": "t1", "title": "One", "area": "Hall", "x": 6, "y": 2, "seconds": 5},
            {"id": "t2", "title": "Two", "area": "Hall", "x": 9, "y": 2, "seconds": 5},
        ],
    }
    game, examiners, students = playing(10, campus=two)
    for player in (*examiners, *students):
        assert sorted(player.tasks) == ["t1", "t2"]


# --- 3. Examiner setting ------------------------------------------------------------------


def test_settings_is_a_known_message_type():
    message = parse_message(json.dumps({"type": "settings", "expellers": 1}), joined=True)
    assert message["expellers"] == 1


def test_the_setting_starts_automatic_and_everyone_sees_it():
    game, players = lobby(4)
    for player in players:
        assert game.snapshot_for(player.id)["settings"] == {"expellers": None}


@pytest.mark.parametrize("value", [1, 2, None])
def test_the_host_can_choose_the_number_of_examiners(value):
    game, players = lobby(4)
    game.set_settings(players[0].id, {"expellers": value})
    assert game.snapshot_for(players[1].id)["settings"] == {"expellers": value}


@pytest.mark.parametrize("value", [0, 3, -1, "2", 1.5, True, [], {}])
def test_an_invalid_number_of_examiners_is_rejected(value):
    game, players = lobby(4)
    with pytest.raises(GameError):
        game.set_settings(players[0].id, {"expellers": value})
    assert game.snapshot_for(players[0].id)["settings"] == {"expellers": None}


def test_a_missing_value_is_rejected():
    game, players = lobby(4)
    with pytest.raises(GameError):
        game.set_settings(players[0].id, {})


def test_only_the_host_can_change_the_setting():
    game, players = lobby(4)
    with pytest.raises(GameError, match="host"):
        game.set_settings(players[1].id, {"expellers": 2})
    assert game.snapshot_for(players[0].id)["settings"] == {"expellers": None}


def test_the_setting_cannot_change_during_a_round():
    game, examiners, students = playing(4)
    with pytest.raises(GameError, match="lobby"):
        game.set_settings(game.host_id, {"expellers": 2})


def test_an_unknown_player_cannot_change_the_setting():
    game, players = lobby(4)
    with pytest.raises(GameError):
        game.set_settings("p99", {"expellers": 1})


def test_one_examiner_with_ten_players():
    game, players = lobby(10)
    game.set_settings(players[0].id, {"expellers": 1})
    game.start(players[0].id)
    assert sum(p.role == "examiner" for p in players) == 1


def test_two_examiners_with_six_players():
    game, players = lobby(6)
    game.set_settings(players[0].id, {"expellers": 2})
    game.start(players[0].id)
    assert sum(p.role == "examiner" for p in players) == 2


def test_two_examiners_need_at_least_six_players():
    game, players = lobby(5)
    game.set_settings(players[0].id, {"expellers": 2})
    with pytest.raises(GameError, match="at least 6"):
        game.start(players[0].id)
    assert game.phase == "lobby"
    assert all(p.role is None for p in players)


@pytest.mark.parametrize("count, expected", [(4, 1), (6, 1), (7, 2), (10, 2)])
def test_automatic_keeps_the_old_rule(count, expected):
    game, examiners, students = playing(count)
    assert len(examiners) == expected


def test_the_setting_stays_for_the_next_round():
    game, players = lobby(4)
    game.set_settings(players[0].id, {"expellers": 1})
    game.start(players[0].id)
    examiner = next(p for p in players if p.role == "examiner")
    game.leave(examiner.id)  # the students win
    assert game.phase == "ended"
    game.restart(game.host_id)
    assert game.snapshot_for(game.host_id)["settings"] == {"expellers": 1}


def test_the_setting_resets_when_everyone_leaves():
    game, players = lobby(4)
    game.set_settings(players[0].id, {"expellers": 2})
    for player in players:
        game.leave(player.id)
    newcomer = game.join("New")
    assert game.snapshot_for(newcomer.id)["settings"] == {"expellers": None}


# --- 4. Ballots -----------------------------------------------------------------------------


def test_ballots_are_hidden_while_voting_and_shown_with_the_result():
    game, examiners, students = playing(4, campus=HALL_MAP)
    examiner = examiners[0]
    game.call_meeting(students[0].id)
    game.vote(students[0].id, examiner.id)
    game.vote(students[1].id, "skip")
    for player in game.players.values():
        assert "ballots" not in game.snapshot_for(player.id)
    game.vote(students[2].id, examiner.id)
    game.vote(examiner.id, students[0].id)
    game.step()  # the voting closes
    expected = {
        students[0].id: examiner.id,
        students[1].id: "skip",
        students[2].id: examiner.id,
        examiner.id: students[0].id,
    }
    for player in game.players.values():
        assert game.snapshot_for(player.id)["ballots"] == expected


def test_players_who_did_not_vote_have_no_ballot():
    game, examiners, students = playing(4, campus=HALL_MAP)
    game.call_meeting(students[0].id)
    game.vote(students[0].id, "skip")
    for _ in range(rules.MEETING_TICKS + 1):
        game.step()
    assert game.snapshot_for(students[1].id)["ballots"] == {students[0].id: "skip"}


def test_ballots_go_when_the_meeting_ends():
    game, examiners, students = playing(4, campus=HALL_MAP)
    game.call_meeting(students[0].id)
    for player in game.players.values():
        game.vote(player.id, "skip")
    game.step()
    assert "ballots" in game.snapshot_for(students[0].id)
    for _ in range(rules.RESULT_TICKS + 1):
        game.step()
    assert game.phase == "playing"
    assert "ballots" not in game.snapshot_for(students[0].id)


# --- WebSocket ----------------------------------------------------------------------------


def receive_until(ws, predicate, limit=200):
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def test_settings_over_the_websocket():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as host, client.websocket_connect("/ws") as guest:
            host.send_json({"type": "join", "name": "Host"})
            receive_until(host, lambda m: m["type"] == "welcome")
            guest.send_json({"type": "join", "name": "Guest"})
            receive_until(guest, lambda m: m["type"] == "welcome")

            guest.send_json({"type": "settings", "expellers": 2})
            error = receive_until(guest, lambda m: m["type"] == "error")
            assert "host" in error["reason"].lower()

            host.send_json({"type": "settings", "expellers": 2})
            state = receive_until(
                guest, lambda m: m["type"] == "state" and m.get("settings") == {"expellers": 2}
            )
            assert state["settings"] == {"expellers": 2}
