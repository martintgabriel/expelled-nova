# Spec 015 — Story UI, how to play, vents like the original, beach

This spec describes what was built. Where the result differs from the first version of the spec, "Changes during implementation" says how and why.

## Why
The game worked, but around the map it still looked like a form: plain text boxes that told none of our story (Nova, undercover examiners, getting expelled). New players also needed a quick "how to play". Vents worked differently from the original, the meeting had no keyboard shortcut, the lobby could not change its host, task places were plain markers, and the beach was a thin strip. This spec closes these gaps. Builds on specs 001–014; spec 014's action buttons, arrow cards, meeting screen and lobby list stay and got the story look.

## What

### 1. Small functional gaps
- **Meeting shortcut:** calling a meeting has the keyboard shortcut **M**, shown as a key badge on its action button like E, R, F, V and Q, and as a keycap in the HUD while a meeting can be called. `tryMeeting()` in `web/main.js` explains the two common reasons itself ("You have already called a meeting", "Go to the meeting table first"); the server checks everything again.
- **Host hand-over:** in the lobby the host can make another player host. Message `{"type": "make_host", "target": "<player id>"}`, rule `Game.make_host` in `server/game.py`.
  - Checked in this order, each a rejection that changes nothing: unknown sender ("Unknown player"), not in the lobby ("The host can only change in the lobby"), not the host ("Only the host can hand over"), target not text ("Target must be a player id"), oneself ("You are already the host"), a player who is not in the game ("Unknown target").
  - The host is stored in `Game.host_id` instead of "first in join order". The first player of an empty game becomes host. If the host leaves, the player who has been in the game longest becomes host, as before. A handed-over host stays host for the next rounds.
  - Browser: the host sees a "Make host" button on every other player's line of the roster. The new host gets the notice "You are the host now. The class register is yours."
- **How to play:** a round "?" button, always in the top right corner (join screen, lobby, game, every overlay), opens the "How to play" handbook. It also opens with **H** (not while typing in a field) and closes with Esc, ×, H again or a click next to the card.
  - Content in short story language: the two roles and their goals, controls (keyboard or touch, chosen by input device), tasks, expelling, reporting and meetings, vents, sabotage, and how each side wins.
  - Purely in the browser: static text in `web/index.html`; it does not pause the game.

### 2. Bigger beach with surfboards (map)
- The grid grew from 42 to **46 columns** (43 rows as before). The four new columns lie in the west: the beach is now **5 tiles of walkable sand** (x 1–5, y 9–35) between the sea (x 0) and the campus. The sea also lies north (y 8) and south (y 36) of the sand and blocks walking, but not sight.
- Every coordinate in `server/campus.json` moved by **+4 columns**: areas, spawns, tasks, the light switch, the meeting point, decor and labels.
- **Surfboards:** new floor decor kind `surfboard` (furniture: walked over). Six boards on the sand, drawn by `drawSurfboards` in `web/render.js` in three looks chosen by the tile (`(col + row) % 3`): lying on the sand, two leaning on a wooden rack, one stuck upright in the sand. The label "Beach" became "Carcavelos Beach".
- **Drawing that moved with the map (`web/render.js`):** the sea's foam is also drawn along the north and south ends of the sand; the Auditorium's free aisle is column 33 now (a fixed number in `drawGround`).
- Tests with hard-coded tile coordinates were updated by the same offset (see "Done when").

### 3. Vents like the original game
The four vents **replace the staff doors** of spec 008, part 6 (map key `vents` instead of `staff_doors`; `Game.use_door` and the `door` message are gone).
- **Placement:** exactly 4 vents, one per corner quadrant of the walkable map, on floor tiles reachable from the spawn: Lecture Hall B (7, 10), Student Services (43, 1), South Lawn (7, 36), Plaza (44, 36).
- **Enter (`Game.enter_vent`, message `vent_enter`):** a living examiner whose centre is on a vent's tile presses V (or the vent button) and climbs in. They sit on the vent's centre, stop walking, and a running (fake) task is cancelled. While inside:
  - they are left out of everyone else's snapshot, also a ghost's and a fellow examiner's;
  - walking, expelling, reporting, calling a meeting, tasks and sabotage are rejected with "Leave the vent first" (stopping, `dx = dy = 0`, is always accepted);
  - their camera sits on the current vent, because their own position is the vent's centre; they see what is in sight from there;
  - **move (`Game.move_vent`, message `vent_move` with `to`):** arrow cards point toward the other vents; a click on a card, or an arrow key / WASD, moves to that vent at once, without a cooldown. A key picks the vent that lies most in the pressed direction (at most 60° off); two keys within 80 ms count as a diagonal;
  - **leave (`Game.leave_vent`, message `vent_leave`):** "Leave vent" (V again) climbs out at the current vent.
