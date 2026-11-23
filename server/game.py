"""Game rules: lobby, host, secret roles, live movement, expelling, ghosts, meetings and
votes, tasks, vents, the lights, the end of a round, player colours and vision.
Plain Python, no network code, so it can be tested directly.

The server owns the truth: browsers only send a direction (dx, dy), "start", "expel",
"report", "meeting", "vote", "task", "vent_enter", "vent_move", "vent_leave", "sabotage", "fix",
"make_host" or "restart". Every tick the server moves each player a fixed
distance and blocks walls. Time is counted in ticks (not the wall clock), so tests can
advance it with step().
"""

import json
import math
import random
import unicodedata
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from server import guard, minigames

TICK_RATE = 20  # server updates per second
SPEED = 160.0  # pixels per second
STEP = SPEED / TICK_RATE  # pixels per tick (8)
PLAYER_HALF = 10  # a player is a 20 x 20 px square; this is half its side
# How far a straight walk slides sideways round the corner of a wall (spec 011): half a
# player, so whoever is at least half in front of a gap slips into it.
CORNER_SLIDE = PLAYER_HALF
MIN_PLAYERS = 4  # needed to start a game
MAX_PLAYERS = 10
NAME_MAX = 16
MAX_MESSAGE_BYTES = 512
RATE_LIMIT = 30  # messages per second per connection
MESSAGE_TYPES = {"join", "input", "start", "restart", "make_host"}  # joining, walking, the round
MESSAGE_TYPES |= {"expel", "report", "meeting", "vote", "task"}  # actions in a round
MESSAGE_TYPES |= {"vent_enter", "vent_move", "vent_leave"}  # examiners in the vents
MESSAGE_TYPES |= {"task_input", "task_cancel"}  # answering or closing a task's mini-game
MESSAGE_TYPES |= {"sabotage", "fix"}  # the lights
MESSAGE_TYPES |= {"chat"}  # spec 029: the meeting chat
MESSAGE_TYPES |= {"settings"}  # the host's lobby settings (spec 019)
EXPEL_RANGE = 48  # px between centres, about 1.5 tiles
EXPEL_COOLDOWN = 30  # seconds between two expels by the same examiner (spec 019: was 20)
EXPEL_COOLDOWN_TICKS = EXPEL_COOLDOWN * TICK_RATE  # 600
VISION_TILES = 6  # how far a living player sees while playing, in tiles
REPORT_RANGE = 48  # px from a player's centre to a failed exam, about 1.5 tiles
# The meeting point (spec 011): a round table with an emergency button. It is drawn on the
# floor and blocks nobody.
MEETING_TABLE_RADIUS = 40  # px from the table's middle to its edge
MEETING_RANGE = 48  # px from a player's centre to the table's edge, about 1.5 tiles
MEETING_CIRCLE = 64  # px from the table's middle to each player's place at a meeting
# Vents (spec 015): a living examiner climbs into a vent, is hidden while inside, moves
# between the vents and climbs out again.
VENT_COOLDOWN = 3  # seconds before an examiner may climb in again after climbing out
VENT_COOLDOWN_TICKS = VENT_COOLDOWN * TICK_RATE  # 60
VENT_OPEN_TICKS = TICK_RATE // 2  # how long a hatch shows open after someone used it (0.5 s)
INSIDE_VENT = "Leave the vent first"  # the reason for every other action while inside
SABOTAGE_COOLDOWN = 30  # seconds before the lights can be turned off (again)
SABOTAGE_COOLDOWN_TICKS = SABOTAGE_COOLDOWN * TICK_RATE  # 600
LIGHTS_OUT_TILES = 1.5  # how far a living student sees while the lights are off, in tiles
FIX_SECONDS = 3  # how long a student stays at the light switch to fix the lights
FIX_TICKS = FIX_SECONDS * TICK_RATE  # 60
SWITCH_RANGE = 48  # px from a player's centre to the centre of the switch's tile
# Spec 023: the sabotage menu. "lights" is spec 008's sabotage; "fire" and "wifi" are new.
SABOTAGE_KINDS = ("lights", "fire", "wifi")
FIRE_SECONDS = 40  # time for every living student to reach the assembly point
FIRE_TICKS = FIRE_SECONDS * TICK_RATE
NO_WIFI = "No Wi-Fi. Try again later."
# Spec 029: the meeting chat.
CHAT_MAX = 80  # characters per message
CHAT_KEEP = 30  # messages a meeting keeps (the oldest go first)
CHAT_COOLDOWN_TICKS = int(1.5 * TICK_RATE)  # one message per player every 1.5 s
TASKS_PER_STUDENT = 3  # dealt to every player at the start with 4-5 players (see tasks_per_player)
TASK_RANGE = 48  # px from a player's centre to the centre of a task's tile, about 1.5 tiles
MEETING_SECONDS = 60  # voting time
RESULT_SECONDS = 5  # how long the result is shown before play resumes
MEETING_TICKS = MEETING_SECONDS * TICK_RATE  # 1200
RESULT_TICKS = RESULT_SECONDS * TICK_RATE  # 100
# Colour numbers 0-9, one per player. Which number is which colour is drawing (web/render.js).
PLAYER_COLORS = range(MAX_PLAYERS)
HAT_COUNT = 10  # spec 022: hat numbers 0-9, drawn by web/hats.js; 0 is the graduation cap

# The Segway security guard (spec 027): a hazard, never a player (see server/guard.py).
# px/s: faster than any player, so nobody can outrun or escort him; spec 034 slowed him
# down from 1.6 * SPEED, at which he crossed the vision circle in about a second.
GUARD_SPEED = 1.2 * SPEED
GUARD_STEP = GUARD_SPEED / TICK_RATE  # px/tick
GUARD_VISION_TILES = 4  # a smaller, narrower view than a player's own (VISION_TILES = 6)
GUARD_CONE_DEGREES = 70
GUARD_PAUSE_CHANCE = 0.25  # checked once with self.rng each time he arrives at a waypoint
GUARD_PAUSE_SECONDS = (1, 3)  # (min, max), both inclusive, drawn with self.rng
GUARD_SWEEP_DEGREES = 25  # how far his facing sweeps either side of sweep_base while paused
GUARD_SWEEP_TICKS = TICK_RATE * 2  # one full left-right-left sweep, in ticks
GUARD_MIN_START_TILES = 10  # how far his starting waypoint must lie from every spawn

# Game phases.
LOBBY = "lobby"  # before the start: players join and walk around
PLAYING = "playing"
MEETING = "meeting"  # everyone around the meeting table: voting, then the result; nobody moves
ENDED = "ended"  # a side has won; all roles are revealed until the host restarts

# Roles. Secret: a player only ever receives their own (see Game.snapshot_for).
STUDENT = "student"
EXAMINER = "examiner"

# Why a meeting was called, and the vote for nobody.
REPORT = "report"
BUTTON = "button"  # the emergency button on the meeting table
SECURITY = "security"  # spec 027: the guard saw an expel; caught names the examiner
SKIP = "skip"

# Winners, shown on the end screen.
STUDENTS_WIN = "students"
EXAMINERS_WIN = "examiners"

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
    alive: bool = True  # False = ghost: walks through walls, cannot expel or be expelled
    color: int = 0  # colour number, unique in the game, kept until the player leaves
    hat: int = 0  # spec 022: chosen when joining, 0 = the graduation cap
    next_expel_tick: int = 0  # first tick at which this player may expel (again)
    vent: str | None = None  # id of the vent this examiner is inside right now, or None
    next_vent_tick: int = 0  # first tick at which this player may climb into a vent (again)
    meeting_used: bool = False  # one call at the meeting table per player per round
    tasks: list = field(default_factory=list)  # ids of this student's tasks (examiners: none)
    tasks_done: list = field(default_factory=list)  # ids of the finished ones
    tasks_step: dict = field(default_factory=dict)  # task id -> stations finished so far
    doing: str | None = None  # id of the task this player is doing right now
    doing_done_tick: int = 0  # plain-wait stations only: the tick at which that task is done
    challenge: dict | None = None  # the running mini-game's state (spec 012), or None
    task_note: str | None = None  # the latest wrong-answer/cancel/time-out message, or None
    fix_done_tick: int | None = None  # while fixing the lights: the tick at which they go on


@dataclass
class FailedExam:
    """The "6/20" sheet left on the floor where a student was expelled."""

    id: str
    x: float
    y: float


@dataclass
class Meeting:
    """A running meeting. The votes stay on the server: players only learn who has voted."""

    reason: str  # REPORT or BUTTON
    called_by: str  # player id
    voting_ends: int  # the tick at which the voting closes at the latest
    votes: dict = field(default_factory=dict)  # voter id -> target id or SKIP
    result: dict | None = None  # set when the voting closes
    result_ends: int = 0  # the tick at which play resumes (set together with the result)
    caught: str | None = None  # spec 027: the examiner id the security guard saw, or None
    chat: list = field(default_factory=list)  # spec 029: {"from": id, "text": str}, oldest first
    chat_ready: dict = field(default_factory=dict)  # spec 029: player id -> next allowed tick


