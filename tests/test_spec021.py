"""Tests for spec 021: hats and a colour of your own."""

import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import game as rules
from server.game import Game, GameError, load_map
from server.main import app

WEB = Path(__file__).resolve().parent.parent / "web"


def new_game():
    return Game(load_map(), rng=random.Random(0))


def test_there_are_ten_hats():
    assert rules.HAT_COUNT == 10


def test_joining_without_a_look_keeps_the_old_behaviour():
    game = new_game()
    a, b = game.join("Ada"), game.join("Bo")
    assert (a.hat, b.hat) == (0, 0)
    assert (a.color, b.color) == (0, 1)


def test_joining_with_a_hat_and_a_colour():
    game = new_game()
    player = game.join("Ada", hat=4, color=7)
    assert (player.hat, player.color) == (4, 7)


def test_any_colour_still_picks_the_lowest_free_one():
    game = new_game()
    game.join("Ada", color=0)
    assert game.join("Bo", hat=2, color=None).color == 1


def test_a_taken_colour_is_rejected_and_nobody_joins():
    game = new_game()
    game.join("Ada", color=5)
    with pytest.raises(GameError, match="Colour is already taken"):
        game.join("Bo", color=5)
    assert len(game.players) == 1


@pytest.mark.parametrize("hat", [-1, 10, "1", 1.0, True, None, [1]])
def test_an_invalid_hat_is_rejected(hat):
    game = new_game()
    with pytest.raises(GameError, match="Hat"):
        game.join("Ada", hat=hat)
    assert not game.players


@pytest.mark.parametrize("color", [-1, 10, "3", 3.0, False, [3]])
def test_an_invalid_colour_is_rejected(color):
    game = new_game()
    with pytest.raises(GameError, match="Colour"):
        game.join("Ada", color=color)
    assert not game.players


def test_every_snapshot_carries_the_hats_of_the_players_it_shows():
    game = new_game()
    players = [game.join(f"P{i}", hat=i) for i in range(4)]
    for player in players:
        assert game.snapshot_for(player.id)["hats"] == {p.id: p.hat for p in players}


def test_the_hats_follow_vision_like_the_colours():
    game = new_game()
    players = [game.join(f"P{i}", hat=i + 1) for i in range(4)]
    game.start(players[0].id)
    for player in players:
        state = game.snapshot_for(player.id)
        assert set(state["hats"]) == set(state["colors"])


def test_the_client_draws_the_hats_from_one_shared_file():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'src="hats.js"' in page
    assert page.index('src="hats.js"') < page.index('src="render.js"')
    hats = (WEB / "hats.js").read_text(encoding="utf-8")
    assert hats.count("name:") == 10
    assert "Hats.drawPhaser" in (WEB / "render.js").read_text(encoding="utf-8")
    assert "Hats.svg" in (WEB / "main.js").read_text(encoding="utf-8")


def receive_until(ws, predicate, limit=200):
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def test_join_with_a_look_over_the_websocket():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
            a.send_json({"type": "join", "name": "Ada", "hat": 3, "color": 6})
            welcome = receive_until(a, lambda m: m["type"] == "welcome")
            b.send_json({"type": "join", "name": "Bo", "color": 6})
            error = receive_until(b, lambda m: m["type"] == "error")
            assert error["reason"] == "Colour is already taken"
            state = receive_until(a, lambda m: m["type"] == "state")
            assert state["hats"][welcome["id"]] == 3
            assert state["colors"][welcome["id"]] == 6
