"""Tests for spec 033: examiners can fix the lights too."""

import random
from pathlib import Path

import pytest

from server.game import FIX_TICKS, SABOTAGE_COOLDOWN_TICKS, Game, GameError

TILE = 32
# One open hall with the light switch on tile (20, 10), like spec 008's LIGHT_MAP.
LIGHT_MAP = {
    "tile_size": TILE,
    "grid": ["#" * 30] + ["#" + "." * 28 + "#"] * 14 + ["#" * 30],
    "areas": [{"name": "Hall", "x": 1, "y": 1, "w": 28, "h": 14, "color": "#3f6e8c"}],
    "spawns": [[2, 2]],
    "light_switch": [20, 10],
    "tasks": [{"id": "desk", "title": "Desk", "area": "Hall", "x": 21, "y": 10, "seconds": 5, "joke": "Done"}],
}


def go_to_switch(player):
    player.x, player.y = 20.5 * TILE, 10.5 * TILE

WEB = Path(__file__).resolve().parent.parent / "web"


def dark_round(count=5, seed=0):
    game = Game(LIGHT_MAP, rng=random.Random(seed))
    players = [game.join(f"P{i}") for i in range(count)]
    game.start(players[0].id)
    examiner = next(p for p in players if p.role == "examiner")
    for _ in range(SABOTAGE_COOLDOWN_TICKS):
        game.step()
    game.sabotage(examiner.id)
    return game, examiner, [p for p in players if p.role == "student"]


def test_an_examiner_can_fix_the_lights():
    game, examiner, _ = dark_round()
    go_to_switch(examiner)
    game.fix(examiner.id)
    for _ in range(FIX_TICKS):
        game.step()
    assert game.lights_on


def test_an_examiner_inside_a_vent_cannot_fix():
    game, examiner, _ = dark_round()
    go_to_switch(examiner)
    examiner.vent = "somewhere"
    with pytest.raises(GameError, match="Leave the vent first"):
        game.fix(examiner.id)
    assert examiner.fix_done_tick is None


def test_every_role_gets_fixing_while_playing():
    game, examiner, students = dark_round()
    for player in (examiner, *students):
        assert game.snapshot_for(player.id)["fixing"] is None
    go_to_switch(examiner)
    game.fix(examiner.id)
    assert game.snapshot_for(examiner.id)["fixing"]["seconds_left"] > 0


def test_the_client_lets_examiners_fix():
    script = (WEB / "main.js").read_text(encoding="utf-8")
    body = script[script.index("function canFix(") : script.index("\n}\n", script.index("function canFix("))]
    assert "isLivingStudent" not in body
    assert 'state.role !== "student" || !welcome.map.light_switch' not in script
