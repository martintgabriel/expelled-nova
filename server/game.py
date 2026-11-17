"""Game rules: lobby, host, secret roles, live movement, expelling, ghosts, meetings and
votes, the end of a round, player colours and the vision radius. Plain Python, no network
code, so it can be tested directly.

The server owns the truth: browsers only send a direction (dx, dy), "start", "expel",
"report", "bell", "vote" or "restart". Every tick the server moves each player a fixed
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

TICK_RATE = 20  # server updates per second
SPEED = 160.0  # pixels per second
STEP = SPEED / TICK_RATE  # pixels per tick (8)
PLAYER_HALF = 10  # a player is a 20 x 20 px square; this is half its side
MIN_PLAYERS = 4  # needed to start a game
MAX_PLAYERS = 10
NAME_MAX = 16
MAX_MESSAGE_BYTES = 512
RATE_LIMIT = 30  # messages per second per connection
MESSAGE_TYPES = {"join", "input", "start", "expel", "report", "bell", "vote", "restart"}
EXPEL_RANGE = 48  # px between centres, about 1.5 tiles
EXPEL_COOLDOWN = 20  # seconds between two expels by the same examiner
EXPEL_COOLDOWN_TICKS = EXPEL_COOLDOWN * TICK_RATE  # 400
VISION_TILES = 6  # how far a living player sees while playing, in tiles
REPORT_RANGE = 48  # px from a player's centre to a failed exam, about 1.5 tiles
MEETING_SECONDS = 60  # voting time
RESULT_SECONDS = 5  # how long the result is shown before play resumes
MEETING_TICKS = MEETING_SECONDS * TICK_RATE  # 1200
RESULT_TICKS = RESULT_SECONDS * TICK_RATE  # 100
MEETING_ROOM = "Auditorium"  # the map area where everyone gathers for a meeting
# Colour numbers 0-9, one per player. Which number is which colour is drawing (web/render.js).
PLAYER_COLORS = range(MAX_PLAYERS)

# Game phases.
LOBBY = "lobby"  # before the start: players join and walk around
PLAYING = "playing"
MEETING = "meeting"  # everyone in the Auditorium: voting, then the result; nobody moves
ENDED = "ended"  # a side has won; all roles are revealed until the host restarts

# Roles. Secret: a player only ever receives their own (see Game.snapshot_for).
STUDENT = "student"
EXAMINER = "examiner"

# Why a meeting was called, and the vote for nobody.
REPORT = "report"
BELL = "bell"
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
    alive: bool = True  # False = ghost: still walks, cannot expel or be expelled
    color: int = 0  # colour number, unique in the game, kept until the player leaves
    next_expel_tick: int = 0  # first tick at which this player may expel (again)
    bell_used: bool = False  # one bell per player per round


@dataclass
class FailedExam:
    """The "6/20" sheet left on the floor where a student was expelled."""

    id: str
    x: float
    y: float


@dataclass
class Meeting:
    """A running meeting. The votes stay on the server: players only learn who has voted."""

    reason: str  # REPORT or BELL
    called_by: str  # player id
    voting_ends: int  # the tick at which the voting closes at the latest
    votes: dict = field(default_factory=dict)  # voter id -> target id or SKIP
    result: dict | None = None  # set when the voting closes
    result_ends: int = 0  # the tick at which play resumes (set together with the result)


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


def is_direction(value):
    # type() instead of isinstance(): True/False are ints in Python and must be rejected.
    return type(value) is int and value in (-1, 0, 1)


class Game:
    def __init__(self, campus, rng=None):
        self.campus = campus
        self.tile = campus["tile_size"]
        self.vision_radius = VISION_TILES * self.tile  # px between centres
        self.grid = campus["grid"]
        self.players = {}  # by id, in join order (Python dicts keep insertion order)
        self.tick = 0
        self.next_id = 1
        self.phase = LOBBY
        self.winner = None  # STUDENTS_WIN or EXAMINERS_WIN once the phase is ENDED
        self.failed_exams = []  # FailedExam objects, visible to everyone
        self.next_exam_id = 1
        self.meeting = None  # a Meeting while the phase is MEETING
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
        x, y = self._tile_centre(*self._free_spawn())
        player = Player(id=f"p{self.next_id}", name=name, x=x, y=y, color=self._free_color())
        self.next_id += 1
        self.players[player.id] = player
        return player

    def leave(self, player_id):
        """Remove a player. If it was the host, the next-longest player is host automatically.

        While playing or in a meeting, a player leaving can decide the game (see _check_win).
        During the vote, the leaver's vote and the votes for them are taken back.
        """
        self.players.pop(player_id, None)
        if not self.players:
            # Everyone has gone: open a clean lobby again, otherwise nobody could ever join.
            self._reset_round()
            return
        if self.phase == MEETING and self.meeting.result is None:
            self.meeting.votes = {
                voter: target
                for voter, target in self.meeting.votes.items()
                if player_id not in (voter, target)
            }
        if self.phase in (PLAYING, MEETING):
            self._check_win()

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
            player.next_expel_tick = self.tick + EXPEL_COOLDOWN_TICKS  # first cooldown
        self.phase = PLAYING

    def _free_spawn(self):
        """First spawn point nobody is standing on (falls back to the first one)."""
        taken = {(p.x, p.y) for p in self.players.values()}
        for col, row in self.campus["spawns"]:
            if self._tile_centre(col, row) not in taken:
                return col, row
        return self.campus["spawns"][0]

    def _tile_centre(self, col, row):
        return (col + 0.5) * self.tile, (row + 0.5) * self.tile

    def _free_color(self):
        """The lowest colour number nobody in the game has (there are as many as players)."""
        taken = {p.color for p in self.players.values()}
        return min(color for color in PLAYER_COLORS if color not in taken)

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
        self.failed_exams.append(FailedExam(f"e{self.next_exam_id}", target.x, target.y))
        self.next_exam_id += 1
        examiner.next_expel_tick = self.tick + EXPEL_COOLDOWN_TICKS
        self._check_win()

    def _cooldown_left(self, player):
        """Whole seconds until the player may expel, rounded up (0 = ready)."""
        return self._seconds_until(player.next_expel_tick)

    def _seconds_until(self, tick):
        """Whole seconds from now until the given tick, rounded up (0 = now or past)."""
        return max(0, math.ceil((tick - self.tick) / TICK_RATE))

    # --- Meetings: report, bell and vote -----------------------------------------------

    def report(self, player_id, exam_id):
        """A living player reports a failed exam within reach, and a meeting starts.

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

    def bell(self, player_id):
        """A living player rings the bell, anywhere on the map, once per round."""
        player = self._check_meeting_caller(player_id, "Ghosts cannot ring the bell")
        if player.bell_used:
            raise GameError("You have already rung the bell")
        player.bell_used = True
        self._start_meeting(BELL, player)

    def _check_meeting_caller(self, player_id, ghost_reason):
        """The checks report and bell share. Returns the player.

        Only while playing: a second report or bell before the next tick finds the
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
        return player

    def _start_meeting(self, reason, caller):
        """Everyone, ghosts too, goes to their own Auditorium tile and stands still."""
        self.phase = MEETING
        self.meeting = Meeting(reason, caller.id, voting_ends=self.tick + MEETING_TICKS)
        # zip() stops at the shorter list: players without a tile stay where they are.
        for player, (col, row) in zip(self.players.values(), self._meeting_tiles()):
            player.x, player.y = self._tile_centre(col, row)
        for player in self.players.values():
            player.dx = player.dy = 0

    def _meeting_tiles(self):
        """The Auditorium's floor tiles in the order players are seated (join order).

        First every second tile of every second row, in reading order, so no two players
        stand on neighbouring tiles; then the other floor tiles. Empty without an Auditorium.
        """
        area = next((a for a in self.campus["areas"] if a["name"] == MEETING_ROOM), None)
        if area is None:
            return []
        floor = [
            (col, row)
            for row in range(area["y"], area["y"] + area["h"])
            for col in range(area["x"], area["x"] + area["w"])
            if not self.blocked(*self._tile_centre(col, row))
        ]
        spaced = [
            (col, row)
            for col, row in floor
            if (col - area["x"]) % 2 == 0 and (row - area["y"]) % 2 == 0
        ]
        return spaced + [tile for tile in floor if tile not in spaced]

    def vote(self, player_id, target):
        """A living player votes for a living player (themself too) or skips, once.

        The sender is checked before the target, as with expel.
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

    def _end(self, winner):
        self.phase = ENDED
        self.winner = winner
        self.meeting = None  # a player leaving can end the game during a meeting
        for player in self.players.values():
            player.dx = player.dy = 0  # movement is rejected now, so nobody keeps walking

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
        """Back to the lobby: no roles, no failed exams, no meeting, everyone alive, with
        their bell back and on a spawn point."""
        self.phase = LOBBY
        self.winner = None
        self.failed_exams = []
        self.meeting = None
        spawns = self.campus["spawns"]
        for index, player in enumerate(self.players.values()):
            player.x, player.y = self._tile_centre(*spawns[index % len(spawns)])
            player.dx = player.dy = 0
            player.role = None
            player.alive = True
            player.next_expel_tick = 0
            player.bell_used = False

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
        player.dx, player.dy = dx, dy

    def step(self):
        """Advance the game by one tick: move every player in their direction.

        In a meeting nobody moves; the tick only counts towards the voting and result time.
        """
        self.tick += 1
        if self.phase == MEETING:
            self._step_meeting()
            return
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
        """True if the point is within the vision radius of the viewer (a plain circle)."""
        return math.hypot(x - viewer.x, y - viewer.y) <= self.vision_radius

    def snapshot(self, see_ghosts=False, viewer=None):
        """The part players may see: phase, host, names, positions, colours and failed exams.

        Never a role. Ghosts are left out unless see_ghosts is set. With a viewer, players
        and failed exams outside the viewer's vision radius are left out as well.
        """
        players = [
            p
            for p in self.players.values()
            if (p.alive or see_ghosts)
            and (viewer is None or p is viewer or self._in_sight(viewer, p.x, p.y))
        ]
        exams = [
            e for e in self.failed_exams if viewer is None or self._in_sight(viewer, e.x, e.y)
        ]
        return {
            "type": "state",
            "tick": self.tick,
            "phase": self.phase,
            "host": self.host_id,
            "players": [
                {"id": p.id, "name": p.name, "x": round(p.x, 1), "y": round(p.y, 1)}
                for p in players
            ],
            # Kept next to the player entries, so those stay exactly {id, name, x, y}.
            "colors": {p.id: p.color for p in players},
            "failed_exams": [{"id": e.id, "x": round(e.x, 1), "y": round(e.y, 1)} for e in exams],
        }

    def snapshot_for(self, player_id):
        """What one player may know: the shared snapshot plus their own role and state.

        - While playing, a living player only gets the players and failed exams within
          the vision radius (spec 005). In the lobby, in a meeting and after the end there
          is no limit (ghosts stay hidden from the living until the end).
        - An examiner also gets the fellow examiners' ids and their own cooldown.
        - A ghost (and everyone once the game has ended) sees all players and who is a ghost.
        - Only in ENDED does anyone get other players' roles, together with the winner.
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
        state["bell_used"] = me.bell_used
        if self.phase == MEETING:
            state["meeting"] = self._meeting_for(me)
        if see_ghosts:
            state["ghosts"] = [p.id for p in self.players.values() if not p.alive]
        if me.role == EXAMINER:
            state["fellow_examiners"] = [
                p.id for p in self.players.values() if p.role == EXAMINER and p.id != me.id
            ]
            state["expel_cooldown"] = self._cooldown_left(me)
        if self.phase == ENDED:
            state["winner"] = self.winner
            state["roles"] = {p.id: p.role for p in self.players.values()}
        return state

    def _meeting_for(self, me):
        """The meeting as one player may see it: who has voted, never whom they voted for."""
        meeting = self.meeting
        voting = meeting.result is None
        return {
            "reason": meeting.reason,
            "called_by": meeting.called_by,
            "living": [p.id for p in self.players.values() if p.alive],
            "voted": [p.id for p in self.players.values() if p.id in meeting.votes],
            "my_vote": meeting.votes.get(me.id),
            "seconds_left": self._seconds_until(
                meeting.voting_ends if voting else meeting.result_ends
            ),
            "result": meeting.result,
        }
