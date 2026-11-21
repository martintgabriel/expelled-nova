# Spec 012 — Task mini-games, fake tasks for examiners and multi-step tasks

## Why
Every task today is "stand next to it for 5 to 8 seconds": no input, no skill, no fun. This is
roadmap item F3 ("More Nova tasks as mini-games"). A real mini-game per task gives students
something to actually do, keeps examiners honestly guessing who is doing a task versus
standing still to seem busy, and gives examiners something to pretend to do themselves
(fake tasks), which is funnier and harder to read than an idle examiner. A certificate that
needs two stops (Library then Student Services) also makes the campus feel bigger. Builds on
spec 004 (tasks, dealing, the task win, `snapshot_for`), spec 007 (touch input, so every
mini-game must work by tap) and spec 008 part 5 (task reliability: cancelling never leaves a
task stuck).

This spec **replaces** two rules from spec 004:
- "Examiners get no tasks" → examiners now get `TASKS_PER_STUDENT` fake tasks from the same
  pool, which never count (see part 3).
- The task texts and durations in the spec 004 table (`coffee`, `eduroam`, plain `seconds`
  waits) → replaced by the six mini-game tasks below; `coffee` and `eduroam` are deleted.

## What

### Part 1 — Delete the boring tasks, keep the engine's plain-wait fallback
- `coffee` (Food Court) and `eduroam` (Courtyard) are removed from `server/campus.json`.
  They get no mini-game and no replacement; the campus has six tasks from here on:
  `certificate`, `helpdesk`, `gate`, `print`, `socket`, `nata`.
- `Game` still accepts a **station** without a mini-game (hold still for its `seconds`,
  exactly as spec 004 built it), because `tests/test_tasks.py`'s `TASK_MAP` and `PLAIN_MAP`
  use that format and must keep working unchanged. But no task in `server/campus.json` may
  be a plain waiting task any more.
- New test: every station of every campus task (see Part 4 for what "station" means) has a
  `minigame` key and no `seconds` key.

### Part 2 — The mini-game framework (server stays the authority)
- **Starting a task** (`{"type": "task", "task": "<id>"}`, same checks as spec 004, plus the
  two new checks in parts 3/4 below): if the task's current station has a `minigame`, the
  server builds a **challenge** with `self.rng` and stores it on the player
  (`Player.challenge`); `Player.doing` is set to the task id as before. If the station has no
  `minigame` (only possible on a test map), behaviour is unchanged from spec 004
  (`doing_done_tick`, no challenge).
- **Only that player** ever receives their challenge, inside their own `doing` (see "What
  each player receives" below). Nothing about it reaches any other snapshot.
- **New message `task_input`:** `{"type": "task_input", "task": "<id>", "value": <value>}`.
  New `Game.task_input(player_id, task_id, value)`, checked in this order, each a rejection
  that changes nothing:
  1. unknown player; game not `playing` (`"Game is over"`, `"Meeting in progress"`,
     `"The game has not started yet"`, same wording as `task()`);
  2. `task_id` must be a string (`"Task must be a task id"`);
  3. `task_id != player.doing` (`"You are not doing this task"`);
  4. the station has no mini-game, i.e. `player.challenge is None`
     (`"This task has no mini-game"`) — only reachable on a test map;
  5. still within `TASK_RANGE` of the current station (`"Too far from the task"`);
  6. `value`'s type/shape does not match the challenge's kind (type, range, length — see
     each mini-game below) → `"Invalid value for this task"`.
  A `value` that passes all checks but is **the wrong answer** is not a rejection: the call
  returns normally, the state changes the way that mini-game's rule says (usually a new
  challenge of the same kind), and a short message is attached for the player (see
  "`task_note`" below). A **correct** value finishes the current station: see Part 4 for a
  multi-step task, or immediately marks the task done for a single-station task, exactly
  like spec 004's task completion (added to `tasks_done`, `joke` becomes visible, the shared
  task win check runs).
- **New message `task_cancel`:** `{"type": "task_cancel", "task": "<id>"}`. A player can
  close the mini-game panel without walking away. New `Game.cancel_task(player_id, task_id)`:
  rejects exactly like steps 1–3 of `task_input` above; otherwise clears `doing` and
  `challenge` (the current station only — a finished earlier step of a multi-step task is
  unaffected) and sets the `task_note` `"Task cancelled."`.
