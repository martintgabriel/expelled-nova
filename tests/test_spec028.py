"""Tests for spec 028: GET /colors and the crossed-out swatches on the ID card."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from server.main import app

WEB = Path(__file__).resolve().parent.parent / "web"


def test_no_colour_is_taken_in_an_empty_game():
    with TestClient(app) as client:
        assert client.get("/colors").json() == {"taken": []}


def test_the_colours_of_the_players_in_the_game_are_taken(fresh_game):
    fresh_game.join("Ada", color=7)
    fresh_game.join("Bo")
    with TestClient(app) as client:
        assert client.get("/colors").json() == {"taken": [0, 7]}


def test_a_colour_is_free_again_when_its_player_leaves(fresh_game):
    ada = fresh_game.join("Ada", color=3)
    fresh_game.leave(ada.id)
    with TestClient(app) as client:
        assert client.get("/colors").json() == {"taken": []}


def test_the_answer_holds_only_numbers_and_ignores_parameters(fresh_game):
    fresh_game.join("Ada", color=2)
    with TestClient(app) as client:
        response = client.get("/colors?id=p1&name=Ada")
    assert response.json() == {"taken": [2]}
    assert "Ada" not in response.text and "p1" not in response.text


def test_the_id_card_asks_for_the_taken_colours_and_crosses_them_out():
    script = (WEB / "main.js").read_text(encoding="utf-8")
    assert 'fetch("/colors")' in script
    assert re.search(r"setInterval\(refreshTakenColors, 2000\)", script)
    assert ".swatch.taken" in (WEB / "style.css").read_text(encoding="utf-8")
