"""Tests for spec 038.

Part 2: the in-game handbook can never drift from the rules again. The handbook in
web/index.html is plain text for people, but every number in it is a rule the server
decides. These tests read the handbook and compare each number with the constant or
function in server/game.py it describes.

Part 3 (further down): a whole round over the real WebSocket with four clients, the
rejections that had no test (docs/review.md, M8) and a disconnect during a meeting.
"""

import asyncio
import contextlib
import copy
import dataclasses
import html
import json
import random
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import main as server_main
from server.game import (
    ENDED,
    EXAMINER,
    EXPEL_COOLDOWN,
    FIRE_SECONDS,
    FIX_SECONDS,
    LOBBY,
    MAX_MESSAGE_BYTES,
    MAX_PLAYERS,
    MEETING,
    MEETING_TICKS,
    MIN_PLAYERS,
    PLAYING,
    SABOTAGE_COOLDOWN,
    SETTLE_DISTANCE,
    SKIP,
    SPEED,
    STUDENT,
    STUDENTS_WIN,
    TICK_RATE,
    VENT_COOLDOWN,
    Game,
    GameError,
    load_map,
    tasks_per_player,
)
from server.main import app

INDEX = Path(__file__).resolve().parent.parent / "web" / "index.html"

# The failed exam's grade (6/20) is part of the story (BRD EX05), not a rule.
STORY_GRADE = "6/20"

NUMBER_WORDS = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def handbook_text():
    """The handbook's visible text: from the help panel to its buttons, tags removed."""
    page = INDEX.read_text(encoding="utf-8")
    start = page.rindex("<", 0, page.index('id="help-panel"'))
    end = page.rindex("<", 0, page.index('id="end-round-button"'))
    text = re.sub(r"<[^>]+>", " ", page[start:end])
    return " ".join(html.unescape(text).split())


def sentence_with(word):
    """The handbook sentence that contains `word`, to show in a failing assertion."""
    return next((s for s in re.split(r"(?<=[.:])\s", handbook_text()) if word in s), "")


def task_bands():
    """[(tasks, fewest players, most players)] from tasks_per_player, e.g. (5, 4, 5)."""
    bands = []
    for players in range(MIN_PLAYERS, MAX_PLAYERS + 1):
        count = tasks_per_player(players)
        if bands and bands[-1][0] == count:
            bands[-1] = (count, bands[-1][1], players)
        else:
            bands.append((count, players, players))
    return bands


def test_the_handbook_names_the_smallest_task_count_in_words():
    fewest = tasks_per_player(MIN_PLAYERS)
    assert f"at least {NUMBER_WORDS[fewest]} errands" in handbook_text(), sentence_with("errands")


def test_the_handbook_gives_the_task_count_for_every_round_size():
    text = handbook_text()
    for count, fewest, most in task_bands():
        assert f"{count} with {fewest}–{most}" in text, sentence_with("errands")


def test_the_handbook_gives_the_expel_cooldown():
    assert f"wait {EXPEL_COOLDOWN} seconds" in handbook_text(), sentence_with("wait")


def test_the_handbook_gives_the_time_to_fix_the_lights():
    assert f"light switch in Student Services for {FIX_SECONDS} seconds" in handbook_text()


def test_the_handbook_gives_the_fire_alarm_time():
    assert f"within {FIRE_SECONDS} seconds" in handbook_text()


def test_the_handbook_gives_the_time_to_restart_the_router():
    # The router is fixed like the light switch (FIX_TICKS, game.py: fix and _step_emergency).
    assert f"router in the Library ({FIX_SECONDS} seconds)" in handbook_text()


