# Spec 008: fixes and remaining mechanics (nine parts)

Implements `specs/008-fixes-and-mechanics.md`: four bug fixes, the tasks of spec 004, staff doors (BRD EX06), vision blocked by walls, lights sabotage (roadmap F4) and the controls as pictograms. Each part was built tests-first and is meant to be reviewed commit by commit ("Part N: … (spec 008)").

- **Tests:** 547 pass (290 before). New: `tests/test_spec008.py` (195 tests, one section per part) and `tests/test_tasks.py` (62 tests).
- **Dependencies:** none added.
- **One extra fix** outside the nine parts: browsers now re-check the page's files on every load (see "Caching fix").

## What the browser and the server now exchange

| | New |
|---|---|
| Messages from the browser | `task`, `door`, `sabotage`, `fix` |
| `welcome` | `step`, `bell_range`, `task_range`, `switch_range`, `lights_out_radius` |
| Every snapshot (from the start of a round) | `task_progress`, `lights_on`, `vision_radius` (the player's own) |
| A student's snapshot | `tasks`, `doing`, `fixing` (their own only) |
| An examiner's snapshot | `door_cooldown`, `sabotage_cooldown` |
| `server/campus.json` | `bell`, `light_switch`, `staff_doors`, `tasks` |

Every new message is rejected before joining, checks the sender before anything else, and a rejection changes nothing (tested with a full state comparison). Player entries are still exactly `{id, name, x, y}`, and no snapshot contains another player's role, tasks or progress.

---

## Part 1 — Movement jitter at walls

**Why (the cause).** The wall rule was copied correctly into the browser; it was driven differently:

1. The server moves 8 px per 50 ms tick. The browser moved `speed × frame time` every frame (about 2.7 px). Because a blocked step drops the rest of its distance, the two ended at different points at corners, door jambs and walls. In a simulation with identical input and no delay, 16–18 % of 5,152 walks on the campus ended more than 1 px apart.
2. The browser only corrected towards the server while standing still, and snapped beyond 2 tiles. Next to a wall one side got blocked and the other did not, the gap grew, and after 64 px the character jumped back.
3. The browser applied a key at once, the server one tick after arrival; the 50 ms send throttle delayed only the server's copy.
4. The server loop never made up its sleep overshoot: 51.1 ms per tick measured locally, so 156 px/s against the browser's 160.
5. The standing-still glide could cross a wall corner and leave the prediction inside a wall.

**What changed.**
- `welcome` carries `step`. The game loop keeps a fixed timetable (`next_tick_at` in `server/main.py`). The movement rule in `server/game.py` is unchanged.
- The browser predicts its own character in whole server ticks with the received step, and reads and sends the direction once per tick.
- The server's position is compared with the last 400 ms of predicted positions (the server's answer is always a little old). A wrong prediction is repaired with the wall rule; the picture glides instead of jumping.
- Simulated with delay and jitter: the largest move of the drawn character in one frame fell from about 70 px to 4–6 px.

**Limits.** The drawn own character is up to one tick (50 ms) behind its own prediction. Start and stop take effect at the next tick. Snapshots stay rounded to 0.1 px.

## Part 2 — No vote for yourself

**What changed.** `vote()` rejects a vote for yourself ("You cannot vote for yourself"). The vote is not used up: the player can still vote for someone else or skip. The own row in the meeting has no Vote button.

**Limits.** `specs/006-meeting-vote.md` still says a vote for yourself is allowed; spec 008 overrides it.

## Part 3 — Ghosts pass through walls

**What changed.** `Game.blocked(x, y, walls=True)`: for a ghost only the edge of the map blocks. The browser's copy of the rule follows the `alive` value the server sends, so a ghost's own prediction matches.

**Limits.** A ghost can float over the border wall but never leaves the map. A ghost standing in a wall is simply drawn on top of it. `specs/003-expel-ghosts-end.md` still says walls block ghosts.

## Part 4 — Bell only at one place

