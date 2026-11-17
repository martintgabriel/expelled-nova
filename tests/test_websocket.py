"""End-to-end tests over the real WebSocket endpoint (server/main.py)."""

import contextlib
import io
import json

import segno
from fastapi.testclient import TestClient

from server.game import RATE_LIMIT, TICK_RATE
from server.main import app, invite_url

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


# --- Expel and ghosts (spec 003) ------------------------------------------------


def test_examiner_expels_over_websocket_and_only_the_ghost_sees_the_ghost(fresh_game):
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            clients = [a, b, c, d]
            ids = [join(ws, name)["id"] for ws, name in zip(clients, ["Kai", "Lia", "Max", "Noa"])]
            a.send_json({"type": "start"})
            roles = {}
            for ws, player_id in zip(clients, ids):
                state = receive_until(
                    ws, lambda m: m["type"] == "state" and m["phase"] == "playing", limit=100
                )
                roles[player_id] = state["role"]
            by_role = {"examiner": [], "student": []}
            for ws, player_id in zip(clients, ids):
                by_role[roles[player_id]].append((ws, player_id))
            ((examiner_ws, examiner_id),) = by_role["examiner"]
            (target_ws, target_id), (other_ws, _) = by_role["student"][:2]

            # Spawn points are 2 tiles apart: out of range, so rejected with a reason.
            examiner_ws.send_json({"type": "expel", "target": target_id})
            error = receive_until(examiner_ws, lambda m: m["type"] == "error", limit=100)
            assert "Too far away" in error["reason"]

            # Skip the 20 s wait: stand on the target's spot and end the cooldown now.
            examiner, target = fresh_game.players[examiner_id], fresh_game.players[target_id]
            examiner.x, examiner.y = target.x, target.y
            examiner.next_expel_tick = fresh_game.tick
            examiner_ws.send_json({"type": "expel", "target": target_id})

            ghost_view = receive_until(
                target_ws, lambda m: m["type"] == "state" and m["alive"] is False, limit=100
            )
            assert sorted(p["id"] for p in ghost_view["players"]) == sorted(ids)
            assert ghost_view["ghosts"] == [target_id]

            living_view = receive_until(
                other_ws, lambda m: m["type"] == "state" and m["failed_exams"], limit=100
            )
            assert living_view["alive"] is True
            assert target_id not in [p["id"] for p in living_view["players"]]


# --- Review follow-ups from spec 001: 11th client and invalid input ------------------


def test_eleventh_client_is_rejected_then_a_new_one_joins_after_a_player_leaves():
    with TestClient(app) as client:
        with contextlib.ExitStack() as stack:
            clients = [stack.enter_context(client.websocket_connect("/ws")) for _ in range(10)]
            for i, ws in enumerate(clients):
                assert join(ws, f"Player {i}")["type"] == "welcome"

            with client.websocket_connect("/ws") as eleventh:
                reply = join(eleventh, "Eleven")
                assert reply["type"] == "error"
                assert "Game is full (10 players)" in reply["reason"]

            clients[0].close()  # one player leaves, freeing a slot
            with client.websocket_connect("/ws") as newcomer:
                assert join(newcomer, "Newcomer")["type"] == "welcome"


def test_invalid_input_over_websocket_leaves_the_position_unchanged():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            player_id = join(ws, "Uma")["id"]
            first = receive_until(ws, lambda m: m["type"] == "state" and find_player(m, player_id))
            start = find_player(first, player_id)
            start_pos = (start["x"], start["y"])

            bad_inputs = [
                {"type": "input", "dx": 2, "dy": 0},
                {"type": "input", "dx": "1", "dy": 0},
                {"type": "input", "dx": True, "dy": 0},
                {"type": "input", "dx": 0},  # dy missing
            ]
            for bad in bad_inputs:
                ws.send_json(bad)
                error = receive_until(ws, lambda m: m["type"] == "error")
                assert "dx and dy" in error["reason"]
                state = receive_until(
                    ws, lambda m: m["type"] == "state" and find_player(m, player_id)
                )
                position = find_player(state, player_id)
                assert (position["x"], position["y"]) == start_pos

            ws.send_json({"type": "input", "dx": 1, "dy": 0})
            receive_until(
                ws,
                lambda m: m["type"] == "state"
                and find_player(m, player_id)
                and find_player(m, player_id)["x"] > start_pos[0],
            )


# --- Invite URL and QR-code join (spec 007) -----------------------------------------


def test_invite_url_uses_the_env_value_with_exactly_one_trailing_slash():
    assert invite_url("https://expelled-nova.onrender.com", "http://ignored/") == (
        "https://expelled-nova.onrender.com/"
    )
    assert invite_url("https://expelled-nova.onrender.com/", "http://ignored/") == (
        "https://expelled-nova.onrender.com/"
    )


def test_invite_url_falls_back_to_the_request_base_url_when_the_env_value_is_not_set():
    assert invite_url(None, "http://192.168.1.20:8000/") == "http://192.168.1.20:8000/"
    assert invite_url(None, "http://192.168.1.20:8000") == "http://192.168.1.20:8000/"


def test_invite_url_treats_an_empty_env_value_as_not_set():
    assert invite_url("", "http://192.168.1.20:8000/") == "http://192.168.1.20:8000/"


def qr_svg_bytes(url):
    """The exact SVG server/main.py's /qr.svg must produce for `url`."""
    buffer = io.BytesIO()
    segno.make(url, error="m").save(buffer, kind="svg", border=4, dark="#000", light="#fff")
    return buffer.getvalue()


def test_qr_svg_encodes_the_render_external_url(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://expelled-nova.onrender.com")
    with TestClient(app) as client:
        response = client.get("/qr.svg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.content == qr_svg_bytes("https://expelled-nova.onrender.com/")


def test_qr_svg_encodes_the_request_base_url_without_render_external_url(monkeypatch):
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    with TestClient(app) as client:
        response = client.get("/qr.svg")
    assert response.content == qr_svg_bytes("http://testserver/")


def test_qr_svg_ignores_a_url_query_parameter(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://expelled-nova.onrender.com")
    with TestClient(app) as client:
        response = client.get("/qr.svg", params={"url": "https://evil.example"})
    assert response.content == qr_svg_bytes("https://expelled-nova.onrender.com/")


def test_qr_svg_rejects_post():
    with TestClient(app) as client:
        assert client.post("/qr.svg").status_code == 405


def test_controls_js_is_served_and_loaded_before_main_js():
    with TestClient(app) as client:
        assert client.get("/controls.js").status_code == 200
        page = client.get("/").text
        controls = page.index('src="controls.js"')
        main = page.index('src="main.js"')
        assert controls < main


def test_page_contains_both_movement_hints():
    with TestClient(app) as client:
        page = client.get("/").text
    assert "Drag the joystick to move" in page
    assert "WASD / arrow keys to move" in page