def test_every_number_in_the_handbook_is_a_rule_from_the_server():
    """A number added to the handbook later must be added here too, with its constant."""
    allowed = {EXPEL_COOLDOWN, FIRE_SECONDS, FIX_SECONDS}
    for count, fewest, most in task_bands():
        allowed |= {count, fewest, most}
    text = handbook_text().replace(STORY_GRADE, "")
    found = {int(number) for number in re.findall(r"\d+", text)}
    assert found <= allowed, f"numbers without a rule: {sorted(found - allowed)}"
    words = {word for number, word in NUMBER_WORDS.items() if number not in allowed}
    stale = [word for word in words if re.search(rf"\b{word}\b", text, re.IGNORECASE)]
    assert not stale, f"number words without a rule: {stale}"


# --- Part 3: a whole round over the WebSocket (docs/review.md, M7) -------------------------

# How many server messages to read at most while waiting for one (30 s of state updates).
# A client that was not read for a while has a backlog of states, so this is generous.
PATIENCE = 30 * TICK_RATE
# Fixes the roles and tasks. The tests still read who got which role; they only need some
# student to have the "gate" task, whose mini-game answer is shown to the player.
SEED = 1


def receive_until(ws, predicate, limit=PATIENCE):
    """Read messages until one matches, or fail after `limit` messages."""
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def join(ws, name):
    ws.send_json({"type": "join", "name": name})
    reply = receive_until(ws, lambda m: m["type"] in ("welcome", "error"))
    assert reply["type"] == "welcome", reply
    return reply["id"]


def state_where(check):
    return lambda m: m["type"] == "state" and check(m)


def phase_is(phase):
    return state_where(lambda m: m["phase"] == phase)


def error_reason(ws):
    return receive_until(ws, lambda m: m["type"] == "error")["reason"]


