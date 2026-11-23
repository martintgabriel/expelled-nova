"""Tests for spec 004 (Nova tasks and the students' task win), built as spec 008, part 5.

Unit tests against server/game.py first, then the WebSocket endpoint. The tests marked
"Reliability" cover the checklist of spec 008, part 5: a task not counting, counting twice,
staying stuck when the player walks away, during a meeting, after being expelled, after a
new round.
"""

import copy
import dataclasses
import json
import random

import pytest
from fastapi.testclient import TestClient

from server import game as rules
from server import minigames
from server.game import TICK_RATE, Game, GameError, load_map, parse_message
from server.main import app

TILE = 32
TASK_RANGE = 48  # px from the player's centre to the centre of the task's tile
TASKS_PER_STUDENT = 3
PLAYER_KEYS = {"id", "name", "x", "y"}
TASK_KEYS = {"id", "title", "area", "x", "y", "done"}

# One big open hall with six task places. t1 and t2 are neighbours, so a player standing
# on one is within reach of the other. Everyone spawns on tile (2, 2), far from every task.
TASK_MAP = {
    "tile_size": TILE,
    "grid": ["#" * 30] + ["#" + "." * 28 + "#"] * 14 + ["#" * 30],
    "areas": [{"name": "Hall", "x": 1, "y": 1, "w": 28, "h": 14, "color": "#3f6e8c"}],
    "spawns": [[2, 2]],
    "tasks": [
        {"id": "t1", "title": "Task one", "area": "Hall", "x": 6, "y": 2, "seconds": 5, "joke": "Joke one"},
        {"id": "t2", "title": "Task two", "area": "Hall", "x": 7, "y": 2, "seconds": 6, "joke": "Joke two"},
        {"id": "t3", "title": "Task three", "area": "Hall", "x": 12, "y": 2, "seconds": 7, "joke": "Joke three"},
        {"id": "t4", "title": "Task four", "area": "Hall", "x": 18, "y": 2, "seconds": 8, "joke": "Joke four"},
        {"id": "t5", "title": "Task five", "area": "Hall", "x": 6, "y": 10, "seconds": 5, "joke": "Joke five"},
        {"id": "t6", "title": "Task six", "area": "Hall", "x": 20, "y": 10, "seconds": 10, "joke": "Joke six"},
    ],
}
# A map without tasks, like the maps of the earlier specs.
PLAIN_MAP = {key: value for key, value in TASK_MAP.items() if key != "tasks"}

# A map with one 2-step task ("cert"), far apart, for testing the multi-step engine
# (spec 012, part 4) on its own, independent of the real campus's "certificate".
MULTISTEP_MAP = {
    **{key: value for key, value in TASK_MAP.items() if key != "tasks"},
    "tasks": [
        {
            "id": "cert",
            "joke": "Two stamps later.",
            "steps": [
                {"title": "Step A", "area": "Hall", "x": 6, "y": 2, "minigame": "paper_jam"},
                {"title": "Step B", "area": "Hall", "x": 20, "y": 10, "minigame": "ticket"},
            ],
        },
    ],
}

# The task places of spec 012: id -> a list of (area, column, row, mini-game kind), one
# tuple per station. Replaces spec 004's SPEC_TASKS table (which had "coffee" and
# "eduroam" with a plain "seconds" wait; spec 012 deletes both and gives every remaining
# task a mini-game instead). "certificate" has two stations (spec 012, part 4).
# Spec 015: the beach grew by 4 columns in the west, so every column here moved by 4.
SPEC_TASKS = {
    "certificate": [
        ("Library", 37, 22, "cert_file"),  # spec 024: was paper_jam
        ("Student Services", 39, 3, "ticket"),
    ],
    "helpdesk": [("Main Entrance", 24, 3, "chat")],  # spec 024: was translate
    "print": [("Library", 41, 20, "print_file")],  # spec 024: was paper_jam
    "socket": [("Auditorium", 34, 40, "cable")],
    "gate": [("Main Entrance", 28, 6, "card")],
    "nata": [("Lower Courtyard", 23, 23, "nata")],  # spec 031: was seagull  # spec 018: the courtyards are named apart
    "tray": [("Cafeteria", 41, 12, "tray")],  # spec 021
    "surf": [("Beach", 3, 17, "surf")],  # spec 021 (playtest: the middle of the beach)
    "beer": [("Beach", 3, 33, "beer")],  # spec 035
    "frisbee": [("Little Courtyard", 10, 34, "frisbee")],  # spec 035
    "seat": [("Lecture hall B", 9, 10, "seat")],  # spec 035 (playtest: in Lecture hall B)
}


def stations_of(task):
    """A task's stations as raw campus.json dicts: its "steps" list, or itself as the
    only station (a one-station task, spec 012 part 4)."""
    return task["steps"] if "steps" in task else [task]


# --- Helpers ----------------------------------------------------------------------


