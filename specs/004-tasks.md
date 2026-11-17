# Spec 004 — Nova tasks and the students' task win

## Why
Students need something to do besides walking around, and examiners need a reason to roam the campus. Tasks give students a goal, create spots where examiners can strike, and give students their third way to win. The task texts carry the game's Nova humour. Covers BRD EX04, R4, the task win in R6, R7 (a task finishing while a meeting starts) and acceptance A5 (student win). Builds on spec 002 (phases, roles, `snapshot_for`), spec 003 (expel, ghosts, win check, restart), spec 005 (vision radius, `render.js`, current area) and spec 006 (meetings).

## What
- **Task places:** a new list `tasks` in `server/campus.json`. The existing entries (`grid`, `areas`, `spawns`, `tile_size`) stay unchanged. Each task has an `id`, a `title`, an `area`, a floor tile (`x`, `y`), a duration in `seconds` and a `joke` that is shown when the task is done:

  | id | Area | Tile | Title | Seconds | Joke |
  |---|---|---|---|---|---|
  | `certificate` | Student Services | 3, 14 | Submit your Bachelor certificate | 8 | Ticket A-347. Now serving: A-012. |
  | `helpdesk` | Main Entrance | 36, 17 | Ask the Helpdesk for help | 6 | Olá! Só em português, por favor. |
  | `print` | Library | 2, 2 | Print your assignment | 7 | PAPER JAM in tray 2. Printed anyway, 1 of 12 pages. |
  | `coffee` | Food Court | 36, 3 | Grab a coffee before class | 5 | Coffee: 0.80 €. Queue: 40 minutes. |
  | `eduroam` | Courtyard | 15, 12 | Reconnect to eduroam | 6 | Connected. Disconnected. Connected. |
  | `socket` | Auditorium | 24, 2 | Find a free socket for your laptop | 5 | All sockets taken. 3 % battery it is. |
  | `gate` | Main Entrance | 31, 24 | Tap your student card at the gate | 5 | Beep. Red. Beep. Red. Beep. Green. |
  | `nata` | Courtyard | 25, 16 | Eat your pastel de nata in the sun | 5 | A seagull took it. Task counts anyway. |

- **Dealing tasks:** when the game starts, the server gives every student `TASKS_PER_STUDENT = 3` different tasks, chosen with the game's `rng` (tests pass a seeded `random.Random`). Examiners get no tasks. Nothing another player receives shows who has tasks, so examiners can stand at task places and pretend.
- **Doing a task:** a student sends `{"type": "task", "task": "<task id>"}`. Accepted only if:
  - the phase is `playing`;
  - the sender is a student (alive or ghost, R4);
  - the task is one of the sender's own tasks and not done yet;
  - the sender's centre is at most `TASK_RANGE` (48 px, about 1.5 tiles, like the expel and report ranges) from the centre of the task's tile;
  - the sender is not already doing a task.

  The sender is checked before the task. An unknown task id and another player's task get the same reason ("Not one of your tasks"), so a browser cannot find out other players' tasks by trying ids. A rejected action changes nothing and returns a short reason, as before.
- **Progress:** an accepted task starts a timer counted in ticks (`seconds × TICK_RATE`). At every tick of `step()` while `playing`, the server checks that the player is still within `TASK_RANGE`. Walking around inside the range is fine. The task is done at the first tick at which the full duration has passed. The progress is cancelled (back to zero, the task stays open, it can be started again) when:
  - the player leaves the range;
  - the player is expelled (as a ghost they can start it again);
  - a meeting starts (all running tasks are cancelled).
- **Simultaneous actions (R7):** no task can finish during a meeting. If a report or bell is processed before the tick at which a task would finish, the meeting wins and the task is cancelled.
- **Shared progress:** finished tasks / total tasks of all students still in the game, ghosts included. A student leaving takes their tasks (done and open) out of both numbers.
- **Task win (R6):** when the shared progress reaches the total, the game ends with phase `ended` and winner `students`. The check runs after every finished task and after every player leaving while `playing` (the leaver may have been the last one with open tasks). The existing win checks from specs 003 and 006 stay as they are.
- **New round and empty game:** restart and the last player leaving clear all tasks and running progress. New tasks are dealt at the next start.
- **What each player receives (`snapshot_for`):**
  - from `playing` on, every snapshot has `task_progress`: `{"done": n, "total": m}` (examiners and ghosts too);
  - a student additionally gets `tasks`: their own tasks as `[{"id", "title", "area", "x", "y", "done"}]` (`x`, `y` in pixels, the tile centre) and `doing`: `null` or `{"task": id, "seconds_left": s}` (whole seconds, rounded up). The joke of a finished task is sent with that task's entry once it is done;
  - never another player's tasks. Player entries stay exactly `{id, name, x, y}`.
  - Task places are not limited by the vision radius: a player's own task places are no secret.