- **Cancel rules stay** (spec 004/008): leaving `TASK_RANGE`, being expelled (students) or
  surfed (either role) in a meeting result, or a meeting starting, cancel the running
  challenge the same way `task_cancel` does, minus the note (unchanged from today: the
  browser infers the reason from phase/alive, as it already does). A new `task` message
  starts a fresh challenge.
- **Time limit:** every mini-game has a fixed overall time limit from the moment its
  challenge is created (not reset by a wrong answer, so repeated wrong answers still run
  out). Checked every tick in `_step_tasks`, like the range check. When it runs out: the
  challenge is cancelled exactly like `cancel_task` (same step, reopened), with a mini-game
  specific `task_note` (see each mini-game). The limits (chosen so a reasonably attentive
  player always has time to finish, with room for a few wrong tries):

  | kind | time limit |
  |---|---|
  | `ticket` | 45 s |
  | `translate` | 30 s |
  | `card` | 30 s |
  | `paper_jam` | 30 s |
  | `socket` | 30 s |
  | `seagull` | 8 s (given by the mini-game's own rule) |

- **Validation stays strict** (type, range, length of `value`; existing `MAX_MESSAGE_BYTES`
  and `RATE_LIMIT` already cover message size and frequency; no change there).
- **Code location:** the challenge data, creation and checking move into a new plain-Python
  module `server/minigames.py` (no network code, importable and testable on its own), with
  one function to build a challenge for a kind, one to validate and apply an answer, one to
  build the player-visible view, and the time-limit table above. `server/game.py` calls into
  it; `Game` keeps owning `self.rng`, the player's state, cancelling and the task win.

### Part 3 — Fake tasks for examiners
- In `Game.start()`, every player — student **and** examiner — is dealt
  `min(TASKS_PER_STUDENT, len(self.tasks))` different tasks with `self.rng.sample`, from the
  same six-task pool. (Today only students are dealt tasks; this spec removes that
  restriction, since `self.rng.sample` is called once per player either way, the order of
  calls per player stays the same — only the examiner branch stops being skipped.)
- `Game.task`, `Game.task_input` and `Game.cancel_task` work the same for both roles, with one
  extra check in `task()`: a player who is an examiner and a ghost (surfed in a meeting)
  cannot start a task (`"Ghosts cannot do tasks"`); a ghost **student** still can, unchanged
  (R4). A living examiner can do fake tasks exactly like a student does real ones: dealt at
  the start, started with `task`, answered with `task_input`, cancelled the same ways, shown
  the same joke on completion.
- **Nothing an examiner does counts:** `_task_progress()` already sums only `role == STUDENT`
  players' `tasks`/`tasks_done`, so an examiner's fake tasks were never part of `done` or
  `total` and stay that way; finishing one never triggers the task win.
- **Secrecy is unchanged in shape:** `snapshot_for` already only ever returns the viewer's
  own `tasks`/`doing`/`challenge`; a student's snapshot shows nothing about any examiner's
  tasks (fake or otherwise), and vice versa. What changes is that the fields that used to
  exist for students only now exist for every player once `phase != LOBBY`.

### Part 4 — Multi-step tasks
- A task in `campus.json` may have `"steps"`: an ordered list of **stations**, each with its
  own `title`, `area`, tile (`x`, `y`) and `minigame` (or `seconds`, on a test map). A task
  without `"steps"` is one station, exactly as before (internally normalised to a list of one
  station, so the rest of the engine only ever deals with "the current station of a task").
- `certificate` becomes a 2-step task:
  1. **Library**, tile (33, 22) — a different tile from `print`'s (37, 20), same area —
     "Print a copy of your certificate", mini-game `paper_jam`.
  2. **Student Services**, tile (35, 3) — the existing tile — "Submit your Bachelor
     certificate", mini-game `ticket`.
- New `Player.tasks_step: dict[str, int]`, defaulting to 0 (no entry needed for a task not
  yet started): how many of a task's steps this player has finished. `task()` starts the
  station at `tasks_step.get(task_id, 0)`; `task_input`'s correct answer increments it. When
  it reaches `len(steps)`, the task moves to `tasks_done` (counts once in `task_progress`) and
  its `joke` becomes visible. A step short of that just clears `doing`/`challenge`: the player
  must send a new `task` message to start the next station (matches the existing pattern —
  and usually means walking somewhere else first).
- **Only the current step can be started, and only at its place:** `task()`'s range check and
  `_step_tasks`' cancellation both read the *current* station's tile (via
  `tasks_step.get(task_id, 0)`), so standing at the Student Services tile does nothing for
  `certificate` until the Library step is done.
- **Cancelling only resets the running step:** cancelling (any of the ways in Part 2) never
  touches `tasks_step`, so a finished step survives it.
- `Player.tasks_step` is cleared on restart and on everyone leaving, like `tasks`/`tasks_done`.

### What each player receives (`snapshot_for`)
- From `playing` on, **every player** (student or examiner, living or ghost) gets:
  - `task_progress`: unchanged shape, `{"done": n, "total": m}`, students only (Part 3);
  - `tasks`: `[{"id", "title", "area", "x", "y", "done"}]`, one entry per task dealt to this
    player — their own, whether real (student) or fake (examiner); never another player's.
    `title`/`area`/`x`/`y` are the *current* station's (Part 4): once a step is done, the next
    step's place and title show instead. A multi-step entry additionally carries `"step"`
    (1-based index of the current/last station) and `"steps"` (total stations); a one-station
    task has neither key (same `TASK_KEYS` as spec 004). `joke` appears once `done` is `true`,
    as before.
  - `doing`: `null`, or `{"task": id, "seconds_left": s}` for a plain-wait station (unchanged
    from spec 004), or `{"task": id, "seconds_left": s, "challenge": {...}}` once a mini-game
    is running. `seconds_left` is the whole seconds (rounded up) left on the time-limit clock.
    `challenge` always has `"kind"` plus the fields below, and never the hidden parts of that
    mini-game.
  - `task_note`: `null`, or a short string, set by a wrong answer, a time-out or a
    `task_cancel`, and explicitly cleared (back to `null`) by starting a task and by every
    other way of cancelling one (walking away, being expelled, a meeting starting). It is
    **not** tick-scoped: an earlier draft of this spec tied it to "the exact tick it
    happened", but `task_input`/`task_cancel` run between game-loop ticks (inside the
    WebSocket message handler), not inside `step()`, so the broadcast that follows a
    message is always for the *next* tick — a same-tick equality check would silently drop
    the note before any client ever saw it. It simply holds the latest status until the
    next task event replaces or clears it; the browser decides how long to display it
    (e.g. a few seconds), the same way it already times out the joke popup.