def test_a_whole_round_over_the_websocket(fresh_game):
    """Four browsers play one round from the lobby to the next round, every step sent as a
    real message: vote_host, start, task, task_cancel, task_input, expel, report, chat,
    vote, the end screen, restart, start again and end_round."""
    game = fresh_game
    names = ["Ana", "Ben", "Cleo", "Dan"]
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            ws = dict(zip(names, (a, b, c, d)))
            ids = {name: join(ws[name], name) for name in names}
            assert game.host_id == ids["Ana"]

            # Lobby: three of the four elect Cleo as host (more than half, spec 037).
            for voter in ("Ben", "Cleo", "Dan"):
                ws[voter].send_json({"type": "vote_host", "target": ids["Cleo"]})
            receive_until(c, state_where(lambda m: m["host"] == ids["Cleo"]))

            # The old host can no longer start; the new one can.
            a.send_json({"type": "start"})
            assert error_reason(a) == "Only the host can start the game"
            game.rng = random.Random(SEED)
            c.send_json({"type": "start"})
            receive_until(c, phase_is(PLAYING))
            game.guard = None  # no security meeting by chance: this test is about the round

            role = {name: game.players[ids[name]].role for name in names}
            examiner = next(name for name in names if role[name] == EXAMINER)
            students = [name for name in names if role[name] == STUDENT]
            doer = next(n for n in students if "gate" in game.players[ids[n]].tasks)
            victim = next(n for n in students if n != doer)
            third = next(n for n in students if n not in (doer, victim))
            me = ws[doer]

            # A task: walk to the gate (placed there), start it, cancel it, start it again
            # and answer the mini-game with the card number the player is shown.
            state = receive_until(me, phase_is(PLAYING))
            gate = next(task for task in state["tasks"] if task["id"] == "gate")
            doer_player = game.players[ids[doer]]
            doer_player.x, doer_player.y = gate["x"], gate["y"]
            me.send_json({"type": "task", "task": "gate"})
            state = receive_until(me, state_where(lambda m: m["doing"] is not None))
            assert state["doing"]["task"] == "gate"
            me.send_json({"type": "task_cancel", "task": "gate"})
            receive_until(me, state_where(lambda m: m["doing"] is None))
            me.send_json({"type": "task", "task": "gate"})
            state = receive_until(me, state_where(lambda m: m["doing"] is not None))
            number = state["doing"]["challenge"]["number"]
            me.send_json({"type": "task_input", "task": "gate", "value": number})
            state = receive_until(
                me, state_where(lambda m: any(t["id"] == "gate" and t["done"] for t in m["tasks"]))
            )
            assert state["task_progress"]["done"] == 1

            # An expel: the examiner stands next to the victim, cooldown over.
            hunter, prey = game.players[ids[examiner]], game.players[ids[victim]]
            hunter.next_expel_tick = 0  # the first cooldown is not what this test is about
            hunter.x, hunter.y = prey.x + 20, prey.y
            ws[examiner].send_json({"type": "expel", "target": ids[victim]})
            receive_until(ws[victim], state_where(lambda m: m["alive"] is False))

            # A report: the doer stands next to the failed exam and reports what they see.
            exam = game.failed_exams[0]
            doer_player.x, doer_player.y = exam.x + 10, exam.y
            state = receive_until(me, state_where(lambda m: m["failed_exams"]))
            me.send_json({"type": "report", "exam": state["failed_exams"][0]["id"]})
            receive_until(c, phase_is(MEETING))

            # The meeting: a living student chats, the ghost cannot.
            ws[third].send_json({"type": "chat", "text": "I saw them at the entrance"})
            state = receive_until(me, state_where(lambda m: m.get("chat")))
            assert state["chat"] == [{"from": ids[third], "text": "I saw them at the entrance"}]
            ws[victim].send_json({"type": "chat", "text": "Boo"})
            assert error_reason(ws[victim]) == "Ghosts cannot chat"

            # The vote: two students vote the examiner out, the examiner skips.
            ws[doer].send_json({"type": "vote", "target": ids[examiner]})
            ws[third].send_json({"type": "vote", "target": ids[examiner]})
            ws[examiner].send_json({"type": "vote", "target": SKIP})
            state = receive_until(
                c, state_where(lambda m: m["phase"] == MEETING and m["meeting"]["result"])
            )
            assert state["meeting"]["result"]["surfing"] == ids[examiner]
            assert state["ballots"] == {
                ids[doer]: ids[examiner],
                ids[third]: ids[examiner],
                ids[examiner]: SKIP,
            }
            game.meeting.result_ends = game.tick  # skip the 5 s the result is shown

            # The end: the only examiner is out, the students win and every role is shown.
            end = receive_until(c, phase_is(ENDED))
            assert end["winner"] == STUDENTS_WIN
            assert end["roles"] == {ids[name]: role[name] for name in names}

            # Restart: the host takes everyone back to the lobby, roles cleared.
            c.send_json({"type": "restart"})
            receive_until(c, phase_is(LOBBY))
            assert all(p.role is None and p.alive for p in game.players.values())

            # A second round, ended by a player who is not the host (spec 036).
            c.send_json({"type": "start"})
            receive_until(c, phase_is(PLAYING))
            a.send_json({"type": "end_round"})
            state = receive_until(c, phase_is(LOBBY))
            assert state["host"] == ids["Cleo"]
            assert len(game.players) == 4


def test_a_disconnect_during_a_meeting_over_the_websocket(fresh_game):
    """A browser that closes during a meeting stays in the round, alive and marked away."""
    game = fresh_game
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
        ):
            ids = [join(ws, name) for ws, name in ((a, "Ana"), (b, "Ben"), (c, "Cleo"))]
            with client.websocket_connect("/ws") as d:
                gone = join(d, "Dan")
                a.send_json({"type": "start"})
                receive_until(b, phase_is(PLAYING))
                game.guard = None
                caller = game.players[ids[0]]
                caller.x, caller.y = tile_centre(game, *game.campus["meeting_point"])
                a.send_json({"type": "meeting"})
                receive_until(b, phase_is(MEETING))
            # d is closed here.
            state = receive_until(b, state_where(lambda m: gone in m["away"]))
            assert state["phase"] == MEETING
            assert gone in state["meeting"]["living"]
            player = game.players[gone]
            assert player.away and player.alive


# --- Part 3: rejections that had no test (docs/review.md, M8) ------------------------------


def tile_centre(game, col, row):
    return (col + 0.5) * game.tile, (row + 0.5) * game.tile


