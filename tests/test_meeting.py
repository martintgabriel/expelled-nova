"""Tests for spec 006: meetings and votes (report, bell, sent surfing).

Unit tests against server/game.py first, then the WebSocket endpoint.
"""

import copy
import dataclasses
import json
import math
import random

import pytest
from fastapi.testclient import TestClient

from server.game import (
    EXPEL_COOLDOWN,
    MAX_PLAYERS,
    MEETING_SECONDS,
    REPORT_RANGE,
    RESULT_SECONDS,
    STEP,
    TICK_RATE,
    Game,
    GameError,
    load_map,
    parse_message,
)
from server.main import app

TILE = 32
COOLDOWN_TICKS = EXPEL_COOLDOWN * TICK_RATE  # 400
MEETING_TICKS = MEETING_SECONDS * TICK_RATE  # 1200
RESULT_TICKS = RESULT_SECONDS * TICK_RATE  # 100
PLAYER_KEYS = {"id", "name", "x", "y"}
# Spec 027: "caught" is the examiner id the security guard saw, None for a report or a button.
MEETING_KEYS = {"reason", "called_by", "caught", "living", "voted", "my_vote", "seconds_left", "result"}

# One big open hall, 30 x 16 tiles, without an Auditorium, so a meeting moves nobody.
# Everyone spawns on the same tile (centre (80, 80)), so at the start everyone is within
# expel and report range of everyone else.
HALL_MAP = {
    "tile_size": TILE,
    "grid": ["#" * 30] + ["#" + "." * 28 + "#"] * 14 + ["#" * 30],
    "areas": [],
    "spawns": [[2, 2]],
}

# A tiny Auditorium of 3 x 3 tiles (columns 2-4, rows 2-4) with a wall on its middle tile.
# It has no meeting point (spec 011: meetings no longer use the Auditorium).
TINY_MAP = {
    "tile_size": TILE,
    "grid": [
        "##########",
        "#........#",
        "#........#",
        "#..#.....#",
        "#........#",
        "#........#",
        "#........#",
        "##########",
    ],
    "areas": [{"name": "Auditorium", "x": 2, "y": 2, "w": 3, "h": 3, "color": "#7a4f86"}],
    "spawns": [[7, 6]],
}


# --- Helpers ----------------------------------------------------------------------


