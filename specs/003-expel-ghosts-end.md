# Spec 003 — Expel, ghosts, game end and new round

## Why
This is the core tension of the game: undercover examiners get students expelled. A round also needs a clear end and a way to play again. Covers BRD EX05, EX08, R3, the examiner part of R6, R7, and acceptance A2 and A5 (examiner win). Builds on spec 002 (phases, host, roles, `snapshot_for`).

## What
- **Expel:** an examiner sends `{"type": "expel", "target": "<player id>"}`. Accepted only if:
  - the phase is `playing`;
  - the sender is a living examiner and the target is a living student;
  - they are at most `EXPEL_RANGE` apart (about 1.5 tiles, 48 px);
  - the sender's cooldown is over (`EXPEL_COOLDOWN` = 20 seconds). It starts when the game starts and again after each expel.

  Otherwise the action is rejected with a short reason and nothing changes.
- **Time in ticks:** cooldowns count game ticks (20 s × `TICK_RATE`), not the wall clock, so tests can advance time with `step()`.
- **Effect of an expel:** the target becomes a ghost (`alive = False`). A failed exam ("6/20") stays on the floor at the target's position, with its own id. The examiner's cooldown restarts.
- **Ghosts:** keep moving (walls still block). They cannot expel or be expelled. A living player's snapshot leaves ghosts out; a ghost's snapshot shows everyone. Failed exams are visible to everyone.
- **Examiner info:** an examiner's snapshot includes the seconds left on their own cooldown. The server checks range and cooldown again on every expel; the button in the browser is only a convenience.
- **Simultaneous actions:** if two examiners expel the same student in the same tick, the first one the server processes wins and the second is rejected ("Already expelled").
- **Winning:** after every expel and every player leaving while `playing`:
  - examiners win if living examiners are at least as many as living students;
  - students win if no examiner is left in the game.

  The game then moves to phase `ended`. The students' win by tasks comes with spec 004, by vote with spec 006.
- **End:** in `ended`, every snapshot includes the winner and all players' roles. Expel and movement messages are rejected ("Game is over").
- **New round:** the host sends `{"type": "restart"}` in `ended` → phase `lobby`. Roles are cleared, everyone is alive again, failed exams are removed, players return to spawn points and cooldowns reset. The same players stay. Rejected from a non-host and in any other phase.
- **Browser:**
  - an examiner sees an "Expel" button (and key E), enabled only when a living student is within range and the cooldown is over, with the cooldown shown;
  - an expelled player sees "You have been expelled" and plays on as a transparent ghost;
  - failed exams are drawn as a small sheet marked "6/20";
  - the end screen shows the winner and all roles; the host sees "New round".

## Out of scope
Reporting, the bell, meetings, voting and "sent surfing" (spec 006); tasks and the students' task win (spec 004); staff doors; map and look changes (spec 005).

## Done when
- Tests for `server/game.py`, written first and red before the implementation:
  - accepted: an examiner next to a student after the cooldown → the student is a ghost, a failed exam lies at their position, the examiner's cooldown restarts;
  - rejected, each leaving the state unchanged:
    - one tick before the cooldown ends,
    - out of range,
    - target is an examiner,
    - target is already a ghost,
    - sender is a student,
    - sender is a ghost,
    - in `lobby`,
    - in `ended`,
    - unknown target,
    - target that is not a string;
  - the cooldown boundary: exactly at 20 seconds the expel is accepted;
  - two expels of the same student in one tick: the second is rejected;
  - examiner win: 4 players, the examiner expels 2 students → `ended`, winner examiners;
  - student win: the only examiner leaves → `ended`, winner students;
  - a living player's snapshot contains no ghosts; a ghost's snapshot contains everyone; no snapshot shows other players' roles before `ended`; all roles are shown in `ended`;
  - restart: only the host, only in `ended`; afterwards phase `lobby`, no roles, everyone alive, no failed exams, players on spawn points.
- One WebSocket test: an examiner expels over the socket; the target receives the ghost state; another living student does not see the ghost.
- `uv run pytest` passes; the output is pasted. Existing tests still pass unchanged.
- Manual check with 4 browser windows locally:
  - the Expel button appears only for the examiner next to a student, and the cooldown is visible;
  - the expelled window switches to the ghost view;
  - the second expel leads to the end screen with all roles;
  - the host starts a new round.
