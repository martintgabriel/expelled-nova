# Spec 014 — UI redesign: action buttons, staff doors, meeting screen, lobby

## Why
The action buttons, staff door list, meeting screen and lobby grew one text button at a time
across specs 002–013. They work, but they do not read as one system: button sizes and
positions shift with what is possible right now, staff doors are a wall of text buttons,
the meeting screen is a plain list, and the lobby is a bare `<li>` list. The browser only
shows what the server sends and sends only inputs (AGENTS.md); this spec changes none of
that — it only changes how the existing state is drawn.

## What
1. **One shared action button component**, used for every in-round action (task/fix = USE,
   report, call a meeting, expel, staff door, lights off):
   - Round, ≥ 64 px (72 px on phones), a simple line icon (same stroke width for every icon)
     with a short uppercase label under it.
   - Fixed slots in the bottom-right corner, one per action the player's role can ever use
     this round. A slot a role never has (e.g. "expel" for a student) is hidden for the
     whole round — that is set once from the role, which cannot change mid-round, so it
     never flips back and forth. A slot the role has but cannot use *right now* (out of
     range, on cooldown, already used, a ghost) stays visible and greyed out, with the
     reason as both `title` and `aria-label`, instead of disappearing — so positions never
     jump mid-round.
   - The primary action (USE for students, EXPEL for examiners) is drawn larger than the rest.
   - A cooldown (expel, staff door, lights off) is drawn as a circular sweep around the
     button with the seconds left in the middle. The one-shot "call a meeting" action has no
     timer from the server (`meeting_used` is a flag, not a countdown — see
     `server/game.py`): once used, its ring shows full and the button greys out, with no
     number, since there is no "seconds left" for it.
   - A keyboard-hint badge (E/R/F/V/Q) sits in the corner of the circle, shown only on
     keyboard devices (the existing `Controls.isTouch` check).
   - Colours carry meaning and stay consistent across every button that shares a meaning:
     USE = accent yellow, REPORT/MEETING = blue, EXPEL/LIGHTS OFF = red, DOOR = purple. Every
     pair passes WCAG AA contrast (≥ 4.5:1) for its label text.
   - The bar must not cover the joystick, the task list or the edge arrows on a phone-sized
     window; the edge arrows measure the actual rendered height of the action bar at runtime
     instead of assuming a fixed size, since the bar's height now depends on the role.
2. **Staff doors**: the destinations other than the one the examiner stands at are drawn as
   small cards (room name + an arrow rotated to point toward that destination in world
   space), grouped above the single round "door" action button, instead of one text button
   per destination.
3. **Meeting screen**: a big timer at the top; living players as a 2-column grid of cards,
   each with a small original character drawn in that player's colour, their name and a
   "you" marker; ghosts are greyed out and not votable; tapping a card opens a confirm/cancel
   step before the vote is actually sent; a player who has voted gets a "VOTED" stamp;
   "Skip vote" is its own card at the bottom of the grid. At the result, each candidate's
   card shows one small dot per vote it received — a count, not an identity, since the
   server never tells a client who voted for whom (R2 in `docs/brd.md`).
4. **Lobby**: players as colour chips with a small original character, the host marked with
   an original symbol (not text), and a big "N/10" count. "Start game" is the main button and
   shows "Need N more players" in its own label while disabled; "Invite players" is a
   secondary button.

All visible text is set as text (`textContent`/appended text nodes), never as HTML, exactly
like the code it replaces. Every element id that `web/main.js` and the tests rely on is kept.
All five existing keyboard shortcuts (E, R, F, V, Q) keep working, unchanged, in
`CampusScene.create()`.

## Out of scope
- Anything in `server/`: no new fields, no new message types, no new cooldown timers for the
  meeting bell (the server only ever sends `meeting_used: bool`).
- New mechanics, roles, sounds or map content.
- Showing who voted for whom at a meeting result: the server does not send it, and this spec
  does not add it.
- Visual rework of the join screen, role screen, end screen, mini-game panel or the HUD's
  existing keycap row (`#control-*`): untouched beyond what naming/colour consistency needs.
- Automated UI tests (the project has no browser test harness); verification is manual in a
  running browser plus the existing `uv run pytest -q` server suite.

## Done when
- `uv run pytest -q` still passes (this spec touches no server code, so the suite is
  unaffected).
- Every id in `web/index.html` that `web/main.js` looks up with `getElementById` still
  exists, and every `send({...})` call it triggers is unchanged.
- As a student: USE, REPORT and MEETING show as round buttons in the same three spots for
  the whole round; greyed out with a reason when not possible, not hidden.
- As an examiner: the same three plus EXPEL (largest), DOOR and LIGHTS OFF show in the same
  six spots for the whole round, with cooldown rings on EXPEL, DOOR and LIGHTS OFF.
- Standing at a staff door shows the other doors as small named, arrowed cards above the
  round door button; picking one sends the same `{type: "door", to}` message as before.
- Pressing E/R/F/V/Q still does the same thing as before the redesign.
- The meeting screen shows the timer, a 2-column card grid, greyed-out ghosts, a
  confirm/cancel step before a vote is sent, "VOTED" stamps, a "Skip vote" card, and
  per-candidate vote dots at the result — all from data the server already sends today.
- The lobby shows chips with a character, a host symbol, "N/10", and a start button whose
  own label reads "Need N more players" while disabled.
- On a 375×667 phone-sized window, the action bar, joystick and task list never overlap, and
  an off-screen task's edge arrow is never covered by the action bar.
