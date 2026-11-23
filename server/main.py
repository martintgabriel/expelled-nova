"""Network layer: WebSocket connections, the 20 Hz game loop and the static web page.

All rules live in server/game.py. This file only receives messages, hands them to the
game and sends results back.
"""

import asyncio
import contextlib
import io
import json
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

import segno
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from server.game import (
    CORNER_SLIDE,
    EXPEL_COOLDOWN,
    EXPEL_RANGE,
    GUARD_CONE_DEGREES,
    LOBBY,
    MEETING_RANGE,
    MEETING_TABLE_RADIUS,
    PLAYER_HALF,
    REPORT_RANGE,
    SABOTAGE_COOLDOWN,
    SPEED,
    STEP,
    SWITCH_RANGE,
    TASK_RANGE,
    TICK_RATE,
    VENT_COOLDOWN,
    Game,
    GameError,
    RateLimiter,
    load_map,
    parse_message,
    validate_nickname,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# The one shared game, kept in memory (a server restart ends it: accepted limit).
game = Game(load_map())
# Joined players' connections, by player id. Only these receive state updates.
connections: dict[str, WebSocket] = {}
# Spec 038: at most this many WebSocket connections at once (joined or not): 10 players
# plus room for phones that reconnect. More are refused before they are accepted.
MAX_CONNECTIONS = 30
open_connections = 0
# Spec 038: player id -> the secret that player's browser needs to come back after a lost
# connection. game.py decides who may come back (only a player who is away); this checks
# that it is the same browser, not just someone who knows the nickname.
rejoin_tokens: dict[str, str] = {}


# After a pause longer than this many ticks, the loop does not run the missed ticks in a burst.
MAX_CATCH_UP_TICKS = 5
# Spec 038 (M5): how long one state may take to send, in seconds. A send only waits when the
# browser is already about 2 s of states behind; one that takes longer is treated as gone.
SEND_TIMEOUT = 1.0


def next_tick_at(scheduled, now):
    """The time at which the next tick is due.

    One tick length after the time the previous tick was scheduled, not after the time it
    really ran. A tick that ran late is followed by a shorter wait, so the game keeps exactly
    TICK_RATE ticks per second and players move at exactly SPEED, the speed the browser
    predicts with (spec 008, part 1). If the loop is more than MAX_CATCH_UP_TICKS behind
    (the server was paused), a new timetable starts at `now`.
    """
    due = scheduled + 1 / TICK_RATE
    if now - due > MAX_CATCH_UP_TICKS / TICK_RATE:
        return now
    return due


async def game_loop():
    """Move everyone one tick, then send each joined player their own snapshot.

    Each player gets snapshot_for(their id), so a browser only ever receives its own role.
    """
    loop = asyncio.get_running_loop()
    due = loop.time()
    while True:
        game.step()
        for player_id, ws in list(connections.items()):
            try:
                text = json.dumps(game.snapshot_for(player_id))
                await asyncio.wait_for(ws.send_text(text), SEND_TIMEOUT)
            except TimeoutError:
                drop_connection(player_id, ws)  # spec 038: never wait for one browser
            except Exception:
                pass  # a client that just closed or left: its own handler removes it
        due = next_tick_at(due, loop.time())
        await asyncio.sleep(max(0.0, due - loop.time()))


def drop_connection(player_id, ws):
    """Spec 038 (M5): a browser that stopped reading is treated as disconnected, exactly as
    if it had closed. Closing it runs in the background, so nothing waits for it."""
    if connections.get(player_id) is ws:
        connections.pop(player_id)
        game.disconnect(player_id)
    asyncio.get_running_loop().create_task(close_quietly(ws))


async def close_quietly(ws):
    with contextlib.suppress(Exception):
        await asyncio.wait_for(ws.close(), SEND_TIMEOUT)


@contextlib.asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(game_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


# Spec 038: no automatic API pages (/docs, /redoc, /openapi.json): the game needs none.
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

# Spec 038: sent with every HTTP answer. The policy lets the page load only its own scripts,
# styles and images (plus data: images, which Phaser uses for its built-in textures) and
# connect only to its own server; no inline code, no plugins, no framing by other sites.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; "
        "object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


def invite_url(env_url, base_url):
    """The URL the QR code points to, ending in exactly one "/".

    `env_url` is RENDER_EXTERNAL_URL (set by Render for every web service); an unset or
    empty value falls back to `base_url`, the base URL of the current request (e.g. the
    laptop's address on the local Wi-Fi).
    """
    url = env_url or base_url
    return url if url.endswith("/") else url + "/"


@app.get("/qr.svg")
def qr_svg(request: Request):
    """The invite URL as a QR code: black on white, with the standard quiet zone.

    Takes no input: query parameters are ignored, so nobody can make the game show a
    QR code for another site.
    """
    url = invite_url(os.environ.get("RENDER_EXTERNAL_URL"), str(request.base_url))
    buffer = io.BytesIO()
    segno.make(url, error="m").save(buffer, kind="svg", border=4, dark="#000", light="#fff")
    return Response(content=buffer.getvalue(), media_type="image/svg+xml")


@app.get("/taken-colors")
def taken_colors(response: Response):
    """Spec 028: the colours players already have, for the colour picker on the join screen.

    Takes no input and changes nothing. The answer is {"taken": {"<colour>": "<nickname>"}}:
    only what the lobby shows anyway. Joining with a taken colour is still rejected by
    Game.join; this only lets the page show it before someone tries. "no-store": the page
    asks again every moment, and an old answer must never be shown.
    """
    response.headers["Cache-Control"] = "no-store"
    return {"taken": game.taken_colors()}


def welcome_message(player):
    """The first message a joined browser gets: its own id, the map and every number it
    needs to predict its own movement and draw ranges and cooldown rings."""
    return {
        "type": "welcome",
        "id": player.id,
        "map": game.campus,
        "sight_grid": game.sight,
        "speed": SPEED,
        "tick_rate": TICK_RATE,
        "step": STEP,
        "player_half": PLAYER_HALF,
        "corner_slide": CORNER_SLIDE,
        "expel_range": EXPEL_RANGE,
        "report_range": REPORT_RANGE,
        "meeting_range": MEETING_RANGE,
        "meeting_table_radius": MEETING_TABLE_RADIUS,
        "task_range": TASK_RANGE,
        "switch_range": SWITCH_RANGE,
        "lights_out_radius": game.lights_out_radius,
        "vision_radius": game.vision_radius,
        "guard_vision_radius": game.guard_vision_radius,
        "guard_cone_degrees": GUARD_CONE_DEGREES,
        # Spec 038: the full cooldowns in seconds, so the browser's
        # cooldown rings never repeat a number of their own.
        "cooldowns": {
            "expel": EXPEL_COOLDOWN,
            "vent": VENT_COOLDOWN,
            "sabotage": SABOTAGE_COOLDOWN,
        },
        "rejoin_token": rejoin_tokens[player.id],  # spec 038: kept by the browser
    }


def check_rejoin_token(message):
    """Spec 038: during a round, a join with the nickname of a player who is away takes that
    player over only with the token from their own welcome. Raises GameError otherwise, with
    the same reason as for any taken nickname."""
    if game.phase == LOBBY:
        return
    name = validate_nickname(message.get("name"))
    player = next((p for p in game.players.values() if p.name.casefold() == name.casefold()), None)
    if player is None or not player.away:
        return  # a new nickname or a connected player: game.join decides
    token = message.get("rejoin_token")
    expected = rejoin_tokens.get(player.id, "")
    if not (isinstance(token, str) and token.isascii() and secrets.compare_digest(token, expected)):
        raise GameError("Nickname is already taken")


def give_rejoin_token(player_id):
    """A new player gets a new token; a player who comes back keeps theirs. Tokens of
    players who are gone are dropped."""
    for gone in [known for known in rejoin_tokens if known not in game.players]:
        del rejoin_tokens[gone]
    rejoin_tokens.setdefault(player_id, secrets.token_urlsafe(16))


def same_site(ws):
    """Spec 038: a browser always sends Origin; it must be this server's own address (so the
    page on localhost, on the Wi-Fi address and on Render, reached by link or QR code, all
    pass). No Origin at all is not a browser page (e.g. the tests) and is let through."""
    origin = ws.headers.get("origin")
    return origin is None or urlsplit(origin).netloc == ws.headers.get("host")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global open_connections
    if not same_site(ws):
        await ws.close(code=1008)  # policy violation: another site's page
        return
    if open_connections >= MAX_CONNECTIONS:
        await ws.close(code=1013)  # try again later
        return
    open_connections += 1
    try:
        await ws.accept()
        await play(ws)
    finally:
        open_connections -= 1


async def play(ws):
    """One browser's connection: receive, check and hand each message to the game."""
    limiter = RateLimiter()
    player_id = None
    try:
        while True:
            event = await ws.receive()
            if event["type"] == "websocket.disconnect":
                break
            if player_id is not None and connections.get(player_id) is not ws:
                break  # spec 038: dropped by the game loop or replaced: this connection is over
            try:
                if not limiter.allow(time.monotonic()):
                    raise GameError("Too many messages (max 30 per second)")
                message = parse_message(event.get("text"), joined=player_id is not None)
                if message["type"] == "join":
                    check_rejoin_token(message)  # spec 038
                    known = set(game.players)
                    player = game.join(
                        message.get("name"), message.get("hat", 0), message.get("color")
                    )
                    player_id = player.id
                    if player_id not in known:
                        rejoin_tokens.pop(player_id, None)  # a new player: never an old token
                    give_rejoin_token(player_id)
                    # Spec 036/037: enrolling again replaces an old connection of the same
                    # player (e.g. a phone that switched networks). It is closed only after
                    # this one is registered, so its ending never removes the player.
                    old = connections.get(player_id)
                    try:
                        await ws.send_json(welcome_message(player))
                    except Exception:
                        # Spec 038 (M3): the browser is gone before its welcome arrived. It is
                        # not registered yet, so `finally` below would not notice: without
                        # this the player would stay in the game for good.
                        game.disconnect(player_id)
                        player_id = None
                        raise
                    connections[player_id] = ws
                    if old is not None and old is not ws:
                        with contextlib.suppress(Exception):
                            await old.send_json({"type": "kicked", "reason": "You enrolled again somewhere else"})
                            await old.close()
                elif message["type"] == "kick":
                    target = message.get("target")
                    game.kick(player_id, target)  # spec 037: only the host
                    gone = connections.pop(target, None)
                    if gone is not None:
                        with contextlib.suppress(Exception):
                            await gone.send_json({"type": "kicked"})
                            await gone.close()
                elif message["type"] == "vote_host":
                    game.vote_host(player_id, message.get("target"))  # spec 037
                elif message["type"] == "leave":
                    game.quit(player_id)  # spec 037: "Leave the game"
                    connections.pop(player_id, None)
                    player_id = None
                    await ws.send_json({"type": "left"})
                elif message["type"] == "start":
                    game.start(player_id)
                elif message["type"] == "chat":
                    game.chat(player_id, message.get("text"))
                elif message["type"] == "settings":
                    game.set_settings(player_id, message)
                elif message["type"] == "make_host":
                    game.make_host(player_id, message.get("target"))
                elif message["type"] == "expel":
                    game.expel(player_id, message.get("target"))
                elif message["type"] == "report":
                    game.report(player_id, message.get("exam"))
                elif message["type"] == "meeting":
                    game.call_meeting(player_id)
                elif message["type"] == "sabotage":
                    game.sabotage(player_id, message.get("kind", "lights"))
                elif message["type"] == "fix":
                    game.fix(player_id)
                elif message["type"] == "vent_enter":
                    game.enter_vent(player_id)
                elif message["type"] == "vent_move":
                    game.move_vent(player_id, message.get("to"))
                elif message["type"] == "vent_leave":
                    game.leave_vent(player_id)
                elif message["type"] == "task":
                    game.task(player_id, message.get("task"))
                elif message["type"] == "task_input":
                    game.task_input(player_id, message.get("task"), message.get("value"))
                elif message["type"] == "task_cancel":
                    game.cancel_task(player_id, message.get("task"))
                elif message["type"] == "vote":
                    game.vote(player_id, message.get("target"))
                elif message["type"] == "restart":
                    game.restart(player_id)
                elif message["type"] == "end_round":
                    game.end_round(player_id)  # spec 036: any player
                else:
                    game.set_input(player_id, message)
            except GameError as error:
                await ws.send_json({"type": "error", "reason": str(error)})
    except WebSocketDisconnect:
        pass
    finally:
        # Spec 036: only if this connection is still the player's own (a rejoin may have
        # replaced it); during a round the player stays, marked away, and may come back.
        if player_id is not None and connections.get(player_id) is ws:
            connections.pop(player_id, None)
            game.disconnect(player_id)


class FreshStaticFiles(StaticFiles):
    """Static files that the browser must re-check on every load.

    The files in web/ belong together: a new main.js with an old, cached render.js breaks
    the page. "Cache-Control: no-cache" lets the browser keep its copy but makes it ask the
    server each time whether the file has changed; an unchanged file is answered with a
    short "304 Not Modified" (found while checking spec 008, part 4).
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Serve web/ at "/" (index.html, main.js, vendor/phaser.min.js). Mounted last so
# /ws and /healthz are matched first.
app.mount("/", FreshStaticFiles(directory=WEB_DIR, html=True), name="web")
