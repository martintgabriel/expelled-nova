"""Tests for spec 037: more tasks, kick, taking over as host, enrolling again, leaving,
emergency arrows, chat for ghosts, wording and the phone layout."""

import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import game as rules
from server.game import (
    ENDED,
    LOBBY,
    PLAYING,
    TICK_RATE,
    Game,
    GameError,
    load_map,
    parse_message,
)
from server.main import app

WEB = Path(__file__).resolve().parent.parent / "web"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def lobby(count=4):
    game = Game(load_map(), rng=random.Random(0))
    players = [game.join(f"P{i}") for i in range(count)]
    return game, players


def started(count=5, seed=0):
    game = Game(load_map(), rng=random.Random(seed))
    players = [game.join(f"P{i}") for i in range(count)]
    game.start(players[0].id)
    game.guard = None
    return game, players


def receive_until(ws, predicate, limit=4 * TICK_RATE):
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


# --- A. more tasks -----------------------------------------------------------------------


@pytest.mark.parametrize("count, tasks", [(4, 5), (5, 5), (6, 6), (7, 6), (8, 7), (10, 7)])
def test_a_more_tasks_per_player(count, tasks):
    assert rules.tasks_per_player(count) == tasks


def test_a_four_players_get_five_tasks_on_the_campus():
    game, players = started(4)
    students = [p for p in players if p.role == "student"]
    assert all(len(set(s.tasks)) == 5 for s in students)


# --- B. kick -------------------------------------------------------------------------------


def test_b_the_host_removes_a_player_in_the_lobby():
    game, players = lobby()
    game.kick(players[0].id, players[2].id)
    assert players[2].id not in game.players and len(game.players) == 3


def test_b_the_host_removes_a_player_during_a_round():
    game, players = started(5)
    game.kick(players[0].id, players[3].id)
    assert players[3].id not in game.players


def test_b_only_the_host_kicks_and_never_themselves():
    game, players = lobby()
    with pytest.raises(GameError, match="Only the host"):
        game.kick(players[1].id, players[2].id)
    with pytest.raises(GameError, match="yourself"):
        game.kick(players[0].id, players[0].id)
    with pytest.raises(GameError, match="Unknown target"):
        game.kick(players[0].id, "p999")
    with pytest.raises(GameError, match="Target must be a player id"):
        game.kick(players[0].id, 3)
    assert len(game.players) == 4


def test_b_removing_the_last_examiner_ends_the_round():
    game, players = started(4)
    examiner = next(p for p in players if p.role == "examiner")
    host = next(p for p in players if p.id == game.host_id)
    if examiner is host:
        game.host_id = next(p.id for p in players if p is not examiner)
    game.kick(game.host_id, examiner.id)
    assert game.phase == ENDED


# --- C. electing a new host in the lobby ---------------------------------------------------


def test_c_more_than_half_elect_a_new_host():
    game, players = lobby(5)  # 3 of 5 is more than half
    target = players[3].id
    game.vote_host(players[1].id, target)
    game.vote_host(players[2].id, target)
    assert game.host_id == players[0].id
    assert game.snapshot_for(players[1].id)["host_votes"] == {target: 2}
    game.vote_host(players[4].id, target)
    assert game.host_id == target
    assert game.snapshot_for(players[1].id)["host_votes"] == {}


def test_c_half_is_not_enough_and_a_vote_can_be_taken_back():
    game, players = lobby(4)
    target = players[2].id
    game.vote_host(players[1].id, target)
    game.vote_host(players[2].id, target)  # voting for yourself is fine
    assert game.host_id == players[0].id  # 2 of 4 is not more than half
    game.vote_host(players[1].id, None)  # taken back
    assert game.snapshot_for(players[0].id)["host_votes"] == {target: 1}


def test_c_a_leaving_player_takes_their_vote_and_the_votes_for_them_along():
    game, players = lobby(5)
    game.vote_host(players[1].id, players[3].id)
    game.vote_host(players[3].id, players[4].id)
    game.leave(players[3].id)
    assert game.snapshot_for(players[0].id)["host_votes"] == {}