def lobby(count, seed=0, campus=HALL_MAP):
    """A lobby with `count` players. players[0] joined first and is the host."""
    game = Game(campus, rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    return game, players


def playing(count=4, seed=0, campus=HALL_MAP):
    """A started game. Returns the game, its examiners and its students (Player objects)."""
    game, players = lobby(count, seed, campus)
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


def bell_meeting(count=4, seed=0):
    """A started game in which students[0] has just rung the bell."""
    game, examiners, students = playing(count, seed)
    game.call_meeting(students[0].id)
    return game, examiners, students


def wait_ticks(game, ticks):
    for _ in range(ticks):
        game.step()


def expel_now(game, examiner, student):
    """Wait for the examiner's cooldown, step onto the student and expel them.

    Returns the failed exam left on the floor.
    """
    wait_ticks(game, max(0, examiner.next_expel_tick - game.tick))
    examiner.x, examiner.y = student.x, student.y
    game.expel(examiner.id, student.id)
    return game.failed_exams[-1]


def everyone_votes(game, target):
    """Every living player votes for `target` (a Player or "skip"); the meeting runs to its end.

    The target skips: nobody can vote for themself (spec 008, part 2).
    """
    choice = target if isinstance(target, str) else target.id
    for player in [p for p in game.players.values() if p.alive]:
        game.vote(player.id, "skip" if player.id == choice else choice)
    game.step()  # the voting closes
    wait_ticks(game, RESULT_TICKS)  # the result time passes


def close_voting(game, viewer):
    """Step until the voting has closed (at most the full voting time); returns the result."""
    for _ in range(MEETING_TICKS):
        game.step()
        result = game.snapshot_for(viewer.id)["meeting"]["result"]
        if result is not None:
            return result
    raise AssertionError("the voting did not close")


def meeting_of(game, player):
    return game.snapshot_for(player.id)["meeting"]


def ids_in(snapshot):
    return sorted(p["id"] for p in snapshot["players"])


def tile_centre(col, row):
    return (col + 0.5) * TILE, (row + 0.5) * TILE


def go_to_bell(player):
    """Put a player on the campus meeting table: a meeting is called only there (spec 011,
    before that at the bell of spec 008, part 4)."""
    player.x, player.y = tile_centre(*load_map()["meeting_point"])


def full_state(game):
    """Everything a rejected action must leave unchanged, including what every player sees."""
    return (
        game.phase,
        game.winner,
        [dataclasses.asdict(p) for p in game.players.values()],  # position, direction, alive, bell
        [dataclasses.asdict(e) for e in game.failed_exams],
        copy.deepcopy(game.meeting),  # votes and timer
        {player_id: game.snapshot_for(player_id) for player_id in game.players},
    )


def assert_rejected(game, action, reason):
    before = full_state(game)
    with pytest.raises(GameError, match=reason):
        action()
    assert full_state(game) == before


# --- Accepted ---------------------------------------------------------------------


def test_student_next_to_a_failed_exam_reports_it():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    reporter = students[1]
    reporter.x, reporter.y = exam.x + 20, exam.y
    game.report(reporter.id, exam.id)
    assert game.phase == "meeting"
    for player_id in game.players:  # the ghost too
        snapshot = game.snapshot_for(player_id)
        assert snapshot["phase"] == "meeting"
        meeting = snapshot["meeting"]
        assert meeting["reason"] == "report"
        assert meeting["called_by"] == reporter.id
        assert meeting["seconds_left"] == MEETING_SECONDS
        assert meeting["result"] is None


def test_examiner_can_report_their_own_failed_exam():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    game.report(examiner.id, exam.id)
    assert game.phase == "meeting"
    assert meeting_of(game, students[1])["called_by"] == examiner.id


def test_bell_rung_anywhere_starts_a_meeting_and_uses_only_that_bell():
    game, _, students = playing(4)
    for player_id in game.players:
        assert game.snapshot_for(player_id)["meeting_used"] is False
    ringer = students[1]
    ringer.x, ringer.y = tile_centre(26, 13)  # far from everyone else
    game.call_meeting(ringer.id)
    assert game.phase == "meeting"
    for player in game.players.values():
        snapshot = game.snapshot_for(player.id)
        assert snapshot["meeting"]["reason"] == "button"
        assert snapshot["meeting"]["called_by"] == ringer.id
        assert snapshot["meeting_used"] is (player is ringer)


# Spec 011: a meeting places everyone in a circle around the meeting table instead of on
# their own Auditorium tile.
def test_meeting_puts_everyone_in_a_circle_around_the_meeting_table_on_the_campus():
    game, examiners, students = playing(MAX_PLAYERS, campus=load_map())
    ghost = students[0]
    expel_now(game, examiners[0], ghost)
    game.set_input(students[1].id, {"type": "input", "dx": 1, "dy": 0})
    game.set_input(ghost.id, {"type": "input", "dx": 0, "dy": -1})
    game.step()
    go_to_bell(students[2])
    game.call_meeting(students[2].id)

    table_x, table_y = tile_centre(*load_map()["meeting_point"])
    circle = 64  # px from the table's middle (MEETING_CIRCLE in server/game.py)
    places = []
    for player in game.players.values():  # join order, the ghost included
        assert math.hypot(player.x - table_x, player.y - table_y) == pytest.approx(circle)
        assert game.area_at(player.x, player.y) != "Auditorium"
        assert not game.blocked(player.x, player.y)
        assert (player.dx, player.dy) == (0, 0)
        places.append((player.x, player.y))
    for index, (x, y) in enumerate(places):
        for other_x, other_y in places[index + 1 :]:
            # Two 20 px squares that do not overlap are apart in x or in y.
            assert max(abs(x - other_x), abs(y - other_y)) >= 20
    # In join order: the first player north of the table, the others clockwise.
    assert places[0] == pytest.approx((table_x, table_y - circle))
    assert places[1][0] > table_x and places[1][1] < table_y


def test_vote_for_a_living_player_and_a_skip_are_accepted():
    game, (examiner,), students = bell_meeting(4)
    voter, skipper = students[1], students[2]
    game.vote(voter.id, examiner.id)
    game.vote(skipper.id, "skip")
    in_join_order = [p.id for p in game.players.values() if p in (voter, skipper)]
    for player_id in game.players:
        assert game.snapshot_for(player_id)["meeting"]["voted"] == in_join_order
    assert meeting_of(game, voter)["my_vote"] == examiner.id
    assert meeting_of(game, skipper)["my_vote"] == "skip"
    assert meeting_of(game, examiner)["my_vote"] is None
    assert meeting_of(game, students[0])["my_vote"] is None
    assert meeting_of(game, voter)["result"] is None  # 2 of 4 have voted: still open


def test_majority_sends_a_player_surfing():
    """A4: 3 votes for one player, 1 for another and 1 skip."""
    game, (examiner,), students = bell_meeting(5)
    target, other = students[0], students[1]
    for voter in [examiner, students[1], students[2]]:
        game.vote(voter.id, target.id)
    game.vote(students[3].id, other.id)
    game.vote(target.id, "skip")
    game.step()

    assert target.alive is False
    assert game.failed_exams == []  # sent surfing leaves no failed exam
    assert game.phase == "meeting"  # the result is shown first
    expected_votes = {p.id: 0 for p in game.players.values()}
    expected_votes[target.id] = 3
    expected_votes[other.id] = 1
    for player_id in game.players:
        assert game.snapshot_for(player_id)["meeting"]["result"] == {
            "votes": expected_votes,
            "skips": 1,
            "surfing": target.id,
        }


def test_after_the_result_play_resumes_without_failed_exams_and_with_fresh_cooldowns():
    game, examiners, students = playing(7)
    expel_now(game, examiners[0], students[0])
    wait_ticks(game, COOLDOWN_TICKS)  # both examiners' cooldowns are over
    assert len(game.failed_exams) == 1
    game.call_meeting(students[1].id)
    for player in [p for p in game.players.values() if p.alive]:
        game.vote(player.id, "skip")
    game.step()  # the voting closes
    wait_ticks(game, RESULT_TICKS - 1)
    assert game.phase == "meeting"
    game.step()

    assert game.phase == "playing"
    assert game.failed_exams == []
    for player_id in game.players:
        snapshot = game.snapshot_for(player_id)
        assert "meeting" not in snapshot
        assert snapshot["failed_exams"] == []
    for examiner in examiners:
        assert game.snapshot_for(examiner.id)["expel_cooldown"] == EXPEL_COOLDOWN
    mover = students[2]
    start_x = mover.x
    game.set_input(mover.id, {"type": "input", "dx": 1, "dy": 0})
    game.step()
    assert mover.x == pytest.approx(start_x + STEP)


def test_voting_out_the_only_examiner_lets_the_students_win_after_the_result():
    game, (examiner,), students = bell_meeting(4)
    for student in students:
        game.vote(student.id, examiner.id)
    game.vote(examiner.id, "skip")
    game.step()
    assert examiner.alive is False
    assert game.phase == "meeting"  # everyone sees the result before the end screen
    wait_ticks(game, RESULT_TICKS - 1)
    assert game.phase == "meeting"
    game.step()
    assert game.phase == "ended"
    for student in students:
        assert game.snapshot_for(student.id)["winner"] == "students"


def test_with_two_examiners_both_must_be_voted_out_for_the_students_to_win():
    game, (first, second), students = bell_meeting(7)
    everyone_votes(game, first)
    assert first.alive is False
    assert game.phase == "playing"  # 1 examiner, 5 students
    game.call_meeting(students[1].id)
    everyone_votes(game, second)
    assert game.phase == "ended"
    assert game.snapshot_for(students[0].id)["winner"] == "students"


def test_voting_out_a_student_can_give_the_examiners_the_win():
    game, (examiner,), students = playing(4)
    expel_now(game, examiner, students[0])  # 1 examiner, 2 living students
    game.call_meeting(students[1].id)
    everyone_votes(game, students[2])  # 1 examiner, 1 living student
    assert game.phase == "ended"
    assert game.snapshot_for(examiner.id)["winner"] == "examiners"


def test_a_new_round_gives_everyone_their_bell_back():
    game, (examiner,), students = bell_meeting(4)  # students[0] rang
    everyone_votes(game, examiner)  # students win
    assert game.phase == "ended"
    assert game.snapshot_for(students[0].id)["meeting_used"] is True
    game.restart(game.host_id)
    for player_id in game.players:
        assert game.snapshot_for(player_id)["meeting_used"] is False
    game.start(game.host_id)
    game.call_meeting(students[0].id)
    assert game.phase == "meeting"


def test_report_bell_and_vote_messages_are_parsed_after_joining():
    assert parse_message('{"type": "report", "exam": "e1"}', joined=True)["exam"] == "e1"
    assert parse_message('{"type": "meeting"}', joined=True) == {"type": "meeting"}
    assert parse_message('{"type": "vote", "target": "skip"}', joined=True)["target"] == "skip"


# --- Rejected: each case returns (game, action) ready for one rejected call -----------


def report_by_ghost():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    return game, lambda: game.report(students[0].id, exam.id)  # standing on their own exam


def report_one_pixel_beyond_range():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    reporter = students[1]
    reporter.x, reporter.y = exam.x + REPORT_RANGE + 1, exam.y
    return game, lambda: game.report(reporter.id, exam.id)


def report_unknown_exam():
    game, (examiner,), students = playing(5)
    expel_now(game, examiner, students[0])
    return game, lambda: game.report(students[1].id, "e99")


def report_in_lobby():
    game, players = lobby(4)
    return game, lambda: game.report(players[0].id, "e1")


def report_in_meeting():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    game.call_meeting(students[2].id)
    return game, lambda: game.report(students[1].id, exam.id)  # the exam is still in reach


def report_in_ended():
    # Also R7: in the same tick as the expel that ended the game.
    game, (examiner,), students = playing(4)
    expel_now(game, examiner, students[0])
    exam = expel_now(game, examiner, students[1])  # examiners win
    return game, lambda: game.report(students[2].id, exam.id)


def report_of_exam_removed_by_previous_meeting():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    game.call_meeting(students[1].id)
    everyone_votes(game, "skip")
    return game, lambda: game.report(students[2].id, exam.id)


def report_by_unknown_player():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    return game, lambda: game.report("nobody", exam.id)


def bell_rung_a_second_time():
    game, _, students = bell_meeting(4)  # students[0] rang
    everyone_votes(game, "skip")
    return game, lambda: game.call_meeting(students[0].id)


def bell_by_ghost():
    game, (examiner,), students = playing(5)
    expel_now(game, examiner, students[0])
    return game, lambda: game.call_meeting(students[0].id)


def bell_in_lobby():
    game, players = lobby(4)
    return game, lambda: game.call_meeting(players[0].id)


def bell_in_meeting():
    game, _, students = bell_meeting(4)
    return game, lambda: game.call_meeting(students[1].id)


def bell_in_ended():
    game, (examiner,), students = playing(4)
    expel_now(game, examiner, students[0])
    expel_now(game, examiner, students[1])  # examiners win
    return game, lambda: game.call_meeting(students[2].id)


def bell_by_unknown_player():
    game, _, _ = playing(4)
    return game, lambda: game.call_meeting("nobody")


def vote_in_lobby():
    game, players = lobby(4)
    return game, lambda: game.vote(players[0].id, players[1].id)


def vote_while_playing():
    game, (examiner,), students = playing(4)
    return game, lambda: game.vote(students[0].id, examiner.id)


def vote_in_ended():
    game, (examiner,), students = playing(4)
    expel_now(game, examiner, students[0])
    expel_now(game, examiner, students[1])  # examiners win
    return game, lambda: game.vote(students[2].id, examiner.id)


def vote_by_ghost():
    game, (examiner,), students = playing(5)
    expel_now(game, examiner, students[0])
    game.call_meeting(students[1].id)
    return game, lambda: game.vote(students[0].id, students[1].id)


def second_vote_same_target():
    game, (examiner,), students = bell_meeting(4)
    game.vote(students[1].id, examiner.id)
    return game, lambda: game.vote(students[1].id, examiner.id)


def second_vote_other_target():
    game, (examiner,), students = bell_meeting(4)
    game.vote(students[1].id, examiner.id)
    return game, lambda: game.vote(students[1].id, "skip")


def vote_for_ghost():
    game, (examiner,), students = playing(5)
    expel_now(game, examiner, students[0])
    game.call_meeting(students[1].id)
    return game, lambda: game.vote(students[1].id, students[0].id)


def vote_for_unknown_id():
    game, _, students = bell_meeting(4)
    return game, lambda: game.vote(students[1].id, "nobody")


def vote_during_result():
    game, (examiner,), students = bell_meeting(4)
    wait_ticks(game, MEETING_TICKS)  # the timer runs out: the result is shown
    return game, lambda: game.vote(students[1].id, examiner.id)


def vote_by_unknown_player():
    game, (examiner,), _ = bell_meeting(4)
    return game, lambda: game.vote("nobody", examiner.id)


def move_during_voting():
    game, _, students = bell_meeting(4)
    return game, lambda: game.set_input(students[1].id, {"type": "input", "dx": 1, "dy": 0})


def move_during_result():
    game, _, students = bell_meeting(4)
    wait_ticks(game, MEETING_TICKS)
    return game, lambda: game.set_input(students[1].id, {"type": "input", "dx": 1, "dy": 0})


def expel_during_meeting():
    game, (examiner,), students = playing(4)
    wait_ticks(game, COOLDOWN_TICKS)  # cooldown over, everyone on the same spot
    game.call_meeting(students[0].id)
    return game, lambda: game.expel(examiner.id, students[1].id)


def join_during_meeting():
    game, _, _ = bell_meeting(4)
    return game, lambda: game.join("Late")


def start_during_meeting():
    game, _, _ = bell_meeting(4)
    return game, lambda: game.start(game.host_id)


def restart_during_meeting():
    game, _, _ = bell_meeting(4)
    return game, lambda: game.restart(game.host_id)


@pytest.mark.parametrize(
    "case, reason",
    [
        (report_by_ghost, "Ghosts cannot report"),
        (report_one_pixel_beyond_range, "No failed exam within reach"),
        (report_unknown_exam, "No failed exam within reach"),
        (report_in_lobby, "The game has not started yet"),
        (report_in_meeting, "A meeting is already running"),
        (report_in_ended, "Game is over"),
        (report_of_exam_removed_by_previous_meeting, "No failed exam within reach"),
        (report_by_unknown_player, "Unknown player"),
        (bell_rung_a_second_time, "You have already called a meeting"),
        (bell_by_ghost, "Ghosts cannot call a meeting"),
        (bell_in_lobby, "The game has not started yet"),
        (bell_in_meeting, "A meeting is already running"),
        (bell_in_ended, "Game is over"),
        (bell_by_unknown_player, "Unknown player"),
        (vote_in_lobby, "No meeting is running"),
        (vote_while_playing, "No meeting is running"),
        (vote_in_ended, "Game is over"),
        (vote_by_ghost, "Ghosts cannot vote"),
        (second_vote_same_target, "You have already voted"),
        (second_vote_other_target, "You have already voted"),
        (vote_for_ghost, "Can only vote for a living player"),
        (vote_for_unknown_id, "Unknown target"),
        (vote_during_result, "Voting has closed"),
        (vote_by_unknown_player, "Unknown player"),
        (move_during_voting, "Meeting in progress"),
        (move_during_result, "Meeting in progress"),
        (expel_during_meeting, "Meeting in progress"),
        (join_during_meeting, "already running"),
        (start_during_meeting, "already running"),
        (restart_during_meeting, "not over"),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_action_changes_nothing(case, reason):
    game, action = case()
    assert_rejected(game, action, reason)


# None stands for a missing field: server/main.py passes message.get("exam").
@pytest.mark.parametrize("exam_id", [1, None, True, ["e1"], {"id": "e1"}])
def test_report_with_an_exam_id_that_is_not_a_string_is_rejected(exam_id):
    game, (examiner,), students = playing(5)
    expel_now(game, examiner, students[0])
    assert_rejected(
        game, lambda: game.report(students[1].id, exam_id), "Exam must be a failed exam id"
    )


# None stands for a missing field: server/main.py passes message.get("target").
@pytest.mark.parametrize("target", [2, None, True, ["p2"], {"id": "p2"}])
def test_vote_with_a_target_that_is_not_a_string_is_rejected(target):
    game, _, students = bell_meeting(4)
    assert_rejected(
        game, lambda: game.vote(students[1].id, target), "Target must be a player id or skip"
    )


def test_unknown_exam_and_exam_out_of_reach_give_the_same_reason():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    reporter = students[1]
    reporter.x, reporter.y = exam.x + REPORT_RANGE + 1, exam.y
    with pytest.raises(GameError) as out_of_reach:
        game.report(reporter.id, exam.id)
    with pytest.raises(GameError) as unknown:
        game.report(reporter.id, "e99")
    assert str(out_of_reach.value) == str(unknown.value)


def test_nobody_moves_during_the_meeting():
    game, _, students = playing(4)
    walker = students[1]
    game.set_input(walker.id, {"type": "input", "dx": 1, "dy": 0})
    game.call_meeting(students[0].id)
    positions = [(p.x, p.y) for p in game.players.values()]
    with pytest.raises(GameError, match="Meeting in progress"):
        game.set_input(walker.id, {"type": "input", "dx": 1, "dy": 0})
    wait_ticks(game, MEETING_TICKS)  # the voting closes by the timer
    with pytest.raises(GameError, match="Meeting in progress"):
        game.set_input(walker.id, {"type": "input", "dx": 1, "dy": 0})
    wait_ticks(game, RESULT_TICKS - 1)  # the last tick of the result time
    assert game.phase == "meeting"
    assert [(p.x, p.y) for p in game.players.values()] == positions


@pytest.mark.parametrize(
    "raw",
    ['{"type": "report", "exam": "e1"}', '{"type": "meeting"}', '{"type": "vote", "target": "skip"}'],
)
def test_report_bell_and_vote_before_joining_are_rejected(raw):
    with pytest.raises(GameError, match="Join"):
        parse_message(raw, joined=False)


# --- Edge cases: two actions in the same tick (R7) ------------------------------------


def test_report_then_bell_in_the_same_tick_gives_one_meeting_and_keeps_the_bell():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    game.report(students[1].id, exam.id)
    with pytest.raises(GameError, match="A meeting is already running"):
        game.call_meeting(students[2].id)
    assert meeting_of(game, students[2])["reason"] == "report"
    assert game.snapshot_for(students[2].id)["meeting_used"] is False
    everyone_votes(game, "skip")
    game.call_meeting(students[2].id)  # the rejected bell was not used up
    assert meeting_of(game, students[2])["reason"] == "button"


def test_bell_then_report_in_the_same_tick_gives_one_meeting():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    game.call_meeting(students[2].id)
    with pytest.raises(GameError, match="A meeting is already running"):
        game.report(students[1].id, exam.id)
    meeting = meeting_of(game, students[1])
    assert (meeting["reason"], meeting["called_by"]) == ("button", students[2].id)


def test_two_reports_of_the_same_exam_in_one_tick_first_wins():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    game.report(students[1].id, exam.id)
    with pytest.raises(GameError, match="A meeting is already running"):
        game.report(students[2].id, exam.id)
    assert meeting_of(game, students[1])["called_by"] == students[1].id


def test_two_bells_in_one_tick_first_wins_and_the_second_is_not_used_up():
    game, _, students = playing(4)
    game.call_meeting(students[0].id)
    with pytest.raises(GameError, match="A meeting is already running"):
        game.call_meeting(students[1].id)
    assert meeting_of(game, students[1])["called_by"] == students[0].id
    assert game.snapshot_for(students[1].id)["meeting_used"] is False


def test_report_then_expel_in_the_same_tick_rejects_the_expel():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    wait_ticks(game, COOLDOWN_TICKS)  # the examiner could expel again
    game.report(students[1].id, exam.id)
    with pytest.raises(GameError, match="Meeting in progress"):
        game.expel(examiner.id, students[2].id)
    assert students[2].alive is True
    assert len(game.failed_exams) == 1


def test_expel_then_report_of_the_new_exam_in_the_same_tick_is_accepted():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    game.report(students[1].id, exam.id)  # no step() in between
    assert game.phase == "meeting"
    assert meeting_of(game, students[1])["reason"] == "report"


# --- Edge cases: range, timer and counting --------------------------------------------


def test_report_from_exactly_report_range_is_accepted():
    game, (examiner,), students = playing(5)
    exam = expel_now(game, examiner, students[0])
    reporter = students[1]
    reporter.x, reporter.y = exam.x + REPORT_RANGE, exam.y
    game.report(reporter.id, exam.id)
    assert game.phase == "meeting"


def test_voting_closes_after_exactly_sixty_seconds_and_non_voters_skip():
    game, (examiner,), students = bell_meeting(4)
    assert meeting_of(game, students[1])["seconds_left"] == MEETING_SECONDS
    wait_ticks(game, MEETING_TICKS - 1)
    meeting = meeting_of(game, students[1])
    assert meeting["seconds_left"] == 1  # one tick left: rounded up
    assert meeting["result"] is None
    game.vote(students[1].id, examiner.id)  # one tick before 60 s: accepted
    game.step()  # exactly 60 s

    meeting = meeting_of(game, students[1])
    assert meeting["result"]["votes"][examiner.id] == 1
    assert meeting["result"]["skips"] == 3  # the three who did not vote
    assert meeting["result"]["surfing"] is None
    assert meeting["seconds_left"] == RESULT_SECONDS
    with pytest.raises(GameError, match="Voting has closed"):
        game.vote(students[2].id, "skip")


def test_nobody_voting_sends_nobody_surfing_and_the_game_goes_on():
    game, _, students = bell_meeting(4)
    wait_ticks(game, MEETING_TICKS)
    assert meeting_of(game, students[0])["result"] == {
        "votes": {player_id: 0 for player_id in game.players},
        "skips": 4,
        "surfing": None,
    }
    wait_ticks(game, RESULT_TICKS)
    assert game.phase == "playing"
    assert all(p.alive for p in game.players.values())


# Ballots in join order: the index of the player voted for, "skip", or None (no vote).
@pytest.mark.parametrize(
    "ballots, votes, skips",
    [
        ([1, 0, 1, 0], [2, 2, 0, 0], 0),
        ([1, "skip", 1, "skip"], [0, 2, 0, 0], 2),
        ([1, "skip", "skip", "skip"], [0, 1, 0, 0], 3),
        ([1, None, None, None], [0, 1, 0, 0], 3),
    ],
    ids=["tie_2_2", "votes_equal_skips", "more_skips", "one_vote_then_timer"],
)
def test_without_a_clear_majority_nobody_is_sent_surfing(ballots, votes, skips):
    game, players = lobby(4)
    game.start(players[0].id)
    game.call_meeting(players[0].id)
    for voter, ballot in zip(players, ballots):
        if ballot is not None:
            game.vote(voter.id, "skip" if ballot == "skip" else players[ballot].id)
    result = close_voting(game, players[0])
    assert result == {
        "votes": {p.id: count for p, count in zip(players, votes)},
        "skips": skips,
        "surfing": None,
    }
    assert all(p.alive for p in players)


def test_a_vote_for_yourself_is_rejected():
    """Spec 008, part 2 replaces spec 006's "a vote for yourself counts"."""
    game, _, students = bell_meeting(4)
    me = students[1]
    assert_rejected(game, lambda: game.vote(me.id, me.id), "You cannot vote for yourself")


def test_voting_closes_at_the_next_tick_once_every_living_player_has_voted():
    game, (examiner,), students = playing(5)
    expel_now(game, examiner, students[0])  # a ghost, who does not vote
    game.call_meeting(students[1].id)
    for player in [examiner, students[1], students[2], students[3]]:
        game.vote(player.id, "skip")
    assert meeting_of(game, students[1])["result"] is None  # not before the tick
    game.step()
    meeting = meeting_of(game, students[1])
    assert meeting["result"] is not None
    assert meeting["seconds_left"] == RESULT_SECONDS  # well before the 60 s timer


def test_living_lists_the_living_players_in_join_order():
    game, (examiner,), students = playing(5)
    expel_now(game, examiner, students[1])
    game.call_meeting(students[0].id)
    living = [p.id for p in game.players.values() if p.alive]
    assert students[1].id not in living
    for player_id in game.players:  # the ghost too
        assert game.snapshot_for(player_id)["meeting"]["living"] == living
    assert meeting_of(game, students[1])["my_vote"] is None


# --- Edge cases: leaving during a meeting ---------------------------------------------


def test_leaving_removes_the_leavers_vote_and_the_votes_for_them():
    game, (examiner,), students = bell_meeting(5)
    leaver = students[3]
    game.vote(students[1].id, leaver.id)
    game.vote(students[2].id, leaver.id)
    game.vote(leaver.id, "skip")
    game.vote(examiner.id, students[1].id)
    game.leave(leaver.id)

    assert game.phase == "meeting"  # 1 examiner, 3 students
    meeting = meeting_of(game, students[1])
    assert meeting["voted"] == [examiner.id]
    assert meeting["living"] == [p.id for p in game.players.values()]
    assert meeting["my_vote"] is None
    assert meeting_of(game, students[2])["my_vote"] is None
    game.vote(students[1].id, "skip")  # they can vote again
    game.vote(students[2].id, examiner.id)


def test_voting_closes_when_the_last_player_who_has_not_voted_leaves():
    game, (examiner,), students = bell_meeting(5)
    for player in [examiner, students[0], students[1], students[2]]:
        game.vote(player.id, "skip")
    game.leave(students[3].id)
    assert meeting_of(game, students[0])["result"] is None
    game.step()
    result = meeting_of(game, students[0])["result"]
    assert result["skips"] == 4
    assert set(result["votes"]) == set(game.players)


def test_only_examiner_leaving_during_the_vote_lets_the_students_win():
    game, (examiner,), students = bell_meeting(4)
    game.vote(students[1].id, examiner.id)
    game.leave(examiner.id)
    assert game.phase == "ended"
    for student in students:
        snapshot = game.snapshot_for(student.id)
        assert snapshot["winner"] == "students"
        assert "meeting" not in snapshot


# --- Edge cases: players sent surfing -------------------------------------------------


def test_a_student_sent_surfing_is_a_ghost_who_can_no_longer_report_ring_or_vote():
    game, (examiner,), students = playing(5)
    surfer = students[0]
    game.call_meeting(students[1].id)
    for player in game.players.values():
        game.vote(player.id, "skip" if player is surfer else surfer.id)
    game.step()
    assert surfer.alive is False
    assert game.failed_exams == []
    wait_ticks(game, RESULT_TICKS)
    assert game.phase == "playing"  # 1 examiner, 3 students

    exam = expel_now(game, examiner, students[1])  # 1 examiner, 2 students; exam in reach
    assert_rejected(game, lambda: game.report(surfer.id, exam.id), "Ghosts cannot report")
    assert_rejected(game, lambda: game.call_meeting(surfer.id), "Ghosts cannot call a meeting")
    game.call_meeting(students[2].id)
    assert_rejected(game, lambda: game.vote(surfer.id, "skip"), "Ghosts cannot vote")


def test_an_examiner_sent_surfing_can_no_longer_expel():
    game, (first, _), students = bell_meeting(7)
    everyone_votes(game, first)
    assert game.phase == "playing"
    wait_ticks(game, COOLDOWN_TICKS)
    assert_rejected(game, lambda: game.expel(first.id, students[1].id), "Ghosts cannot expel")


# --- Edge cases: vision and privacy ---------------------------------------------------


def test_vision_in_a_meeting_has_no_radius_but_ghosts_stay_hidden_from_the_living():
    game, (examiner,), students = playing(5)
    ghost = students[0]
    exam = expel_now(game, examiner, ghost)
    viewer = students[2]
    viewer.x, viewer.y = tile_centre(26, 13)  # far from everyone else and from the exam
    playing_view = game.snapshot_for(viewer.id)
    assert ids_in(playing_view) == [viewer.id]
    assert playing_view["failed_exams"] == []

    game.call_meeting(viewer.id)
    view = game.snapshot_for(viewer.id)
    living = sorted(p.id for p in game.players.values() if p.alive)
    assert ids_in(view) == living
    assert ghost.id not in view["colors"]
    assert [e["id"] for e in view["failed_exams"]] == [exam.id]
    assert all(set(p) == PLAYER_KEYS for p in view["players"])
    ghost_view = game.snapshot_for(ghost.id)
    assert ids_in(ghost_view) == sorted(game.players)
    assert len(ghost_view["failed_exams"]) == 1

    everyone_votes(game, "skip")
    assert game.phase == "playing"
    assert ids_in(game.snapshot_for(viewer.id)) == [viewer.id]  # the radius applies again


def test_nobody_learns_whom_another_player_voted_for():
    def others_see(choice):
        """What everyone but players[1] receives after players[1] voted for `choice`."""
        game, _, _ = bell_meeting(4)
        players = list(game.players.values())
        voter = players[1]
        game.vote(voter.id, choice if choice == "skip" else players[choice].id)
        return {p.id: game.snapshot_for(p.id) for p in players if p is not voter}

    assert others_see("skip") == others_see(0) == others_see(2) == others_see(3)


def test_meeting_and_result_contain_only_the_allowed_fields():
    game, (examiner,), students = bell_meeting(4)
    for player_id in game.players:
        assert set(game.snapshot_for(player_id)["meeting"]) == MEETING_KEYS
    for player in game.players.values():
        game.vote(player.id, "skip" if player is examiner else examiner.id)
    game.step()
    for player_id in game.players:
        meeting = game.snapshot_for(player_id)["meeting"]
        assert set(meeting) == MEETING_KEYS
        assert set(meeting["result"]) == {"votes", "skips", "surfing"}


def test_a_students_snapshot_shows_no_other_role_during_or_after_a_meeting():
    game, _, students = playing(7)

    def assert_no_roles():
        for student in students:
            snapshot = game.snapshot_for(student.id)
            assert "roles" not in snapshot
            assert "examiner" not in json.dumps(snapshot)
            assert all(set(p) == PLAYER_KEYS for p in snapshot["players"])

    game.call_meeting(students[0].id)
    assert_no_roles()  # voting
    for player in game.players.values():
        game.vote(player.id, "skip" if player is students[1] else students[1].id)
    game.step()
    assert_no_roles()  # result
    wait_ticks(game, RESULT_TICKS)
    assert game.phase == "playing"
    assert_no_roles()  # after the meeting


# --- Edge cases: cooldown, clean-up and placement -------------------------------------


def test_examiner_cooldown_restarts_in_full_at_the_end_of_the_meeting():
    game, (examiner,), students = playing(4)
    wait_ticks(game, COOLDOWN_TICKS)  # the cooldown is over before the meeting
    game.call_meeting(students[0].id)
    everyone_votes(game, "skip")  # the meeting ends with this tick
    assert game.phase == "playing"
    wait_ticks(game, COOLDOWN_TICKS - 1)
    with pytest.raises(GameError, match="Cooldown"):
        game.expel(examiner.id, students[1].id)
    game.step()
    game.expel(examiner.id, students[1].id)
    assert students[1].alive is False


def test_restart_after_a_game_that_ended_in_a_meeting_clears_meeting_and_bell():
    game, (examiner,), students = bell_meeting(4)  # students[0] rang
    game.vote(students[1].id, "skip")
    game.leave(examiner.id)  # students win during the meeting
    assert game.phase == "ended"
    assert game.meeting is None
    game.restart(game.host_id)
    assert game.phase == "lobby"
    assert game.meeting is None
    for player_id in game.players:
        snapshot = game.snapshot_for(player_id)
        assert snapshot["meeting_used"] is False
        assert "meeting" not in snapshot


def test_everyone_leaving_during_a_meeting_leaves_a_clean_lobby():
    game, examiners, students = bell_meeting(4)
    game.vote(students[1].id, examiners[0].id)
    for player_id in list(game.players):
        game.leave(player_id)
    assert game.phase == "lobby"
    assert game.meeting is None
    newcomer = game.join("Newcomer")
    snapshot = game.snapshot_for(newcomer.id)
    assert snapshot["meeting_used"] is False
    assert "meeting" not in snapshot


# Spec 011: the Auditorium is no meeting room any more, so its seating order has no rule
# left to test. On a map with an Auditorium but without a meeting point nobody is moved;
# tests/test_spec011.py tests the circle around the table and a map too tight for it.
def test_an_auditorium_without_a_meeting_point_moves_nobody():
    game, players = lobby(MAX_PLAYERS, campus=TINY_MAP)
    game.start(players[0].id)
    players[8].x, players[8].y = 200.0, 100.0
    players[9].x, players[9].y = 250.0, 200.0
    game.set_input(players[9].id, {"type": "input", "dx": -1, "dy": 0})
    positions = [(p.x, p.y) for p in players]
    game.call_meeting(players[0].id)
    assert [(p.x, p.y) for p in players] == positions
    assert all((p.dx, p.dy) == (0, 0) for p in players)


def test_without_an_auditorium_everyone_stays_where_they_are():
    game, _, students = playing(4)
    students[1].x, students[1].y = 300.5, 200.25
    game.set_input(students[1].id, {"type": "input", "dx": 1, "dy": 1})
    positions = [(p.x, p.y) for p in game.players.values()]
    game.call_meeting(students[0].id)
    assert [(p.x, p.y) for p in game.players.values()] == positions
    assert all((p.dx, p.dy) == (0, 0) for p in game.players.values())


def test_campus_auditorium_has_a_floor_tile_for_every_player():
    game = Game(load_map())
    (area,) = [a for a in game.campus["areas"] if a["name"] == "Auditorium"]
    floor = [
        (col, row)
        for row in range(area["y"], area["y"] + area["h"])
        for col in range(area["x"], area["x"] + area["w"])
        if not game.blocked(*tile_centre(col, row))
    ]
    assert len(floor) >= MAX_PLAYERS


# --- Over the real WebSocket endpoint -------------------------------------------------

FIVE_SECONDS = 5 * TICK_RATE


def receive_until(ws, predicate, limit=FIVE_SECONDS):
    """Read messages until one matches, or fail after `limit` messages."""
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def in_meeting(message):
    return message["type"] == "state" and message["phase"] == "meeting"


def has_result(message):
    return in_meeting(message) and message["meeting"]["result"] is not None


def start_four(clients, names):
    """Join four clients and start the game. Returns their ids and roles in client order."""
    ids = []
    for ws, name in zip(clients, names):
        ws.send_json({"type": "join", "name": name})
        welcome = receive_until(ws, lambda m: m["type"] in ("welcome", "error"))
        assert welcome["type"] == "welcome"
        assert welcome["report_range"] == REPORT_RANGE
        ids.append(welcome["id"])
    clients[0].send_json({"type": "start"})
    roles = [
        receive_until(ws, lambda m: m["type"] == "state" and m["phase"] == "playing")["role"]
        for ws in clients
    ]
    return ids, roles


def test_bell_over_websocket_opens_the_meeting_for_every_client(fresh_game):
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            clients = [a, b, c, d]
            ids, _ = start_four(clients, ["Ada", "Bo", "Cy", "Di"])
            go_to_bell(fresh_game.players[ids[1]])
            b.send_json({"type": "meeting"})
            for ws in clients:
                meeting = receive_until(ws, in_meeting)["meeting"]
                assert meeting["reason"] == "button"
                assert meeting["called_by"] == ids[1]
                assert meeting["living"] == ids


def test_second_vote_over_websocket_gets_an_error_and_the_connection_stays_usable(fresh_game):
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            clients = [a, b, c, d]
            ids, _ = start_four(clients, ["Eli", "Fay", "Gus", "Hal"])
            go_to_bell(fresh_game.players[ids[0]])
            a.send_json({"type": "meeting"})
            receive_until(a, in_meeting)
            a.send_json({"type": "vote", "target": "skip"})
            a.send_json({"type": "vote", "target": "skip"})
            error = receive_until(a, lambda m: m["type"] == "error")
            assert "You have already voted" in error["reason"]
            state = receive_until(a, lambda m: in_meeting(m) and m["meeting"]["my_vote"])
            assert state["meeting"]["my_vote"] == "skip"


def test_four_votes_over_websocket_send_the_student_surfing(fresh_game):
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws") as a,
            client.websocket_connect("/ws") as b,
            client.websocket_connect("/ws") as c,
            client.websocket_connect("/ws") as d,
        ):
            clients = [a, b, c, d]
            ids, roles = start_four(clients, ["Ivy", "Jay", "Kim", "Lou"])
            target = ids[roles.index("student")]
            go_to_bell(fresh_game.players[ids[0]])
            a.send_json({"type": "meeting"})
            for ws in clients:
                receive_until(ws, in_meeting)
            for ws, player_id in zip(clients, ids):
                ws.send_json({"type": "vote", "target": "skip" if player_id == target else target})
            for ws, player_id in zip(clients, ids):
                state = receive_until(ws, has_result)
                result = state["meeting"]["result"]
                assert result["votes"][target] == 3
                assert result["skips"] == 1
                assert result["surfing"] == target
                if player_id == target:
                    assert state["alive"] is False
