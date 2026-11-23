"""Tests for spec 036: never stuck, smooth stopping, chat feedback and campus polish."""

import random
import re
from pathlib import Path

import pytest

from server.game import (
    ENDED,
    LOBBY,
    MEETING,
    PLAYING,
    SETTLE_DISTANCE,
    STEP,
    Game,
    GameError,
    load_map,
    parse_message,
)

WEB = Path(__file__).resolve().parent.parent / "web"
TILE = 32


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def started(count=5, seed=0):
    game = Game(load_map(), rng=random.Random(seed))
    players = [game.join(f"P{i}") for i in range(count)]
    game.start(players[0].id)
    game.guard = None
    return game, players


# --- A. nobody is ever stuck -----------------------------------------------------------


def test_a_lost_player_stays_away_and_comes_back_with_the_same_nickname():
    game, players = started()
    lost = players[2]
    role = lost.role
    game.disconnect(lost.id)
    assert lost.id in game.players and lost.away
    assert game.snapshot_for(players[0].id)["away"] == [lost.id]
    back = game.join("p2")  # any capitals
    assert back is lost and back.role == role and not back.away
    assert game.snapshot_for(players[0].id)["away"] == []


def test_a_new_nickname_joins_a_running_round_as_a_ghost():
    game, players = started()
    late = game.join("Stranger", 2)
    assert late.id in game.players and not late.alive and late.role == "student"
    assert late.tasks == [] and late.hat == 2
    assert game.phase == PLAYING  # the round goes on, nothing is decided by the ghost
    game.end_round(late.id)  # and from there they can end it like everyone
    assert game.phase == LOBBY and game.players[late.id].alive


def test_no_late_ghost_when_the_game_is_full_or_in_a_meeting():
    game, _ = started(count=10)
    with pytest.raises(GameError, match="Game is full"):
        game.join("Eleven")
    game, players = started()
    from server.game import Meeting

    game.phase = MEETING
    game.meeting = Meeting(reason="meeting", called_by=players[1].id, voting_ends=game.tick + 1000)
    with pytest.raises(GameError, match="meeting is running"):
        game.join("Stranger")


def test_in_the_lobby_a_lost_player_simply_leaves():
    game = Game(load_map())
    a, b = game.join("Ana"), game.join("Ben")
    game.disconnect(b.id)
    assert b.id not in game.players and a.id in game.players


def test_the_host_role_moves_at_once_when_the_host_is_gone():
    game, players = started()
    assert game.host_id == players[0].id
    game.disconnect(players[0].id)
    assert game.host_id == players[1].id


def test_nobody_connected_opens_an_empty_lobby():
    game, players = started()
    for p in players:
        game.disconnect(p.id)
    assert game.phase == LOBBY and not game.players and game.host_id is None
    assert game.join("Ana").id in game.players


@pytest.mark.parametrize("phase", [PLAYING, ENDED])
def test_any_player_ends_the_round_and_away_players_leave(phase):
    game, players = started()
    game.disconnect(players[0].id)  # the host
    if phase == ENDED:
        game.phase = ENDED
    game.end_round(players[3].id)
    assert game.phase == LOBBY
    assert players[0].id not in game.players
    assert game.host_id == players[1].id
    assert all(p.role is None for p in game.players.values())


def test_ending_needs_a_running_round_and_a_player_in_the_game():
    game, players = started()
    with pytest.raises(GameError, match="Unknown player"):
        game.end_round(None)
    game.end_round(players[1].id)
    with pytest.raises(GameError, match="No round is running"):
        game.end_round(players[1].id)
    with pytest.raises(GameError, match="Join the game first"):
        parse_message('{"type": "end_round"}', joined=False)


def test_the_server_keeps_a_lost_player_and_replaces_old_connections():
    main = (Path(__file__).resolve().parent.parent / "server" / "main.py").read_text(encoding="utf-8")
    assert "game.disconnect(player_id)" in main and "game.leave(player_id)" not in main
    assert "connections.get(player_id) is ws" in main
    assert 'game.end_round(player_id)' in main


def test_the_browser_offers_ending_and_coming_back():
    html, js = read("index.html"), read("main.js")
    assert 'id="end-round-button"' in html
    assert 'send({ type: "end_round" })' in js
    assert "NICKNAME_KEY" in js and "localStorage.setItem(NICKNAME_KEY" in js
    assert "Waiting for the host to start a new round" not in js


# --- B. stopping does not jump back ---------------------------------------------------


def test_a_stop_takes_the_browsers_spot_when_it_is_close():
    game, players = started()
    p = players[1]
    x, y = p.x, p.y
    game.set_input(p.id, {"type": "input", "dx": 0, "dy": 0, "at": {"x": x + STEP * 1.5, "y": y}})
    assert (p.x, p.y) == (x + STEP * 1.5, y)


def test_a_stop_too_far_away_keeps_the_servers_spot():
    game, players = started()
    p = players[1]
    x, y = p.x, p.y
    game.set_input(p.id, {"type": "input", "dx": 0, "dy": 0, "at": {"x": x + SETTLE_DISTANCE + 1, "y": y}})
    assert (p.x, p.y) == (x, y)


