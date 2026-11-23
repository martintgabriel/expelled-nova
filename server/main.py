"""Network layer: WebSocket connections, the 20 Hz game loop and the static web page.

All rules live in server/game.py. This file only receives messages, hands them to the
game and sends results back.
"""

import asyncio
import contextlib
import io
import json
import os
import time
from pathlib import Path

import segno
from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from server.game import (
    CORNER_SLIDE,
    EXPEL_RANGE,
    MEETING_RANGE,
    MEETING_TABLE_RADIUS,
    PLAYER_HALF,
    REPORT_RANGE,
    SPEED,
    STEP,
    SWITCH_RANGE,
    TASK_RANGE,
    TICK_RATE,
    Game,
    GameError,
    RateLimiter,
    load_map,
    parse_message,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# The one shared game, kept in memory (a server restart ends it: accepted limit).
game = Game(load_map())
# Joined players' connections, by player id. Only these receive state updates.
connections: dict[str, WebSocket] = {}


# After a pause longer than this many ticks, the loop does not run the missed ticks in a burst.
MAX_CATCH_UP_TICKS = 5


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
            # A client that just closed (or has just left the game) raises here;
            # its own handler removes it.
            with contextlib.suppress(Exception):
                await ws.send_text(json.dumps(game.snapshot_for(player_id)))
        due = next_tick_at(due, loop.time())
        await asyncio.sleep(max(0.0, due - loop.time()))


@contextlib.asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(game_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(lifespan=lifespan)


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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    limiter = RateLimiter()
    player_id = None
    try:
        while True:
            event = await ws.receive()
            if event["type"] == "websocket.disconnect":
                break
            try:
                if not limiter.allow(time.monotonic()):
                    raise GameError("Too many messages (max 30 per second)")
                message = parse_message(event.get("text"), joined=player_id is not None)
                if message["type"] == "join":
                    player = game.join(
                        message.get("name"), message.get("hat", 0), message.get("color")
                    )
                    player_id = player.id
                    await ws.send_json(
                        {
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
                        }
                    )
                    connections[player_id] = ws
                elif message["type"] == "start":
                    game.start(player_id)
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
                    game.sabotage(player_id)
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
                else:
                    game.set_input(player_id, message)
            except GameError as error:
                await ws.send_json({"type": "error", "reason": str(error)})
    except WebSocketDisconnect:
        pass
    finally:
        if player_id is not None:
            connections.pop(player_id, None)
            game.leave(player_id)


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
