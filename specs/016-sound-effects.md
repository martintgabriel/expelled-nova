# Spec 016 — Sound effects

This spec describes what was built. Where the result differs from the first version of the
spec, "Changes during implementation" says how and why.

## Why
The game looks like a social-deduction game but plays silent: no footsteps, no click when a
button is pressed, no tension when a meeting starts, nothing when an examiner strikes. A
few generated sounds, with a small Nova twist where the story already gives us one (a
school gong for the meeting, paper ripping for an expelled exam), make the round feel like
the kind of game it is without recording or shipping a single audio file. Builds on specs
001–015 (every event a sound reacts to — movement, buttons, votes, roles, tasks, meetings,
expelling, mini-games — already exists; this spec only adds a reaction to it).

## What

### `web/sound.js`: everything generated, nothing recorded
A new, self-contained module, loaded before `main.js`. It exposes one object, `Sound`, with
`play(name)`, `isMuted()`, `setMuted(value)` and `toggleMute()`; `main.js` is the only file
that calls it.

- **Generated, not recorded:** every effect is built from two small primitives, a `tone()`
  (one oscillator with a volume envelope) and a `noise()` (a short burst of filtered white
  noise). Sixteen named effects are each a few lines combining these two: `footstep`,
  `click`, `voteSelf`, `voteOther`, `roleReveal`, `taskDone`, `taskStep`, `meetingChime`,
  `expel`, `error`, and the six mini-game sounds `ticketDing`, `cardAccept`, `cableClick`,
  `seagullHit`, `typingClick`, `paperRattle`. No audio files, no third-party library.
- **One `AudioContext`, created on the first gesture:** a `pointerdown` or `keydown`
  listener on `document`, each `{ once: true }`, creates the shared `AudioContext` and its
  one master `GainNode` the first time either fires anywhere on the page — joining the game
  is normally that first gesture, but any earlier tap or key also works. Before that (and if
  `window.AudioContext` does not exist at all) `Sound.play()` is a no-op: the game behaves
  exactly as before, just silent.
- **One master volume constant:** `MASTER_VOLUME` in `web/sound.js`, the only place the
  overall loudness is set.
- **Mute, remembered per browser:** `setMuted()` sets the master gain to 0 or
  `MASTER_VOLUME` and stores the choice in `localStorage` under one key, both the read and
  the write wrapped in `try`/`catch` (storage unavailable → sound starts on, the choice just
  does not survive a reload).

### The mute button
A round button, the same shape as the existing "?" button, placed directly to its left so
both sit in the top right corner on every screen (join, lobby, game, every overlay), exactly
like the "?" button already does. Two inline SVG icon states (a plain speaker, a speaker
with a line through it) are swapped by hiding one and showing the other; no images, no
emoji. The lobby roster and role-badge panels (`.panel` in `style.css`) moved further left
to leave room for both round buttons.

### Where each sound is hooked in (all in `web/main.js`; the server is untouched)
Every sound reacts only to what the browser already receives in its own snapshot or from a
local action; nothing new was added to the server.

1. **Footsteps** — `CampusScene.predictTick()` already recomputes the own character's
   walking direction every server tick. While it is non-zero, a tick counter plays
   `footstep` every `FOOTSTEP_TICKS` (6) ticks, about three times a second: a steady,
   quiet cadence instead of one sound per tick. Only the own prediction drives this; other
   players are drawn from the server's positions elsewhere and never trigger it.
2. **UI clicks** — one `Sound.play("click")` added to the existing listener of every round
   action button (expel, report, meeting, fix, sabotage, vent, use/task), the lobby's start
   and "Make host" buttons, the vent's arrow cards, the invite/help/minigame-close overlay
   buttons, the restart button, the join form's submit, and a meeting card's own
   select/cancel taps.
3. **Voting** — `castVote()` plays `voteSelf` the moment a vote is sent (win or lose, the
   player acted). `renderMeeting()` compares the server's `meeting.voted` id list against a
   per-meeting `knownVoted` set and plays the softer `voteOther` for every id that is new
   and not the player's own — `meeting.voted` only ever carries ids, never a target, so this
   cannot learn or leak who anyone voted for.
4. **Role reveal** — `showRoleScreen()` plays `roleReveal` as its very first line, before it
   even looks at `roleName`: the same call runs on the exact same code path for a student
   and an examiner, so the chord is identical by construction, not by coincidence.