**What changed.** The bell is a tile in the map (`"bell": [20, 15]`, in the Courtyard). It rings only within `BELL_RANGE` = 48 px (about 1.5 tiles) of that tile; a bell rejected for distance is not used up. The browser draws the bell and shows the Bell button only when in range.

**Limits.** A map without a `bell` entry rings anywhere (only the small test maps). The button uses the latest server position. The bell has no cooldown of its own (unchanged from spec 006).

## Caching fix (not one of the nine parts)

**Why.** While checking part 4, a browser combined the new `main.js` with an old cached `render.js` and the map stayed blank. The server sent no `Cache-Control` header for the files in `web/`.

**What changed.** `FreshStaticFiles` in `server/main.py` sends `Cache-Control: no-cache` with every page file. The browser asks on each load whether a file changed; an unchanged file gets a short "304 Not Modified".

**Limits.** The header only reaches a browser when it next fetches a file. **A browser that opened the game before this deploy may need one hard reload (Cmd+Shift+R / Ctrl+Shift+R) the first time after it.**

## Part 5 — Tasks (spec 004)

**Why.** The audit found nothing to audit: this branch had no task code at all (only the spec). The team decided to build spec 004 here, against a reliability checklist.

**What changed.**
- The 8 task places of spec 004 are in `server/campus.json`. At the start every student gets 3 different tasks; examiners none.
- A `task` message starts a student's own open task within 48 px of its tile. Every playing tick, a running task is cancelled if its player is out of range and done when its time is up.
- Browser: a task list, marks on the own open task places (also in the dark), a "Do task" button and key F, a ring with the seconds left, a toast when a task is cancelled, the joke popup, a shared progress strip along the top edge, and "All tasks done: students win" on the end screen.

**Reliability checklist** (13 tests named `test_reliability_…`): a meeting cancels every running task and none finishes in it; walking or being moved away cancels; an expel cancels and the ghost can start again; a finished task counts once; a new round and an empty game clear everything; a leaver's tasks leave both numbers; the end of the game clears running tasks; a bell or report processed first wins over a task finishing in the same tick; a map without tasks never gives a task win.

**Limits and decisions.**
- When a player leaving gives both sides their win at once, the examiners' count rule is checked first (spec 004: "the existing win checks stay as they are").
- The browser works out the reason of a cancelled task from the state; the server sends none.
- The progress strip shows no numbers.

## Part 6 — Staff doors (BRD EX06)

**What changed.** Four staff doors form one network (`staff_doors` in the map: Library, Food Court, Student Services, Main Entrance). A living examiner whose centre is on a door's tile sends `{"type": "door", "to": "<door id>"}` and stands on the chosen door at once. Cooldown: 3 seconds. Browser: hatches for everyone, one button per destination for an examiner on a door, key V for the next door.

**Visibility.** No new rule was needed: snapshots are already limited to what a player sees, so others see the examiner vanish or appear only within their vision. The browser no longer draws a moved player gliding across the map.

**Limits.** The cooldown is per examiner and starts at zero. A meeting does not reset it. Everyone can see where the hatches are.

## Part 7 — Vision blocked by walls

