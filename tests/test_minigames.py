"""Tests for spec 012, parts 1-2: deleting the boring tasks and the mini-game framework
(the six mini-games, task_input, task_cancel, the time limit). Fake tasks for examiners
(part 3) and multi-step tasks (part 4) are tested separately, once those parts land.

Unit tests against server/game.py and server/minigames.py first, then one WebSocket test.
"""

import copy
import dataclasses
import random

import pytest
from fastapi.testclient import TestClient

from server import game as rules
from server import minigames
from server.game import TICK_RATE, Game, GameError, load_map
from server.main import app

TILE = 32

# One hall with six task places, one per mini-game kind, far from the shared spawn.
MINIGAME_MAP = {
    "tile_size": TILE,
    "grid": ["#" * 30] + ["#" + "." * 28 + "#"] * 14 + ["#" * 30],
    "areas": [{"name": "Hall", "x": 1, "y": 1, "w": 28, "h": 14, "color": "#3f6e8c"}],
    "spawns": [[2, 2]],
    "tasks": [
        {"id": "ticket", "title": "Now serving", "area": "Hall", "x": 6, "y": 2, "minigame": "ticket", "joke": "Joke ticket"},
        {"id": "translate", "title": "Helpdesk", "area": "Hall", "x": 9, "y": 2, "minigame": "translate", "joke": "Joke translate"},
        {"id": "card", "title": "Gate", "area": "Hall", "x": 12, "y": 2, "minigame": "card", "joke": "Joke card"},
        {"id": "paper_jam", "title": "Printer", "area": "Hall", "x": 15, "y": 2, "minigame": "paper_jam", "joke": "Joke jam"},
        {"id": "socket", "title": "Socket", "area": "Hall", "x": 18, "y": 2, "minigame": "cable", "joke": "Joke socket"},
        {"id": "seagull", "title": "Nata", "area": "Hall", "x": 21, "y": 2, "minigame": "seagull", "joke": "Joke seagull"},
    ],
}
# A task without a mini-game (only test maps may have one; server/campus.json may not).
PLAIN_MAP = {
    **MINIGAME_MAP,
    "tasks": MINIGAME_MAP["tasks"] + [
        {"id": "plain", "title": "Plain wait", "area": "Hall", "x": 24, "y": 2, "seconds": 5, "joke": "Joke plain"},
    ],
}

KINDS = ["ticket", "translate", "card", "paper_jam", "socket", "seagull"]


# --- Helpers ----------------------------------------------------------------------