5. **Task completed vs. one step completed** — `showJoke()` (already only ever called for
   the task's own owner, spec 004/012) plays `taskDone`. A new per-task map,
   `lastTaskSteps`, remembers each multi-step task's last-seen current station; when it
   moves forward without the task being done yet, `updateTasks()` plays the shorter
   `taskStep` instead. An examiner's fake task uses the exact same code path as a student's
   real one, so the sound cannot tell them apart.
6. **Meeting starts** — `updatePhase()` now keeps the *previous* phase in a local variable
   before overwriting `lastPhase`, and plays `meetingChime` the one tick the phase becomes
   `"meeting"`. Since this fires on the phase change itself, it is the same for the button
   and for a report, and for every player at once.
7. **Expel** — purely local to the two players involved, never broadcast:
   - the **expelled player**: the same phase-change tracking already distinguishes a
     mid-round expel (phase stays `"playing"`, `alive` flips to `false`) from a meeting
     vote-out (which flips `alive` during the `"meeting"` phase instead), so the rip plays
     only for a real expel, never for a vote-out;
   - the **examiner**: `tryExpel()` sets a local `pendingExpel` flag when it sends the
     message; `checkExpelSound()` plays the rip once the server's own snapshot confirms it
     (`expel_cooldown` becomes greater than 0 — the only way that happens while playing),
     and a rejection (the `"error"` message) clears the flag instead, so a target who
     stepped out of range in the meantime makes no sound at all.
8. **Mini-games (spec 012):** six fitting sounds, one shared error buzz.
   - For the four kinds where the right answer is already fully visible on screen
     (`ticket`'s counter/number, `card`'s shown number, `cable`'s own cables/port, `seagull`'s
     shown cell), the matching sound (`ticketDing`, `cardAccept`, `cableClick`,
     `seagullHit`) plays right on the tap, the same moment the existing client-side
     animations (`cable`'s "plugged"/"shake", `seagull`'s tart wobble) already guess at it —
     nothing new is revealed, since the player already sees this data.
   - For the two kinds whose right answer is secret (`translate`, `paper_jam`), every tap
     plays an unconditional flavour sound (`typingClick`, `paperRattle`) regardless of
     whether it turns out right; the clear moment of success is the existing `taskDone`/
     `taskStep` chime once the station actually clears.
   - **One shared `error` buzz**, in `updateMinigame()`: every wrong-but-valid answer in
     every kind sets a `task_note` while `doing` is still non-null (spec 012 — a time-out or
     a cancel always clears `doing` and the note together, so they never reach this
     branch), so a single check — "a new, non-empty note arrived while the mini-game is
     still running" — covers all six kinds without a kind-specific guess at wrong answers.

## Out of scope
Report-body alarm, vent sounds, sabotage/light sounds, ambient sounds (beach waves),
background music, win/lose jingles, other players' footsteps, a volume slider (the spec
only asks for a master constant and a mute button).

## Done when
- **Tests first (AGENTS.md):** `tests/test_spec016.py`, written and shown to fail before any
  of the above existed (17 of 18 failed; the server-untouched check passed trivially since
  nothing had been touched yet). As with spec 015's story UI, a sound's actual sound cannot
  be checked by pytest, so these tests guard what can be checked from outside a browser:
  the file is served (`GET /sound.js`) and loaded before `main.js`; the mute button exists
  next to the help button and the panels moved over for it; `sound.js` contains no audio
  file extension and no external URL, has exactly one `MASTER_VOLUME` constant, wraps
  `localStorage` in `try`/`catch`, and unlocks on a gesture, not on load; every one of the 16
  named sounds is actually called from `main.js`; the role-reveal call sits before the
  role branch (so it cannot differ by role); the expel sound is called exactly twice,
  guarded by `pendingExpel`; the task-done and task-step calls are distinct, with
  `taskDone` specifically inside `showJoke`; the meeting-start call is tied to the phase
  change, not to who called it; the vote sounds only ever read `meeting.voted`, an id list;
  the error buzz sits inside the branch that only runs while a mini-game is still running;
  and, finally, that `server/game.py` and `server/main.py` gained no sound-related code at
  all (this spec needed no new message — every sound already had everything it needs in the
  existing snapshots).