**What changed.** A living player receives another player or a failed exam only if it is within the radius **and** no wall tile lies on the straight line between the two tiles (Bresenham's line algorithm, always traced from the smaller end, so vision is the same in both directions). The visible tiles of a tile are worked out once and kept, because walls never change. Ghosts, the lobby, meetings and the end are unchanged. The browser repeats the rule and darkens the tiles behind walls.

**Tick time with 10 players** (`step()` plus one snapshot and `json.dumps` per player, 2,000 ticks on the campus; budget 50 ms):

| | Mean | 99 % under | Worst |
|---|---|---|---|
| Before part 7 | 0.18 ms | 0.26 ms | 0.44 ms |
| After part 7 | 0.24 ms | 0.71 ms | 3.11 ms |
| After part 8, lights on | 0.24 ms | 0.72 ms | 2.93 ms |
| After part 8, lights off | 0.20 ms | 0.67 ms | 1.20 ms |

The worst case is the first tick, when ten players stand on tiles nobody stood on before.

**Limits.** Visibility is per tile, so it changes at tile borders and the shadows have tile-shaped edges. A line exactly through the corner between two diagonal wall tiles counts as clear (the campus has no such gap).

## Part 8 — Lights sabotage (roadmap F4)

**What changed.**
- `sabotage`: a living examiner turns off the lights. Living students then see 1.5 tiles (48 px); examiners and ghosts are not affected.
- `fix`: a living student within 48 px of the light switch (`"light_switch": [10, 20]`, Student Services) stays there for 3 seconds. Leaving the range or being expelled cancels.
- A meeting turns the lights back on.
- Browser: a "Lights out" banner, a flashing mark above the switch, a Fix button (key F) with the progress ring, and a "Lights off" button (key Q) with the cooldown for examiners.

**Decisions taken (please confirm).**
- The 30-second cooldown is shared by all examiners. It runs from the start of the game, from the moment the lights are fixed and from the end of every meeting.
- "Hold" means: press once, then stay within reach for 3 seconds.
- One student is enough; if two fix at once, the first to finish turns the lights on.
- Sabotage is rejected on a map without a light switch.

**Limits.** A ghost student cannot fix the lights. The lights stay off until fixed or until a meeting. Nothing shows who turned them off.

## Part 9 — Controls as pictograms

**What changed.** The HUD shows keycaps drawn with HTML and CSS (no images): W-A-S-D and the arrows for moving, and E, R, F, V, Q each only while its action button is shown. On touch devices the keycaps are hidden and a joystick pictogram with "drag to move" shows instead; the choice is by input device, not by window width.

**Limits.** Manual check only, as the spec says. On a narrow keyboard window with several action keys the HUD can wrap.

---

## Existing tests that changed, and why

| Part | Test | Change | Reason |
|---|---|---|---|
| 2 | `test_meeting.py`: helper `everyone_votes` | the target skips instead of voting for themself | a self-vote is now rejected |
| 2 | `test_a_vote_for_yourself_counts` | replaced by `test_a_vote_for_yourself_is_rejected` | the rule changed |
| 2 | `test_without_a_clear_majority_nobody_is_sent_surfing` | two ballots without self-votes (`tie_2_2`, `votes_equal_skips`) | same outcomes, no self-votes |
| 2 | three tests where everyone voted for one player | that player skips | same |
| 2 | `test_four_votes_over_websocket_send_the_student_surfing` | the target skips; expects 3 votes and 1 skip | same |
| 3 | `test_game.py`: `test_ghost_keeps_moving_and_walls_still_block` | now `…_and_passes_walls` | the rule changed |
| 4 | `test_meeting.py`: four tests ringing on the real campus | the ringer is put at the bell first; no assertion changed | the bell rings only there |
| 8 | `test_tasks.py`: helper `other_views` | also leaves out `sabotage_cooldown` | it counts down every second, like `expel_cooldown` |

## Checked in the browser

One window plus scripted players (no second human window): walking into and along walls with 60 ms artificial delay; the vote screen; a ghost through walls; the bell place; a task round (finish, cancel by walking away, cancel by a meeting); staff door travel; line of sight against the server at five positions (0 mismatches); lights out and fixing; the keycaps for both roles and an emulated phone.

## Still to check by hand (spec 008, "Manual check")

- 4 browser windows and one real phone, each part's behaviour.
- Walking along walls for 30 seconds without visible jitter.
- A full task win with all tasks done, and the "you were expelled" toast for a cancelled task.
- R (report) and "F fix lights" in the keycap row.

## Notes for reviewers

- Old specs are not edited. Spec 008 overrides: 003 (walls block ghosts), 005 (vision is a plain circle), 006 (self-vote allowed, bell rings anywhere).
- The browser repeats a few server rules for prediction and drawing only. Each copy is marked `REPEATS SERVER RULE` in `web/main.js`; the server decides.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