- Never another player's `tasks`, `doing`, `challenge` or `task_note`. Player entries stay
  exactly `{id, name, x, y}`.

### The six mini-games
Every kind below is implemented in `server/minigames.py`: one function builds the challenge
(secret + visible parts) with `self.rng`, one validates and applies a `value`, one builds the
visible `challenge` dict. All six share the cancel/time-limit/validation rules from Part 2.

1. **`ticket`** (certificate, step 2 — "Now serving", Student Services)
   `value` must be exactly `true` (type `bool`); anything else is invalid. The challenge
   tracks `start_tick` and `number` (3–6, `rng.randint`, above the counter's start of 0); the
   counter is `(tick - start_tick) // TICK_RATE`. Visible: `{"kind": "ticket", "number",
   "counter"}`. Pressing while `counter < number`: `"Not your turn. Take a new ticket."`
   (new `start_tick = tick`, new random `number`). Pressing while `counter > number`:
   `"You missed your number."` (same reroll). Pressing exactly at `counter == number`:
   station done. Time-out note: `"The queue moved on without you."`

2. **`translate`** (helpdesk — "Só em português", Main Entrance)
   Five fixed Portuguese/English pairs (European Portuguese) live in `minigames.py`:
   "Preciso de ajuda." / "I need help."; "Onde fica a biblioteca?" / "Where is the library?";
   "Perdi o meu cartão de estudante." / "I lost my student card."; "A senha do wifi não
   funciona." / "The Wi-Fi password doesn't work."; "Quando abre a secretaria?" / "When does
   the office open?". A challenge picks one pair (`rng.randrange`), two wrong translations
   from the other four (`rng.sample`), and shuffles all three into `options`
   (`rng.sample(..., 3)`), remembering the correct index. `value` must be an `int` that is
   `0`, `1` or `2`. Visible: `{"kind": "translate", "sentence", "options"}`. Wrong index:
   `"Não percebi."` (new sentence and options). Correct index: station done. Time-out note:
   `"The queue moved on."`

3. **`card`** (gate — "Tap your card", Main Entrance)
   The challenge holds a 5-digit `number` (`f"{rng.randrange(100000):05d}"`), shown to the
   player — this is deliberately a copy-it-back task, not a memory test. `value` must be a
   `str` of exactly 5 ASCII digits. Visible: `{"kind": "card", "number"}`. Any 5-digit value
   that does not match: `"Beep. Red."` (new number). A match: station done. Time-out note:
   `"The gate locks again."`

4. **`paper_jam`** (print, and certificate step 1 — "Paper jam", Library)
   A 3×3 grid (cells numbered 0–8, row-major); the challenge picks 3 distinct jam cells
   (`rng.sample(range(9), 3)`) and tracks which of them are `cleared`. `value` must be an
   `int` in `0`–`8`. Visible: `{"kind": "paper_jam", "cleared": [...]}` (jam cells not yet
   cleared stay hidden). Tapping a cell with an uncleared jam: added to `cleared`; all 3
   cleared: station done. Tapping anything else (no jam there, or already cleared):
   `"Nothing there."`, no state change. Time-out note: `"Someone else cleared it."`

5. **`socket`** (socket — "Find a free socket", Auditorium)
   12 sockets (0–11); the challenge picks one `free` socket (`rng.randrange(12)`) and tracks
   which of the other 11 the player has already tried (`tried`). `value` must be an `int` in
   `0`–`11`. Visible: `{"kind": "socket", "taken": [...]}` (`free` never appears here before
   it is tapped). Tapping the free socket: station done. Tapping any other socket (whether
   new or already known taken): added to `tried` if new, `"Taken."`, no further change.
   Time-out note: `"All sockets taken. Try again later."`

6. **`seagull`** (nata — "Protect your pastel de nata", Courtyard)
   A 3×3 grid (0–8); the challenge tracks the seagull's current `cell` (`rng.randrange(9)`
   to start) and `hits` (0 at the start). `value` must be an `int` in `0`–`8`. Visible:
   `{"kind": "seagull", "cell", "hits"}`. Tapping the seagull's cell: `hits += 1`; if `hits`
   reaches 5, station done; otherwise the seagull jumps to a different random cell
   (`rng.choice` over the other 8). Tapping any other cell: no change, no note (a plain miss
   is not an error). The whole mini-game must finish within its 8 s time limit (Part 2), not
   per hit; time-out note (also the task's joke's punchline, reused here): `"A seagull took
   it."`

