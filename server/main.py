"""Network layer: WebSocket connections, the 20 Hz game loop and the static web page.

All rules live in server/game.py. This file only receives messages, hands them to the
game and sends results back.
"""

import asyncio
import contextlib
import json
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from server.game import (
    PLAYER_HALF,
    SPEED,
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


async def game_loop():
    """Move everyone one tick, then send each joined player their own snapshot.

    Each player gets snapshot_for(their id), so a browser only ever receives its own role.
    """
    loop = asyncio.get_running_loop()
    while True:
        started = loop.time()
        game.step()
        for player_id, ws in list(connections.items()):
            # A client that just closed (or has just left the game) raises here;
            # its own handler removes it.
            with contextlib.suppress(Exception):
                await ws.send_text(json.dumps(game.snapshot_for(player_id)))
        await asyncio.sleep(max(0.0, 1 / TICK_RATE - (loop.time() - started)))


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
                    player = game.join(message.get("name"))
                    player_id = player.id
                    await ws.send_json(
                        {
                            "type": "welcome",
                            "id": player.id,
                            "map": game.campus,
                            "speed": SPEED,
                            "tick_rate": TICK_RATE,
                            "player_half": PLAYER_HALF,
                        }
                    )
                    connections[player_id] = ws
                elif message["type"] == "start":
                    game.start(player_id)
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


# Serve web/ at "/" (index.html, main.js, vendor/phaser.min.js). Mounted last so
# /ws and /healthz are matched first.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