# Map decor (spec 009): only changes how the map looks, never a rule. Solid kinds must lie
# on wall tiles ("#"): the sea, roofs, glass and screens block walking like any wall. Floor
# kinds are painted on the floor tiles of their rectangle. Furniture and plants are floor
# kinds (spec 011): players walk over them.
SOLID_DECOR = {"sea", "solar", "greenroof", "roof", "glasswall", "screen"}
GROUND_DECOR = {"sand", "paving", "grass", "terrace", "pergola", "glassroof", "shopfloor", "seats"}
FURNITURE_DECOR = {
    "beanbag", "counter", "shelf", "desk", "studytable", "table", "cafetable", "woodtable",
    "shopshelf", "foodcounter", "piano", "steps", "picnic", "tree", "surfboard",
}
FLOOR_DECOR = GROUND_DECOR | FURNITURE_DECOR
# The solid kinds that also block sight (spec 010, part 2), like every plain wall tile:
# roofs and screens. Glass and the sea only block walking.
SIGHT_DECOR = {"roof", "greenroof", "solar", "screen"}
LABEL_MAX = 24  # characters of a map label


def sight_grid(campus):
    """The tiles that block sight, in the same form as the map's grid: "#" blocks, "." not.

    A wall tile blocks sight unless it is glass or sea: a solid kind that is not in
    SIGHT_DECOR. A tile with both kinds of decor blocks. Floor tiles never block, whatever
    furniture stands on them.
    The browser receives this grid in "welcome", so both sides use the same rule.
    """
    low, tall = set(), set()
    for entry in campus.get("decor", []):
        if entry["kind"] in SOLID_DECOR:
            tiles = {
                (col, row)
                for row in range(entry["y"], entry["y"] + entry["h"])
                for col in range(entry["x"], entry["x"] + entry["w"])
            }
            (tall if entry["kind"] in SIGHT_DECOR else low).update(tiles)
    return [
        "".join(
            "#" if tile == "#" and ((col, row) in tall or (col, row) not in low) else "."
            for col, tile in enumerate(line)
        )
        for row, line in enumerate(campus["grid"])
    ]


def load_map(path=MAP_PATH):
    with open(path, encoding="utf-8") as file:
        campus = json.load(file)
    validate_campus(campus)
    return campus


def _whole(value):
    return type(value) is int


def validate_campus(campus):
    """Check the optional "decor" and "labels" lists of a map (spec 009).

    Solid kinds must lie on wall tiles and furniture on floor tiles (spec 011); the
    ground kinds (grass, paving, ...) may span both and are painted on the floor tiles.

    Raises ValueError with a short reason, so a broken map fails at server start and in
    the tests instead of in the middle of a game. A map without them is valid.
    """
    grid = campus["grid"]
    rows, cols = len(grid), len(grid[0])
    for entry in campus.get("decor", []):
        kind = entry.get("kind")
        if kind not in SOLID_DECOR | FLOOR_DECOR:
            raise ValueError(f"Unknown decor kind: {kind!r}")
        for key in ("x", "y", "w", "h"):
            if key not in entry:
                raise ValueError(f"Decor {kind} is missing {key}")
            if not _whole(entry[key]):
                raise ValueError(f"Decor {kind}: {key} must be a whole number")
        x, y, w, h = entry["x"], entry["y"], entry["w"], entry["h"]
        if w < 1 or h < 1:
            raise ValueError(f"Decor {kind}: w and h must be at least 1")
        if x < 0 or y < 0 or x + w > cols or y + h > rows:
            raise ValueError(f"Decor {kind} at {x}, {y} lies outside the grid")
        for row in range(y, y + h):
            for col in range(x, x + w):
                if kind in SOLID_DECOR and grid[row][col] != "#":
                    raise ValueError(f"Decor {kind} covers the floor tile {col}, {row}")
                if kind in FURNITURE_DECOR and grid[row][col] != ".":
                    raise ValueError(f"Decor {kind} stands on the wall tile {col}, {row}")
    for label in campus.get("labels", []):
        text = label.get("text")
        if not isinstance(text, str) or not 1 <= len(text) <= LABEL_MAX:
            raise ValueError(f"A label needs a text of 1 to {LABEL_MAX} characters")
        x, y = label.get("x"), label.get("y")
        if not all(type(v) in (int, float) for v in (x, y)):
            raise ValueError(f"Label {text!r}: x and y must be numbers")
        if not (0 <= x < cols and 0 <= y < rows):
            raise ValueError(f"Label {text!r} lies outside the grid")
    if "guard_route" in campus:
        guard.build_route(campus, campus["tile_size"], PLAYER_HALF)


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
    before joining only "join", after joining everything except "join".
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


EXAMINER_SETTINGS = (None, 1, 2)  # None = automatic (examiner_count), spec 019
MIN_PLAYERS_FOR_TWO_EXAMINERS = 6


def tasks_per_player(player_count):
    """Spec 019: 3 tasks for 4-5 players, 4 for 6-7, 5 for 8-10, so bigger rounds last longer."""
    if player_count <= 5:
        return TASKS_PER_STUDENT
    if player_count <= 7:
        return TASKS_PER_STUDENT + 1
    return TASKS_PER_STUDENT + 2


def is_direction(value):
    # type() instead of isinstance(): True/False are ints in Python and must be rejected.
    return type(value) is int and value in (-1, 0, 1)


def _normalize_station(raw):
    """One station of a task, keeping only what the engine needs: a place, a title, an
    area, and either a mini-game kind (spec 012) or a plain wait (spec 004, test maps only)."""
    station = {"title": raw["title"], "area": raw["area"], "x": raw["x"], "y": raw["y"]}
    if "minigame" in raw:
        station["minigame"] = raw["minigame"]
    else:
        station["seconds"] = raw["seconds"]
    return station


