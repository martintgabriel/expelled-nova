"""Game rules: lobby, host, secret roles and live movement. Plain Python, no network code,
so it can be tested directly.

The server owns the truth: browsers only send a direction (dx, dy) or "start". Every tick
the server moves each player a fixed distance and blocks walls.
"""

import json
import math
import random
import unicodedata
from collections import deque
from dataclasses import dataclass
from pathlib import Path

TICK_RATE = 20  # server updates per second
SPEED = 160.0  # pixels per second
STEP = SPEED / TICK_RATE  # pixels per tick (8)
PLAYER_HALF = 10  # a player is a 20 x 20 px square; this is half its side
MIN_PLAYERS = 4  # needed to start a game
MAX_PLAYERS = 10
NAME_MAX = 16
MAX_MESSAGE_BYTES = 512
RATE_LIMIT = 30  # messages per second per connection
MESSAGE_TYPES = {"join", "input", "start"}

# Game phases. Later specs add "meeting" and "ended".
LOBBY = "lobby"  # before the start: players join and walk around
PLAYING = "playing"

# Roles. Secret: a player only ever receives their own (see Game.snapshot_for).
STUDENT = "student"
EXAMINER = "examiner"

MAP_PATH = Path(__file__).with_name("campus.json")


class GameError(Exception):
    """A rejected action. The message is the short reason shown to the player."""


@dataclass
class Player:
    id: str
    name: str
    x: float
    y: float
    dx: int = 0
    dy: int = 0
    role: str | None = None  # None in the lobby, then STUDENT or EXAMINER


def load_map(path=MAP_PATH):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def validate_nickname(raw):
    """Return the cleaned nickname or raise GameError. Uniqueness is checked in Game.join."""
    if not isinstance(raw, str):
        raise GameError("Nickname must be text")
    # Trim spaces only: other whitespace such as newlines or tabs is rejected below.
    name = unicodedata.normalize("NFC", raw).strip(" ")
    if not name:
        raise GameError("Nickname must not be empty")
    if len(name) > NAME_MAX:
        raise GameError(f"Nickname must be at most {NAME_MAX} characters")
    if not all(ch.isalpha() or ch in "0123456789 " for ch in name):
        raise GameError("Nickname may only contain letters, digits and spaces")
    return name


def parse_message(raw, joined):
    """Turn one raw WebSocket message into a dict, or raise GameError.

    Checks size, JSON, shape, type and whether the type is allowed right now:
    before joining only "join", after joining only "input" and "start".
    """
    if not isinstance(raw, str):
        raise GameError("Messages must be text")
    if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise GameError("Message too long")
    try:
        message = json.loads(raw)
    except ValueError:
        raise GameError("Message is not valid JSON") from None
    if not isinstance(message, dict):
        raise GameError("Message must be a JSON object")
    kind = message.get("type")
    if kind not in MESSAGE_TYPES:
        raise GameError("Unknown message type")
    if not joined and kind != "join":
        raise GameError("Join the game first")
    if joined and kind == "join":
        raise GameError("You have already joined")
    return message


class RateLimiter:
    """Allows at most `limit` messages in any `window` seconds (sliding window)."""

    def __init__(self, limit=RATE_LIMIT, window=1.0):
        self.limit = limit
        self.window = window
        self.times = deque()

    def allow(self, now):
        while self.times and now - self.times[0] >= self.window:
            self.times.popleft()
        if len(self.times) >= self.limit:
            return False
        self.times.append(now)
        return True


def examiner_count(player_count):
    """1 examiner for 4-6 players, 2 for 7-10."""
    return 1 if player_count <= 6 else 2


def is_direction(value):
    # type() instead of isinstance(): True/False are ints in Python and must be rejected.
    return type(value) is int and value in (-1, 0, 1)


