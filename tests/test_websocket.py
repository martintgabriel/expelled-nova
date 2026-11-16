"""End-to-end tests over the real WebSocket endpoint (server/main.py)."""

import json

from fastapi.testclient import TestClient

from server.game import RATE_LIMIT, TICK_RATE
from server.main import app

# How many server messages to read before giving up (2 seconds of state updates).
TWO_SECONDS = 2 * TICK_RATE


def receive_until(ws, predicate, limit=TWO_SECONDS):
    """Read messages until one matches, or fail after `limit` messages."""
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def join(ws, name):
    ws.send_json({"type": "join", "name": name})
    return receive_until(ws, lambda m: m["type"] in ("welcome", "error"))


def find_player(state, player_id):
    return next((p for p in state["players"] if p["id"] == player_id), None)


def test_client_b_sees_client_a_move():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
            welcome_a = join(a, "Alice")
            assert welcome_a["type"] == "welcome"
            assert "grid" in welcome_a["map"]
            a_id = welcome_a["id"]
            assert join(b, "Bob")["type"] == "welcome"

            first = receive_until(b, lambda m: m["type"] == "state" and find_player(m, a_id))
            start_x = find_player(first, a_id)["x"]

            a.send_json({"type": "input", "dx": 1, "dy": 0})
            receive_until(
                b,
                lambda m: m["type"] == "state"
                and find_player(m, a_id)
                and find_player(m, a_id)["x"] > start_x,
            )


def test_disconnected_player_disappears_for_others():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as b:
            with client.websocket_connect("/ws") as a:
                a_id = join(a, "Alice")["id"]
                join(b, "Bob")
                receive_until(b, lambda m: m["type"] == "state" and find_player(m, a_id))
            receive_until(b, lambda m: m["type"] == "state" and not find_player(m, a_id))


def test_invalid_messages_get_an_error_and_connection_stays_usable():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "input", "dx": 1, "dy": 0})
            assert "Join" in ws.receive_json()["reason"]

            ws.send_text("not json")
            assert ws.receive_json()["type"] == "error"

            reply = join(ws, "")
            assert reply["type"] == "error"
            assert reply["reason"]

            assert join(ws, "Carol")["type"] == "welcome"


def test_duplicate_nickname_over_websocket_is_rejected():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
            assert join(a, "Dana")["type"] == "welcome"
            reply = join(b, "dana")
            assert reply["type"] == "error"
            assert "taken" in reply["reason"]


def test_flooding_messages_are_rate_limited():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            assert join(ws, "Eve")["type"] == "welcome"
            for _ in range(RATE_LIMIT + 10):
                ws.send_json({"type": "input", "dx": 0, "dy": 0})
            error = receive_until(ws, lambda m: m["type"] == "error", limit=200)
            assert "Too many messages" in error["reason"]


def test_page_and_health_check_are_served():
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "vendor/phaser.min.js" in page.text
        assert client.get("/vendor/phaser.min.js").status_code == 200
        assert client.get("/healthz").json() == {"status": "ok"}


# --- Lobby, host and secret roles (spec 002) ----------------------------------


def test_host_starts_and_each_client_gets_only_its_own_role():
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            clients = [a, b, c, d]
            ids = [join(ws, name)["id"] for ws, name in zip(clients, ["Hana", "Ben", "Cleo", "Dev"])]

            # In the lobby everyone sees the first player as host and has no role yet.
            for ws in clients:
                state = receive_until(ws, lambda m: m["type"] == "state" and len(m["players"]) == 4)
                assert state["phase"] == "lobby"
                assert state["host"] == ids[0]
                assert state["role"] is None

            a.send_json({"type": "start"})

            roles = []
            for ws in clients:
                state = receive_until(
                    ws, lambda m: m["type"] == "state" and m["phase"] == "playing", limit=100
                )
                assert state["role"] in ("student", "examiner")
                assert all(set(p) == {"id", "name", "x", "y"} for p in state["players"])
                if state["role"] == "student":
                    assert "fellow_examiners" not in state
                    assert "examiner" not in json.dumps(state)
                else:
                    assert state["fellow_examiners"] == []
                roles.append(state["role"])
            assert roles.count("examiner") == 1

            with client.websocket_connect("/ws") as late:
                reply = join(late, "Late")
                assert reply["type"] == "error"
                assert "already running" in reply["reason"]


def test_start_is_rejected_from_non_host_and_with_too_few_players():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
            a_id = join(a, "Ines")["id"]
            assert join(b, "Jon")["type"] == "welcome"

            b.send_json({"type": "start"})
            error = receive_until(b, lambda m: m["type"] == "error")
            assert "Only the host" in error["reason"]

            a.send_json({"type": "start"})
            error = receive_until(a, lambda m: m["type"] == "error")
            assert "at least 4 players" in error["reason"]

            state = receive_until(a, lambda m: m["type"] == "state")
            assert state["phase"] == "lobby"
            assert state["host"] == a_id