class Game:
    def __init__(self, campus, rng=None):
        self.tile = campus["tile_size"]
        # Spec 027: the guard's own route is built from the map here and then kept out of
        # self.campus (the same dict server/main.py sends verbatim as welcome.map), so no
        # browser, in any role, can ever receive the waypoints or the connections.
        self._guard_route = guard.build_route(campus, self.tile, PLAYER_HALF)
        self.campus = {key: value for key, value in campus.items() if key != "guard_route"}
        self.guard_vision_radius = GUARD_VISION_TILES * self.tile
        self.guard = None  # a GuardState while PLAYING on a map with a guard_route, else None
        self.security_witnessed = False  # set True on the ENDED state (see expel())
        self.vision_radius = VISION_TILES * self.tile  # px between centres
        self.grid = campus["grid"]
        self.tasks = {
            raw["id"]: {
                "id": raw["id"],
                "joke": raw.get("joke"),
                "steps": [_normalize_station(s) for s in raw.get("steps", [raw])],
            }
            for raw in campus.get("tasks", [])
        }  # task id -> {id, joke, steps}; a flat task (no "steps") normalises to one station
        self.vents = {vent["id"]: vent for vent in campus.get("vents", [])}  # by id
        self.vent_open = {}  # vent id -> the tick until which its hatch shows open
        self.sight = sight_grid(campus)  # which tiles block sight; walls never change
        self.lights_out_radius = LIGHTS_OUT_TILES * self.tile  # px, for students in the dark
        self.lights_on = True
        # Spec 023: the running fire alarm or Wi-Fi outage, or None. The lights stay in
        # lights_on (spec 008). {"kind": "fire", "ends_tick", "evacuated": set of ids} or
        # {"kind": "wifi"}.
        self.emergency = None
        self.fire_lost = False  # the round ended because the fire alarm ran out
        self.next_sabotage_tick = 0  # first tick at which an examiner may turn the lights off
        self.players = {}  # by id, in join order (Python dicts keep insertion order)
        # The host's player id (spec 015): the first player to join, until the host hands
        # over (make_host) or leaves (then the player who has been in the game longest).
        self.host_id = None
        # The host's lobby settings (spec 019). None = automatic number of examiners.
        self.examiner_setting = None
        self.tick = 0
        self.next_id = 1
        self.phase = LOBBY
        self.winner = None  # STUDENTS_WIN or EXAMINERS_WIN once the phase is ENDED
        self.failed_exams = []  # FailedExam objects; the living see those within vision, ghosts all
        self.next_exam_id = 1
        self.meeting = None  # a Meeting while the phase is MEETING
        # Operating-system randomness, so nobody can predict the roles.
        # Tests pass a seeded random.Random to fix the outcome.
        self.rng = rng or random.SystemRandom()

    # --- Joining and leaving --------------------------------------------------

    def join(self, raw_name, hat=0, color=None):
        """Spec 022: `hat` 0-9 and `color` 0-9 (or None for any free colour) are chosen on
        the ID card. Checks everything before changing anything."""
        if self.phase != LOBBY:
            raise GameError("Game already running")
        if len(self.players) >= MAX_PLAYERS:
            raise GameError(f"Game is full ({MAX_PLAYERS} players)")
        name = validate_nickname(raw_name)
        if any(p.name.casefold() == name.casefold() for p in self.players.values()):
            raise GameError("Nickname is already taken")
        # type() instead of isinstance(): True/False are ints in Python and must be rejected.
        if not (type(hat) is int and 0 <= hat < HAT_COUNT):
            raise GameError(f"Hat must be a number from 0 to {HAT_COUNT - 1}")
        if color is not None and not (type(color) is int and color in PLAYER_COLORS):
            raise GameError(f"Colour must be a number from 0 to {MAX_PLAYERS - 1}")
        if color is not None and any(p.color == color for p in self.players.values()):
            raise GameError("Colour is already taken")
        x, y = self._tile_centre(*self._free_spawn())
        chosen = self._free_color() if color is None else color
        player = Player(id=f"p{self.next_id}", name=name, x=x, y=y, color=chosen, hat=hat)
        self.next_id += 1
        self.players[player.id] = player
        if self.host_id is None:
            self.host_id = player.id  # the first player in an empty game
        return player

    def leave(self, player_id):
        """Remove a player. If it was the host, the player who has been in the game longest
        (the first one in join order) becomes host.

        While playing or in a meeting, a player leaving can decide the game (see _check_win).
        During the vote, the leaver's vote and the votes for them are taken back.
        """
        self.players.pop(player_id, None)
        if not self.players:
            # Everyone has gone: open a clean lobby again, otherwise nobody could ever join.
            self.host_id = None
            self.examiner_setting = None
            self._reset_round()
            return
        if player_id == self.host_id:
            self.host_id = next(iter(self.players))
        if self.phase == MEETING and self.meeting.result is None:
            self.meeting.votes = {
                voter: target
                for voter, target in self.meeting.votes.items()
                if player_id not in (voter, target)
            }
        if self.phase in (PLAYING, MEETING):
            self._check_win()

    def make_host(self, player_id, target_id):
        """The host hands the host role to another player, in the lobby only (spec 015).

        The sender is checked before the target. Checks everything before changing anything.
        """
        if player_id not in self.players:
            raise GameError("Unknown player")
        if self.phase != LOBBY:
            raise GameError("The host can only change in the lobby")
        if player_id != self.host_id:
            raise GameError("Only the host can hand over")
        if not isinstance(target_id, str):
            raise GameError("Target must be a player id")
        if target_id == player_id:
            raise GameError("You are already the host")
        if target_id not in self.players:
            raise GameError("Unknown target")
        self.host_id = target_id

    def set_settings(self, player_id, message):
        """The host changes a lobby setting (spec 019). For now only the number of
        examiners: None (automatic), 1 or 2. Checks everything before changing anything."""
        if player_id not in self.players:
            raise GameError("Unknown player")
        if self.phase != LOBBY:
            raise GameError("Settings can only change in the lobby")
        if player_id != self.host_id:
            raise GameError("Only the host can change the settings")
        if "expellers" not in message:
            raise GameError("Missing setting: expellers")
        value = message["expellers"]
        # type() instead of isinstance(): True/False are ints in Python and must be rejected.
        if not (value is None or (type(value) is int and value in EXAMINER_SETTINGS)):
            raise GameError("Examiners must be automatic, 1 or 2")
        self.examiner_setting = value

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
        wanted = self.examiner_setting or examiner_count(len(self.players))
        if wanted == 2 and len(self.players) < MIN_PLAYERS_FOR_TWO_EXAMINERS:
            raise GameError(
                f"2 examiners need at least {MIN_PLAYERS_FOR_TWO_EXAMINERS} players"
            )
        examiners = self.rng.sample(list(self.players), wanted)
        tasks_each = min(tasks_per_player(len(self.players)), len(self.tasks))
        for player in self.players.values():
            player.role = EXAMINER if player.id in examiners else STUDENT
            player.next_expel_tick = self.tick + EXPEL_COOLDOWN_TICKS  # first cooldown
            # Different tasks for each player; a map with fewer tasks deals what it has.
            # Examiners get the same count from the same pool as fake tasks (spec 012,
            # part 3), which never count towards the task win (see _task_progress).
            player.tasks = self.rng.sample(list(self.tasks), tasks_each)
        self.next_sabotage_tick = self.tick + SABOTAGE_COOLDOWN_TICKS  # first cooldown
        self._place_on_spawns()
        self.phase = PLAYING
        self.security_witnessed = False
        self.guard = self._spawn_guard()

    def _spawn_guard(self):
        """A fresh GuardState on a waypoint at least GUARD_MIN_START_TILES from every spawn
        (spec 027), or None on a map with no guard_route."""
        if self._guard_route is None:
            return None
        spawn_centres = [self._tile_centre(*spawn) for spawn in self.campus["spawns"]]
        far_enough = GUARD_MIN_START_TILES * self.tile
        start_ids = [
            wid
            for wid, point in self._guard_route.items()
            if all(
                math.hypot(point["x"] - sx, point["y"] - sy) >= far_enough
                for sx, sy in spawn_centres
            )
        ]
        return guard.start_guard(self._guard_route, self.rng, start_ids or list(self._guard_route))

    def _free_spawn(self):
        """First spawn point nobody is standing on (falls back to the first one)."""
        taken = {(p.x, p.y) for p in self.players.values()}
        for col, row in self.campus["spawns"]:
            if self._tile_centre(col, row) not in taken:
                return col, row
        return self.campus["spawns"][0]

    def _place_on_spawns(self):
        """Put every player on a different spawn point, in join order, and stop them
        walking (used when a round starts and when it resets, spec 013)."""
        spawns = self.campus["spawns"]
        for index, player in enumerate(self.players.values()):
            player.x, player.y = self._tile_centre(*spawns[index % len(spawns)])
            player.dx = player.dy = 0

    def _tile_centre(self, col, row):
        return (col + 0.5) * self.tile, (row + 0.5) * self.tile

    def _free_color(self):
        """The lowest colour number nobody in the game has (there are as many as players)."""
        taken = {p.color for p in self.players.values()}
        return min(color for color in PLAYER_COLORS if color not in taken)

    def taken_colors(self):
        """Spec 028: which colours are taken, as {colour number: that player's nickname}.

        For the colour picker on the join screen, so it is also given to someone who has
        not joined yet. It holds only what the lobby shows anyway (nickname and colour):
        no player id, no role, no position, and a ghost keeps its colour like everyone.
        """
        return {p.color: p.name for p in self.players.values()}

    # --- Expelling ----------------------------------------------------------------

    def expel(self, player_id, target_id):
        """An examiner hands a student a failed exam. Checks everything before changing anything.

        The sender is checked before the target, so a rejection never tells a student
        anything about another player's role. If two examiners expel the same student
        in one tick, the first call wins and the second gets "Already expelled".
        """
        examiner = self.players.get(player_id)
        if examiner is None:
            raise GameError("Unknown player")
        if self.phase == ENDED:
            raise GameError("Game is over")
        if self.phase == MEETING:
            raise GameError("Meeting in progress")
        if self.phase != PLAYING:
            raise GameError("The game has not started yet")
        if not examiner.alive:
            raise GameError("Ghosts cannot expel")
        if examiner.role != EXAMINER:
            raise GameError("Only examiners can expel")
        if examiner.vent is not None:
            raise GameError(INSIDE_VENT)
        if not isinstance(target_id, str):
            raise GameError("Target must be a player id")
        target = self.players.get(target_id)
        if target is None:
            raise GameError("Unknown target")
        if not target.alive:
            raise GameError("Already expelled")
        if target.role != STUDENT:
            raise GameError("Cannot expel an examiner")
        if math.hypot(target.x - examiner.x, target.y - examiner.y) > EXPEL_RANGE:
            raise GameError("Too far away")
        if self.tick < examiner.next_expel_tick:
            raise GameError(f"Cooldown: {self._cooldown_left(examiner)} s left")

        target.alive = False
        target.doing = None  # a running task is cancelled; the ghost may start it again
        target.challenge = None
        target.task_note = None
        target.fix_done_tick = None  # and so is fixing the lights
        self.failed_exams.append(FailedExam(f"e{self.next_exam_id}", target.x, target.y))
        self.next_exam_id += 1
        examiner.next_expel_tick = self.tick + EXPEL_COOLDOWN_TICKS
        # Spec 027: checked here, both their centres still exactly where the expel left them,
        # before _check_win() can end the round or a new meeting can move anyone.
        seen_by_guard = self._seen_by_guard(examiner.x, examiner.y) or self._seen_by_guard(
            target.x, target.y
        )
        self._check_win()
        if self.phase == ENDED:
            if seen_by_guard:
                self.security_witnessed = True
        elif seen_by_guard:
            self._start_meeting(SECURITY, examiner, caught=examiner.id)

    def _seen_by_guard(self, x, y):
        """Whether the guard sees the point (x, y): within his vision radius, within his cone
        angle of his facing, and a clear sight_clear line to his centre. Never shrunk by the
        lights (spec 027): he carries his own light."""
        if self.guard is None:
            return False
        if math.hypot(x - self.guard.x, y - self.guard.y) > self.guard_vision_radius:
            return False
        angle_to = math.atan2(y - self.guard.y, x - self.guard.x)
        difference = (angle_to - self.guard.facing + math.pi) % (2 * math.pi) - math.pi
        if abs(difference) > math.radians(GUARD_CONE_DEGREES) / 2:
            return False
        return self.sight_clear(self.guard.x, self.guard.y, x, y)

    def _cooldown_left(self, player):
        """Whole seconds until the player may expel, rounded up (0 = ready)."""
        return self._seconds_until(player.next_expel_tick)

    def _seconds_until(self, tick):
        """Whole seconds from now until the given tick, rounded up (0 = now or past)."""
        return max(0, math.ceil((tick - self.tick) / TICK_RATE))

    # --- Vents (spec 015; they replace the staff doors of spec 008, part 6) --------------

    def enter_vent(self, player_id):
        """A living examiner standing on a vent climbs in.

        While inside they sit on the vent's centre, are left out of everyone else's
        snapshot (see snapshot) and can only move to another vent or climb out: walking,
        expelling, reporting, calling a meeting, tasks and sabotage are rejected. The sender
        is checked before the place, so a rejection tells a student nothing.
        """
        player = self._check_vent_user(player_id)
        if player.vent is not None:
            raise GameError("You are already inside a vent")
        here = self._vent_under(player)
        if here is None:
            raise GameError("You are not standing on a vent")
        if self.tick < player.next_vent_tick:
            left = self._seconds_until(player.next_vent_tick)
            raise GameError(f"Vent cooldown: {left} s left")

        player.vent = here
        player.x, player.y = self._vent_centre(here)
        player.dx = player.dy = 0
        player.doing = None  # a running (fake) task is cancelled
        player.challenge = None
        player.task_note = None
        self.vent_open[here] = self.tick + VENT_OPEN_TICKS  # others see the hatch move

    def move_vent(self, player_id, destination):
        """An examiner inside a vent moves to another vent, at once and without a cooldown.
        No hatch opens: nobody can tell where they are."""
        player = self._check_vent_user(player_id)
        if player.vent is None:
            raise GameError("You are not inside a vent")
        if not isinstance(destination, str):
            raise GameError("Destination must be a vent id")
        if destination not in self.vents:
            raise GameError("Unknown vent")
        if destination == player.vent:
            raise GameError("You are already at this vent")
        player.vent = destination
        player.x, player.y = self._vent_centre(destination)

    def leave_vent(self, player_id):
        """An examiner inside a vent climbs out at the vent they are in. Climbing in again
        (anywhere) has a cooldown of VENT_COOLDOWN seconds from now."""
        player = self._check_vent_user(player_id)
        if player.vent is None:
            raise GameError("You are not inside a vent")
        self.vent_open[player.vent] = self.tick + VENT_OPEN_TICKS
        player.vent = None  # they already sit on the vent's centre
        player.next_vent_tick = self.tick + VENT_COOLDOWN_TICKS

    def _check_vent_user(self, player_id):
        """The checks the three vent actions share. Returns the player."""
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Unknown player")
        if self.phase == ENDED:
            raise GameError("Game is over")
        if self.phase == MEETING:
            raise GameError("Meeting in progress")
        if self.phase != PLAYING:
            raise GameError("The game has not started yet")
        if not player.alive:
            raise GameError("Ghosts cannot use vents")
        if player.role != EXAMINER:
            raise GameError("Only examiners can use vents")
        return player

    def _vent_under(self, player):
        """The id of the vent whose tile the player's centre is on, or None."""
        col, row = math.floor(player.x / self.tile), math.floor(player.y / self.tile)
        for vent in self.vents.values():
            if (vent["x"], vent["y"]) == (col, row):
                return vent["id"]
        return None

    def _vent_centre(self, vent_id):
        vent = self.vents[vent_id]
        return self._tile_centre(vent["x"], vent["y"])

    # --- Meetings: report, meeting table and vote ---------------------------------------

    def report(self, player_id, exam_id):
        """A living player reports a failed exam within reach, anywhere on the map, and a
        meeting starts.

        An unknown exam and an exam out of reach get the same reason, so a browser cannot
        find out about failed exams it cannot see by trying ids.
        """
        player = self._check_meeting_caller(player_id, "Ghosts cannot report")
        if not isinstance(exam_id, str):
            raise GameError("Exam must be a failed exam id")
        exam = next((e for e in self.failed_exams if e.id == exam_id), None)
        if exam is None or math.hypot(exam.x - player.x, exam.y - player.y) > REPORT_RANGE:
            raise GameError("No failed exam within reach")
        self._start_meeting(REPORT, player)

    def call_meeting(self, player_id):
        """A living player at the meeting table presses its button, once per round.

        The table's tile comes from the map ("meeting_point": [col, row]). The player
        must stand at most MEETING_RANGE from the table's edge. A map without a meeting
        point (only the small test maps) calls from anywhere. A rejected call is not used up.
        """
        player = self._check_meeting_caller(player_id, "Ghosts cannot call a meeting")
        if self.emergency is not None and self.emergency["kind"] == "fire":
            raise GameError("Not during the fire alarm")  # spec 023: reports still work
        if player.meeting_used:
            raise GameError("You have already called a meeting")
        place = self.campus.get("meeting_point")
        if place is not None:
            x, y = self._tile_centre(*place)
            if math.hypot(x - player.x, y - player.y) > MEETING_TABLE_RADIUS + MEETING_RANGE:
                raise GameError("Too far from the meeting table")
        player.meeting_used = True
        self._start_meeting(BUTTON, player)

    def _check_meeting_caller(self, player_id, ghost_reason):
        """The checks report and call_meeting share. Returns the player.

        Only while playing: a second report or call before the next tick finds the
        meeting already running, so the first one the server processes wins (R7).
        """
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Unknown player")
        if self.phase == ENDED:
            raise GameError("Game is over")
        if self.phase == MEETING:
            raise GameError("A meeting is already running")
        if self.phase != PLAYING:
            raise GameError("The game has not started yet")
        if not player.alive:
            raise GameError(ghost_reason)
        if player.vent is not None:
            raise GameError(INSIDE_VENT)
        return player

    def _start_meeting(self, reason, caller, caught=None):
        """Everyone, ghosts too, goes to their place around the meeting table and stands
        still. Whoever is inside a vent is taken out first (spec 015) and placed like
        everyone else. `caught` (spec 027): the examiner id the security guard saw, for a
        SECURITY meeting only."""
        self.phase = MEETING
        self.meeting = Meeting(
            reason, caller.id, voting_ends=self.tick + MEETING_TICKS, caught=caught
        )
        self.vent_open = {}
        for player in self.players.values():
            player.vent = None
        for player, spot in zip(self.players.values(), self._meeting_spots()):
            if spot is not None:
                player.x, player.y = spot
        for player in self.players.values():
            player.dx = player.dy = 0
            player.doing = None  # no task runs or finishes during a meeting
            player.challenge = None
            player.task_note = None
            player.fix_done_tick = None
        self.lights_on = True  # a meeting turns the lights back on
        self.emergency = None  # spec 023: and ends every other emergency

    def _meeting_spots(self):
        """One place (x, y) per player, in join order, on a circle around the meeting table.

        The places are evenly spaced: the first one north of the table, the others
        clockwise. With MEETING_CIRCLE px to the table's middle, 10 players do not overlap.
        A place that is not free floor is None: that player stays where they are (only on
        a map too tight for the circle; the campus has room, see the tests). Empty without
        a meeting point.
        """
        place = self.campus.get("meeting_point")
        if place is None:
            return []
        centre_x, centre_y = self._tile_centre(*place)
        spots = []
        for index in range(len(self.players)):
            angle = 2 * math.pi * index / len(self.players) - math.pi / 2  # -90 degrees: north
            x = centre_x + MEETING_CIRCLE * math.cos(angle)
            y = centre_y + MEETING_CIRCLE * math.sin(angle)
            spots.append(None if self.blocked(x, y) else (x, y))
        return spots

    def vote(self, player_id, target):
        """A living player votes for another living player or skips, once.

        The sender is checked before the target, as with expel. A vote for yourself is
        rejected and not used up: the player can still vote (spec 008, part 2).
        """
        voter = self.players.get(player_id)
        if voter is None:
            raise GameError("Unknown player")
        if self.phase == ENDED:
            raise GameError("Game is over")
        if self.phase != MEETING:
            raise GameError("No meeting is running")
        if self.meeting.result is not None:
            raise GameError("Voting has closed")
        if not voter.alive:
            raise GameError("Ghosts cannot vote")
        if voter.id in self.meeting.votes:
            raise GameError("You have already voted")
        if not isinstance(target, str):
            raise GameError("Target must be a player id or skip")
        if target == voter.id:
            raise GameError("You cannot vote for yourself")
        if target != SKIP:
            chosen = self.players.get(target)
            if chosen is None:
                raise GameError("Unknown target")
            if not chosen.alive:
                raise GameError("Can only vote for a living player")
        self.meeting.votes[voter.id] = target

    def _step_meeting(self):
        """Called every tick of a meeting: close the voting when due, end the meeting after
        the result time."""
        meeting = self.meeting
        if meeting.result is None:
            living = [p for p in self.players.values() if p.alive]
            if self.tick >= meeting.voting_ends or all(p.id in meeting.votes for p in living):
                self._close_voting(living)
        elif self.tick >= meeting.result_ends:
            self._end_meeting()

    def _close_voting(self, living):
        """Count the votes (R5). Whoever has not voted counts as a skip.

        A player is sent surfing only with more votes than every other player and more
        votes than skips. The player sent surfing becomes a ghost and leaves no failed exam.
        """
        votes = self.meeting.votes
        counts = {p.id: 0 for p in living}
        for target in votes.values():
            if target in counts:  # a living player (not SKIP)
                counts[target] += 1
        skips = sum(votes.get(p.id, SKIP) == SKIP for p in living)
        top = max(counts.values(), default=0)
        leaders = [player_id for player_id, count in counts.items() if count == top]
        surfing = leaders[0] if len(leaders) == 1 and top > skips else None
        if surfing is not None:
            self.players[surfing].alive = False
        self.meeting.result = {"votes": counts, "skips": skips, "surfing": surfing}
        self.meeting.result_ends = self.tick + RESULT_TICKS

    def _end_meeting(self):
        """After the result: failed exams go, cooldowns restart, play resumes, then the win
        check (so everyone has seen the result before the end screen)."""
        self.meeting = None
        self.failed_exams = []
        for player in self.players.values():
            if player.role == EXAMINER:
                player.next_expel_tick = self.tick + EXPEL_COOLDOWN_TICKS
        self.next_sabotage_tick = self.tick + SABOTAGE_COOLDOWN_TICKS
        self.phase = PLAYING
        self._check_win()

    # --- Winning and a new round --------------------------------------------------

    def _check_win(self):
        """Called after every expel, every meeting end and every player leaving while
        playing or in a meeting.

        Only living players count, so examiners voted out count as gone.
        """
        living = [p for p in self.players.values() if p.alive]
        examiners = sum(p.role == EXAMINER for p in living)
        students = sum(p.role == STUDENT for p in living)
        if examiners == 0:
            self._end(STUDENTS_WIN)
        elif examiners >= students:
            self._end(EXAMINERS_WIN)
        elif self._all_tasks_done():  # a leaver may have been the last one with open tasks
            self._end(STUDENTS_WIN)

    def _end(self, winner):
        self.phase = ENDED
        self.winner = winner
        self.meeting = None  # a player leaving can end the game during a meeting
        self.guard = None  # spec 027: he does not exist once the round has ended
        self.emergency = None  # spec 023
        self.vent_open = {}
        for player in self.players.values():
            player.vent = None  # everyone is shown on the end screen
            player.dx = player.dy = 0  # movement is rejected now, so nobody keeps walking
            player.doing = None  # and no task keeps running
            player.challenge = None
            player.task_note = None
            player.fix_done_tick = None

    def restart(self, player_id):
        """The host starts a new round with the same players. Checks before changing anything."""
        if player_id not in self.players:
            raise GameError("Unknown player")
        if self.phase != ENDED:
            raise GameError("The round is not over yet")
        if player_id != self.host_id:
            raise GameError("Only the host can start a new round")
        self._reset_round()

    def _reset_round(self):
        """Back to the lobby: no roles, no tasks, no failed exams, no meeting, everyone
        alive, with their meeting call back and on a spawn point."""
        self.phase = LOBBY
        self.winner = None
        self.failed_exams = []
        self.meeting = None
        self.guard = None  # spec 027: he does not exist in the lobby
        self.emergency = None  # spec 023
        self.fire_lost = False
        self.security_witnessed = False
        self.lights_on = True
        self.next_sabotage_tick = 0
        self.vent_open = {}
        self._place_on_spawns()
        for player in self.players.values():
            player.role = None
            player.alive = True
            player.next_expel_tick = 0
            player.vent = None
            player.next_vent_tick = 0
            player.meeting_used = False
            player.tasks = []
            player.tasks_done = []
            player.tasks_step = {}
            player.doing = None
            player.challenge = None
            player.task_note = None
            player.fix_done_tick = None

    # --- Tasks (spec 004, mini-games and fake tasks spec 012) -------------------------

    def task(self, player_id, task_id):
        """A student or a living examiner starts one of their own open tasks at its
        current station's place (spec 012, part 4: a multi-step task has more than one).

        A living examiner has fake tasks exactly like a student's real ones (spec 012,
        part 3), except a ghost examiner cannot start one; a ghost student still can,
        unchanged (R4). A station with a mini-game creates a challenge (see
        server/minigames.py); a station without one (test maps only) runs for its
        seconds, as spec 004 built it. The sender is checked before the task: an unknown
        task and another player's task get the same reason, so a browser cannot find out
        other players' tasks by trying.
        """
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Unknown player")
        if self.phase == ENDED:
            raise GameError("Game is over")
        if self.phase == MEETING:
            raise GameError("Meeting in progress")
        if self.phase != PLAYING:
            raise GameError("The game has not started yet")
        if player.role == EXAMINER and not player.alive:
            raise GameError("Ghosts cannot do tasks")
        if player.vent is not None:
            raise GameError(INSIDE_VENT)
        if not isinstance(task_id, str):
            raise GameError("Task must be a task id")
        if task_id not in player.tasks:
            raise GameError("Not one of your tasks")
        if task_id in player.tasks_done:
            raise GameError("Task already done")
        if player.doing is not None:
            raise GameError("You are already doing a task")
        if player.fix_done_tick is not None:
            raise GameError("You are fixing the lights")
        if self.emergency is not None and self.emergency["kind"] == "wifi":
            raise GameError(NO_WIFI)  # spec 023
        if self._distance_to_task(player, task_id) > TASK_RANGE:
            raise GameError("Too far from the task")
        station = self._current_station(player, task_id)
        player.doing = task_id
        player.task_note = None
        if "minigame" in station:
            player.challenge = minigames.make_challenge(station["minigame"], self.rng, self.tick, TICK_RATE)
        else:
            player.challenge = None
            player.doing_done_tick = self.tick + station["seconds"] * TICK_RATE

    def task_input(self, player_id, task_id, value):
        """An answer to the mini-game of the task the player is currently doing.

        Checked in order: phase, is this the task the player is doing, does its station
        even have a mini-game, still in range, then whether `value` has the right shape
        for that mini-game's kind. Each of those is a rejection that changes nothing. A
        value that is the wrong (but valid) answer is accepted: the mini-game's own rule
        decides what changes (usually a new challenge) and leaves a short task_note.
        """
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Unknown player")
        if self.phase == ENDED:
            raise GameError("Game is over")
        if self.phase == MEETING:
            raise GameError("Meeting in progress")
        if self.phase != PLAYING:
            raise GameError("The game has not started yet")
        if not isinstance(task_id, str):
            raise GameError("Task must be a task id")
        if player.doing != task_id:
            raise GameError("You are not doing this task")
        if player.challenge is None:
            raise GameError("This task has no mini-game")
        if self.emergency is not None and self.emergency["kind"] == "wifi":
            raise GameError(NO_WIFI)  # spec 023 (a running task is cancelled anyway)
        if self._distance_to_task(player, task_id) > TASK_RANGE:
            raise GameError("Too far from the task")
        try:
            minigames.validate_value(player.challenge["kind"], value)
        except ValueError as error:
            raise GameError(str(error)) from None
        done, note = minigames.apply_answer(player.challenge, value, self.rng, self.tick, TICK_RATE)
        if done:
            player.task_note = None
            self._finish_step(player, task_id)
            if self._all_tasks_done():
                self._end(STUDENTS_WIN)
        else:
            player.task_note = note

    def cancel_task(self, player_id, task_id):
        """Closing the mini-game panel without walking away. Only resets the running
        station; an earlier finished step of a multi-step task is unaffected."""
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Unknown player")
        if self.phase == ENDED:
            raise GameError("Game is over")
        if self.phase == MEETING:
            raise GameError("Meeting in progress")
        if self.phase != PLAYING:
            raise GameError("The game has not started yet")
        if not isinstance(task_id, str):
            raise GameError("Task must be a task id")
        if player.doing != task_id:
            raise GameError("You are not doing this task")
        player.doing = None
        player.challenge = None
        player.task_note = "Task cancelled."

    def _current_station(self, player, task_id):
        """The station of `task_id` the player is on now: the first not-yet-finished one."""
        steps = self.tasks[task_id]["steps"]
        index = min(player.tasks_step.get(task_id, 0), len(steps) - 1)
        return steps[index]

    def _finish_step(self, player, task_id):
        """The player's current station of `task_id` is done: move on to the next one,
        or, if that was the last, mark the whole task done. Always clears the running
        attempt. A multi-step task counts once, at its last station (spec 012, part 4)."""
        steps = self.tasks[task_id]["steps"]
        index = min(player.tasks_step.get(task_id, 0), len(steps) - 1)
        player.tasks_step[task_id] = index + 1
        if index + 1 >= len(steps):
            player.tasks_done.append(task_id)
        player.doing = None
        player.challenge = None

    def _step_tasks(self):
        """Called every tick while playing, after the movement.

        A station whose player is no longer within TASK_RANGE is cancelled: back to the
        start of that station, still open. A mini-game whose time limit is up is cancelled
        the same way, with a note. A plain-wait station (test maps only) whose time is up is
        done, exactly once. Then the task win (R6).
        """
        finished = False
        for player in self.players.values():
            if player.doing is None:
                continue
            if self._distance_to_task(player, player.doing) > TASK_RANGE:
                player.doing = None
                player.challenge = None
                player.task_note = None
                continue
            if player.challenge is not None:
                # Spec 031: a challenge can also be lost on its own (the seagulls).
                lost = minigames.failure(player.challenge, self.tick)
                if lost is None and self.tick >= player.challenge["deadline_tick"]:
                    lost = minigames.TIMEOUT_NOTES[player.challenge["kind"]]
                if lost is not None:
                    player.task_note = lost
                    player.doing = None
                    player.challenge = None
                continue
            if self.tick >= player.doing_done_tick:
                self._finish_step(player, player.doing)
                finished = True
        if finished and self._all_tasks_done():
            self._end(STUDENTS_WIN)

    def _distance_to_task(self, player, task_id):
        station = self._current_station(player, task_id)
        x, y = self._tile_centre(station["x"], station["y"])
        return math.hypot(x - player.x, y - player.y)

    def _task_progress(self):
        """Finished and total tasks of all students still in the game, ghosts included."""
        students = [p for p in self.players.values() if p.role == STUDENT]
        return sum(len(p.tasks_done) for p in students), sum(len(p.tasks) for p in students)

    def _all_tasks_done(self):
        done, total = self._task_progress()
        return total > 0 and done == total  # a map without tasks has no task win

    def _task_for(self, player, task_id):
        """One of the player's own tasks as they receive it: the current station's title
        and place (spec 012, part 4), with "step"/"steps" added for a multi-step task. The
        joke only shows once the whole task is done."""
        task = self.tasks[task_id]
        steps = task["steps"]
        done = task_id in player.tasks_done
        index = len(steps) - 1 if done else min(player.tasks_step.get(task_id, 0), len(steps) - 1)
        station = steps[index]
        x, y = self._tile_centre(station["x"], station["y"])
        entry = {"id": task_id, "title": station["title"], "area": station["area"]}
        entry.update({"x": x, "y": y, "done": done})
        if len(steps) > 1:
            entry["step"] = index + 1
            entry["steps"] = len(steps)
        if done:
            entry["joke"] = task["joke"]
        return entry

    # --- Lights sabotage (spec 008, part 8) ---------------------------------------------

    def sabotage(self, player_id, kind="lights"):
        """A living examiner starts one emergency (spec 023): "lights" (spec 008: living
        students then see only LIGHTS_OUT_TILES far, until someone fixes the lights or a
        meeting starts), "fire" (the fire alarm) or "wifi" (no tasks until the router is
        restarted). Only one emergency runs at a time.

        The cooldown is shared by all examiners. It runs from the start of the game, from
        the moment the lights are fixed and from the end of every meeting. Nothing a player
        receives shows who turned the lights off.
        """
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Unknown player")
        if self.phase == ENDED:
            raise GameError("Game is over")
        if self.phase == MEETING:
            raise GameError("Meeting in progress")
        if self.phase != PLAYING:
            raise GameError("The game has not started yet")
        if not player.alive:
            raise GameError("Ghosts cannot turn off the lights")
        if player.role != EXAMINER:
            raise GameError("Only examiners can turn off the lights")
        if player.vent is not None:
            raise GameError(INSIDE_VENT)
        if type(kind) is not str or kind not in SABOTAGE_KINDS:
            raise GameError("Unknown sabotage")
        if kind == "lights" and "light_switch" not in self.campus:
            raise GameError("This map has no light switch")  # nobody could fix them
        if kind != "lights" and self._sabotage_place(kind) is None:
            names = {"fire": "fire alarm", "wifi": "router"}
            raise GameError(f"This map has no {names[kind]}")
        if kind == "lights" and not self.lights_on:
            raise GameError("The lights are already off")
        if self.emergency is not None or not self.lights_on:
            raise GameError("An emergency is already running")
        if self.tick < self.next_sabotage_tick:
            left = self._seconds_until(self.next_sabotage_tick)
            prefix = "Lights" if kind == "lights" else "Sabotage"
            raise GameError(f"{prefix} cooldown: {left} s left")
        if kind == "lights":
            self.lights_on = False
        elif kind == "fire":
            self.emergency = {"kind": "fire", "ends_tick": self.tick + FIRE_TICKS, "evacuated": set()}
        else:
            self.emergency = {"kind": "wifi"}
            for other in self.players.values():  # every running task breaks off
                if other.doing is not None:
                    other.doing = None
                    other.challenge = None
                    other.task_note = NO_WIFI

    def chat(self, player_id, raw_text):
        """Spec 029: a living player says something in the meeting, while the vote is open.
        Checks everything before changing anything; the text is kept as plain text."""
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Unknown player")
        if self.phase != MEETING:
            raise GameError("You can chat only in a meeting")
        if self.meeting.result is not None:
            raise GameError("Voting is over")
        if not player.alive:
            raise GameError("Ghosts cannot chat")
        if not isinstance(raw_text, str):
            raise GameError("A message must be text")
        text = raw_text.strip()
        if not text:
            raise GameError("Write something first")
        if len(text) > CHAT_MAX:
            raise GameError(f"At most {CHAT_MAX} characters")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
            raise GameError("No line breaks or control characters")
        if self.tick < self.meeting.chat_ready.get(player.id, 0):
            raise GameError("Slow down")
        self.meeting.chat.append({"from": player.id, "text": text})
        del self.meeting.chat[:-CHAT_KEEP]
        self.meeting.chat_ready[player.id] = self.tick + CHAT_COOLDOWN_TICKS

    def _sabotage_place(self, kind):
        """The map's entry for a sabotage kind (spec 023), or None."""
        return next((s for s in self.campus.get("sabotages", []) if s["kind"] == kind), None)

    def _in_assembly(self, player):
        area = self._sabotage_place("fire")["assembly"]
        col, row = int(player.x // self.tile), int(player.y // self.tile)
        return area["x"] <= col < area["x"] + area["w"] and area["y"] <= row < area["y"] + area["h"]

    def _distance_to_router(self, player):
        router = self._sabotage_place("wifi")
        x, y = self._tile_centre(router["x"], router["y"])
        return math.hypot(x - player.x, y - player.y)

    def _end_emergency(self):
        self.emergency = None
        self.next_sabotage_tick = self.tick + SABOTAGE_COOLDOWN_TICKS
        for player in self.players.values():
            player.fix_done_tick = None

    def _step_emergency(self):
        """Every tick while playing (spec 023): fire alarm check-ins, its end and its
        time-out; the router fix of a Wi-Fi outage."""
        if self.emergency is None:
            return
        if self.emergency["kind"] == "fire":
            students = [p for p in self.players.values() if p.role == STUDENT and p.alive]
            for student in students:
                if self._in_assembly(student):
                    self.emergency["evacuated"].add(student.id)
            if all(s.id in self.emergency["evacuated"] for s in students):
                self._end_emergency()
            elif self.tick >= self.emergency["ends_tick"]:
                self.fire_lost = True
                self._end(EXAMINERS_WIN)
            return
        for player in self.players.values():  # wifi: the router fix, like the light switch
            if player.fix_done_tick is None:
                continue
            if self._distance_to_router(player) > SWITCH_RANGE:
                player.fix_done_tick = None
            elif self.tick >= player.fix_done_tick:
                self._end_emergency()
                return

    def _emergency_for(self):
        """What every player sees of the running emergency (spec 023), or None."""
        if not self.lights_on:
            return {"kind": "lights", "seconds_left": None}
        if self.emergency is None:
            return None
        if self.emergency["kind"] == "fire":
            students = [p for p in self.players.values() if p.role == STUDENT and p.alive]
            evacuated = sum(s.id in self.emergency["evacuated"] for s in students)
            return {
                "kind": "fire",
                "seconds_left": self._seconds_until(self.emergency["ends_tick"]),
                "evacuated": evacuated,
                "students": len(students),
            }
        return {"kind": "wifi", "seconds_left": None}

    def fix(self, player_id):
        """A living player at the light switch starts fixing the lights. Spec 033: students
        and examiners alike (an examiner may blend in by fixing).

        It takes FIX_SECONDS; the player may move but must stay within SWITCH_RANGE
        (see _step_lights). One player is enough.
        """
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Unknown player")
        if self.phase == ENDED:
            raise GameError("Game is over")
        if self.phase == MEETING:
            raise GameError("Meeting in progress")
        if self.phase != PLAYING:
            raise GameError("The game has not started yet")
        if not player.alive:
            raise GameError("Ghosts cannot fix the lights")
        if player.vent is not None:
            raise GameError(INSIDE_VENT)
        wifi = self.emergency is not None and self.emergency["kind"] == "wifi"
        if self.lights_on and not wifi:
            raise GameError("The lights are on")
        if player.fix_done_tick is not None:
            raise GameError("You are already fixing the lights")
        if player.doing is not None:
            raise GameError("You are already doing a task")
        if wifi:  # spec 023: the router, same rules as the light switch
            if self._distance_to_router(player) > SWITCH_RANGE:
                raise GameError("Too far from the router")
        elif self._distance_to_switch(player) > SWITCH_RANGE:
            raise GameError("Too far from the light switch")
        player.fix_done_tick = self.tick + FIX_TICKS

    def _step_lights(self):
        """Called every tick while playing: a student who left the switch stops fixing
        (back to zero); the first one whose time is up turns the lights on for everyone."""
        if self.emergency is not None and self.emergency["kind"] == "wifi":
            return  # spec 023: the router fix is handled by _step_emergency
        for player in self.players.values():
            if player.fix_done_tick is None:
                continue
            if self._distance_to_switch(player) > SWITCH_RANGE:
                player.fix_done_tick = None
            elif self.tick >= player.fix_done_tick:
                self.lights_on = True
                self.next_sabotage_tick = self.tick + SABOTAGE_COOLDOWN_TICKS
        if self.lights_on:
            for player in self.players.values():
                player.fix_done_tick = None

    def _distance_to_switch(self, player):
        x, y = self._tile_centre(*self.campus["light_switch"])
        return math.hypot(x - player.x, y - player.y)

    def _vision_radius_for(self, viewer):
        """How far a player sees, in px. Only living students are affected by the lights."""
        if not self.lights_on and viewer.role == STUDENT and viewer.alive:
            return self.lights_out_radius
        return self.vision_radius

    # --- Input and movement ---------------------------------------------------

    def set_input(self, player_id, message):
        """Store a player's direction. Validates everything before changing anything."""
        player = self.players.get(player_id)
        if player is None:
            raise GameError("Unknown player")
        if self.phase == ENDED:
            raise GameError("Game is over")
        if self.phase == MEETING:
            raise GameError("Meeting in progress")
        if not isinstance(message, dict) or message.get("type") != "input":
            raise GameError("Not an input message")
        dx, dy = message.get("dx"), message.get("dy")
        if not (is_direction(dx) and is_direction(dy)):
            raise GameError("dx and dy must each be -1, 0 or 1")
        if player.vent is not None and (dx, dy) != (0, 0):
            raise GameError(INSIDE_VENT)  # stopping is always accepted
        player.dx, player.dy = dx, dy

    def step(self):
        """Advance the game by one tick: move every player in their direction, then let
        the running tasks go on.

        In a meeting nobody moves; the tick only counts towards the voting and result time.
        """
        self.tick += 1
        if self.phase == MEETING:
            self._step_meeting()
            return
        for player in self.players.values():
            if player.dx == 0 and player.dy == 0:
                continue
            self._walk(player)
        if self.phase == PLAYING and self.guard is not None:
            guard.step_guard(
                self.guard,
                self._guard_route,
                GUARD_STEP,
                GUARD_PAUSE_CHANCE,
                GUARD_PAUSE_SECONDS,
                TICK_RATE,
                (math.radians(GUARD_SWEEP_DEGREES), GUARD_SWEEP_TICKS),
                self.rng,
                self.tick,
            )
        if self.phase == PLAYING:
            self._step_tasks()
        if self.phase == PLAYING:  # the last task may just have ended the game
            self._step_lights()
        if self.phase == PLAYING:
            self._step_emergency()  # spec 023

    def _walk(self, player):
        """One tick of walking: one fixed step, first along x and then along y.

        Each axis moves on its own, so a diagonal walk into a wall slides along it. A
        straight walk that a wall stops slides round the wall's corner (see _slide).
        """
        length = math.hypot(player.dx, player.dy)  # 1 straight, about 1.41 diagonal
        left_x = self._move_axis(player, player.dx / length * STEP, 0)
        left_y = self._move_axis(player, 0, player.dy / length * STEP)
        if player.dy == 0 and left_x > 0:
            self._slide(player, player.dx, 0, left_x)
        elif player.dx == 0 and left_y > 0:
            self._slide(player, 0, player.dy, left_y)

    def _move_axis(self, player, mx, my):
        """Move in small pieces of at most 1 px and stop at the first piece that hits a wall.
        Returns the distance that was not walked (0 if nothing was in the way).

        So a player walks up to a wall (to within 1 px) but never into it, and a move
        straight into a wall leaves the position unchanged. A ghost ignores walls and is
        only stopped by the edge of the map (spec 008, part 3).
        """
        remaining = abs(mx) + abs(my)
        sign_x = (mx > 0) - (mx < 0)
        sign_y = (my > 0) - (my < 0)
        while remaining > 0:
            part = min(1.0, remaining)
            nx, ny = player.x + sign_x * part, player.y + sign_y * part
            if self.blocked(nx, ny, walls=player.alive):
                return remaining
            player.x, player.y = nx, ny
            remaining -= part
        return 0

    def _slide(self, player, dx, dy, distance):
        """Slide round a corner (spec 011): a wall stopped a straight walk in direction
        (dx, dy) with `distance` px of the step left.

        If the way ahead is free at most CORNER_SLIDE px to one side, the player moves
        there with what is left of the step and then walks on. So a doorway or a gap of
        one tile needs no precise aiming. In front of a plain wall no side is free and
        nothing moves. The nearest free side wins; a step never gets longer than STEP.
        """
        for offset in range(1, CORNER_SLIDE + 1):
            for side in (-1, 1):
                # Sideways is along y for a walk along x, and the other way round.
                side_x, side_y = side * abs(dy), side * abs(dx)
                ahead_x = player.x + dx + side_x * offset
                ahead_y = player.y + dy + side_y * offset
                if not self.blocked(ahead_x, ahead_y, walls=player.alive):
                    slid = min(distance, offset)
                    self._move_axis(player, side_x * slid, side_y * slid)
                    self._move_axis(player, dx * (distance - slid), dy * (distance - slid))
                    return

    def blocked(self, x, y, walls=True):
        """True if a player square centred at (x, y) overlaps a wall or leaves the map.

        With walls=False (a ghost) only leaving the map counts.
        """
        left = math.floor((x - PLAYER_HALF) / self.tile)
        right = math.floor((x + PLAYER_HALF) / self.tile - 1e-9)
        top = math.floor((y - PLAYER_HALF) / self.tile)
        bottom = math.floor((y + PLAYER_HALF) / self.tile - 1e-9)
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                if row < 0 or row >= len(self.grid) or col < 0 or col >= len(self.grid[row]):
                    return True
                if walls and self.grid[row][col] == "#":
                    return True
        return False

    # --- What the browsers receive --------------------------------------------

    def area_at(self, x, y):
        """Name of the campus area whose rectangle contains the point, or None (a corridor)."""
        col, row = math.floor(x / self.tile), math.floor(y / self.tile)
        for area in self.campus["areas"]:
            in_columns = area["x"] <= col < area["x"] + area["w"]
            in_rows = area["y"] <= row < area["y"] + area["h"]
            if in_columns and in_rows:
                return area["name"]
        return None

    def _in_sight(self, viewer, x, y):
        """True if the viewer sees a player or failed exam at (x, y) (spec 010, part 3).

        Its centre must be within the vision radius, measured between centres. Then one
        straight line from the viewer's centre must be clear: to its centre or to one of
        the four corners of its square. So whoever sticks out behind a wall is seen.
        """
        if math.hypot(x - viewer.x, y - viewer.y) > self._vision_radius_for(viewer):
            return False
        h = PLAYER_HALF
        points = ((x, y), (x - h, y - h), (x + h, y - h), (x - h, y + h), (x + h, y + h))
        return any(self.sight_clear(viewer.x, viewer.y, px, py) for px, py in points)

    def sight_clear(self, x0, y0, x1, y1):
        """True if the straight line between two points crosses no sight-blocking tile.

        The line is cut at every grid line it crosses. Each piece then lies inside one
        tile, and the middle of the piece tells which. A line through the corner of a tile
        has no piece inside that tile, so only touching a corner does not block.
        """
        t = self.tile
        dx, dy = x1 - x0, y1 - y0
        cuts = [0.0, 1.0]  # places along the line, from 0 (its start) to 1 (its end)
        if dx:
            low, high = min(x0, x1), max(x0, x1)
            cuts += [(k * t - x0) / dx for k in range(math.floor(low / t) + 1, math.ceil(high / t))]
        if dy:
            low, high = min(y0, y1), max(y0, y1)
            cuts += [(k * t - y0) / dy for k in range(math.floor(low / t) + 1, math.ceil(high / t))]
        cuts.sort()
        for a, b in zip(cuts, cuts[1:]):
            if b - a > 1e-9:  # two cuts at the same place: the line goes through a corner
                middle = (a + b) / 2
                if self._blocks_sight_at(x0 + dx * middle, y0 + dy * middle):
                    return False
        return True

    def _blocks_sight_at(self, x, y):
        """True if the point lies inside sight-blocking tiles.

        A point exactly on the line between two tiles (a line of sight running along a
        wall) only counts if the tiles on both sides block: along a wall's face is clear,
        along the joint between two wall tiles is not.
        """
        t = self.tile
        col, row = math.floor(x / t), math.floor(y / t)
        cols = (col - 1, col) if x % t == 0 else (col,)
        rows = (row - 1, row) if y % t == 0 else (row,)
        return all(self._blocks_sight(c, r) for c in cols for r in rows)

    def _blocks_sight(self, col, row):
        inside = 0 <= row < len(self.sight) and 0 <= col < len(self.sight[row])
        return inside and self.sight[row][col] == "#"

    def snapshot(self, see_ghosts=False, viewer=None):
        """The part players may see: phase, host, names, positions, colours and failed exams.

        Never a role. Ghosts are left out unless see_ghosts is set. With a viewer, players
        and failed exams the viewer cannot see (too far or behind a wall) are left out too.
        A player inside a vent is left out for everyone but themselves (spec 015).
        "open_vents" lists the hatches that show open right now, by vent id only: never who
        used them, and with a viewer only the ones in sight.
        """
        players = [
            p
            for p in self.players.values()
            if (p.alive or see_ghosts)
            and (p.vent is None or p is viewer)
            and (viewer is None or p is viewer or self._in_sight(viewer, p.x, p.y))
        ]
        open_vents = [
            vent_id
            for vent_id, until in self.vent_open.items()
            if self.tick < until
            and (viewer is None or self._in_sight(viewer, *self._vent_centre(vent_id)))
        ]
        exams = [
            e for e in self.failed_exams if viewer is None or self._in_sight(viewer, e.x, e.y)
        ]
        state = {
            "type": "state",
            "tick": self.tick,
            "phase": self.phase,
            "host": self.host_id,
            "settings": {"expellers": self.examiner_setting},
            "players": [
                {"id": p.id, "name": p.name, "x": round(p.x, 1), "y": round(p.y, 1)}
                for p in players
            ],
            # Kept next to the player entries, so those stay exactly {id, name, x, y}.
            "colors": {p.id: p.color for p in players},
            "hats": {p.id: p.hat for p in players},  # spec 022
            "failed_exams": [{"id": e.id, "x": round(e.x, 1), "y": round(e.y, 1)} for e in exams],
            "open_vents": open_vents,
        }
        # Spec 027: present only when the guard exists and, for a living player while
        # playing, only when that player's own sight (their own radius, their own line of
        # sight, shrunk by the lights if the lights are off) reaches him. A ghost, the lobby,
        # a meeting and the end screen use no viewer and so always get him when he exists.
        if self.guard is not None and (viewer is None or self._in_sight(viewer, self.guard.x, self.guard.y)):
            state["guard"] = {
                "x": round(self.guard.x, 1),
                "y": round(self.guard.y, 1),
                "facing": round(self.guard.facing, 3),
                "paused": self.guard.paused,
            }
        return state

    def snapshot_for(self, player_id):
        """What one player may know: the shared snapshot plus their own role and state.

        - While playing, a living player only gets the players and failed exams within
          the vision radius (spec 005) with a clear line of sight (spec 010). In the
          lobby, in a meeting and after the end there is no limit (ghosts stay hidden from
          the living until the end).
        - An examiner also gets the fellow examiners' ids, their own cooldowns (expel and
          vent) and the vent they are inside (never anyone else's).
        - A ghost (and everyone once the game has ended) sees all players and who is a ghost.
        - Only in ENDED does anyone get other players' roles, together with the winner.
        - From the start on, everyone gets the shared task progress (students only, spec
          004) and their own tasks and the one they are doing, student or examiner alike
          (spec 012, part 3: an examiner's are fake); never another player's.
        - From the start on, everyone gets whether the lights are on and how far they
          themselves see. A student also gets their own fixing, an examiner the cooldown.
        """
        me = self.players.get(player_id)
        if me is None:
            raise GameError("Unknown player")
        see_ghosts = not me.alive or self.phase == ENDED
        limited = self.phase == PLAYING and me.alive
        state = self.snapshot(see_ghosts, viewer=me if limited else None)
        state["area"] = self.area_at(me.x, me.y)
        state["role"] = me.role
        state["alive"] = me.alive
        state["meeting_used"] = me.meeting_used
        if self.phase == MEETING:
            state["meeting"] = self._meeting_for(me)
            state["chat"] = [dict(m) for m in self.meeting.chat]  # spec 029
            if self.meeting.result is not None:
                # Spec 019: once counted, who voted for whom ("skip" or a player id); only
                # votes actually cast. Never sent while the vote is still running.
                state["ballots"] = dict(self.meeting.votes)
        if self.phase != LOBBY:
            state["lights_on"] = self.lights_on
            state["emergency"] = self._emergency_for()  # spec 023
            state["vision_radius"] = self._vision_radius_for(me)
            # Spec 033: every role can fix, so every role gets its own "fixing".
            state["fixing"] = None
            if me.fix_done_tick is not None:
                state["fixing"] = {"seconds_left": self._seconds_until(me.fix_done_tick)}
            if me.role == EXAMINER:
                state["sabotage_cooldown"] = self._seconds_until(self.next_sabotage_tick)
            done, total = self._task_progress()
            state["task_progress"] = {"done": done, "total": total}
            # Every player has tasks from here on, student or examiner (spec 012, part
            # 3): an examiner's are fake and never count in task_progress above, but the
            # shape of what they receive is exactly a student's.
            state["tasks"] = [self._task_for(me, task_id) for task_id in me.tasks]
            state["doing"] = None
            state["task_note"] = me.task_note
            if me.doing is not None:
                if me.challenge is not None:
                    state["doing"] = {
                        "task": me.doing,
                        "seconds_left": self._seconds_until(me.challenge["deadline_tick"]),
                        "challenge": minigames.public_view(me.challenge, self.tick, TICK_RATE),
                    }
                else:
                    seconds_left = self._seconds_until(me.doing_done_tick)
                    state["doing"] = {"task": me.doing, "seconds_left": seconds_left}
        if see_ghosts:
            state["ghosts"] = [p.id for p in self.players.values() if not p.alive]
        if me.role == EXAMINER:
            state["fellow_examiners"] = [
                p.id for p in self.players.values() if p.role == EXAMINER and p.id != me.id
            ]
            state["expel_cooldown"] = self._cooldown_left(me)
            state["vent"] = me.vent
            state["vent_cooldown"] = self._seconds_until(me.next_vent_tick)
        if self.phase == ENDED:
            state["winner"] = self.winner
            state["roles"] = {p.id: p.role for p in self.players.values()}
            state["fire_lost"] = self.fire_lost  # spec 023
            # Spec 027: True only when the expel that ended the game was itself seen.
            state["security_witnessed"] = self.security_witnessed
        return state

    def _meeting_for(self, me):
        """The meeting as one player may see it: who has voted, never whom they voted for."""
        meeting = self.meeting
        voting = meeting.result is None
        return {
            "reason": meeting.reason,
            "called_by": meeting.called_by,
            "caught": meeting.caught,  # spec 027: None for a report or a button meeting
            "living": [p.id for p in self.players.values() if p.alive],
            "voted": [p.id for p in self.players.values() if p.id in meeting.votes],
            "my_vote": meeting.votes.get(me.id),
            "seconds_left": self._seconds_until(
                meeting.voting_ends if voting else meeting.result_ends
            ),
            "result": meeting.result,
        }