class Game:
    def __init__(self, campus, rng=None):
        self.campus = campus
        self.tile = campus["tile_size"]
        self.grid = campus["grid"]
        self.players = {}  # by id, in join order (Python dicts keep insertion order)
        self.tick = 0
        self.next_id = 1
        self.phase = LOBBY
        # Operating-system randomness, so nobody can predict the roles.
        # Tests pass a seeded random.Random to fix the outcome.
        self.rng = rng or random.SystemRandom()

    @property
    def host_id(self):
        """The player who has been in the game longest: the first one in join order."""
        return next(iter(self.players), None)

    # --- Joining and leaving --------------------------------------------------

    def join(self, raw_name):
        if self.phase != LOBBY:
            raise GameError("Game already running")
        if len(self.players) >= MAX_PLAYERS:
            raise GameError(f"Game is full ({MAX_PLAYERS} players)")
        name = validate_nickname(raw_name)
        if any(p.name.casefold() == name.casefold() for p in self.players.values()):
            raise GameError("Nickname is already taken")
        col, row = self._free_spawn()
        player = Player(
            id=f"p{self.next_id}",
            name=name,
            x=(col + 0.5) * self.tile,
            y=(row + 0.5) * self.tile,
        )
        self.next_id += 1
        self.players[player.id] = player
        return player

    def leave(self, player_id):
        """Remove a player. If it was the host, the next-longest player is host automatically."""
        self.players.pop(player_id, None)
        if not self.players:
            # Everyone has gone: open the lobby again, otherwise nobody could ever join.
            self.phase = LOBBY

    # --- Starting and roles -----------------------------------------------------

    def start(self, player_id):
        """Start the game and deal the secret roles. Checks everything before changing anything."""
        if player_id not in self.players:
            raise GameError("Unknown player")
        if self.phase != LOBBY:
            raise GameError("Game already running")
        if player_id != self.host_id:
            raise GameError("Only the host can start the game")
        if len(self.players) < MIN_PLAYERS:
            raise GameError(f"Need at least {MIN_PLAYERS} players")
        examiners = self.rng.sample(list(self.players), examiner_count(len(self.players)))
        for player in self.players.values():
            player.role = EXAMINER if player.id in examiners else STUDENT
        self.phase = PLAYING

    def _free_spawn(self):
        """First spawn point nobody is standing on (falls back to the first one)."""
        taken = {(p.x, p.y) for p in self.players.values()}
        for col, row in self.campus["spawns"]:
            if ((col + 0.5) * self.tile, (row + 0.5) * self.tile) not in taken:
                return col, row
        return self.campus["spawns"][0]

    # --- Input and movement ---------------------------------------------------

    def set_input(self, player_id, message):
        """Store a player's direction. Validates everything before changing anything."""
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Unknown player")
        if not isinstance(message, dict) or message.get("type") != "input":
            raise GameError("Not an input message")
        dx, dy = message.get("dx"), message.get("dy")
        if not (is_direction(dx) and is_direction(dy)):
            raise GameError("dx and dy must each be -1, 0 or 1")
        player.dx, player.dy = dx, dy

    def step(self):
        """Advance the game by one tick: move every player in their direction."""
        self.tick += 1
        for player in self.players.values():
            if player.dx == 0 and player.dy == 0:
                continue
            length = math.hypot(player.dx, player.dy)  # 1 straight, about 1.41 diagonal
            self._move_axis(player, player.dx / length * STEP, 0)
            self._move_axis(player, 0, player.dy / length * STEP)

    def _move_axis(self, player, mx, my):
        """Move in small pieces of at most 1 px and stop at the first piece that hits a wall.

        So a player walks up to a wall (to within 1 px) but never into it, and a move
        straight into a wall leaves the position unchanged.
        """
        remaining = abs(mx) + abs(my)
        sign_x = (mx > 0) - (mx < 0)
        sign_y = (my > 0) - (my < 0)
        while remaining > 0:
            part = min(1.0, remaining)
            nx, ny = player.x + sign_x * part, player.y + sign_y * part
            if self.blocked(nx, ny):
                return
            player.x, player.y = nx, ny
            remaining -= part

    def blocked(self, x, y):
        """True if a player square centred at (x, y) overlaps a wall or leaves the map."""
        left = math.floor((x - PLAYER_HALF) / self.tile)
        right = math.floor((x + PLAYER_HALF) / self.tile - 1e-9)
        top = math.floor((y - PLAYER_HALF) / self.tile)
        bottom = math.floor((y + PLAYER_HALF) / self.tile - 1e-9)
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                if row < 0 or row >= len(self.grid) or col < 0 or col >= len(self.grid[row]):
                    return True
                if self.grid[row][col] == "#":
                    return True
        return False

    # --- What the browsers receive --------------------------------------------

    def snapshot(self):
        """The part every player may see: phase, host, names and positions. Never a role."""
        return {
            "type": "state",
            "tick": self.tick,
            "phase": self.phase,
            "host": self.host_id,
            "players": [
                {"id": p.id, "name": p.name, "x": round(p.x, 1), "y": round(p.y, 1)}
                for p in self.players.values()
            ],
        }

    def snapshot_for(self, player_id):
        """What one player may know: the shared snapshot plus their own role.

        An examiner also gets the ids of the fellow examiners. Nobody gets anyone else's role.
        """
        me = self.players.get(player_id)
        if me is None:
            raise GameError("Unknown player")
        state = self.snapshot()
        state["role"] = me.role
        if me.role == EXAMINER:
            state["fellow_examiners"] = [
                p.id for p in self.players.values() if p.role == EXAMINER and p.id != me.id
            ]
        return state