- **Others:** each use of a hatch (climbing in or out) opens it for `VENT_OPEN_TICKS` (0.5 s). Every snapshot lists the open hatches in sight as `open_vents`: vent ids only, never who. Moving between vents opens no hatch.
- **Limits of the rule:** a meeting start takes everyone out of the vents and places them around the meeting table like everyone else (no cooldown). So does the end of the game. Climbing in again has a cooldown of 3 seconds after climbing out (`VENT_COOLDOWN`). Students and ghosts cannot use vents.
- **Server is the authority:** `Player.vent` and `Player.next_vent_tick` live in `server/game.py`. Only an examiner's own snapshot has `vent` (their own vent id or null) and `vent_cooldown`; nobody receives another player's vent.
- **Browser:** `Render.makeVent` / `updateVent` draw the hatches; the lid slides aside while a hatch is open. The own character is not drawn while inside; its eyes look out of the vent it sits in. The other action buttons are greyed out with "Leave the vent first".

### 4. Task places in the map
- The green "!" markers are gone. Every task station of the map is an object drawn on the floor by `Render.makeTaskPlace`, chosen by the station's mini-game kind (no new map data):

  | Mini-game | Object | Task |
  |---|---|---|
  | `paper_jam` | printer with a red jam light | Print your assignment; Print a copy of your certificate (Library) |
  | `ticket` | red ticket machine, "now serving" display | Submit your Bachelor certificate (Student Services) |
  | `translate` | blue "?" helpdesk sign | Ask the Helpdesk for help (Main Entrance) |
  | `cable` | projector with a loose cable | Get your slides on the projector (Auditorium) |
  | `card` | card gate with a yellow arm | Tap your student card at the gate (Main Entrance) |
  | `seagull` | pastel de nata on a plate | Eat your pastel de nata in the sun (Courtyard) |

- **Recognisable:** an own open task place has a soft, slowly breathing green glow with an outline (`Render.makeTaskGlow`). A finished one loses it; a two-step task's glow moves to its next station. The edge arrows to open tasks stay.

### 5. Story UI around the map
One look for every screen and panel outside the map: **campus paperwork** (cream paper, navy ink, rubber stamps), drawn with CSS and inline SVG only, system fonts, no image or font files.
- **Join screen:** a Nova Campus student ID card with a photo, the nickname on a dotted line, a barcode and the title "Expelled!" as a red stamp. The button says "Enrol".
- **Role reveal:** a letter with a stamp. Student: "Office of Admissions", motto "Survive the semester", green stamp "Enrolled". Undercover Examiner: "Examination Board · strictly confidential", motto "Fail them all", red stamp "Undercover".
- **Task list:** "Semester to-do", a page of a ring notebook with tick boxes; a finished task is ticked and crossed out. Hidden during a meeting.
- **Lobby:** "Class roster" with one numbered, ruled line per player (character, name), the host marked (spec 014's symbol plus a "host" tag), the "Make host" button on the host's screen and the "N/10 enrolled" count.
- **Meeting and result:** "Emergency faculty meeting"; player file cards, a green "VOTED" stamp, the result "The faculty has decided" with the verdict as the last line of the minutes.
- **End screen:** a diploma with a green "Passed" seal for the students' win, an exmatriculation notice with a red "Expelled" stamp for the examiners' win. The clear title ("Students win!", "Examiners win!", "All tasks done: students win") stays. The class list below shows every player's character, role and ghost tag.
- **Toasts and errors:** a "Campus notice" slip. The text is still the server's (or the browser's) plain reason.
- **Also restyled:** HUD (a hall pass), role badge, ghost and lights banners, the task joke (a sticky note), invite, mini-game and "connection lost" cards, the handbook, and the round action buttons (ink edge, paper label tags).
- **Kept:** every element id that `web/main.js` and the tests use, text set as text (never as HTML), WCAG AA contrast (the ratios are noted in `web/style.css`), and layouts for a phone and a wide window.
- **Layout:** the "?" button owns the top right corner, so the lobby roster sits next to it and no card reaches under it (long cards scroll inside). Role badge and notebook stack under the HUD; `main.js` gives the stylesheet the HUD's real bottom edge (`--hud-bottom`), because the HUD wraps on narrow windows.