### Browser
- One mini-game panel, in `web/index.html`/`style.css`, driven from `web/main.js` (or a new
  `web/minigames.js`, whichever keeps `main.js` readable — this spec leaves the file split to
  whoever implements it, since it is a client-only decision). All six kinds render in the same
  panel shell: a title, the kind-specific content, and a "Close" button that sends
  `task_cancel`. Every tap target also responds to a mouse click; the panel never needs the
  keyboard except the "F" shortcut to open it (same as today's "Do task") and `gate`'s number
  field, which uses `<input type="number" inputmode="numeric">` so phones show a number pad.
  All text is added as text, never as HTML (existing rule).
- The panel opens when `doing.challenge` first appears in the player's own snapshot and closes
  when `doing` goes back to `null` (done, cancelled or timed out). While open, the browser
  stops sending `input` messages (no accidental walking while tapping the panel) — this is a
  client-side choice; the server still accepts movement during a task exactly as before
  (spec 004), so nothing breaks if a browser does send one.
- `task_note` is shown inline in the open panel (wrong answer, time-out); when the task is
  done, the existing joke popup is used, as today.
- The task list shows `"Step 1/2: <title>"` when an entry has `step`/`steps`, otherwise just
  the title, as today; only the current step's place is marked on the map, because that is
  the only pair of coordinates the entry carries (Part 4).
- An examiner sees the exact same task list, markers, "Do task" button and mini-game panel as
  a student, and can play through them; nothing in the UI marks them as fake (that would give
  the examiner away).

## Out of scope
- New task types beyond the six listed; sabotage interactions with tasks beyond the existing
  "a meeting cancels every running task" rule (unchanged); staff doors (spec 008 part 6/9),
  sound.
- Changing `TASK_RANGE`, `TASKS_PER_STUDENT`, the rate limit or the message-size limit.
- A real campus-wide ticket counter shared between players, or any state shared between two
  players' challenges — every challenge is private to the one player doing it.
- Accessibility beyond "every tap target also works with a mouse/keyboard" (already required
  by spec 007); no sound cues, no difficulty settings.

## Done when

### Existing tests this spec changes on purpose (in `tests/test_tasks.py`)
- `test_the_campus_has_the_eight_task_places_of_spec_004` → replaced: the campus has six
  tasks now, and `certificate` has two stations, so there is no single flat table of eight
  `(area, x, y, seconds)` tuples any more.
- `test_every_campus_task_is_on_a_floor_tile_in_its_area_and_takes_5_to_10_seconds` →
  replaced: campus stations have a `minigame` key instead of `seconds`; the new version
  checks every station of every task (including both `certificate` stations) is a floor
  tile in its area with a known mini-game kind, and that no campus task lacks a `minigame`
  (Part 1).
- `test_every_student_gets_three_different_tasks_and_examiners_none` → replaced: examiners
  now get `TASKS_PER_STUDENT` tasks too (Part 3); the new version checks students and
  examiners both get 3 different tasks from the pool.
- `test_no_snapshot_contains_another_players_tasks_in_any_phase` → the examiner branch
  (`"tasks" not in snapshot`) is replaced with the same check as for students (an examiner's
  own `tasks` match their own `Player.tasks`), since examiners now have tasks too.
- `test_an_examiner_cannot_tell_who_has_which_task_by_trying` → replaced: since an examiner
  now has real tasks of their own, the test instead checks they cannot tell another player's
  task id from an unknown one (the student version of this test, applied to an examiner).
- `task_by_an_examiner` / `unknown_task_by_an_examiner` rejection cases → replaced by a ghost
  examiner case (`"Ghosts cannot do tasks"`) and an examiner trying another player's/unknown
  task id (`"Not one of your tasks"`), since a living examiner with their own tasks is no
  longer always rejected.

### New tests, written first and red before the implementation
- `tests/test_minigames.py` (or added to `tests/test_tasks.py`, kept in a clearly separated
  section):
  - **Campus data:** no task in `server/campus.json` is a plain waiting task; every station
    (including both `certificate` stations) is a floor tile in its named area; `certificate`'s
    two stations are at different tiles.
  - **Per mini-game** (`ticket`, `translate`, `card`, `paper_jam`, `socket`, `seagull`), with a
    seeded `random.Random`: a correct solution finishes the station; the mini-game's own wrong
    rule (reroll + note, or no-op + note, or silent miss) happens on a wrong-but-valid value;
    an invalid value (wrong type, out of range, wrong length, missing) is rejected with a
    reason and changes nothing; the time limit cancels the station with its note and the
    station can be started again from the top; `socket`'s challenge never reveals the free
    socket before it is tapped, in any player's snapshot.
  - **Framework:** leaving `TASK_RANGE`, being expelled and a meeting starting all cancel a
    running challenge exactly like before (spec 004/008); `task_cancel` cancels the current
    station and leaves earlier steps/other tasks untouched; `task_input`/`task_cancel` for a
    task the player is not doing, for a station without a mini-game, out of range, and before
    joining (`parse_message`) are all rejected with a reason and change nothing.
  - **Fake tasks:** a started game deals `TASKS_PER_STUDENT` different tasks to every examiner
    too; finishing an examiner's task changes neither `done` nor `total` in `task_progress`
    and never ends the game; a ghost examiner cannot start a task but a ghost student still
    can (R4, unchanged); a student's snapshot never contains any field about an examiner's
    tasks, and vice versa.
  - **Multi-step:** `certificate`'s second station cannot be started before the first is done,
    and only at its own tile; finishing the first station does not finish the task
    (`task_progress` unchanged) but does move the task's entry to the second station's title
    and place; cancelling the second station leaves the first station's completion in place;
    finishing the second station finishes the task once (`task_progress` grows by exactly 1)
    and reveals the joke.
  - **WebSocket:** a student starts a task, solves its mini-game over one or more
    `task_input` messages (including at least one wrong answer first), and another player's
    `task_progress` grows once it is done.
- `uv run pytest` passes; the output is pasted. All existing tests not listed above keep their
  assertions unchanged.
- Built and tested part by part, in the order: 1 delete the boring tasks → 2 mini-game
  framework (`server/minigames.py`, `task_input`, `task_cancel`) with all six mini-games → 3
  fake tasks for examiners → 4 multi-step `certificate` → then the browser. `uv run pytest`
  after each part.
- Manual check with 4 browser windows locally (one at phone width):
  - each of the six mini-games can be played to completion by tap and by mouse; a wrong
    answer shows its message and lets the player keep trying; the time limit, left idle,
    cancels the station with its message;
  - the shared task bar never moves when an examiner finishes a fake task;
  - the `certificate` task goes Library (paper jam) → Student Services (now serving), with
    the task list and map marker following the current station;
  - the "Close" button leaves the task open and startable again, without walking away;
  - an examiner cannot be told apart from a student by their task list, markers or button.
