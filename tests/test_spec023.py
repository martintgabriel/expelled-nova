"""Tests for spec 023: the sabotage menu (lights, fire alarm, Wi-Fi down)."""

import json
import random
from pathlib import Path

import pytest

from server import game as rules
from server.game import (
    FIRE_TICKS,
    FIX_TICKS,
    SABOTAGE_COOLDOWN_TICKS,
    FailedExam,
    Game,
    GameError,
    load_map,
    parse_message,
)

WEB = Path(__file__).resolve().parent.parent / "web"


def started(count=5, seed=0):
    """A round on the real campus in which the first sabotage cooldown is over."""
    game = Game(load_map(), rng=random.Random(seed))
    players = [game.join(f"P{i}") for i in range(count)]
    game.start(players[0].id)
    game.guard = None  # spec 027's guard never interferes with these tests
    for _ in range(SABOTAGE_COOLDOWN_TICKS):
        game.step()
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


def place(game, kind):
    return next(s for s in game.campus["sabotages"] if s["kind"] == kind)


def stand_on(game, player, col, row):
    player.x, player.y = (col + 0.5) * game.tile, (row + 0.5) * game.tile
    player.dx = player.dy = 0


def evacuate(game, player):
    area = place(game, "fire")["assembly"]
    stand_on(game, player, area["x"], area["y"])


def emergency(game, player):
    return game.snapshot_for(player.id)["emergency"]


# --- The campus data -------------------------------------------------------------------------------


def test_the_campus_has_three_sabotage_places_on_the_floor():
    campus = load_map()
    kinds = [s["kind"] for s in campus["sabotages"]]
    assert kinds == ["lights", "fire", "wifi"]
    for entry in campus["sabotages"]:
        assert entry["name"]
        assert campus["grid"][entry["y"]][entry["x"]] == "."
    lights = next(s for s in campus["sabotages"] if s["kind"] == "lights")
    assert [lights["x"], lights["y"]] == campus["light_switch"]
    area = next(s for s in campus["sabotages"] if s["kind"] == "fire")["assembly"]
    for row in range(area["y"], area["y"] + area["h"]):
        for col in range(area["x"], area["x"] + area["w"]):
            assert campus["grid"][row][col] == "."


# --- Choosing ------------------------------------------------------------------------------------------


def test_the_old_message_without_kind_still_turns_off_the_lights():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id)
    assert game.lights_on is False
    assert emergency(game, students[0]) == {"kind": "lights", "seconds_left": None}


@pytest.mark.parametrize("kind", ["lights", "fire", "wifi"])
def test_an_examiner_can_choose_each_sabotage(kind):
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, kind)
    assert emergency(game, students[0])["kind"] == kind


def test_a_sabotage_message_with_a_kind_parses():
    message = parse_message(json.dumps({"type": "sabotage", "kind": "fire"}), joined=True)
    assert message["kind"] == "fire"


@pytest.mark.parametrize("kind", ["boom", "", "LIGHTS", 3, None, ["fire"], True])
def test_an_unknown_sabotage_is_rejected(kind):
    game, (examiner, *_), students = started()
    with pytest.raises(GameError, match="Unknown sabotage"):
        game.sabotage(examiner.id, kind)
    assert emergency(game, students[0]) is None


def test_a_student_cannot_sabotage():
    game, _, students = started()
    with pytest.raises(GameError, match="Only examiners"):
        game.sabotage(students[0].id, "fire")
    assert emergency(game, students[0]) is None


def test_a_ghost_examiner_cannot_sabotage():
    game, (examiner, *_), students = started()
    examiner.alive = False
    with pytest.raises(GameError, match="Ghosts"):
        game.sabotage(examiner.id, "wifi")


def test_only_one_emergency_at_a_time():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "wifi")
    for kind in ("fire", "lights"):
        with pytest.raises(GameError, match="An emergency is already running"):
            game.sabotage(examiner.id, kind)
    assert emergency(game, students[0])["kind"] == "wifi"


def test_the_cooldown_is_shared_by_every_kind():
    game = Game(load_map(), rng=random.Random(0))
    players = [game.join(f"P{i}") for i in range(5)]
    game.start(players[0].id)
    examiner = next(p for p in players if p.role == "examiner")
    with pytest.raises(GameError, match="cooldown"):
        game.sabotage(examiner.id, "fire")


def test_no_sabotage_in_the_lobby_or_a_meeting():
    game = Game(load_map(), rng=random.Random(0))
    players = [game.join(f"P{i}") for i in range(5)]
    with pytest.raises(GameError, match="not started"):
        game.sabotage(players[0].id, "fire")
    game, (examiner, *_), students = started()
    game.failed_exams.append(FailedExam("e1", students[0].x, students[0].y))
    game.report(students[0].id, "e1")
    with pytest.raises(GameError, match="Meeting in progress"):
        game.sabotage(examiner.id, "fire")


def test_a_map_without_sabotage_places_only_has_the_lights():
    campus = {k: v for k, v in load_map().items() if k != "sabotages"}
    game = Game(campus, rng=random.Random(0))
    players = [game.join(f"P{i}") for i in range(5)]
    game.start(players[0].id)
    game.guard = None
    for _ in range(SABOTAGE_COOLDOWN_TICKS):
        game.step()
    examiner = next(p for p in players if p.role == "examiner")
    with pytest.raises(GameError, match="no fire alarm"):
        game.sabotage(examiner.id, "fire")
    game.sabotage(examiner.id, "lights")
    assert game.lights_on is False


