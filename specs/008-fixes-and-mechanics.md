# Spec 008 — Fixes and remaining mechanics (one release, nine parts)

## Why
Team testing found bugs, and two core mechanics from the BRD are still missing (staff doors EX06, sabotage F4). We ship them in one pull request to save time. So that the result can still be reviewed and explained, it is built and committed **part by part**, each part with its own tests. Builds on specs 001–007.

## What (implement in this order)

### Part 1 — Movement jitter at walls (bug)
- **Symptom:** next to walls the own character jitters or jumps back.
- **Likely cause:** the browser's movement prediction and the server's movement disagree near walls. Find and name the actual cause first.
- **Requirement:** the browser predicts with exactly the same speed, step size, player size and collision rule as `server/game.py`, on the same map data. Server corrections are blended smoothly instead of snapping. The server stays the authority.

### Part 2 — No vote for yourself (bug)
A player cannot vote for themselves. The vote is rejected with a reason, and the own entry has no vote button.

### Part 3 — Ghosts pass through walls
Ghosts ignore walls but stay inside the map. Living players are unchanged.

### Part 4 — Bell only at one place
- The emergency bell is an object in the middle of the map. Its position is stored in `server/campus.json` (e.g. `"bell": [col, row]`) so a new map can move it.
- It can only be rung within about 1.5 tiles of the bell. All other rules from spec 006 stay (living players only, once per player per game).
- Browser: the bell is drawn on the map; the Bell button appears only when close to it.

### Part 5 — Tasks work reliably
- First audit the task code from spec 004 and list every reliability problem. Examples to check: a task not counting, counting twice, staying stuck when the player walks away, during a meeting, after being expelled, after a new round.
- Fix each problem, with a test that fails before the fix. The task rules from spec 004 stay unless a problem requires a change; say so.

### Part 6 — Staff doors (vents, BRD EX06)
- **Doors:** 3–4 staff doors at fixed places, stored in `server/campus.json` and connected as one network.
- **Travel:** a living examiner standing on a staff door can travel instantly to any other door of the network and chooses the destination. Cooldown: 3 seconds.
- **Rejected for:** students, ghosts, during a meeting, in `lobby` or `ended`, when not standing on a door, an unknown destination, during the cooldown.
- **Visibility:** other players see the examiner disappear and appear only if it happens within their vision.
- **Browser:** doors are drawn as hatches. An examiner on a door sees one button per destination.

### Part 7 — Vision blocked by walls
- Vision (enforced on the server since spec 005) also needs a line of sight: a player or failed exam within the radius is visible only if no wall tile lies on the straight line between the two tile centres.
- Ghosts and the meeting phase are unchanged: they see everything.
- **Keep it cheap:** compute the visibility once per tick per player on the tile grid. After this part, report how long one server tick takes with 10 players.
- **Browser:** the darkness follows the walls, so what is drawn matches what the server sends.

### Part 8 — Lights sabotage
- **Trigger:** a living examiner can turn off the lights. Cooldown 30 seconds; not during a meeting; not while the lights are already off.
- **Effect:** students' vision radius shrinks to about 1.5 tiles until the lights are fixed. Examiners and ghosts are not affected.
- **Fix:** a living student holds the light switch for 3 seconds. The switch position is stored in `server/campus.json`, e.g. in Student Services. Moving away cancels.
- A meeting turns the lights back on.
- **Browser:** a clear "Lights out" message for students, the switch marked on the map, a progress bar while fixing.

### Part 9 — Controls as pictograms
- The HUD shows the controls as small pictograms drawn by our own code: keycaps for WASD/arrows (move) and the action keys, plus the actions only shown when relevant (staff door, sabotage).
- Keep the existing keys; use V for staff doors and Q for sabotage unless they are taken.
- On touch devices, show the touch controls from spec 007 instead. Do not hide hints by window width.

## Out of scope
The new campus map (spec 009), sound, new task types, accounts.

## Done when
- **Per part:**
  - its tests are written first and fail before the implementation;
  - then `uv run pytest` passes;
  - existing tests stay unchanged unless the part requires it, with the reason stated.
- **Tests per part, at least:**
  - Part 1: the movement constants the browser receives equal the server's; movement along and into walls stays deterministic.
  - Part 2: voting for yourself is rejected; the state is unchanged.
  - Part 3: a ghost moves through a wall tile but not off the map; a living player is still blocked.
  - Part 4: ringing next to the bell is accepted; ringing far away is rejected; the spec 006 limits still hold.
  - Part 5: one failing-then-passing test per reliability problem found.
  - Part 6: travel accepted; each rejected case leaves the state unchanged; the cooldown boundary.
  - Part 7: a target behind a wall within the radius is hidden; a target in open space is visible; a target around a corner is hidden; a ghost sees through walls; in a meeting everyone sees everyone.
  - Part 8: sabotage accepted; rejected (student, ghost, cooldown, meeting, already off); reduced vision for students only; fixed after holding 3 seconds; moving away cancels; a meeting turns the lights back on.
  - Part 9: manual check only (drawing).
- The agent stops after each part, runs all tests, pastes the summary and lists the changed files, so the part can be committed separately as "Part N: … (spec 008)".
- The time per server tick with 10 players is reported after parts 7 and 8.
- **Manual check** with 4 browser windows and one phone: each part's behaviour, and walking along walls for 30 seconds without visible jitter.
- The pull request description lists each part: what changed, why, and its limits.