def new_round(count=4, seed=0, campus=TASK_MAP):
    """A started game. Returns the game, its examiners and its students (Player objects)."""
    game = Game(campus, rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


def round_with(*task_ids, count=4):
    """A started game in which one student has all of `task_ids`. That student comes first."""
    for seed in range(200):
        game, examiners, students = new_round(count, seed)
        for student in students:
            if set(task_ids) <= set(student.tasks):
                return game, examiners, [student] + [s for s in students if s is not student]
    raise AssertionError(f"no seed deals {task_ids} to one student")


def place_of(game, task_id):
    """The centre of a task's tile, in pixels."""
    task = next(t for t in game.campus["tasks"] if t["id"] == task_id)
    return (task["x"] + 0.5) * TILE, (task["y"] + 0.5) * TILE


def ticks_of(game, task_id):
    task = next(t for t in game.campus["tasks"] if t["id"] == task_id)
    return task["seconds"] * TICK_RATE


def go_to(game, player, task_id, dx=0, dy=0):
    """Put a player on a task place, or `dx`, `dy` pixels next to it."""
    x, y = place_of(game, task_id)
    player.x, player.y = x + dx, y + dy


def wait(game, ticks):
    for _ in range(ticks):
        game.step()


def do_task(game, student, task_id):
    """Walk to the task place, start the task and stay until it is done."""
    go_to(game, student, task_id)
    game.task(student.id, task_id)
    wait(game, ticks_of(game, task_id))


def progress(game, viewer):
    return game.snapshot_for(viewer.id)["task_progress"]


def entry(game, student, task_id):
    """The student's own snapshot entry of one task."""
    return next(t for t in game.snapshot_for(student.id)["tasks"] if t["id"] == task_id)


def doing(game, student):
    return game.snapshot_for(student.id)["doing"]


def ready_examiner(game, examiner):
    """Let the examiner's first cooldown pass (nobody moves meanwhile)."""
    wait(game, max(0, examiner.next_expel_tick - game.tick))


def expel(game, examiner, student):
    examiner.x, examiner.y = student.x, student.y
    game.expel(examiner.id, student.id)


def skip_meeting(game):
    """Every living player skips; the meeting runs to its end."""
    for player in [p for p in game.players.values() if p.alive]:
        game.vote(player.id, "skip")
    game.step()  # the voting closes
    wait(game, rules.RESULT_SECONDS * TICK_RATE)


def full_state(game):
    """Everything a rejected action must leave unchanged, including what every player sees."""
    return (
        game.phase,
        game.winner,
        [dataclasses.asdict(p) for p in game.players.values()],  # tasks and progress too
        [dataclasses.asdict(e) for e in game.failed_exams],
        copy.deepcopy(game.meeting),
        {player_id: game.snapshot_for(player_id) for player_id in game.players},
    )


def assert_rejected(game, action, reason):
    before = full_state(game)
    with pytest.raises(GameError, match=reason):
        action()
    assert full_state(game) == before


def multistep_round(count=4, seed=0):
    """A started game on MULTISTEP_MAP: every player is dealt its one task, "cert"."""
    game = Game(MULTISTEP_MAP, rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    game.start(players[0].id)
    students = [p for p in players if p.role == "student"]
    return game, students


def multistep_place(index):
    """The centre of MULTISTEP_MAP's "cert" station `index` (0 or 1), in pixels."""
    station = MULTISTEP_MAP["tasks"][0]["steps"][index]
    return (station["x"] + 0.5) * TILE, (station["y"] + 0.5) * TILE


def solve_paper_jam(game, player, task_id):
    for cell in list(player.challenge["jams"]):
        game.task_input(player.id, task_id, cell)


def solve_ticket(game, player, task_id):
    wait(game, player.challenge["number"] * TICK_RATE)
    game.task_input(player.id, task_id, True)


# --- Map data ---------------------------------------------------------------------


def test_the_campus_has_the_six_task_places_of_spec_012():
    # Replaces spec 004's test of the same shape: "coffee" and "eduroam" are gone (no
    # mini-game fits them), every remaining task has a "minigame" kind instead of a plain
    # "seconds" wait (spec 012, part 1), and "certificate" has two stations instead of
    # one flat place (spec 012, part 4), so there is no single flat table any more.
    tasks = load_map()["tasks"]
    assert len({task["id"] for task in tasks}) == len(tasks) == 11  # unique ids (spec 021: 6 -> 8, spec 035: -> 11)
    found = {
        task["id"]: [(s["area"], s["x"], s["y"], s["minigame"]) for s in stations_of(task)]
        for task in tasks
    }
    assert found == SPEC_TASKS


def test_no_campus_task_is_a_plain_waiting_task_and_every_station_is_a_floor_tile():
    # Replaces spec 004's test of the same shape, which checked a "seconds" wait on every
    # task; spec 012 requires a mini-game kind instead (the engine still accepts a plain
    # wait, but only test maps use it), checked on every station of every task, including
    # both of "certificate"'s stations (spec 012, part 4).
    campus = load_map()
    game = Game(campus)
    for task in campus["tasks"]:
        assert task["joke"], task["id"]
        for station in stations_of(task):
            assert "seconds" not in station, task["id"]
            assert station["minigame"] in minigames.KINDS, task["id"]
            x, y = (station["x"] + 0.5) * TILE, (station["y"] + 0.5) * TILE
            assert campus["grid"][station["y"]][station["x"]] == ".", task["id"]
            assert not game.blocked(x, y), task["id"]
            # Spec 021: the beach is sand, not an area (spec 015), so the surf station names
            # it by its own label "Beach"; every other station sits inside its area.
            # Spec 035: a named place that is not an area (Hall B, the Little Courtyard)
            # works like the beach: its stations lie outside every area.
            areas = {a["name"] for a in campus["areas"]}
            expected = station["area"] if station["area"] in areas else None
            assert game.area_at(x, y) == expected, task["id"]
            assert station["title"], task["id"]
            assert [station["x"], station["y"]] != campus["meeting_point"], task["id"]


def test_certificates_two_stations_are_at_different_tiles():
    steps = next(t for t in load_map()["tasks"] if t["id"] == "certificate")["steps"]
    assert len(steps) == 2
    assert (steps[0]["x"], steps[0]["y"]) != (steps[1]["x"], steps[1]["y"])


def test_the_task_constants():
    assert rules.TASKS_PER_STUDENT == TASKS_PER_STUDENT
    assert rules.TASK_RANGE == TASK_RANGE == 1.5 * TILE


# --- Accepted: dealing ------------------------------------------------------------


@pytest.mark.parametrize("count", [4, 7, 10])
def test_every_player_gets_different_tasks_from_the_same_pool(count):
    # Replaces spec 004's test of the same shape: examiners now get the same number of
    # fake tasks too, from the same pool as students (spec 012, part 3). Spec 019: the
    # number grows with the player count (tasks_per_player).
    game, examiners, students = new_round(count)
    known = {task["id"] for task in TASK_MAP["tasks"]}
    expected = min(rules.tasks_per_player(count), len(TASK_MAP["tasks"]))
    for player in (*examiners, *students):
        assert len(player.tasks) == len(set(player.tasks)) == expected
        assert set(player.tasks) <= known
        assert player.tasks_done == [] and player.doing is None


def test_the_same_seed_deals_the_same_tasks():
    def dealt(seed):
        game, _, _ = new_round(7, seed)
        return {p.id: p.tasks for p in game.players.values()}

    assert dealt(3) == dealt(3)
    assert len({json.dumps(dealt(seed)) for seed in range(10)}) > 1  # and it is random


def test_on_the_campus_every_student_gets_tasks_per_player_of_the_campus_tasks():
    # Spec 019: with 10 players everyone gets tasks_per_player(10) tasks, not 3.
    game, _, students = new_round(10, campus=load_map())
    for student in students:
        assert len(set(student.tasks)) == min(rules.tasks_per_player(10), len(game.tasks))
        assert set(student.tasks) <= set(SPEC_TASKS)


def test_a_map_with_fewer_tasks_deals_what_there_is():
    two = {**TASK_MAP, "tasks": TASK_MAP["tasks"][:2]}
    game, _, students = new_round(4, campus=two)
    assert all(sorted(student.tasks) == ["t1", "t2"] for student in students)


# --- Accepted: doing a task --------------------------------------------------------


def test_a_student_at_the_task_place_starts_it_and_it_is_done_after_exactly_its_seconds():
    game, (examiner,), students = new_round(4)
    student = students[0]
    task_id = student.tasks[0]
    go_to(game, student, task_id)
    game.task(student.id, task_id)
    assert doing(game, student)["task"] == task_id
    wait(game, ticks_of(game, task_id) - 1)
    assert entry(game, student, task_id)["done"] is False  # one tick earlier: not yet
    assert progress(game, examiner) == {"done": 0, "total": 9}
    game.step()
    assert entry(game, student, task_id)["done"] is True
    assert doing(game, student) is None
    for player in game.players.values():  # the shared bar grows for everyone
        assert progress(game, player) == {"done": 1, "total": 9}


@pytest.mark.parametrize("dx, dy", [(TASK_RANGE, 0), (-TASK_RANGE, 0), (0, TASK_RANGE), (0, -TASK_RANGE)])
def test_a_task_can_be_started_and_finished_from_exactly_the_task_range(dx, dy):
    game, _, students = new_round(4)
    student = students[0]
    task_id = student.tasks[0]
    go_to(game, student, task_id, dx, dy)
    game.task(student.id, task_id)
    wait(game, ticks_of(game, task_id))
    assert entry(game, student, task_id)["done"] is True


def test_seconds_left_counts_down_in_whole_seconds_rounded_up():
    game, _, students = round_with("t1")  # 5 seconds
    student = students[0]
    go_to(game, student, "t1")
    game.task(student.id, "t1")
    assert doing(game, student) == {"task": "t1", "seconds_left": 5}
    game.step()
    assert doing(game, student)["seconds_left"] == 5  # 4.95 s
    wait(game, TICK_RATE - 1)
    assert doing(game, student)["seconds_left"] == 4
    wait(game, 4 * TICK_RATE - 1)
    assert doing(game, student)["seconds_left"] == 1  # one tick before the end


def test_walking_inside_the_range_does_not_cancel():
    game, _, students = new_round(4)
    student = students[0]
    task_id = student.tasks[0]
    go_to(game, student, task_id)
    game.task(student.id, task_id)
    for tick in range(ticks_of(game, task_id)):
        # Three ticks right, three ticks left: at most 24 px from the task place.
        direction = 1 if tick % 6 < 3 else -1
        game.set_input(student.id, {"type": "input", "dx": direction, "dy": 0})
        game.step()
    assert entry(game, student, task_id)["done"] is True


def test_a_ghost_student_can_start_and_finish_their_own_task():
    game, (examiner,), students = new_round(4)
    ghost = students[0]
    ready_examiner(game, examiner)
    expel(game, examiner, ghost)
    do_task(game, ghost, ghost.tasks[0])
    assert entry(game, ghost, ghost.tasks[0])["done"] is True
    assert progress(game, students[1]) == {"done": 1, "total": 9}


def test_two_students_can_do_the_same_task_place_at_the_same_time():
    for seed in range(200):
        game, _, students = new_round(4, seed)
        sharing = [s for s in students if "t1" in s.tasks]
        if len(sharing) >= 2:
            break
    first, second = sharing[:2]
    for student in (first, second):
        go_to(game, student, "t1")
        game.task(student.id, "t1")
    wait(game, ticks_of(game, "t1"))
    assert entry(game, first, "t1")["done"] and entry(game, second, "t1")["done"]
    assert progress(game, first)["done"] == 2  # both count, in the same tick


# --- Fake tasks for examiners (spec 012, part 3) ------------------------------------


def test_an_examiners_fake_task_behaves_exactly_like_a_students_real_one():
    game, (examiner,), students = new_round(4)
    task_id = examiner.tasks[0]
    do_task(game, examiner, task_id)
    assert entry(game, examiner, task_id)["done"] is True
    assert entry(game, examiner, task_id)["joke"]


def test_finishing_an_examiners_fake_task_never_counts_or_ends_the_game():
    game, (examiner,), students = new_round(4)
    do_task(game, examiner, examiner.tasks[0])
    assert examiner.tasks_done == [examiner.tasks[0]]
    assert game.phase == "playing"
    for player in game.players.values():
        assert progress(game, player) == {"done": 0, "total": 9}  # only students count


def test_a_ghost_examiner_cannot_start_a_task_but_a_ghost_student_still_can():
    # R4, unchanged: the ghost-student half is already covered by
    # test_a_ghost_student_can_start_and_finish_their_own_task.
    game, examiners, students = new_round(7)
    target = examiners[0]
    surf(game, target, students)
    go_to(game, target, target.tasks[0])
    assert_rejected(game, lambda: game.task(target.id, target.tasks[0]), "Ghosts cannot do tasks")


# --- Multi-step tasks (spec 012, part 4) --------------------------------------------


def test_the_second_station_cannot_be_started_before_the_first_is_done_and_only_at_its_place():
    game, students = multistep_round()
    student = students[0]
    student.x, student.y = multistep_place(1)  # standing at the second station already
    assert_rejected(game, lambda: game.task(student.id, "cert"), "Too far from the task")


def test_finishing_the_first_station_moves_the_task_to_the_second_stations_place_and_title():
    game, students = multistep_round()
    student = students[0]
    student.x, student.y = multistep_place(0)
    game.task(student.id, "cert")
    solve_paper_jam(game, student, "cert")
    assert student.tasks_step.get("cert") == 1
    assert student.tasks_done == []  # not finished yet
    assert doing(game, student) is None  # a new "task" message is needed for the next step
    moved = entry(game, student, "cert")
    assert moved["done"] is False
    assert (moved["step"], moved["steps"]) == (2, 2)
    assert moved["title"] == "Step B"
    assert (moved["x"], moved["y"]) == multistep_place(1)
    assert progress(game, student) == {"done": 0, "total": 3}  # 3 students, 1 task each


def test_cancelling_the_second_station_leaves_the_first_stations_completion_in_place():
    game, students = multistep_round()
    student = students[0]
    student.x, student.y = multistep_place(0)
    game.task(student.id, "cert")
    solve_paper_jam(game, student, "cert")
    student.x, student.y = multistep_place(1)
    game.task(student.id, "cert")
    game.cancel_task(student.id, "cert")
    assert student.tasks_step.get("cert") == 1  # the first step's completion survives
    assert doing(game, student) is None
    assert game.snapshot_for(student.id)["task_note"] == "Task cancelled."
    game.task(student.id, "cert")  # the second station can be started again
    assert doing(game, student)["task"] == "cert"


def test_finishing_the_second_station_finishes_the_task_once_and_reveals_the_joke():
    game, students = multistep_round()
    student = students[0]
    student.x, student.y = multistep_place(0)
    game.task(student.id, "cert")
    solve_paper_jam(game, student, "cert")
    student.x, student.y = multistep_place(1)
    game.task(student.id, "cert")
    solve_ticket(game, student, "cert")
    assert student.tasks_done == ["cert"]
    assert progress(game, student) == {"done": 1, "total": 3}  # 3 students, 1 task each
    done = entry(game, student, "cert")
    assert done["done"] is True
    assert done["joke"] == "Two stamps later."


# --- What each player receives -----------------------------------------------------


def test_a_students_snapshot_lists_their_own_tasks_with_place_and_state():
    game, _, students = new_round(4)
    student = students[0]
    snapshot = game.snapshot_for(student.id)
    assert [task["id"] for task in snapshot["tasks"]] == student.tasks
    for task in snapshot["tasks"]:
        assert set(task) == TASK_KEYS  # no joke before the task is done
        source = next(t for t in TASK_MAP["tasks"] if t["id"] == task["id"])
        assert (task["title"], task["area"]) == (source["title"], source["area"])
        assert (task["x"], task["y"]) == place_of(game, task["id"])
        assert task["done"] is False
    assert snapshot["doing"] is None


def test_the_joke_is_sent_only_once_the_task_is_done():
    game, _, students = round_with("t1")
    student = students[0]
    assert "Joke" not in json.dumps(game.snapshot_for(student.id))
    do_task(game, student, "t1")
    done = entry(game, student, "t1")
    assert set(done) == TASK_KEYS | {"joke"}
    assert done["joke"] == "Joke one"
    others = [task for task in game.snapshot_for(student.id)["tasks"] if task["id"] != "t1"]
    assert all("joke" not in task for task in others)


def test_task_places_are_not_limited_by_the_vision_radius():
    game, _, students = new_round(4, campus=load_map())
    student = students[0]
    student.x, student.y = 2.5 * TILE, 22.5 * TILE  # a far corner of the campus
    assert len(game.snapshot_for(student.id)["tasks"]) == TASKS_PER_STUDENT


def test_the_lobby_has_no_task_fields_and_every_later_phase_has_the_progress():
    game = Game(TASK_MAP, rng=random.Random(0))
    players = [game.join(f"Player {i}") for i in range(4)]
    for player in players:
        snapshot = game.snapshot_for(player.id)
        assert not {"task_progress", "tasks", "doing"} & set(snapshot)
    game.start(players[0].id)
    for player in players:
        assert progress(game, player) == {"done": 0, "total": 9}  # playing
    student = next(p for p in players if p.role == "student")
    game.call_meeting(student.id)
    for player in players:
        assert progress(game, player) == {"done": 0, "total": 9}  # meeting
    examiner = next(p for p in players if p.role == "examiner")
    game.leave(examiner.id)  # the students win
    assert game.phase == "ended"
    for player in game.players.values():
        assert progress(game, player) == {"done": 0, "total": 9}  # ended


# --- Rejected: each leaves tasks, progress, phase and players unchanged ----------------


def task_in_the_lobby():
    game = Game(TASK_MAP)
    players = [game.join(f"Player {i}") for i in range(4)]
    return game, lambda: game.task(players[0].id, "t1")


def task_in_a_meeting():
    game, _, students = new_round(4)
    game.call_meeting(students[1].id)
    go_to(game, students[0], students[0].tasks[0])
    return game, lambda: game.task(students[0].id, students[0].tasks[0])


def task_after_the_end():
    game, (examiner,), students = new_round(4)
    game.leave(examiner.id)  # the students win
    go_to(game, students[0], students[0].tasks[0])
    return game, lambda: game.task(students[0].id, students[0].tasks[0])


def surf(game, target, voters):
    """Vote `target` off at a meeting called by someone else, running it to the end.

    Every living player must have voted for the voting to close on the next tick
    (otherwise it would only close once MEETING_SECONDS have passed): `voters` vote for
    `target`, everyone else still alive (including `target`) skips.
    """
    caller = next(p for p in voters if p.id != target.id)
    game.call_meeting(caller.id)
    for voter in voters:
        game.vote(voter.id, target.id)
    for player in game.players.values():
        if player.alive and player.id not in game.meeting.votes:
            game.vote(player.id, "skip")
    game.step()  # the voting closes
    wait(game, rules.RESULT_SECONDS * TICK_RATE)


def task_by_a_ghost_examiner():
    # A living examiner now has real fake tasks (spec 012, part 3), so only a ghost
    # examiner is always rejected (R4): one examiner is surfed, the other stays alive
    # so the game keeps playing.
    game, examiners, students = new_round(7)
    target = examiners[0]
    surf(game, target, students)
    go_to(game, target, target.tasks[0])
    return game, lambda: game.task(target.id, target.tasks[0])


def unknown_task_by_an_examiner():
    # The sender is checked before the task: an examiner learns nothing about task ids.
    game, (examiner,), _ = new_round(4)
    return game, lambda: game.task(examiner.id, "no-such-task")


def another_players_task_by_an_examiner():
    for seed in range(200):
        game, examiners, students = new_round(4, seed)
        examiner = examiners[0]
        others_tasks = [t for s in students for t in s.tasks if t not in examiner.tasks]
        if others_tasks:
            break
    task_id = others_tasks[0]
    go_to(game, examiner, task_id)
    return game, lambda: game.task(examiner.id, task_id)


def another_students_task():
    for seed in range(200):
        game, _, students = new_round(4, seed)
        pairs = [(a, b, t) for a in students for b in students for t in a.tasks if t not in b.tasks]
        if pairs:
            break
    _, other, task_id = pairs[0]
    go_to(game, other, task_id)
    return game, lambda: game.task(other.id, task_id)


def unknown_task_id():
    game, _, students = new_round(4)
    return game, lambda: game.task(students[0].id, "no-such-task")


def task_already_done():
    game, _, students = new_round(4)
    do_task(game, students[0], students[0].tasks[0])
    return game, lambda: game.task(students[0].id, students[0].tasks[0])


def one_pixel_out_of_range():
    game, _, students = new_round(4)
    go_to(game, students[0], students[0].tasks[0], dx=TASK_RANGE + 1)
    return game, lambda: game.task(students[0].id, students[0].tasks[0])


def from_the_spawn():
    game, _, students = new_round(4)
    return game, lambda: game.task(students[0].id, students[0].tasks[0])


def already_doing_the_same_task():
    game, _, students = new_round(4)
    go_to(game, students[0], students[0].tasks[0])
    game.task(students[0].id, students[0].tasks[0])
    wait(game, 10)
    return game, lambda: game.task(students[0].id, students[0].tasks[0])


def already_doing_another_task():
    game, _, students = round_with("t1", "t2")  # neighbours: both within reach
    go_to(game, students[0], "t1")
    game.task(students[0].id, "t1")
    wait(game, 10)
    return game, lambda: game.task(students[0].id, "t2")


def task_by_an_unknown_player():
    game, _, _ = new_round(4)
    return game, lambda: game.task("nobody", "t1")


@pytest.mark.parametrize(
    "case, reason",
    [
        (task_in_the_lobby, "The game has not started yet"),
        (task_in_a_meeting, "Meeting in progress"),
        (task_after_the_end, "Game is over"),
        (task_by_a_ghost_examiner, "Ghosts cannot do tasks"),
        (unknown_task_by_an_examiner, "Not one of your tasks"),
        (another_players_task_by_an_examiner, "Not one of your tasks"),
        (another_students_task, "Not one of your tasks"),
        (unknown_task_id, "Not one of your tasks"),
        (task_already_done, "Task already done"),
        (one_pixel_out_of_range, "Too far from the task"),
        (from_the_spawn, "Too far from the task"),
        (already_doing_the_same_task, "You are already doing a task"),
        (already_doing_another_task, "You are already doing a task"),
        (task_by_an_unknown_player, "Unknown player"),
    ],
    ids=lambda value: value.__name__ if callable(value) else None,
)
def test_rejected_task_changes_nothing(case, reason):
    game, action = case()
    assert_rejected(game, action, reason)


# None stands for a missing field: server/main.py passes message.get("task").
@pytest.mark.parametrize("task_id", [2, None, True, ["t1"], {"id": "t1"}])
def test_a_task_id_that_is_not_a_string_is_rejected(task_id):
    game, _, students = new_round(4)
    go_to(game, students[0], students[0].tasks[0])
    assert_rejected(game, lambda: game.task(students[0].id, task_id), "Task must be a task id")


def test_task_messages_are_parsed_after_joining_and_rejected_before():
    raw = '{"type": "task", "task": "print"}'
    assert parse_message(raw, joined=True) == {"type": "task", "task": "print"}
    with pytest.raises(GameError, match="Join the game first"):
        parse_message(raw, joined=False)


# --- Cancelling ---------------------------------------------------------------------


def test_reliability_walking_out_of_the_range_cancels_and_nothing_stays_stuck():
    game, _, students = new_round(4)
    student = students[0]
    task_id = student.tasks[0]
    go_to(game, student, task_id)
    game.task(student.id, task_id)
    wait(game, 20)
    game.set_input(student.id, {"type": "input", "dx": 0, "dy": 1})
    wait(game, 6)  # 48 px: still exactly within reach
    assert doing(game, student) is not None
    game.step()  # 56 px away
    assert doing(game, student) is None
    assert student.doing is None
    wait(game, ticks_of(game, task_id))  # walking on never finishes it
    assert entry(game, student, task_id)["done"] is False
    assert progress(game, student)["done"] == 0


def test_reliability_after_cancelling_the_task_starts_again_from_zero():
    game, _, students = new_round(4)
    student = students[0]
    task_id = student.tasks[0]
    full = ticks_of(game, task_id)
    go_to(game, student, task_id)
    game.task(student.id, task_id)
    wait(game, full - 1)  # almost done
    go_to(game, student, task_id, dx=TASK_RANGE + 1)
    game.step()  # out of reach: cancelled
    assert doing(game, student) is None
    go_to(game, student, task_id)
    game.task(student.id, task_id)
    wait(game, full - 1)
    assert entry(game, student, task_id)["done"] is False  # the first attempt does not count
    game.step()
    assert entry(game, student, task_id)["done"] is True


def test_reliability_being_expelled_cancels_and_the_ghost_can_start_again():
    game, (examiner,), students = new_round(4)
    student = students[0]
    task_id = student.tasks[0]
    ready_examiner(game, examiner)
    go_to(game, student, task_id)
    game.task(student.id, task_id)
    wait(game, 30)
    expel(game, examiner, student)
    assert doing(game, student) is None
    wait(game, ticks_of(game, task_id))
    assert entry(game, student, task_id)["done"] is False
    game.task(student.id, task_id)  # as a ghost, from zero
    wait(game, ticks_of(game, task_id))
    assert entry(game, student, task_id)["done"] is True


def test_reliability_a_meeting_cancels_every_running_task_and_none_finishes_in_it():
    game, _, students = new_round(4)
    for student in students:
        go_to(game, student, student.tasks[0])
        game.task(student.id, student.tasks[0])
    wait(game, 40)
    game.call_meeting(students[0].id)
    assert all(doing(game, student) is None for student in students)
    for student in students:
        go_to(game, student, student.tasks[0])  # even standing on the task place
    wait(game, rules.MEETING_SECONDS * TICK_RATE + rules.RESULT_SECONDS * TICK_RATE)
    assert game.phase == "playing"
    wait(game, 5)
    assert progress(game, students[0]) == {"done": 0, "total": 9}  # nothing counted late
    assert all(doing(game, student) is None for student in students)
    do_task(game, students[0], students[0].tasks[0])  # and it can be started again
    assert progress(game, students[0])["done"] == 1


def test_reliability_the_end_of_the_game_clears_running_tasks():
    game, (examiner,), students = new_round(4)
    ready_examiner(game, examiner)
    expel(game, examiner, students[0])
    go_to(game, students[1], students[1].tasks[0])
    game.task(students[1].id, students[1].tasks[0])
    examiner.next_expel_tick = game.tick  # skip the second cooldown
    expel(game, examiner, students[2])  # 1 examiner, 1 living student: the examiners win
    assert game.phase == "ended"
    assert doing(game, students[1]) is None
    assert students[1].doing is None


# --- Edge cases ---------------------------------------------------------------------


def test_reliability_a_bell_in_the_tick_before_a_task_would_finish_wins():
    game, _, students = new_round(4)
    student = students[0]
    task_id = student.tasks[0]
    go_to(game, student, task_id)
    game.task(student.id, task_id)
    wait(game, ticks_of(game, task_id) - 1)
    game.call_meeting(students[1].id)  # processed before the tick that would finish the task
    game.step()
    assert game.phase == "meeting"
    assert entry(game, student, task_id)["done"] is False
    assert progress(game, student)["done"] == 0


def test_reliability_a_report_in_the_tick_before_a_task_would_finish_wins():
    game, (examiner,), students = new_round(5)
    ready_examiner(game, examiner)
    expel(game, examiner, students[3])
    exam = game.failed_exams[-1]
    student = students[0]
    task_id = student.tasks[0]
    go_to(game, student, task_id)
    game.task(student.id, task_id)
    wait(game, ticks_of(game, task_id) - 1)
    students[1].x, students[1].y = exam.x, exam.y
    game.report(students[1].id, exam.id)
    game.step()
    assert game.phase == "meeting"
    assert entry(game, student, task_id)["done"] is False


def test_reliability_a_finished_task_counts_once():
    game, _, students = new_round(4)
    student = students[0]
    do_task(game, student, student.tasks[0])
    assert progress(game, student)["done"] == 1
    wait(game, 400)  # standing on the task place for another 20 seconds
    assert progress(game, student)["done"] == 1
    assert student.tasks_done == [student.tasks[0]]


def test_the_last_open_task_ends_the_game_with_a_student_win():
    game, (examiner,), students = new_round(4)
    jobs = [(student, task_id) for student in students for task_id in student.tasks]
    for index, (student, task_id) in enumerate(jobs):
        assert game.phase == "playing"
        assert progress(game, examiner)["done"] == index
        do_task(game, student, task_id)
    assert game.phase == "ended"
    for player in game.players.values():
        snapshot = game.snapshot_for(player.id)
        assert snapshot["winner"] == "students"
        assert snapshot["task_progress"] == {"done": 9, "total": 9}


def test_reliability_a_student_leaving_takes_their_tasks_out_of_both_numbers():
    game, (examiner,), students = new_round(4)
    do_task(game, students[0], students[0].tasks[0])
    do_task(game, students[2], students[2].tasks[0])
    assert progress(game, examiner) == {"done": 2, "total": 9}
    game.leave(students[2].id)  # one done and two open tasks go
    assert game.phase == "playing"
    assert progress(game, examiner) == {"done": 1, "total": 6}


def test_reliability_students_win_when_the_last_student_with_open_tasks_leaves():
    game, (examiner,), students = new_round(4)
    for student in students[:2]:
        for task_id in student.tasks:
            do_task(game, student, task_id)
    do_task(game, students[2], students[2].tasks[0])
    assert (game.phase, progress(game, examiner)) == ("playing", {"done": 7, "total": 9})
    game.leave(students[2].id)
    assert game.phase == "ended"
    assert game.snapshot_for(examiner.id)["winner"] == "students"
    assert progress(game, examiner) == {"done": 6, "total": 6}


def test_when_a_leave_gives_both_sides_their_win_the_examiners_count_is_checked_first():
    # The win checks of specs 003 and 006 stay as they are and run before the task win.
    game, (examiner,), students = new_round(4)
    for student in students[:2]:
        for task_id in student.tasks:
            do_task(game, student, task_id)
    ready_examiner(game, examiner)
    expel(game, examiner, students[1])  # a ghost whose tasks are all done
    game.leave(students[2].id)  # 1 examiner, 1 living student, and every task left is done
    assert game.phase == "ended"
    assert game.winner == "examiners"


def test_reliability_a_new_round_has_no_tasks_and_the_next_start_deals_new_ones():
    game, (examiner,), students = new_round(4)
    do_task(game, students[0], students[0].tasks[0])
    go_to(game, students[1], students[1].tasks[0])
    game.task(students[1].id, students[1].tasks[0])
    game.leave(examiner.id)  # the students win
    assert game.phase == "ended"
    game.restart(game.host_id)
    for player in game.players.values():
        assert (player.tasks, player.tasks_done, player.doing) == ([], [], None)
        assert not {"task_progress", "tasks", "doing"} & set(game.snapshot_for(player.id))
    game.join("Player 9")  # four players again
    game.start(game.host_id)
    new_students = [p for p in game.players.values() if p.role == "student"]
    for student in new_students:
        assert len(set(student.tasks)) == TASKS_PER_STUDENT
        assert student.tasks_done == []
    assert progress(game, new_students[0]) == {"done": 0, "total": 9}


def test_reliability_everyone_leaving_clears_tasks_and_progress():
    game, _, students = new_round(4)
    do_task(game, students[0], students[0].tasks[0])
    for player_id in list(game.players):
        game.leave(player_id)
    assert game.phase == "lobby"
    players = [game.join(f"New {i}") for i in range(4)]
    assert all((p.tasks, p.tasks_done, p.doing) == ([], [], None) for p in players)
    game.start(players[0].id)
    assert progress(game, players[0])["done"] == 0


def test_reliability_a_map_without_tasks_never_gives_a_task_win():
    game, (examiner,), students = new_round(4, campus=PLAIN_MAP)
    assert all(student.tasks == [] for student in students)
    wait(game, 100)
    assert game.phase == "playing"
    assert progress(game, examiner) == {"done": 0, "total": 0}
    game.leave(students[0].id)  # the win check runs: still no task win
    assert game.phase == "playing"


# --- Secrecy ------------------------------------------------------------------------


def other_views(game, player):
    """What everyone else receives, without the fields that change with every tick."""
    views = {}
    for other in game.players.values():
        if other is not player:
            view = game.snapshot_for(other.id)
            view.pop("tick")
            view.pop("expel_cooldown", None)
            view.pop("sabotage_cooldown", None)  # counts down too (spec 008, part 8)
            views[other.id] = view
    return views


def test_no_snapshot_contains_another_players_tasks_in_any_phase():
    game, examiners, students = new_round(7)

    def check():
        for player in game.players.values():
            snapshot = game.snapshot_for(player.id)
            assert all(set(p) == PLAYER_KEYS for p in snapshot["players"])
            # Both roles have real tasks now (spec 012, part 3): each player's own
            # snapshot shows exactly their own, never another player's, real or fake.
            assert [task["id"] for task in snapshot["tasks"]] == player.tasks
            assert "task_progress" in snapshot

    check()  # playing
    do_task(game, students[0], students[0].tasks[0])
    go_to(game, students[1], students[1].tasks[0])
    game.task(students[1].id, students[1].tasks[0])
    check()  # one task done, one running
    game.call_meeting(students[2].id)
    check()  # meeting
    for examiner in examiners:
        game.leave(examiner.id)
    assert game.phase == "ended"
    check()  # ended


def test_starting_a_task_changes_nothing_in_what_the_others_receive():
    game, _, students = new_round(7)
    student = students[0]
    go_to(game, student, student.tasks[0])
    before = other_views(game, student)
    game.task(student.id, student.tasks[0])
    assert other_views(game, student) == before


def test_finishing_a_task_shows_the_others_only_the_shared_progress():
    game, _, students = new_round(7)
    student = students[0]
    go_to(game, student, student.tasks[0])
    game.task(student.id, student.tasks[0])
    wait(game, ticks_of(game, student.tasks[0]) - 1)
    before = other_views(game, student)
    game.step()
    after = other_views(game, student)
    total = len(students) * rules.tasks_per_player(7)  # spec 019: 4 tasks each with 7 players
    for player_id, view in after.items():
        assert view.pop("task_progress") == {"done": 1, "total": total}
        assert before[player_id].pop("task_progress") == {"done": 0, "total": total}
        assert view == before[player_id]


def test_an_examiner_cannot_tell_another_players_task_from_an_unknown_id():
    # Replaces spec 004's test of the same shape: a living examiner now has real tasks
    # of their own (spec 012, part 3), so the stronger guarantee is the student one
    # (test_a_student_cannot_tell_another_students_task_from_an_unknown_id), applied here.
    game, action = another_players_task_by_an_examiner()
    with pytest.raises(GameError) as other:
        action()
    game, action = unknown_task_by_an_examiner()
    with pytest.raises(GameError) as unknown:
        action()
    assert str(other.value) == str(unknown.value) == "Not one of your tasks"


def test_a_student_cannot_tell_another_students_task_from_an_unknown_id():
    game, action = another_students_task()
    with pytest.raises(GameError) as other:
        action()
    game, action = unknown_task_id()
    with pytest.raises(GameError) as unknown:
        action()
    assert str(other.value) == str(unknown.value) == "Not one of your tasks"


# --- WebSocket ----------------------------------------------------------------------


def receive_until(ws, predicate, limit=5 * TICK_RATE):
    """Read messages until one matches, or fail after `limit` messages."""
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def test_a_student_does_a_task_over_the_websocket_and_everyone_sees_the_progress(fresh_game):
    # Seed 1 deals the real campus: Ada (joins first) is a student with "gate" (the
    # "card" mini-game) as her first task, Bo is the examiner (same seed as the
    # equivalent test in test_minigames.py).
    fresh_game.rng = random.Random(4)  # spec 021: 8 tasks deal differently; seed 4 = old seed 1
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
                assert welcome["task_range"] == TASK_RANGE
                ids.append(welcome["id"])
            a.send_json({"type": "start"})
            states = [
                receive_until(ws, lambda m: m["type"] == "state" and m["phase"] == "playing")
                for ws in clients
            ]
            roles = [state["role"] for state in states]
            # Every player has real tasks now, student or examiner (spec 012, part 3).
            assert all("tasks" in state for state in states)
            assert all(state["task_progress"] == {"done": 0, "total": 9} for state in states)

            me = roles.index("student")
            ws, player = clients[me], fresh_game.players[ids[me]]
            task = states[me]["tasks"][0]
            other_index = roles.index("examiner")
            other, other_player = clients[other_index], fresh_game.players[ids[other_index]]

            not_the_examiners_task = next(t for t in SPEC_TASKS if t not in other_player.tasks)
            other.send_json({"type": "task", "task": not_the_examiners_task})
            error = receive_until(other, lambda m: m["type"] == "error")
            assert error["reason"] == "Not one of your tasks"
            ws.send_json({"type": "task", "task": "no-such-task"})
            error = receive_until(ws, lambda m: m["type"] == "error")
            assert error["reason"] == "Not one of your tasks"

            player.x, player.y = task["x"], task["y"]  # skip the walk to the task place
            ws.send_json({"type": "task", "task": task["id"]})
            running = receive_until(ws, lambda m: m["type"] == "state" and m["doing"])
            assert running["doing"]["task"] == task["id"]
            assert running["doing"]["challenge"]["kind"] == "card"

            wrong_number = "00000" if player.challenge["number"] != "00000" else "11111"
            ws.send_json({"type": "task_input", "task": task["id"], "value": wrong_number})
            after_wrong = receive_until(ws, lambda m: m["type"] == "state" and m.get("task_note"))
            assert after_wrong["task_note"] == "Beep. Red."

            ws.send_json({"type": "task_input", "task": task["id"], "value": player.challenge["number"]})
            done = receive_until(
                ws, lambda m: m["type"] == "state" and any(t["done"] for t in m["tasks"])
            )
            finished = next(t for t in done["tasks"] if t["id"] == task["id"])
            assert finished["done"] is True and finished["joke"]
            assert done["doing"] is None
            seen = receive_until(
                other, lambda m: m["type"] == "state" and m["task_progress"]["done"] == 1
            )
            assert seen["task_progress"] == {"done": 1, "total": 9}
            # The examiner's own (fake) tasks, never the student's.
            assert [t["id"] for t in seen["tasks"]] == other_player.tasks