def in_lobby():
    game = Game(load_map(), rng=random.Random(SEED))
    players = [game.join(name) for name in ("Ana", "Ben", "Cleo", "Dan")]
    return game, players


def playing():
    game, players = in_lobby()
    game.start(players[0].id)
    game.guard = None  # the guard walks on his own; these tests are about one action
    return game, players


def in_meeting():
    game, players = playing()
    caller = players[0]
    caller.x, caller.y = tile_centre(game, *game.campus["meeting_point"])
    game.call_meeting(caller.id)
    return game, players


def ended():
    """A real end: the only examiner leaves, so the students win."""
    game, players = playing()
    game.quit(next(p.id for p in players if p.role == EXAMINER))
    assert game.phase == ENDED
    return game, [p for p in players if p.id in game.players]


def everything(game):
    """Everything a rejected action must leave unchanged, including what every player sees."""
    return (
        game.phase,
        game.winner,
        game.tick,
        game.host_id,
        dict(game.host_votes),
        [dataclasses.asdict(p) for p in game.players.values()],
        [dataclasses.asdict(e) for e in game.failed_exams],
        copy.deepcopy(game.meeting),
        copy.deepcopy(game.emergency),
        game.lights_on,
        {player_id: game.snapshot_for(player_id) for player_id in game.players},
    )


UNKNOWN = "p99"  # an id that no player has


@pytest.mark.parametrize(
    "setup, action, reason",
    [
        pytest.param(playing, lambda g, p: g.task_input(UNKNOWN, "gate", "12345"), "Unknown player", id="task_input-unknown-player"),
        pytest.param(in_lobby, lambda g, p: g.task_input(p[0].id, "gate", "12345"), "The game has not started yet", id="task_input-lobby"),
        pytest.param(ended, lambda g, p: g.task_input(p[0].id, "gate", "12345"), "Game is over", id="task_input-ended"),
        pytest.param(playing, lambda g, p: g.task_input(p[0].id, 7, "12345"), "Task must be a task id", id="task_input-id-not-text"),
        pytest.param(playing, lambda g, p: g.cancel_task(UNKNOWN, "gate"), "Unknown player", id="task_cancel-unknown-player"),
        pytest.param(in_lobby, lambda g, p: g.cancel_task(p[0].id, "gate"), "The game has not started yet", id="task_cancel-lobby"),
        pytest.param(in_meeting, lambda g, p: g.cancel_task(p[0].id, "gate"), "Meeting in progress", id="task_cancel-meeting"),
        pytest.param(ended, lambda g, p: g.cancel_task(p[0].id, "gate"), "Game is over", id="task_cancel-ended"),
        pytest.param(playing, lambda g, p: g.cancel_task(p[0].id, ["gate"]), "Task must be a task id", id="task_cancel-id-not-text"),
        pytest.param(in_lobby, lambda g, p: g.kick(UNKNOWN, p[1].id), "Unknown player", id="kick-unknown-player"),
        pytest.param(playing, lambda g, p: g.quit(UNKNOWN), "Unknown player", id="leave-unknown-player"),
        pytest.param(in_meeting, lambda g, p: g.chat(UNKNOWN, "hello"), "Unknown player", id="chat-unknown-player"),
    ],
)
def test_a_rejected_action_gives_its_reason_and_changes_nothing(setup, action, reason):
    game, players = setup()
    before = everything(game)
    with pytest.raises(GameError, match=f"^{re.escape(reason)}$"):
        action(game, players)
    assert everything(game) == before


# --- Part 3: a disconnect during a meeting (docs/review.md, M8 and R9) ----------------------


def test_a_player_who_disconnects_in_a_meeting_stays_alive_and_keeps_their_vote():
    game, players = in_meeting()
    leaver = players[3]
    game.vote(leaver.id, SKIP)
    game.disconnect(leaver.id)
    assert game.phase == MEETING
    assert leaver.id in game.players
    assert leaver.away and leaver.alive
    assert game.meeting.votes[leaver.id] == SKIP
    assert leaver.id in game.snapshot_for(players[0].id)["away"]