def test_c_host_votes_are_checked():
    game, players = lobby(4)
    with pytest.raises(GameError, match="already the host"):
        game.vote_host(players[1].id, players[0].id)
    with pytest.raises(GameError, match="Unknown target"):
        game.vote_host(players[1].id, "p999")
    with pytest.raises(GameError, match="Target must be a player id"):
        game.vote_host(players[1].id, 5)
    with pytest.raises(GameError, match="Unknown player"):
        game.vote_host("p999", players[1].id)
    game.start(players[0].id)
    with pytest.raises(GameError, match="only in the lobby"):
        game.vote_host(players[1].id, players[2].id)


def test_b_e_new_message_types_need_joining():
    for kind in ("kick", "leave", "vote_host"):
        assert parse_message(f'{{"type": "{kind}"}}', joined=True)["type"] == kind
        with pytest.raises(GameError, match="Join the game first"):
            parse_message(f'{{"type": "{kind}"}}', joined=False)


# --- D. a nickname in use is never taken over --------------------------------------------------


def test_d_a_taken_nickname_is_rejected_in_the_lobby():
    game, players = lobby()
    with pytest.raises(GameError, match="Nickname is already taken"):
        game.join("p2")
    assert len(game.players) == 4


def test_d_a_connected_players_nickname_is_rejected_during_a_round():
    game, players = started(5)
    role = players[2].role
    with pytest.raises(GameError, match="Nickname is already taken"):
        game.join("P2")
    assert players[2].role == role and not players[2].away


def test_d_only_a_player_who_lost_the_connection_can_come_back():
    game, players = started(5)
    game.disconnect(players[2].id)
    assert game.join("p2") is players[2] and not players[2].away


def test_d_a_second_connection_cannot_take_a_name_over_the_websocket():
    with TestClient(app) as client, client.websocket_connect("/ws") as first:
        first.send_json({"type": "join", "name": "Leonard"})
        receive_until(first, lambda m: m["type"] == "welcome")
        with client.websocket_connect("/ws") as second:
            second.send_json({"type": "join", "name": "leonard"})
            error = receive_until(second, lambda m: m["type"] in ("welcome", "error"))
            assert error == {"type": "error", "reason": "Nickname is already taken"}
        state = receive_until(first, lambda m: m["type"] == "state")
        assert [p["name"] for p in state["players"]] == ["Leonard"]


# --- E. leaving and kicking over the WebSocket -----------------------------------------------


def test_e_leave_removes_the_player_and_says_so():
    with TestClient(app) as client, client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        a.send_json({"type": "join", "name": "Ana"})
        receive_until(a, lambda m: m["type"] == "welcome")
        b.send_json({"type": "join", "name": "Ben"})
        receive_until(b, lambda m: m["type"] == "welcome")
        b.send_json({"type": "leave"})
        assert receive_until(b, lambda m: m["type"] == "left") == {"type": "left"}
        receive_until(a, lambda m: m["type"] == "state" and len(m["players"]) == 1)


def test_e_kick_tells_the_removed_player():
    with TestClient(app) as client, client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        a.send_json({"type": "join", "name": "Ana"})
        receive_until(a, lambda m: m["type"] == "welcome")
        b.send_json({"type": "join", "name": "Ben"})
        ben = receive_until(b, lambda m: m["type"] == "welcome")["id"]
        a.send_json({"type": "kick", "target": ben})
        assert receive_until(b, lambda m: m["type"] == "kicked") == {"type": "kicked"}
        receive_until(a, lambda m: m["type"] == "state" and len(m["players"]) == 1)


# --- F-I. the browser ----------------------------------------------------------------------------


def test_f_an_emergency_shows_a_big_arrow():
    js, render = read("main.js"), read("render.js")
    assert "makeEmergencyArrow" in render and "updateEmergencyArrow" in render
    assert "emergencyTarget(" in js


def test_g_ghosts_are_told_why_they_cannot_chat():
    assert "Ghosts cannot chat. You can still read along." in read("main.js")


def test_h_expel_them_all():
    html, js = read("index.html"), read("main.js")
    assert "fail them all" not in html.lower() and "fail them all" not in js.lower()
    assert "expel them all" in html.lower() and "expel them all" in js.lower()


def test_i_phone_layout_and_new_buttons():
    html, js, css = read("index.html"), read("main.js"), read("style.css")
    assert "-webkit-touch-callout: none" in css and "user-select: none" in css
    assert "(pointer: coarse)" in css
    assert 'id="todo-toggle"' in html and 'id="roster-toggle"' in html
    assert 'id="leave-button"' in html and 'send({ type: "leave" })' in js
    assert 'type: "vote_host"' in js
    assert 'type: "kick"' in js