def test_a_stop_never_goes_through_a_wall():
    game, players = started()
    p = players[1]
    # Stand right next to a wall, then ask for a spot behind it.
    while not game.blocked(p.x - 1, p.y, walls=True):
        p.x -= 1
    x = p.x
    game.set_input(p.id, {"type": "input", "dx": 0, "dy": 0, "at": {"x": x - STEP, "y": p.y}})
    assert p.x == x


@pytest.mark.parametrize("message", [
    {"type": "input", "dx": 1, "dy": 0, "at": {"x": 1, "y": 1}},
    {"type": "input", "dx": 0, "dy": 0, "at": {"x": "1", "y": 1}},
    {"type": "input", "dx": 0, "dy": 0, "at": {"x": True, "y": 1}},
    {"type": "input", "dx": 0, "dy": 0, "at": [1, 1]},
])
def test_a_bad_at_is_rejected(message):
    game, players = started()
    with pytest.raises(GameError):
        game.set_input(players[1].id, message)


def test_the_browser_sends_its_spot_with_a_stop():
    assert "at: { x: Math.round(this.predicted.x" in read("main.js")


# --- C. chat ---------------------------------------------------------------------------


def test_a_player_who_is_not_the_host_and_has_voted_can_chat():
    game, players = started()
    from server.game import Meeting

    game.phase = MEETING
    game.meeting = Meeting(reason="meeting", called_by=players[1].id, voting_ends=game.tick + 1000)
    writer = players[3]
    game.meeting.votes[writer.id] = "skip"
    game.chat(writer.id, "It was P1")
    assert game.meeting.chat[-1] == {"from": writer.id, "text": "It was P1"}


def test_a_rejected_message_is_explained_under_the_input():
    html, js = read("index.html"), read("main.js")
    assert 'id="chat-status"' in html
    assert "setText(ui.chatStatus, message.reason)" in js


# --- D. campus polish ------------------------------------------------------------------


def stations(campus):
    for task in campus["tasks"]:
        yield from task.get("steps", [task])


def test_every_task_is_drawn_as_an_object():
    render = read("render.js")
    block = render[render.index("const TASK_OBJECTS = {") : render.index("};", render.index("const TASK_OBJECTS = {"))]
    keys = set(re.findall(r"^\s+(\w+): draw", block, re.M))
    assert {s["minigame"] for s in stations(load_map())} <= keys


def test_no_task_lies_on_a_name():
    campus = load_map()
    names = [(l["x"], l["y"] + 0.3, len(l["text"])) for l in campus["labels"] if not l.get("only_on_map")]
    for area in campus["areas"]:
        x, y = area.get("name_at") or (area["x"] + area["w"] / 2, area["y"] + area["h"] - 0.8)
        names.append((x, y + 0.3, len(area["name"])))
    for s in stations(campus):
        cx, cy = s["x"] + 0.5, s["y"] + 0.5
        for x, y, length in names:
            assert not (abs(cx - x) < length * 0.3 and abs(cy - y) < 0.9), (s, x, y)


def test_the_hedge_over_lecture_hall_d_is_continuous():
    campus = load_map()
    roofs = [d for d in campus["decor"] if d["kind"] == "greenroof" and d["y"] == 25]
    assert any(d["x"] <= 7 and d["x"] + d["w"] >= 23 for d in roofs)


def test_the_upper_courtyard_reaches_down_to_the_lower_one():
    campus = load_map()
    upper = next(a for a in campus["areas"] if a["name"] == "Upper Courtyard")
    assert upper["extra"] == [{"x": 7, "y": 17, "w": 9, "h": 5}]
    game = Game(campus)
    assert game.area_at(10 * TILE, 19 * TILE) == "Upper Courtyard"
    assert game.area_at(10 * TILE, 23 * TILE) == "Lower Courtyard"
    assert "area.extra" in read("campusmap.js") and "inArea" in read("render.js")


def test_the_nova_sign_looks_real_and_covers_nothing():
    campus = load_map()
    x, y = campus["nova_sign"]
    things = [(d["x"] + 0.5, d["y"] + 0.5) for d in campus["decor"] if d["kind"] == "tree"]
    things += [(s["x"] + 0.5, s["y"] + 0.5) for s in stations(campus)]
    for tx, ty in things:
        assert not (abs(tx - x) < 2.5 and abs(ty - y) < 1.3), (tx, ty)
    render = read("render.js")
    sign = render[render.index("function makeNovaSign") : render.index("function makeSabotagePlaces")]
    assert "map.nova_sign" in sign and "#0b3d91" not in sign and "#ffffff" in sign


def test_poke_house_and_the_cut_are_two_food_counters():
    campus = load_map()
    texts = {l["text"] for l in campus["labels"]}
    assert "Poke House" in texts and "Pokehaus" not in texts and "The Cut" in texts
    kinds = {d["kind"] for d in campus["decor"] if 32 <= d["x"] <= 42 and d["y"] == 9}
    assert {"pokecounter", "pizzacounter"} <= kinds and "shopshelf" not in kinds
    assert 'kind === "pokecounter"' in read("render.js")