def test_the_host_role_moves_on_when_the_host_disconnects_in_a_meeting():
    game, players = in_meeting()
    host = players[0]
    assert game.host_id == host.id
    game.disconnect(host.id)
    assert game.phase == MEETING
    assert game.host_id == players[1].id  # the first player still connected


def test_an_away_player_who_has_not_voted_keeps_the_vote_open_until_the_timer():
    """A known limit (docs/review.md, R9): an away player still counts as living, so the
    vote does not close early; when the time is up they count as a skip."""
    game, players = in_meeting()
    away = players[3]
    game.disconnect(away.id)
    for player in players[:3]:
        game.vote(player.id, SKIP)
    game.step()
    assert game.meeting.result is None  # all present players voted, still open
    for _ in range(MEETING_TICKS):
        if game.meeting.result is not None:
            break
        game.step()
    assert game.meeting.result == {
        "votes": {p.id: 0 for p in players},
        "skips": 4,
        "surfing": None,
    }


# --- Part 4: security and robustness (docs/review.md) ---------------------------------------
# Each test below was written before its fix and shown failing first.

ROOT = Path(__file__).resolve().parent.parent
HUGE = "9" * 400  # an integer far too big for a float: math.isfinite() raised OverflowError


# 1. M2: one source of truth for the cooldowns -------------------------------------------


def test_the_welcome_message_sends_the_cooldowns():
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "name": "Ana"})
        welcome = receive_until(ws, lambda m: m["type"] in ("welcome", "error"))
    assert welcome["cooldowns"] == {
        "expel": EXPEL_COOLDOWN,
        "vent": VENT_COOLDOWN,
        "sabotage": SABOTAGE_COOLDOWN,
    }


def test_the_browser_has_no_cooldown_numbers_of_its_own():
    main_js = (ROOT / "web" / "main.js").read_text(encoding="utf-8")
    assert not re.search(r"const (EXPEL|VENT|SABOTAGE)_COOLDOWN\s*=\s*\d", main_js)
    assert "welcome.cooldowns" in main_js


# 2. M3: no phantom player when the welcome cannot be sent ------------------------------


class GoneDuringWelcome:
    """A browser that sends "join" and is gone before the welcome reaches it."""

    headers = {}

    def __init__(self):
        self.events = [
            {"type": "websocket.receive", "text": json.dumps({"type": "join", "name": "Phantom"})},
            {"type": "websocket.disconnect", "code": 1006},
        ]

    async def accept(self):
        pass

    async def receive(self):
        return self.events.pop(0)

    async def send_json(self, data):
        raise WebSocketDisconnect(1006)

    async def send_text(self, data):
        raise WebSocketDisconnect(1006)

    async def close(self, code=1000, reason=None):
        pass


def test_a_browser_gone_during_the_welcome_leaves_no_player_behind(fresh_game):
    asyncio.run(server_main.websocket_endpoint(GoneDuringWelcome()))
    assert fresh_game.players == {}
    assert fresh_game.host_id is None
    assert server_main.connections == {}


# 3. M4: a huge number is a normal rejection, never a crash --------------------------------


def test_a_huge_number_in_a_stop_is_rejected_and_changes_nothing():
    game, players = playing()
    before = everything(game)
    message = json.loads('{"type": "input", "dx": 0, "dy": 0, "at": {"x": %s, "y": 1}}' % HUGE)
    with pytest.raises(GameError, match=r"^at must be \{x, y\} and only comes with a stop$"):
        game.set_input(players[1].id, message)
    assert everything(game) == before


