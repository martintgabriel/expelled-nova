"""Tests for spec 029: the chat in a meeting."""

import json
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import game as rules
from server.game import CHAT_COOLDOWN_TICKS, Game, GameError, parse_message
from server.main import app

TILE = 32
HALL = {
    "tile_size": TILE,
    "grid": ["#" * 30] + ["#" + "." * 28 + "#"] * 14 + ["#" * 30],
    "areas": [],
    "spawns": [[2, 2]],
}
WEB = Path(__file__).resolve().parent.parent / "web"


def meeting(count=5, seed=0):
    game = Game(HALL, rng=random.Random(seed))
    players = [game.join(f"P{i}") for i in range(count)]
    game.start(players[0].id)
    game.call_meeting(players[0].id)
    return game, players


def wait(game, ticks):
    for _ in range(ticks):
        game.step()


def test_a_living_player_can_chat_and_everyone_sees_it():
    game, players = meeting()
    game.chat(players[1].id, "  I saw P3 near the library  ")
    for player in players:
        assert game.snapshot_for(player.id)["chat"] == [{"from": players[1].id, "text": "I saw P3 near the library"}]


def test_messages_keep_their_order():
    game, players = meeting()
    game.chat(players[1].id, "one")
    game.chat(players[2].id, "two")
    texts = [m["text"] for m in game.snapshot_for(players[0].id)["chat"]]
    assert texts == ["one", "two"]


def test_chat_is_a_known_message_type():
    assert parse_message(json.dumps({"type": "chat", "text": "hi"}), joined=True)["text"] == "hi"


@pytest.mark.parametrize("text", ["", "   ", "x" * 81, "line\nbreak", "tab\there", "\x07", 5, None, ["hi"], {"t": 1}])
def test_invalid_text_is_rejected(text):
    game, players = meeting()
    with pytest.raises(GameError):
        game.chat(players[1].id, text)
    assert game.snapshot_for(players[0].id)["chat"] == []


def test_eighty_characters_are_fine():
    game, players = meeting()
    game.chat(players[1].id, "x" * 80)
    assert len(game.snapshot_for(players[0].id)["chat"][0]["text"]) == 80


def test_too_fast_is_rejected():
    game, players = meeting()
    game.chat(players[1].id, "first")
    with pytest.raises(GameError, match="Slow down"):
        game.chat(players[1].id, "second")
    wait(game, CHAT_COOLDOWN_TICKS)
    game.chat(players[1].id, "second")
    assert len(game.snapshot_for(players[0].id)["chat"]) == 2


def test_ghosts_cannot_chat():
    game, players = meeting()
    players[2].alive = False
    with pytest.raises(GameError, match="Ghosts cannot chat"):
        game.chat(players[2].id, "boo")


def test_no_chat_while_playing_or_in_the_lobby():
    game = Game(HALL, rng=random.Random(0))
    players = [game.join(f"P{i}") for i in range(4)]
    with pytest.raises(GameError, match="only in a meeting"):
        game.chat(players[0].id, "hi")
    game.start(players[0].id)
    with pytest.raises(GameError, match="only in a meeting"):
        game.chat(players[0].id, "hi")
    assert "chat" not in game.snapshot_for(players[0].id)


def test_no_chat_once_the_result_shows():
    game, players = meeting()
    for player in players:
        game.vote(player.id, "skip")
    game.step()
    with pytest.raises(GameError, match="Voting is over"):
        game.chat(players[1].id, "gg")


def test_only_the_last_thirty_messages_are_kept():
    game, players = meeting(count=10)
    for i in range(35):
        game.chat(players[i % 10].id, f"m{i}")
        if i % 10 == 9:
            wait(game, CHAT_COOLDOWN_TICKS)
    chat = game.snapshot_for(players[0].id)["chat"]
    assert len(chat) == rules.CHAT_KEEP == 30
    assert chat[0]["text"] == "m5" and chat[-1]["text"] == "m34"


def test_the_next_meeting_starts_with_an_empty_chat():
    game, players = meeting()
    game.chat(players[1].id, "hello")
    for player in players:
        game.vote(player.id, "skip")
    wait(game, rules.RESULT_TICKS + 2)
    assert game.phase == "playing"
    game.call_meeting(players[1].id)
    assert game.snapshot_for(players[0].id)["chat"] == []


def receive_until(ws, predicate, limit=300):
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def test_chat_over_the_websocket(fresh_game):
    fresh_game.rng = random.Random(0)
    with TestClient(app) as client:
        sockets = [client.websocket_connect("/ws") for _ in range(4)]
        clients = [s.__enter__() for s in sockets]
        try:
            ids = []
            for ws, name in zip(clients, ["Ada", "Bo", "Cy", "Di"]):
                ws.send_json({"type": "join", "name": name})
                ids.append(receive_until(ws, lambda m: m["type"] == "welcome")["id"])
            fresh_game.start(ids[0])
            player = fresh_game.players[ids[0]]
            table = fresh_game.campus.get("meeting_point")
            if table:
                player.x, player.y = (table[0] + 0.5) * fresh_game.tile, (table[1] + 1.5) * fresh_game.tile
            fresh_game.call_meeting(ids[0])
            clients[0].send_json({"type": "chat", "text": "<b>hi</b>"})
            state = receive_until(clients[1], lambda m: m["type"] == "state" and m.get("chat"))
            assert state["chat"] == [{"from": ids[0], "text": "<b>hi</b>"}]  # kept as plain text
        finally:
            for s in sockets:
                s.__exit__(None, None, None)


def test_the_client_shows_the_chat_as_plain_text_and_frees_the_keys_while_typing():
    script = (WEB / "main.js").read_text(encoding="utf-8")
    body = script[script.index("function renderMeetingChat(") : script.index("\n}\n", script.index("function renderMeetingChat("))]
    assert "innerHTML" not in body
    assert "textContent" in body
    assert 'send({ type: "chat", text' in script
    assert "disableGlobalCapture" in script and "enableGlobalCapture" in script
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="chat-input"' in page and 'maxlength="80"' in page