## Out of scope
New mechanics beyond the above, sound, accounts, changing rules from earlier specs except where stated (host storage, vents).

## Done when
- **Tests for `server/game.py`,** written first and failing before the change, in the new file `tests/test_spec015.py` (106 tests):
  - **make_host (26 tests):** accepted from the host in the lobby; the stored host starts and restarts, the first player no longer can; rejected from a non-host, outside the lobby (playing, meeting, ended), for oneself, for an unknown player, for a player who left, with a target that is not text; hand-over on leave (handed-over host, first host, during a round, empty game); the WebSocket messages. 25 failed before the change; "the first host leaving passes the host on" was already true.
  - **map, beach (11 tests):** 46 columns; every coordinate moved by 4; five tiles of reachable sand; the sea west, north and south blocks walking and not sight; a walk across the beach ends at the water; the openings to the campus; surfboards are floor decor on the sand; the label. 9 failed before the change; two of the three walks to the water were already true.
  - **vents (69 tests):** climbing in on each of the four vents, anywhere on the tile; rejected for students, ghosts (student and examiner), off a vent, one pixel beside it, during the cooldown, in a meeting, in the lobby, after the end, when already inside, on a map without vents; moving to another vent, without a cooldown, and its rejections; leaving places the examiner on that vent, visible and walking again; the cooldown ends after exactly 3 seconds; while inside: in nobody else's snapshot (student next to the vent, fellow examiner, ghost), the vent id never sent to others, and walking, expelling, reporting, calling a meeting, tasks and sabotage rejected with the state unchanged; a meeting (button and report) and the end of the game take them out; hatches open and close for players in sight only; the messages; the map (exactly 4 vents, one per corner quadrant; every spawn, task place, vent, the light switch and the meeting point reachable from the first spawn). All 69 failed before the change.
- **Existing tests** changed only where a rule or coordinates changed, each with its reason in a comment:
  - coordinates (+4 columns): `tests/test_campus.py`, `tests/test_spec008.py`, `tests/test_spec010.py`, `tests/test_spec011.py`, `tests/test_tasks.py`;
  - the bigger map: grid size 46 × 43; the longest walk from the spawn is 62 tiles (limit 64 tiles / 13 s instead of 60 / 12 s); "in the middle of the map" for the meeting point is measured from the middle of the buildings; the campus has 4 one-tile gaps left instead of 38 (the beach was a path of them); the beach label; `surfboard` in the list of floor kinds;
  - vents: the 33 staff-door tests of `tests/test_spec008.py` (part 6) were removed with the rule; their cases are covered for vents in `tests/test_spec015.py`. Four map tests read `vents` instead of `staff_doors` (one in `tests/test_campus.py`, one in `tests/test_spec008.py`, two in `tests/test_spec011.py`).
- `uv run pytest` passes: 953 tests (880 before, plus 106, minus 33).
- **Checked in a running game** (5 browser tabs on one laptop, one of them at 375 × 812 with touch emulation, plus 700, 1000 and 1280 px wide windows):
  - "?" opens and closes the guide (button, H, Esc, ×); H while typing the nickname does not open it;
  - M at the table calls a meeting; M far away shows the notice;
  - the host hands over in the lobby and back; a non-host is rejected with the reason;
  - vents: V climbs in, the arrow keys (also a diagonal), WASD and the cards move, V climbs out somewhere else with the 3-second ring; a student standing three tiles away no longer receives the examiner; a meeting called meanwhile puts the examiner at the table;
  - task objects stand in their rooms and glow for their owner;
  - the bigger beach with sea foam, the label and the three surfboard looks;
  - join, role, tasks, lobby, meeting, result and both end screens have the story look and stay readable; on the phone size HUD, badge, notebook, action buttons, joystick and "?" do not overlap;
  - HUD, role badge, notebook and "?" do not overlap at 640 and 1000 px with an examiner's full row of keycaps. This one was checked with the panels filled in by hand in the lobby, not in a real examiner round.
- **Still to check by hand:** a real phone, a full round with 10 players, the hatch animation seen by another player (covered by server tests only), and the examiners' end screen after a real examiner win (its look was checked with the students' data).

## Map changes
Every change to `server/campus.json`, with its reason:

| Change | Reason |
|---|---|
| 4 columns inserted after column 1; the grid is 46 × 43 | Section 2: the beach is five tiles wide. |
| Every area, spawn, task place, the light switch, the meeting point, all decor and labels east of the old beach: x + 4 | Section 2: everything moves with the map. |
| Sand decor x 1, w 1 → x 1, w 5 (y 9–35) | Section 2: the new columns are sand. |
| Sea decor north of the beach x 1, w 1, y 0–7 → x 1, w 5, y 0–8; south x 1, w 1 → w 5 | The wall tile (1, 8) at the beach's north end had no look; the beach is a bay with water on three sides now. |
| 6 `surfboard` entries on (2, 13), (3, 16), (4, 18), (3, 23), (4, 26), (2, 29) | Section 2: surfboards. The tiles give two lying, three leaning and one stuck in the sand. |
| Label "Beach" (1.2, 20) → "Carcavelos Beach" (3.5, 20.4) | Section 2; centred on the wider beach. |
| `staff_doors` (Library, Food Court, Student Services, Main Entrance) → `vents`: Lecture Hall B (7, 10), Student Services (43, 1), South Lawn (7, 36), Plaza (44, 36) | Section 3: exactly four vents, one near each corner. The old doors all lay in the north and east. |

No wall tile of the campus buildings changed; all openings between the beach and the campus are where they were.

## Changes during implementation
- **Vents replace the staff doors** instead of standing next to them. The first version did not say so; spec 008 already called the staff doors "vents", and V and the purple button were theirs. Two travel mechanics for the same role would be one too many.
- **Three vent messages** (`vent_enter`, `vent_move`, `vent_leave`) instead of the one `door` message, so each has one clear rule.
- **`open_vents`** was added to every snapshot so others can see a hatch move. It carries vent ids only.
- **A player inside is hidden from ghosts and fellow examiners too.** The first version said "invisible to everyone else"; this takes it literally.
- **The end of the game also takes players out of the vents,** so everyone is on the end screen's map.
- **Task objects are chosen by mini-game kind in the browser,** not stored in the map: the six kinds already tell the six stories.
- **The to-do notebook is hidden during a meeting.** As an opaque sheet of paper it covered the players around the table on a phone.
- **Role badge and notebook stack under the HUD on every window size,** and the lobby roster drops under the HUD below 760 px (before: below 600 px), because the HUD and the panels overlapped on windows between 600 and about 950 px.
- **On windows up to 400 px the round buttons are 66 px** (spec 014: 72 px on phones) and closer together. At 375 px three 72 px buttons reached 21 px into the joystick.
- **Shells on the sand are scattered** instead of one per tile of every sixth row, which drew a dotted line across the wider beach.
- **`aria-label` on the handbook** instead of `aria-labelledby`: a test of spec 011 forbids the letters "bell" in `web/index.html`.

## Limits
- **Arrow keys pick by direction.** A vent more than 60° off the pressed direction is not chosen; from some vents one neighbour needs two keys together (a diagonal) or its card.
- **No joystick control inside a vent.** On a phone the vents are chosen with the arrow cards.
- **A hatch is only seen while in sight.** Someone who looks away for half a second misses it; a vent tells nothing about who is inside.
- **The camera glides to the next vent** (it follows the own position), it does not cut.
- **An examiner inside still counts as a living examiner** for the win check and can be voted on: a meeting takes them out first.
- **Task objects are drawn under the characters** and do not block; the projector stands on a seat tile of the Auditorium, where its task place has always been.
- **The glow shows through the darkness,** like the old marker: a player's own task places are no secret. The objects themselves are darkened like the rest of the map.
- **The surfboard look depends on the tile.** Moving a board in the map can change how it is drawn.
- **`docs/brd.md` still says "staff doors"** (EX06) and "bell". The requirements document was not changed by this spec.
- **System fonts only.** The serif and typewriter faces differ a little between phones and laptops.
- **The Auditorium's aisle is a fixed column in `web/render.js`.** Moving the Auditorium in the map needs that number changed too (it was already so before this spec).
- **The vent cooldown is repeated in `web/main.js`** (`VENT_COOLDOWN`), only to size the ring on the button; the seconds shown are the server's.
- **No automatic browser tests.** Everything in `web/` was checked in a running game; two tests read the files (the M shortcut and the handbook; the vent messages and the kept ids).