# --- Fire alarm ---------------------------------------------------------------------------------------


def test_the_fire_alarm_counts_down_and_counts_the_evacuated():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "fire")
    for player in (examiner, *students):
        state = emergency(game, player)
        assert state == {"kind": "fire", "seconds_left": rules.FIRE_SECONDS, "evacuated": 0, "students": len(students)}
    evacuate(game, students[0])
    game.step()
    assert emergency(game, students[1])["evacuated"] == 1
    stand_on(game, students[0], 22, 4)  # leaving again does not undo it
    game.step()
    assert emergency(game, students[1])["evacuated"] == 1


def test_every_living_student_evacuated_ends_the_alarm():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "fire")
    for student in students:
        evacuate(game, student)
    game.step()
    assert emergency(game, students[0]) is None
    assert game.phase == "playing"
    assert game.next_sabotage_tick == game.tick + SABOTAGE_COOLDOWN_TICKS


def test_examiners_need_not_evacuate():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "fire")
    stand_on(game, examiner, 22, 4)
    for student in students:
        evacuate(game, student)
    game.step()
    assert emergency(game, students[0]) is None


def test_the_examiners_win_when_the_time_runs_out():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "fire")
    evacuate(game, students[0])
    for _ in range(FIRE_TICKS + 1):
        game.step()
    assert game.phase == "ended"
    assert game.winner == "examiners"
    assert game.snapshot_for(students[0].id)["fire_lost"] is True


def test_the_emergency_button_is_blocked_during_the_fire_alarm_but_a_report_is_not():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "fire")
    stand_on(game, students[0], *game.campus["meeting_point"])
    with pytest.raises(GameError, match="Not during the fire alarm"):
        game.call_meeting(students[0].id)
    assert students[0].meeting_used is False
    game.failed_exams.append(FailedExam("e1", students[1].x, students[1].y))
    game.report(students[1].id, "e1")
    assert game.phase == "meeting"
    assert emergency(game, students[0]) is None


# --- Wi-Fi down ------------------------------------------------------------------------------------------


def task_ready(game, student):
    task_id = student.tasks[0]
    station = game._current_station(student, task_id)
    stand_on(game, student, station["x"], station["y"])
    return task_id


def test_no_task_can_start_without_wi_fi():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "wifi")
    task_id = task_ready(game, students[0])
    with pytest.raises(GameError, match="No Wi-Fi"):
        game.task(students[0].id, task_id)
    assert students[0].doing is None


def test_a_running_task_is_cancelled_when_the_wi_fi_goes_down():
    game, (examiner, *_), students = started()
    task_id = task_ready(game, students[0])
    game.task(students[0].id, task_id)
    game.sabotage(examiner.id, "wifi")
    assert students[0].doing is None and students[0].challenge is None
    assert students[0].task_note == "No Wi-Fi. Try again later."


def test_the_router_fixes_the_wi_fi_after_three_seconds():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "wifi")
    router = place(game, "wifi")
    stand_on(game, students[0], router["x"], router["y"])
    game.fix(students[0].id)
    assert game.snapshot_for(students[0].id)["fixing"]["seconds_left"] == 3
    for _ in range(FIX_TICKS):
        game.step()
    assert emergency(game, students[0]) is None
    assert game.next_sabotage_tick == game.tick + SABOTAGE_COOLDOWN_TICKS
    task_id = task_ready(game, students[0])
    game.task(students[0].id, task_id)  # works again


def test_walking_away_from_the_router_stops_the_fix():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "wifi")
    router = place(game, "wifi")
    stand_on(game, students[0], router["x"], router["y"])
    game.fix(students[0].id)
    stand_on(game, students[0], 22, 4)
    for _ in range(FIX_TICKS + 1):
        game.step()
    assert emergency(game, students[0])["kind"] == "wifi"


def test_fixing_far_from_the_router_is_rejected():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "wifi")
    stand_on(game, students[0], 22, 4)
    with pytest.raises(GameError, match="Too far from the router"):
        game.fix(students[0].id)


def test_an_examiner_can_restart_the_router_too():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "wifi")
    router = place(game, "wifi")
    stand_on(game, examiner, router["x"], router["y"])
    game.fix(examiner.id)
    for _ in range(FIX_TICKS):
        game.step()
    assert emergency(game, students[0]) is None


def test_a_meeting_ends_every_emergency():
    game, (examiner, *_), students = started()
    game.sabotage(examiner.id, "wifi")
    game.failed_exams.append(FailedExam("e1", students[1].x, students[1].y))
    game.report(students[1].id, "e1")
    assert emergency(game, students[0]) is None


# --- Client ----------------------------------------------------------------------------------------------


def test_the_client_opens_the_map_to_choose_and_shows_the_emergency():
    script = (WEB / "main.js").read_text(encoding="utf-8")
    assert "CampusMap.setSabotageChoices(" in script
    assert 'send({ type: "sabotage", kind' in script
    assert "emergency-banner" in (WEB / "index.html").read_text(encoding="utf-8")
    assert "function setSabotageChoices(" in (WEB / "campusmap.js").read_text(encoding="utf-8")
