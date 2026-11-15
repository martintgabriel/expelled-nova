"""End-to-end tests over the real WebSocket endpoint (server/main.py)."""

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