def new_round(count=4, seed=0, campus=MINIGAME_MAP):
    game = Game(campus, rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


def round_with(task_id, count=4):
    """A started game in which one student has `task_id`. That student comes first."""
    for seed in range(200):
        game, examiners, students = new_round(count, seed)
        for student in students:
            if task_id in student.tasks:
                return game, examiners, [student] + [s for s in students if s is not student]
    raise AssertionError(f"no seed deals {task_id} to one student")


def place_of(game, task_id):
    task = next(t for t in game.campus["tasks"] if t["id"] == task_id)
    return (task["x"] + 0.5) * TILE, (task["y"] + 0.5) * TILE


def go_to(game, player, task_id, dx=0, dy=0):
    x, y = place_of(game, task_id)
    player.x, player.y = x + dx, y + dy


def wait(game, ticks):
    for _ in range(ticks):
        game.step()


def start_task(game, student, task_id):
    go_to(game, student, task_id)
    game.task(student.id, task_id)


def doing(game, student):
    return game.snapshot_for(student.id)["doing"]


def challenge_of(student):
    return student.challenge


def entry(game, student, task_id):
    return next(t for t in game.snapshot_for(student.id)["tasks"] if t["id"] == task_id)


def note_of(game, student):
    return game.snapshot_for(student.id)["task_note"]


def full_state(game):
    return (
        game.phase,
        game.winner,
        [dataclasses.asdict(p) for p in game.players.values()],
        copy.deepcopy(game.meeting),
        {player_id: game.snapshot_for(player_id) for player_id in game.players},
    )


def assert_rejected(game, action, reason):
    before = full_state(game)
    with pytest.raises(GameError, match=reason):
        action()
    assert full_state(game) == before


def ready_examiner(game, examiner):
    wait(game, max(0, examiner.next_expel_tick - game.tick))


def expel(game, examiner, student):
    examiner.x, examiner.y = student.x, student.y
    game.expel(examiner.id, student.id)


# --- Campus data -------------------------------------------------------------------


def test_no_campus_task_is_a_plain_waiting_task():
    # "certificate" has two stations now (spec 012, part 4), so every station of every
    # task is checked, not just the (no longer always present) top-level fields.
    for task in load_map()["tasks"]:
        stations = task["steps"] if "steps" in task else [task]
        for station in stations:
            assert "seconds" not in station
            assert station["minigame"] in minigames.KINDS


def test_a_station_without_a_minigame_still_works_hold_still_as_before():
    game, _, students = new_round(4, campus=PLAIN_MAP)
    student = students[0]
    start_task(game, student, "plain")
    assert doing(game, student) == {"task": "plain", "seconds_left": 5}
    assert challenge_of(student) is None
    wait(game, 5 * TICK_RATE)
    assert entry(game, student, "plain")["done"] is True


# --- ticket -------------------------------------------------------------------------


def test_ticket_pressing_at_the_right_moment_finishes_it():
    game, _, students = round_with("ticket")
    student = students[0]
    start_task(game, student, "ticket")
    number = student.challenge["number"]
    wait(game, number * TICK_RATE)
    assert doing(game, student)["challenge"]["counter"] == number
    game.task_input(student.id, "ticket", True)
    assert entry(game, student, "ticket")["done"] is True


def test_ticket_pressing_too_early_rerolls_with_a_note():
    game, _, students = round_with("ticket")
    student = students[0]
    start_task(game, student, "ticket")
    game.task_input(student.id, "ticket", True)  # counter is 0, always below the number
    assert note_of(game, student) == "Not your turn. Take a new ticket."
    assert doing(game, student)["task"] == "ticket"  # still running, a fresh ticket
    assert entry(game, student, "ticket")["done"] is False


def test_ticket_missing_the_number_rerolls_with_a_note():
    game, _, students = round_with("ticket")
    student = students[0]
    start_task(game, student, "ticket")
    number = student.challenge["number"]
    wait(game, (number + 1) * TICK_RATE)  # one second past the number
    game.task_input(student.id, "ticket", True)
    assert note_of(game, student) == "You missed your number."
    assert entry(game, student, "ticket")["done"] is False


def test_ticket_invalid_values_are_rejected_and_change_nothing():
    for value in [False, 1, "true", None, [True]]:
        game, _, students = round_with("ticket")
        student = students[0]
        start_task(game, student, "ticket")
        assert_rejected(game, lambda: game.task_input(student.id, "ticket", value), "Invalid value")


def test_ticket_times_out_and_can_be_started_again():
    game, _, students = round_with("ticket")
    student = students[0]
    start_task(game, student, "ticket")
    wait(game, minigames.TIME_LIMITS["ticket"] * TICK_RATE)
    assert doing(game, student) is None
    assert note_of(game, student) == minigames.TIMEOUT_NOTES["ticket"]
    start_task(game, student, "ticket")
    assert doing(game, student)["task"] == "ticket"


# --- translate -----------------------------------------------------------------------


def test_translate_the_right_option_finishes_it():
    game, _, students = round_with("translate")
    student = students[0]
    start_task(game, student, "translate")
    challenge = student.challenge
    correct_index = challenge["options"].index(challenge["correct"])
    game.task_input(student.id, "translate", correct_index)
    assert entry(game, student, "translate")["done"] is True


def test_translate_a_wrong_option_rerolls_with_a_note():
    game, _, students = round_with("translate")
    student = students[0]
    start_task(game, student, "translate")
    challenge = student.challenge
    correct_index = challenge["options"].index(challenge["correct"])
    wrong_index = (correct_index + 1) % 3
    before_sentence = challenge["sentence"]
    game.task_input(student.id, "translate", wrong_index)
    assert note_of(game, student) == "Não percebi."
    assert entry(game, student, "translate")["done"] is False
    # A new sentence (not necessarily different by chance, but the challenge rerolled).
    assert student.challenge["kind"] == "translate"
    assert len(student.challenge["options"]) == 3


@pytest.mark.parametrize("value", [3, -1, "0", 1.0, None])
def test_translate_invalid_values_are_rejected_and_change_nothing(value):
    game, _, students = round_with("translate")
    student = students[0]
    start_task(game, student, "translate")
    assert_rejected(game, lambda: game.task_input(student.id, "translate", value), "Invalid value")


def test_translate_times_out_and_can_be_started_again():
    game, _, students = round_with("translate")
    student = students[0]
    start_task(game, student, "translate")
    wait(game, minigames.TIME_LIMITS["translate"] * TICK_RATE)
    assert doing(game, student) is None
    assert note_of(game, student) == minigames.TIMEOUT_NOTES["translate"]
    start_task(game, student, "translate")
    assert doing(game, student)["task"] == "translate"


# --- card ----------------------------------------------------------------------------


def test_card_the_matching_number_finishes_it():
    game, _, students = round_with("card")
    student = students[0]
    start_task(game, student, "card")
    game.task_input(student.id, "card", student.challenge["number"])
    assert entry(game, student, "card")["done"] is True


def test_card_a_wrong_number_rerolls_with_a_note():
    game, _, students = round_with("card")
    student = students[0]
    start_task(game, student, "card")
    real = student.challenge["number"]
    wrong = "00000" if real != "00000" else "11111"
    game.task_input(student.id, "card", wrong)
    assert note_of(game, student) == "Beep. Red."
    assert entry(game, student, "card")["done"] is False
    new_number = student.challenge["number"]
    assert len(new_number) == 5 and new_number.isdigit()  # rerolled to a fresh 5-digit number


@pytest.mark.parametrize("value", ["1234", "123456", "1234a", 12345, None, True])
def test_card_invalid_values_are_rejected_and_change_nothing(value):
    game, _, students = round_with("card")
    student = students[0]
    start_task(game, student, "card")
    assert_rejected(game, lambda: game.task_input(student.id, "card", value), "Invalid value")


def test_card_times_out_and_can_be_started_again():
    game, _, students = round_with("card")
    student = students[0]
    start_task(game, student, "card")
    wait(game, minigames.TIME_LIMITS["card"] * TICK_RATE)
    assert doing(game, student) is None
    assert note_of(game, student) == minigames.TIMEOUT_NOTES["card"]
    start_task(game, student, "card")
    assert doing(game, student)["task"] == "card"


# --- paper_jam -------------------------------------------------------------------------


def test_paper_jam_clearing_all_three_jams_finishes_it():
    game, _, students = round_with("paper_jam")
    student = students[0]
    start_task(game, student, "paper_jam")
    jams = list(student.challenge["jams"])
    for cell in jams[:-1]:
        game.task_input(student.id, "paper_jam", cell)
        assert entry(game, student, "paper_jam")["done"] is False
    game.task_input(student.id, "paper_jam", jams[-1])
    assert entry(game, student, "paper_jam")["done"] is True


def test_paper_jam_tapping_an_empty_cell_does_nothing_but_a_note():
    game, _, students = round_with("paper_jam")
    student = students[0]
    start_task(game, student, "paper_jam")
    jams = student.challenge["jams"]
    empty = next(c for c in range(9) if c not in jams)
    game.task_input(student.id, "paper_jam", empty)
    assert note_of(game, student) == "Nothing there."
    assert student.challenge["cleared"] == []
    assert doing(game, student)["task"] == "paper_jam"


def test_paper_jam_view_never_reveals_which_cells_have_jams():
    # Not even to the player doing it: finding the jams is the whole mini-game.
    game, _, students = round_with("paper_jam")
    student = students[0]
    start_task(game, student, "paper_jam")
    view = doing(game, student)["challenge"]
    assert "jams" not in view
    assert view == {"kind": "paper_jam", "cleared": []}


@pytest.mark.parametrize("value", [-1, 9, "0", 1.0, None, True])
def test_paper_jam_invalid_values_are_rejected_and_change_nothing(value):
    game, _, students = round_with("paper_jam")
    student = students[0]
    start_task(game, student, "paper_jam")
    assert_rejected(game, lambda: game.task_input(student.id, "paper_jam", value), "Invalid value")


def test_paper_jam_times_out_and_can_be_started_again():
    game, _, students = round_with("paper_jam")
    student = students[0]
    start_task(game, student, "paper_jam")
    wait(game, minigames.TIME_LIMITS["paper_jam"] * TICK_RATE)
    assert doing(game, student) is None
    assert note_of(game, student) == minigames.TIMEOUT_NOTES["paper_jam"]
    start_task(game, student, "paper_jam")
    assert doing(game, student)["task"] == "paper_jam"


# --- cable (projector) ----------------------------------------------------------------


def correct_cable_index(challenge):
    return challenge["cables"].index(challenge["port"])


def wrong_cable_index(challenge):
    return (correct_cable_index(challenge) + 1) % 4


def test_cable_three_correct_rounds_in_a_row_finishes_it():
    game, _, students = round_with("socket")
    student = students[0]
    start_task(game, student, "socket")
    for round_number in range(1, 4):
        assert student.challenge["round"] == round_number
        index = correct_cable_index(student.challenge)
        game.task_input(student.id, "socket", {"cable": index})
    assert entry(game, student, "socket")["done"] is True


def test_cable_a_wrong_cable_gives_no_signal_and_counts_one_wrong_try():
    game, _, students = round_with("socket")
    student = students[0]
    start_task(game, student, "socket")
    index = wrong_cable_index(student.challenge)
    game.task_input(student.id, "socket", {"cable": index})
    assert note_of(game, student) == "No signal."
    assert student.challenge["wrong"] == 1
    assert student.challenge["round"] == 1  # the round is not reset by the first wrong try
    assert entry(game, student, "socket")["done"] is False


def test_cable_a_second_wrong_try_restarts_at_round_one_with_new_rounds():
    game, _, students = round_with("socket")
    student = students[0]
    start_task(game, student, "socket")
    for _ in range(2):
        index = wrong_cable_index(student.challenge)
        game.task_input(student.id, "socket", {"cable": index})
    assert note_of(game, student) == "Two wrong cables. Start again."
    assert student.challenge["round"] == 1
    assert student.challenge["wrong"] == 0
    assert entry(game, student, "socket")["done"] is False


@pytest.mark.parametrize(
    "value",
    [
        {"cable": -1},
        {"cable": 4},
        {"cable": "0"},
        {"cable": 1.0},
        {"cable": True},
        {},
        {"cable": 0, "extra": 0},
        {"from": 0},
        [0],
        0,
        None,
    ],
)
def test_cable_invalid_values_are_rejected_and_change_nothing(value):
    game, _, students = round_with("socket")
    student = students[0]
    start_task(game, student, "socket")
    assert_rejected(game, lambda: game.task_input(student.id, "socket", value), "Invalid value")


def test_cable_times_out_and_can_be_started_again():
    game, _, students = round_with("socket")
    student = students[0]
    start_task(game, student, "socket")
    wait(game, minigames.TIME_LIMITS["cable"] * TICK_RATE)
    assert doing(game, student) is None
    assert note_of(game, student) == minigames.TIMEOUT_NOTES["cable"]
    start_task(game, student, "socket")
    assert doing(game, student)["task"] == "socket"


def test_cable_challenge_is_never_sent_to_any_other_player():
    game, examiners, students = round_with("socket", count=7)
    student = students[0]
    start_task(game, student, "socket")
    for other_id, other in game.players.items():
        snapshot = game.snapshot_for(other_id)
        if other is student:
            assert snapshot["doing"]["challenge"]["kind"] == "cable"
        else:
            assert snapshot["doing"] is None


# --- seagull -------------------------------------------------------------------------


def test_seagull_five_hits_within_the_time_limit_finishes_it():
    game, _, students = round_with("seagull")
    student = students[0]
    start_task(game, student, "seagull")
    for _ in range(5):
        cell = student.challenge["cell"]
        game.task_input(student.id, "seagull", cell)
    assert entry(game, student, "seagull")["done"] is True


def test_seagull_a_miss_changes_nothing_and_leaves_no_note():
    game, _, students = round_with("seagull")
    student = students[0]
    start_task(game, student, "seagull")
    cell = student.challenge["cell"]
    miss = (cell + 1) % 9
    game.task_input(student.id, "seagull", miss)
    assert note_of(game, student) is None
    assert student.challenge["cell"] == cell
    assert student.challenge["hits"] == 0


@pytest.mark.parametrize("value", [-1, 9, "0", 1.0, None, True])
def test_seagull_invalid_values_are_rejected_and_change_nothing(value):
    game, _, students = round_with("seagull")
    student = students[0]
    start_task(game, student, "seagull")
    assert_rejected(game, lambda: game.task_input(student.id, "seagull", value), "Invalid value")


def test_seagull_time_up_takes_the_pastry_and_the_task_can_be_started_again():
    game, _, students = round_with("seagull")
    student = students[0]
    start_task(game, student, "seagull")
    wait(game, minigames.TIME_LIMITS["seagull"] * TICK_RATE)
    assert doing(game, student) is None
    assert note_of(game, student) == "A seagull took it."
    start_task(game, student, "seagull")
    assert doing(game, student)["task"] == "seagull"


# --- Framework: cancelling ----------------------------------------------------------


@pytest.mark.parametrize("task_id", KINDS)
def test_leaving_the_range_cancels_the_running_challenge(task_id):
    game, _, students = round_with(task_id)
    student = students[0]
    start_task(game, student, task_id)
    go_to(game, student, task_id, dx=rules.TASK_RANGE + 1)
    game.step()
    assert doing(game, student) is None
    assert student.challenge is None


def test_being_expelled_cancels_the_running_challenge():
    game, (examiner,), students = round_with("paper_jam")
    student = students[0]
    ready_examiner(game, examiner)
    start_task(game, student, "paper_jam")
    expel(game, examiner, student)
    assert doing(game, student) is None
    assert student.challenge is None
    # As a ghost, the same station can be started again.
    start_task(game, student, "paper_jam")
    assert doing(game, student)["task"] == "paper_jam"


def test_a_meeting_cancels_the_running_challenge():
    game, _, students = round_with("socket")
    student = students[0]
    start_task(game, student, "socket")
    game.call_meeting(students[1].id)
    assert doing(game, student) is None
    assert student.challenge is None


def test_task_cancel_resets_the_running_station_and_can_be_restarted():
    game, _, students = round_with("translate")
    student = students[0]
    start_task(game, student, "translate")
    game.cancel_task(student.id, "translate")
    assert doing(game, student) is None
    assert note_of(game, student) == "Task cancelled."
    start_task(game, student, "translate")
    assert doing(game, student)["task"] == "translate"


def test_task_cancel_for_a_task_not_being_done_is_rejected():
    game, _, students = round_with("translate")
    student = students[0]
    assert_rejected(game, lambda: game.cancel_task(student.id, "translate"), "You are not doing this task")


def test_task_cancel_for_someone_elses_current_task_is_rejected():
    game, _, students = round_with("translate")
    student = students[0]
    start_task(game, student, "translate")
    other = students[1]
    assert_rejected(game, lambda: game.cancel_task(other.id, "translate"), "You are not doing this task")


# --- Framework: task_input/task_cancel rejections -----------------------------------


def test_task_input_for_a_task_the_player_is_not_doing_is_rejected():
    game, _, students = round_with("card")
    student = students[0]
    assert_rejected(game, lambda: game.task_input(student.id, "card", "00000"), "You are not doing this task")


def test_task_input_while_doing_a_different_task_is_rejected():
    for seed in range(200):
        game, _, students = new_round(4, seed)
        student = next((s for s in students if "ticket" in s.tasks and "card" in s.tasks), None)
        if student:
            break
    else:
        raise AssertionError("no seed deals both tasks to one student")
    start_task(game, student, "ticket")
    assert_rejected(game, lambda: game.task_input(student.id, "card", "00000"), "You are not doing this task")


def test_task_input_for_a_station_without_a_minigame_is_rejected():
    game, _, students = new_round(4, campus=PLAIN_MAP)
    student = students[0]
    start_task(game, student, "plain")
    assert_rejected(game, lambda: game.task_input(student.id, "plain", True), "This task has no mini-game")


def test_task_input_out_of_range_is_rejected():
    game, _, students = round_with("card")
    student = students[0]
    start_task(game, student, "card")
    go_to(game, student, "card", dx=rules.TASK_RANGE + 1)
    assert_rejected(game, lambda: game.task_input(student.id, "card", "00000"), "Too far from the task")


def test_task_input_while_a_meeting_is_running_is_rejected():
    game, _, students = round_with("card")
    student = students[0]
    start_task(game, student, "card")
    number = student.challenge["number"]
    game.call_meeting(students[1].id)
    assert_rejected(game, lambda: game.task_input(student.id, "card", number), "Meeting in progress")


def test_task_input_and_task_cancel_messages_are_parsed_after_joining_and_rejected_before():
    raw_input = '{"type": "task_input", "task": "card", "value": "00000"}'
    raw_cancel = '{"type": "task_cancel", "task": "card"}'
    assert rules.parse_message(raw_input, joined=True) == {"type": "task_input", "task": "card", "value": "00000"}
    assert rules.parse_message(raw_cancel, joined=True) == {"type": "task_cancel", "task": "card"}
    with pytest.raises(GameError, match="Join the game first"):
        rules.parse_message(raw_input, joined=False)
    with pytest.raises(GameError, match="Join the game first"):
        rules.parse_message(raw_cancel, joined=False)


# --- Secrecy -------------------------------------------------------------------------


def test_no_snapshot_contains_another_players_challenge():
    # Examiners have real (fake) tasks and challenges of their own now (spec 012, part
    # 3): nobody but `student` is doing anything in this round, so everyone else's
    # "doing" (student and examiner alike) must be None, never a glimpse of this
    # challenge.
    game, examiners, students = round_with("paper_jam", count=7)
    student = students[0]
    start_task(game, student, "paper_jam")
    for other_id, other in game.players.items():
        snapshot = game.snapshot_for(other_id)
        assert all("challenge" not in task for task in snapshot["tasks"])
        if other is student:
            assert snapshot["doing"]["task"] == "paper_jam"
        else:
            assert snapshot["doing"] is None


# --- WebSocket -----------------------------------------------------------------------


def receive_until(ws, predicate, limit=10 * TICK_RATE):
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def test_a_student_solves_a_minigame_over_the_websocket_and_another_player_sees_progress(fresh_game):
    # Seed 4 deals the real campus: Ada (joins first) is a student with "gate" (the
    # "card" mini-game) as her first task, Bo is the examiner (checked once, below).
    # Spec 021: was seed 1 before the campus had 8 tasks.
    fresh_game.rng = random.Random(4)
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            clients = [a, b, c, d]
            ids = []
            for ws, name in zip(clients, ["Ada", "Bo", "Cy", "Di"]):
                ws.send_json({"type": "join", "name": name})
                welcome = receive_until(ws, lambda m: m["type"] == "welcome")
                ids.append(welcome["id"])
            a.send_json({"type": "start"})
            states = [
                receive_until(ws, lambda m: m["type"] == "state" and m["phase"] == "playing")
                for ws in clients
            ]
            assert [state["role"] for state in states] == ["student", "examiner", "student", "student"]
            ws, other, player = a, b, fresh_game.players[ids[0]]
            other_player = fresh_game.players[ids[1]]
            task = states[0]["tasks"][0]
            assert task["id"] == "gate"

            player.x, player.y = task["x"], task["y"]  # skip the walk to the task place
            ws.send_json({"type": "task", "task": "gate"})
            running = receive_until(ws, lambda m: m["type"] == "state" and m["doing"])
            assert running["doing"]["challenge"]["kind"] == "card"

            wrong_number = "00000" if player.challenge["number"] != "00000" else "11111"
            ws.send_json({"type": "task_input", "task": "gate", "value": wrong_number})
            after_wrong = receive_until(ws, lambda m: m["type"] == "state" and m.get("task_note"))
            assert after_wrong["task_note"] == "Beep. Red."

            real_number = player.challenge["number"]  # rerolled after the wrong try
            ws.send_json({"type": "task_input", "task": "gate", "value": real_number})
            done = receive_until(
                ws, lambda m: m["type"] == "state" and any(t["done"] for t in m["tasks"])
            )
            finished = next(t for t in done["tasks"] if t["id"] == "gate")
            assert finished["done"] is True and finished["joke"]
            assert done["doing"] is None
            seen = receive_until(
                other, lambda m: m["type"] == "state" and m["task_progress"]["done"] == 1
            )
            assert seen["task_progress"]["done"] == 1
            # The examiner's own (fake) tasks, never the student's.
            assert [t["id"] for t in seen["tasks"]] == other_player.tasks