- **`server/main.py` / `parse_message`:** `task` becomes an allowed message type (rejected before joining) and is passed to the game like `report`. `welcome` also carries `task_range`.
- **Browser** (new drawing code in `web/render.js`, panels as before in `index.html`, `style.css`, `main.js`; texts always added as text, never as HTML):
  - a task list in a corner for students: title and area, finished tasks crossed out;
  - the player's own open task places are marked on the map, also outside the vision radius;
  - a **"Do task" button** (and key **F**): shown to a student (alive or ghost) while `playing`, only when one of their own open tasks is within `task_range` of the latest server position. It starts the nearest one. The button must also work by tap, so spec 007 can use it on phones;
  - while a task runs: a progress ring at the player with the seconds left. If it is cancelled, a toast says why ("Task cancelled: you walked away");
  - when a task is done: a short popup with its joke;
  - a shared progress bar at the top for everyone while playing and in meetings;
  - the end screen says "All tasks done: students win" when the task win ended the game.

## Out of scope
- Tasks as mini-games (roadmap F3): a task is "stand there for N seconds".
- Fake tasks for examiners.
- Sabotage (F4), staff doors, phone controls (spec 007).
- The real campus map: if it moves the areas later, the task tiles move with it in that spec.
- Existing rules (movement, roles, expel, meetings, votes, vision, colours, restart) change only where stated above.

## Done when
- Tests in a new file `tests/test_tasks.py`, written first and red before the implementation.
  - Map data:
    - every task in `campus.json` has a unique id, its tile is a floor tile (not `blocked()`) and lies in its named area (`area_at`), its duration is between 5 and 10 seconds.
  - Accepted:
    - at the start every student has 3 different tasks, examiners none; with the same seed the same tasks are dealt;
    - a student at their task place starts it; after exactly `seconds × TICK_RATE` ticks it is done (one tick earlier it is not); `task_progress.done` grows by 1;
    - walking inside the range does not cancel it;
    - a ghost student can start and finish their own task;
    - after cancelling, the same task can be started again from zero and finished.
  - Rejected (each leaves tasks, progress, phase and players unchanged, with a reason):
    - in `lobby`, in `meeting`, in `ended`;
    - sender is an examiner;
    - another student's task and an unknown task id, both with "Not one of your tasks";
    - task already done;
    - out of range;
    - already doing a task;
    - task id that is not a string, and a missing task id;
    - a `task` message before joining (`parse_message`).
  - Cancelling:
    - leaving the range cancels the progress;
    - being expelled cancels it;
    - a meeting starting cancels every running task; during the meeting no task finishes.
  - Edge cases:
    - a report processed in the tick before a task would finish: meeting, task not done;
    - a student leaves: their tasks leave the total; if the remaining students have finished all theirs, students win;
    - the last open task finished → `ended`, winner students (A5);
    - restart: no tasks, no progress; a new start deals new tasks.
  - Secrecy:
    - no snapshot contains another player's tasks or progress, in any phase;
    - an examiner's snapshot contains `task_progress` but no `tasks`.
- One WebSocket test: a student sends `task` at their task place, the server ticks, the student's snapshot shows the task done and another player sees `task_progress` grow.
- `uv run pytest` passes; the output is pasted. Existing tests still pass unchanged.
- Manual check with 4 browser windows locally:
  - a student sees 3 tasks in the list and their places on the map; the examiner sees none;
  - "Do task" appears only at the student's own place; the ring counts down; the joke pops up;
  - walking away mid-task cancels it with a toast;
  - ringing the bell mid-task cancels it;
  - all students finishing their tasks ends the game with "All tasks done: students win".