HUGE_MESSAGES = [
    '{"type": "input", "dx": 0, "dy": 0, "at": {"x": %s, "y": 1}}' % HUGE,
    '{"type": "input", "dx": 0, "dy": 0, "at": {"x": 1e999, "y": 1}}',
    '{"type": "input", "dx": %s, "dy": 0}' % HUGE,
    '{"type": "settings", "expellers": %s}' % HUGE,
    '{"type": "vote_host", "target": %s}' % HUGE,
    '{"type": "make_host", "target": %s}' % HUGE,
    '{"type": "kick", "target": %s}' % HUGE,
    '{"type": "chat", "text": %s}' % HUGE,
    '{"type": "task_input", "task": "gate", "value": %s}' % HUGE,
    '{"type": "sabotage", "kind": %s}' % HUGE,
    '{"type": "vote", "target": 1e999}',
]


def test_huge_numbers_in_any_message_get_an_error_and_the_connection_stays_usable():
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        join(ws, "Ana")
        for raw in HUGE_MESSAGES:
            assert len(raw.encode()) <= MAX_MESSAGE_BYTES
            ws.send_text(raw)
            reply = receive_until(ws, lambda m: m["type"] != "state")
            assert reply["type"] == "error", raw
        ws.send_json({"type": "input", "dx": 1, "dy": 0})  # still connected and playing
        receive_until(ws, lambda m: m["type"] == "state")


# 4. M5: a stuck browser never freezes the game loop ----------------------------------------


class StuckBrowser:
    """A browser that stopped reading: every send waits forever."""

    async def send_text(self, data):
        await asyncio.Event().wait()

    async def close(self, code=1000, reason=None):
        await asyncio.Event().wait()


class ListeningBrowser:
    def __init__(self):
        self.received = []

    async def send_text(self, data):
        self.received.append(data)

    async def close(self, code=1000, reason=None):
        pass


def test_a_stuck_browser_is_dropped_and_the_others_keep_getting_states(fresh_game, monkeypatch):
    monkeypatch.setattr(server_main, "SEND_TIMEOUT", 0.2)
    stuck, listening = fresh_game.join("Stuck"), fresh_game.join("Listening")
    good = ListeningBrowser()
    server_main.connections[stuck.id] = StuckBrowser()  # first in line on purpose
    server_main.connections[listening.id] = good

    async def run_loop_for(seconds):
        task = asyncio.create_task(server_main.game_loop())
        await asyncio.sleep(seconds)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run_loop_for(1.5))
    assert len(good.received) >= TICK_RATE // 2  # well over half a second of states
    assert stuck.id not in server_main.connections
    assert stuck.id not in fresh_game.players  # treated as disconnected (lobby: removed)


# 5. The server limits movement, whatever the browser sends ---------------------------------


def open_floor(game, length):
    """A spot with at least `length` px of free floor to its right."""
    for row in range(len(game.grid)):
        y = (row + 0.5) * game.tile
        for col in range(len(game.grid[0])):
            x = (col + 0.5) * game.tile
            if all(not game.blocked(x + d, y, walls=True) for d in range(0, length, 4)):
                return x, y
    raise AssertionError("no open floor on the map")


def test_many_stops_without_walking_move_a_player_at_most_one_settle():
    game, players = playing()
    p = players[1]
    p.x, p.y = start = open_floor(game, 30 * int(SETTLE_DISTANCE))
    for _ in range(30):  # the rate limit allows 30 messages a second
        game.set_input(p.id, {"type": "input", "dx": 0, "dy": 0, "at": {"x": p.x + SETTLE_DISTANCE, "y": p.y}})
    assert p.x - start[0] <= SETTLE_DISTANCE


def test_walking_and_stopping_every_tick_is_no_faster_than_walking():
    game, players = playing()
    p = players[1]
    p.x, p.y = start = open_floor(game, 30 * int(SETTLE_DISTANCE))
    for _ in range(TICK_RATE):  # one second
        game.set_input(p.id, {"type": "input", "dx": 1, "dy": 0})
        game.step()
        game.set_input(p.id, {"type": "input", "dx": 0, "dy": 0, "at": {"x": p.x + SETTLE_DISTANCE, "y": p.y}})
    assert p.x - start[0] <= SPEED + SETTLE_DISTANCE