- `uv run pytest` passes: 971 tests (953 before, plus 18 new; see pasted output below).
- **A manual check list on the deployed app** (two browser tabs, one of them at phone width
  with touch emulation):
  - **footsteps:** walking makes a soft, steady step sound for the own character only;
    another player walking nearby makes no sound on this browser;
  - **UI clicks:** every round button, the lobby's Start/Make host, the vent arrow cards,
    the invite/help/"Close" buttons and the join button each make one clean click;
  - **voting:** casting a vote makes a click; a second browser's vote (visible only as the
    "VOTED" stamp, not as a name) makes a softer tick on the first browser;
  - **role reveal:** the chord sounds identical on a student's and an examiner's browser;
  - **tasks:** finishing a one-station task plays the bright chime; finishing step 1 of
    `certificate` (the paper jam) plays the shorter chime, step 2 (the ticket counter) the
    full one; an examiner's fake task plays the same chime as a student's real one;
  - **meeting:** both the button and a report make the gong play for every player at the
    same moment the meeting screen appears;
  - **expel:** on two tabs, only the examiner's own tab and the expelled player's own tab
    hear the rip; a third (living, uninvolved) tab stays silent;
  - **mini-games:** each of the six kinds makes its own sound on a correct tap (`ticket`,
    `card`, `cable`, `seagull` immediately; `translate`/`paper_jam`'s clicks/rattle on every
    tap, their own completion chime coming from the shared task sound); a wrong answer in
    any of the six makes the one shared buzz;
  - **mute:** the button mutes/unmutes every sound above at once, survives a reload (checked
    via `localStorage`), and sits in the same corner on the join screen, the lobby, mid-round
    and every overlay;
  - checked on a laptop and (joystick controls, button layout, the mute/"?" pair not
    overlapping any panel) on a phone-width window with touch emulation.

## Changes during implementation
- **`meetingChime`, not `meetingBell`:** spec 011 retired an old "bell" message and added a
  test (`tests/test_spec011.py`) that forbids the word "bell" in `server/game.py`,
  `server/main.py`, `server/campus.json`, `web/index.html`, `web/main.js`, `web/render.js`
  and `web/style.css`, so a plain **b-e-l-l** name anywhere in those files is a regression
  guard, not a free name. `web/sound.js` is a new file the old guard never lists, so the
  effect itself could still be called a gong internally; only the name `main.js` passes to
  `Sound.play(...)` had to change.
- **The per-tap mini-game sounds only cover `ticket`/`card`/`cable`/`seagull`, not
  `translate`/`paper_jam`'s correctness**, because the first four's challenges hide nothing
  from the player already (spec 012 says so outright for `cable`; the others' "number"/
  "cell" are shown the same way) while the second two's correct answer is a genuine server
  secret. Guessing at it client-side would either be wrong sometimes or require duplicating
  the server's secret-keeping logic in the browser for a cosmetic sound; the shared
  `error`-on-note-change rule already covers their wrong case for free, and their own
  flavour sound plays on every tap instead, which also matches the spec's wording for
  `translate` ("short keyboard typing clicks", not "a click when right").
- **No separate "paper feed" sound distinct from the task-complete chime.** The spec's
  wording for `paper_jam` ("printer rattle, then a paper feed sound when cleared") is
  implemented as the existing per-tap rattle plus the shared `taskDone`/`taskStep` chime at
  the moment the station actually clears, rather than a fourth, `paper_jam`-only "feed"
  sound: the station completing is already exactly the moment `taskDone`/`taskStep` exists
  for, and a mini-game cannot tell the difference between its own secret success and a
  server-side time-out/cancel until the server says so anyway.

## Limits
- **A pre-existing toast can still fire next to the new step chime.** Finishing step 1 of a
  multi-step task clears `doing`/`task_note` the same way a cancel does (spec 012);
  `updateTasks()`'s existing toast logic was not written with this case in mind and may
  still show "Task cancelled: you walked away" alongside the new `taskStep` chime. This
  predates spec 016 and is not a sound bug; fixing the toast is out of scope here.
- **Footstep timing is a fixed tick count (`FOOTSTEP_TICKS`), not tied to `welcome.speed`.**
  It looks right at the one movement speed the game currently has; a future change to
  `SPEED` would need this constant tuned again by ear.
- **The examiner's expel sound waits for the server's confirmation, so it can lag the click
  by up to one network round trip** (usually under 50 ms); the expelled player's own rip is
  not delayed this way, since it reacts to their own `alive` flag directly.
- **No automated browser tests**, same as spec 015: `tests/test_spec016.py` reads the files
  in `web/` to guard what must stay in place; everything about how a sound actually sounds,
  and the two-tab expel/vote/role scoping, was checked by hand (see "Done when").

## Files created or changed
- `web/sound.js` — new: the whole sound module (`Sound.play`/`isMuted`/`setMuted`/
  `toggleMute`), generated audio only.
- `web/main.js` — every `Sound.play(...)` call listed above; `pendingExpel`,
  `wasAliveForExpelSound`, `knownVoted`, `lastTaskSteps`, `FOOTSTEP_TICKS`; the mute
  button's own setup (`updateMuteIcon`, its click listener); `checkExpelSound()`.
- `web/index.html` — the mute button (two inline SVG icon states) next to the "?" button;
  `<script src="sound.js">` before `main.js`.
- `web/style.css` — `.mute-button`; `.panel`'s `right`/`max-width` moved over for it.
- `tests/test_spec016.py` — new: the tests described above.
