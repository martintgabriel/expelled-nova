"""Tests for spec 029: examiners recognise each other on the map and in meetings."""

import random
import re
from pathlib import Path

from server.game import Game, load_map

WEB = Path(__file__).resolve().parent.parent / "web"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def function_body(script, name):
    start = script.index(f"function {name}(")
    end = script.index("\n}\n", start)
    return script[start:end]


def test_only_examiners_learn_who_their_fellow_examiners_are():
    game = Game(load_map(), rng=random.Random(0))
    players = [game.join(f"P{i}") for i in range(8)]
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    assert len(examiners) == 2
    for player in players:
        state = game.snapshot_for(player.id)
        if player.role == "examiner":
            others = [e.id for e in examiners if e.id != player.id]
            assert state["fellow_examiners"] == others
        else:
            assert "fellow_examiners" not in state


def test_the_examiner_team_comes_only_from_the_own_role_and_fellows():
    body = function_body(read("main.js"), "examinerTeam")
    assert 'state.role !== "examiner"' in body
    assert "fellow_examiners" in body
    assert "roles" not in body  # never the end-of-round roles


def test_names_on_the_map_are_coloured_from_the_examiner_team():
    render = read("render.js")
    assert re.search(r'EXAMINER_NAME_COLOR = "#[0-9a-fA-F]{6}"', render)
    assert "function setNameColor(" in render
    assert re.search(r"return \{[^}]*setNameColor", render, re.S)
    script = read("main.js")
    assert "Render.setNameColor(" in script
    assert "examinerTeam(latestState)" in script


def test_meeting_cards_tag_the_examiner_team():
    script = read("main.js")
    assert script.count('tag("examiner", "examiner")') >= 2  # voting cards and result cards