# 6. Coming back needs the rejoin token, not only the nickname -----------------------------


def test_an_away_player_comes_back_only_with_their_rejoin_token(fresh_game):
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
            join(a, "Ana")
            join(b, "Ben")
            with client.websocket_connect("/ws") as c, client.websocket_connect("/ws") as d:
                join(c, "Cleo")
                d.send_json({"type": "join", "name": "Dan"})
                welcome = receive_until(d, lambda m: m["type"] == "welcome")
                token = welcome["rejoin_token"]
                assert isinstance(token, str) and len(token) >= 16
                a.send_json({"type": "start"})
                receive_until(a, phase_is(PLAYING))
            receive_until(a, state_where(lambda m: welcome["id"] in m["away"]))
            for wrong in (None, "guess", token[:-1]):
                with client.websocket_connect("/ws") as thief:
                    thief.send_json({"type": "join", "name": "Dan", "rejoin_token": wrong})
                    reply = receive_until(thief, lambda m: m["type"] in ("welcome", "error"))
                    assert reply == {"type": "error", "reason": "Nickname is already taken"}
            assert fresh_game.players[welcome["id"]].away
            with client.websocket_connect("/ws") as back:
                back.send_json({"type": "join", "name": "Dan", "rejoin_token": token})
                reply = receive_until(back, lambda m: m["type"] in ("welcome", "error"))
                assert reply["type"] == "welcome" and reply["id"] == welcome["id"]


def test_the_browser_keeps_the_rejoin_token_across_reloads_and_closed_tabs():
    """localStorage, not sessionStorage: the token survives closing and reopening the tab."""
    main_js = (ROOT / "web" / "main.js").read_text(encoding="utf-8")
    assert "localStorage.setItem(REJOIN_KEY" in main_js
    assert "rejoin_token" in main_js


# 7. Origin, headers, API pages, open connections -------------------------------------------


def test_a_websocket_from_another_site_is_refused():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}) as ws:
                ws.send_json({"type": "join", "name": "Mallory"})
                ws.receive_json()


@pytest.mark.parametrize("origin", ["http://testserver", None])
def test_a_websocket_from_the_page_itself_or_without_origin_is_accepted(origin):
    headers = {"origin": origin} if origin else {}
    with TestClient(app) as client, client.websocket_connect("/ws", headers=headers) as ws:
        join(ws, "Ana")


@pytest.mark.parametrize("path", ["/", "/main.js", "/healthz", "/qr.svg", "/taken-colors"])
def test_every_response_has_the_security_headers(path):
    with TestClient(app) as client:
        headers = client.get(path).headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    policy = headers["content-security-policy"]
    for rule in (
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "base-uri 'none'",
    ):
        assert rule in policy, rule


def test_the_page_has_no_inline_scripts_or_handlers():
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"\son[a-z]+\s*=", page)  # onclick="…" and friends
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page)
    assert not re.search(r"\sstyle\s*=", page)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_api_pages_are_turned_off(path):
    with TestClient(app) as client:
        assert client.get(path).status_code == 404


def test_open_connections_are_limited():
    limit = server_main.MAX_CONNECTIONS
    assert MAX_PLAYERS < limit <= 100
    with TestClient(app) as client, contextlib.ExitStack() as stack:
        for _ in range(limit):
            stack.enter_context(client.websocket_connect("/ws"))
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as extra:
                extra.send_json({"type": "join", "name": "Extra"})
                extra.receive_json()


# 8. The transport limit for one message ---------------------------------------------------


def ws_max_size(args):
    return int(args[args.index("--ws-max-size") + 1])


def test_the_transport_limit_is_set_where_the_server_is_started():
    launch = json.loads((ROOT / ".claude" / "launch.json").read_text(encoding="utf-8"))
    value = ws_max_size(launch["configurations"][0]["runtimeArgs"])
    assert MAX_MESSAGE_BYTES <= value <= 64 * 1024
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"--ws-max-size {value}" in readme
