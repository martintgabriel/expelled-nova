<<<<<<< Updated upstream
# Spec 018 — Campus map (key C)
=======
# Spec 018 — Campus map (key M)
>>>>>>> Stashed changes

## Why
In a meeting, players have to say where they walked and where they found a failed exam,
but the only place the room names appear is in the world itself, and only near where the
player stands. Without an overview, "I was near the… thing by the stairs" is all anyone
<<<<<<< Updated upstream
can say. Like the map in other games of this genre, a full campus map that opens with C
("campus"; M already calls a meeting, spec 015) or a button on phones lets every player look up room names and corridors and describe
exactly where they were. It also shows the player's own open tasks, so they can walk
straight to them and know what each one is before choosing it. It never shows where anyone
else is or anyone else's tasks, so it gives no new information about any player. Builds on specs 001–017
(the map data, areas, labels and walls already reach every browser in `welcome.map`; the
help overlay of spec 015 is the pattern for opening and closing; the round buttons of
specs 016/017 are the row the map button joins). The server is untouched.
=======
can say. Like the map in other games of this genre, a full campus map that opens with M
(or a button on phones) lets every player look up room names and corridors and describe
exactly where they were. It is for orientation only: it shows the campus, never where
anyone else is, so it gives no new information about any player. Builds on specs 001–017
(the map data, areas, labels and walls already reach every browser in `welcome.map`; the
help overlay of spec 015 is the pattern for opening and closing). The server is untouched.
>>>>>>> Stashed changes

## What

### `web/campusmap.js`: the map drawn once, from `welcome.map` only
<<<<<<< Updated upstream
A new, self-contained module, loaded after `music.js` and before `main.js` (order:
`sound.js`, `music.js`, `campusmap.js`, `main.js`). It exposes one object, `CampusMap`,
with `build(map)` (returns one `<svg>` element), `setYou(point, color)` (the own
position in map pixels and the own colour, or `null` to hide the marker) and
`setTasks(list)` (the own open tasks as numbered markers, `[]` for none). `main.js` is the
only file that calls it.

- **Reads only what it draws:** `welcome.map` is all of `server/campus.json`, so it also
  contains `vents`, `tasks` and `spawns`. `campusmap.js` reads only `tile_size`, `grid`,
  `decor` (kinds `sea` and `sand`), `areas`, `labels`, `meeting_point` and `light_switch`,
  and never anything else; a test guards this. In particular it never reads the map's
  `tasks`, which list every task's stations, everyone's.

- **Drawn as SVG, in tile units:** `viewBox` is the grid size in tiles, so the map scales
  to any screen. `grid` only knows `#` (blocked) and `.` (walkable): blocked tiles are
  dark, walkable tiles light, so corridors are clearly visible as corridors. The sea is `#`
  in the grid and only recognisable through the `sea` decor, so `sea` and `sand` from
  `decor` are drawn on top. No Phaser, no images, no dependency.
- **Grey:** the whole base map is in greys (walls, floors, sea, sand, areas, the two fixed
  places). Only the player's own things are in colour: the own marker and the own tasks.
- **Areas and names:** every entry in `areas` is a grey rectangle (its `color` is not used)
  with its `name`; every entry in `labels` (Hall B, Spine, Carcavelos Beach, …) is its
  `text`. Every name has one size, the size of "Hall D" (`NAME_FONT`, 0.9 tiles). All text
  is set with `textContent`, never `innerHTML`.
- **Every name centred in its room:** each label in `server/campus.json` has a `room`, a
  rectangle of tiles that are all floor (or all wall, for the Gym's roof), so a name never
  crosses a wall; no two rooms overlap. An area's name uses the area's rectangle. A name is
  centred in its room; if it is too wide it is wrapped at its spaces ("Lecture / hall B");
  in a tall, narrow room (the beach, the Spine) it is written along the room, turned 90
  degrees to the left. It is only made smaller if a single word still does not fit.
  A label's `x`/`y` stay its place in the game world (`web/render.js`), which is unchanged.
- **Every name unique:** "Lecture hall B" and "Lecture hall D" (the two "Lecture hall"
  labels) and "CTT Student Hall" (was "Student Hall"), changed in the data, so the game
  world says the same.
- **Two fixed places:** the meeting table (`meeting_point`) and the light switch
  (`light_switch`) get a mark. Their names, "Meeting point" and "Light switch", are labels
  with a room too, marked `"only_on_map": true`, so the game world (which draws both places
  itself) skips them. Both are static parts of the campus that every player can already see
  in the world.
=======
A new, self-contained module, loaded before `main.js`. It exposes one object,
`CampusMap`, with `build(map)` (returns one `<svg>` element) and `setYou(point)` (a
position in map pixels, or `null` to hide the marker). `main.js` is the only file that
calls it. `CampusMap` receives nothing but `welcome.map` and the own position, so it
cannot show anything else even by mistake.

- **Drawn as SVG, in tile units:** `viewBox` is the grid size in tiles, so the map scales
  to any screen. Walls and buildings from `grid` are dark, walkable tiles are light, so
  corridors are clearly visible as corridors; `sea` and `sand` from `decor` are tinted so
  the beach is recognisable. No Phaser, no images, no dependency.
- **Areas and names:** every entry in `areas` is a tinted rectangle in its own `color`
  with its `name`; every entry in `labels` (Hall B, Spine, Carcavelos Beach, …) is a
  text at its position. Area names are larger than label names. All text is set with
  `textContent`, never `innerHTML`.
- **Two fixed places:** the meeting table (`meeting_point`) marked "Meeting point", and
  the light switch (`light_switch`) marked "Light switch". Both are static parts of the
  campus that every player can already see in the world.
>>>>>>> Stashed changes
- **Built once:** `main.js` calls `CampusMap.build(welcome.map)` once after the welcome
  message and puts the result into the overlay; opening the map never rebuilds it.

### The map overlay and how it opens
- **Overlay:** `#map-panel`, built like the help overlay (spec 015): a dimmed background
  with a card holding the title "Campus map", the SVG, and a close cross. Closed with the
  cross, Esc, or a click on the dimmed background.
<<<<<<< Updated upstream
- **Key C toggles it:** press C once to open, press C again to close. Same guards as the
  H key for help: not while typing in an input, not with Ctrl/Cmd/Alt, not on key repeat.
  M stays the meeting key exactly as in spec 015. The handbook's controls list gets one
  line for C.
- **Map button for phones (spec 007):** a round button with an inline SVG map icon (no
  image, no emoji), the same `help-button` shape, placed in the top-right row directly left of
  the mute button (so: map, mute, "?"), visible on every screen once the welcome message
  has arrived (before that there is no map to show, so it stays hidden). `aria-label` "Campus map",
  `aria-expanded` reflects the state, a `click` sound on press (spec 016). The lobby
  roster/role panels (`.panel`) and the HUD (`#hud`'s `max-width`) move further left so
  nothing runs under the three round buttons on narrow windows.
- **Works during a meeting:** the button and the overlay sit above the meeting screen
  (same layering as help), so
  the map can be opened in the middle of the discussion; closing it returns to the meeting
  exactly as it was (a vote already selected or cast stays as it is).
- **One overlay at a time:** opening the map closes the help overlay and vice versa.
  While open, the map's dimmed background covers the round buttons, like help does, so on
  phones it closes with the cross or a tap on the background.
- **In `index.html`, `#map-panel` comes after `#help-panel`,** so the help overlay's
  content (which `tests/test_spec017.py` checks for the music switch) is unchanged.
=======
- **Key M toggles it:** press M once to open, press M again to close. Same guards as the
  H key for help: not while typing in an input, not with Ctrl/Cmd/Alt, not on key repeat.
- **Map button for phones (spec 007):** a round button with an inline SVG map icon (no
  image, no emoji), the same `help-button` shape, placed in the top-right row next to the
  mute and "?" buttons, visible on every screen once the welcome message has arrived
  (before that there is no map to show, so it stays hidden). `aria-label` "Campus map",
  `aria-expanded` reflects the state, a `click` sound on press (spec 016). The lobby
  roster/role panels move further left if needed so nothing overlaps.
- **Works during a meeting:** the button and the overlay sit above the meeting screen, so
  the map can be opened in the middle of the discussion; closing it returns to the meeting
  exactly as it was (a vote already selected or cast stays as it is).
- **One overlay at a time:** opening the map closes the help overlay and vice versa.
>>>>>>> Stashed changes
- **Does not pause the game:** like help, the map is only in the browser. The character
  keeps standing (or keeps walking on keyboard input) while the map is open.

### "You are here": only the player's own position
<<<<<<< Updated upstream
- While the phase is `"playing"`, a small marker in the own colour (`colors` of the own
  id) shows the own predicted position, updated from `CampusScene.predictTick()` only while the map is open,
  and a line under the title says "You are in: <state.area>" (hidden when there is no
  area). In the lobby, during a meeting and at the end, the marker and the line are
  hidden: everybody is at the table then, and the map is purely for describing places.
- It is the player's own position, which they already see on their own screen.

### Own tasks on the map
- While the phase is `"playing"`, each of the player's own open tasks is a green numbered
  marker (1, 2, 3) on its current station, so the player can walk straight there. Under
  the map, a list with the same numbers says what each task is and where: "Print your
  assignment · Library", with "· step 1 of 2" for a multi-step task. So a player knows a
  task before walking to it and pressing Use.
- The tasks come from the own snapshot only (`state.tasks`, which the server sends to its
  owner alone; spec 012), handed to `CampusMap.setTasks()` by one function in `main.js`,
  `updateMapTasks()`, which leaves out finished tasks. A finished task disappears; a
  multi-step task's marker moves to its next station. The list is filled as text.
- An examiner's (fake) tasks look exactly like a student's, as in the to-do list, so the
  map tells nothing about the role. Ghosts see their own tasks too (they can still do them).
- In the lobby, during a meeting and at the end, markers and list are hidden.

### What the map must never show
Other players or their colours, ghosts, failed exams, vents or open hatches, anyone
else's tasks or the task stations of the whole map, anything role-specific, or the
lights-out darkness. Apart from the own marker and the own tasks, the map is
pixel-for-pixel the same for every player, every role, alive or ghost, lights on or off.

## Out of scope
Other players' tasks or all task stations, vents, highlighting a sabotage, zooming or panning, drawing on the map,
hold-to-peek (C only toggles), changing the meeting key, showing other players in any form, any server change.
=======
- While the phase is `"playing"`, a small marker in the own colour shows the own
  predicted position, updated from `CampusScene.predictTick()` only while the map is open,
  and a line under the title says "You are in: <state.area>" (hidden when there is no
  area). In the lobby, during a meeting and at the end, the marker and the line are
  hidden: everybody is at the table then, and the map is purely for describing places.
- This is the only thing on the map that depends on the player, and it is the player's
  own position, which they already see on their own screen.

### What the map must never show
Other players or their colours, ghosts, failed exams, vents or open hatches, tasks (own or
anyone else's), anything role-specific, or the lights-out darkness. Apart from the own
marker, the map is pixel-for-pixel the same for every player, every role, alive or ghost,
lights on or off.

## Out of scope
Task markers, vents, highlighting a sabotage, zooming or panning, drawing on the map,
hold-to-peek (M only toggles), showing other players in any form, any server change.
>>>>>>> Stashed changes

## Done when
- **Tests first (AGENTS.md):** `tests/test_spec018.py`, written and shown to fail before
  the implementation, in the style of `tests/test_spec016.py`/`test_spec017.py`:
<<<<<<< Updated upstream
  - `GET /campusmap.js` is served, and `index.html` loads `sound.js`, `music.js`,
    `campusmap.js`, `main.js` in this order;
  - `index.html` has the map button (with `aria-label`) in the top-right row next to the
    help and mute buttons, a `#map-panel` overlay with a close button after `#help-panel`,
    and a handbook line for C;
  - `main.js` toggles the map on "c"/"C" with the same typing/modifier/repeat guards as
    "h", closes it on Escape, and closes help when the map opens and vice versa; the M
    meeting key is unchanged;
  - `main.js` calls `CampusMap.build` with `welcome.map` and `CampusMap.setYou` only with
    the own position and colour (or `null`);
  - `campusmap.js` uses no `innerHTML`, and never reads `players`, `ghosts`, `vents`,
    `open_vents`, `spawns`, `role`, `fellow_examiners` or `failed_exams`. The test
    matches these as whole identifiers (word boundaries / property access), not as plain
    substrings, so `pointer-events` or an SVG's `role="img"` attribute do not count;
    it reads no key of the map other than the seven it draws (so never `map.tasks`);
  - own tasks: `campusmap.js` exposes `setTasks`; `index.html` has the `#map-tasks` list
    in the map panel; `updateMapTasks()` in `main.js` is the only caller of `setTasks`,
    reads `state.tasks`, leaves out `done` tasks, only works while `"playing"`, fills the
    list as text and never touches `welcome.map`, other players or roles; the map refreshes
    them when it opens and on each new snapshot while open;
  - grey: the map's colour constants are greys and `area.color` is not used;
  - names: the two lecture halls and the CTT Student Hall have their full names and no two
    labels share one; every label has a room inside the grid that is all floor or all wall;
    no two rooms overlap; "Meeting point" (right under the table) and "Light switch" are the
    only `only_on_map` labels and `render.js` skips those; `campusmap.js` centres names in
    `.room`, turns tall ones (`rotate(-90`) and has one font size for names (`NAME_FONT`);
=======
  - `GET /campusmap.js` is served, and `index.html` loads it before `main.js`;
  - `index.html` has the map button (with `aria-label`) in the top-right row next to the
    help and mute buttons, and a `#map-panel` overlay with a close button;
  - `main.js` toggles the map on "m"/"M" with the same typing/modifier/repeat guards as
    "h", closes it on Escape, and closes help when the map opens and vice versa;
  - `main.js` calls `CampusMap.build` with `welcome.map` and `CampusMap.setYou` only with
    the own position (or `null`);
  - `campusmap.js` uses no `innerHTML`, and never mentions `players`, `ghosts`, `vents`,
    `open_vents`, `tasks`, `role`, `fellow_examiners` or the failed-exam field of the
    snapshot;
>>>>>>> Stashed changes
  - `server/game.py` and `server/main.py` gained no map-overlay code;
  - all earlier tests still pass unchanged (including the b-e-l-l guard of spec 011).
- `uv run pytest` passes in full (output pasted into this spec).
- **A manual check list on the deployed app** (two browser tabs, one at phone width with
  touch emulation):
<<<<<<< Updated upstream
  - C opens the map, C again closes it; Esc, the cross and the background close it too;
    M still calls a meeting at the table;
  - on the phone-width tab, the map button opens and closes it, and does not overlap the
    "?" or mute button, the HUD or any panel;
=======
  - M opens the map, M again closes it; Esc, the cross and the background close it too;
  - on the phone-width tab, the map button opens and closes it, and does not overlap the
    "?" or mute button or any panel;
>>>>>>> Stashed changes
  - every room and area name is readable at phone width, and corridors are clearly
    visible between the rooms;
  - while playing, the own marker moves with the own character and "You are in" matches
    the room; in the lobby, a meeting and at the end, both are hidden;
  - during a meeting, the map opens above the meeting screen and closing it leaves the
    vote untouched;
  - with an examiner in a vent, a failed exam on the floor and the lights out, both tabs'
    maps show none of it and look identical apart from the own marker;
<<<<<<< Updated upstream
  - opening help closes the map and the other way round;
  - while playing, the own open tasks are numbered green markers on their places, the list
    under the map says what and where; a finished task disappears; a student's and an
    examiner's tabs look the same apart from which tasks they list.

## Test results
Before the implementation, 17 of the 20 new tests failed: each because the file, element or
function they check did not exist yet. The 3 that passed were guards that were already true
(the identifier guard checks itself, M still calls a meeting, the server has no map code).
After it:

```
tests/test_spec017.py ......................                             [ 89%]
tests/test_spec018.py ....................                               [ 91%]
tests/test_tasks.py .................................................... [ 96%]
...................                                                      [ 98%]
tests/test_websocket.py ....................                             [100%]
======================= 1013 passed, 1 warning in 6.32s ========================
```
(993 before, plus 20 new. The one warning is Starlette's `httpx` deprecation notice from the
test client, unrelated to this spec.)

The courtyard rename (see below) changed four existing tests first; they failed against the
old map (`4 failed, 1009 passed`) and pass after it. Still 1013 tests in all:

```
======================= 1013 passed, 1 warning in 5.80s ========================
```

Own tasks and the grey map (see below): 6 new tests, written first. 5 failed before the
change (no `setTasks`, no `#map-tasks` list, no `updateMapTasks()`, no refresh on open, the
colours not grey); the guard "never reads the map's task stations" was already true. After:

```
tests/test_spec018.py ..........................                         [ 91%]
======================= 1019 passed, 1 warning in 5.78s ========================
```

Names centred in their rooms (see below): 5 new tests, written first, and one existing test
in `tests/test_campus.py` changed to expect "CTT Student Hall". All 6 failed before the
change (`6 failed, 60 passed` in those two files). After:

```
tests/test_campus.py ...................................                 [  3%]
tests/test_spec018.py ...............................                    [ 91%]
======================= 1024 passed, 1 warning in 5.67s ========================
```

## Changes during implementation
- **`setYou` gets a CSS colour.** The snapshot's `colors` holds palette numbers, not colours,
  so `main.js` passes `Render.colorCss(latestState.colors[welcome.id])`; `campusmap.js` needs
  no access to `render.js`. The test was changed to accept that call.
- **Area names fit their rectangle.** A fixed size made "MAIN ENTRANCE" run into "STUDENT
  SERVICES". Each area name now takes the largest size up to `AREA_FONT` that fits its
  rectangle; a name that would come out smaller than the other place names goes on one line
  per word ("STUDENT / SERVICES").
- **Names are measured.** While `build()` runs, the SVG is in the page but invisible, so
  each name's real width can be measured with `getBBox()`.
- **Smaller marks.** The own marker and the meeting table are smaller circles than at first.
- **Names centred in rooms, one size (asked for during the review).** A first version kept
  each label near its `x`/`y` and only pushed it back inside an area or the map, with three
  sizes (areas 1.25, labels 0.9, places 0.75). That left names off-centre and let "Meeting
  point" run over a wall and "Lecture hall" past its room. Now every name has Hall D's size,
  every label has a `room` in `server/campus.json` and is centred in it, wrapped onto two
  lines where needed, and Carcavelos Beach and the Spine are written along their rooms. The
  rooms are data, not computed: the grid only knows floor and wall, and a room's edges
  (where a hall ends and a corridor begins) are a design decision. The names of the meeting
  point and the light switch moved from `campusmap.js` into the data as `only_on_map` labels,
  so they follow the same rule; `web/render.js` skips them (one line).
- **Lecture hall B, Lecture hall D, CTT Student Hall (asked for during the review),** in the
  data like the courtyards, so the game world shows the same names. One existing test
  (`tests/test_campus.py`, the label names) expects "CTT Student Hall" now, with a comment.
- **"Upper Courtyard" and "Lower Courtyard" (asked for during the review).** The two
  courtyards had the same name, so nobody could say which one they meant. The rename is in
  the game's data, not only on the map, so the HUD, "You are in", the to-do list and the map
  all say the same. This is the one exception to "the server is untouched": only
  `server/campus.json` changed (both area names and the nata task's area), no rule.
  `web/render.js` recognised the courtyards by their exact name; it now checks that the name
  ends with "Courtyard". Four existing tests named the areas and were changed, each with a
  comment: `tests/test_campus.py` (the area names, now required to be unique, and the two
  `area_at` checks), `tests/test_game.py` (the area names), `tests/test_tasks.py` (the nata
  task's area) and `tests/test_spec015.py` (the coordinate check finds the courtyards by
  "ends with Courtyard"). The descriptions in `tests/test_spec011.py` ("the north Courtyard")
  and the old test map `tests/maps/campus_spec008.json` were left as they are.
- **C does nothing before the welcome message.** The button is hidden then, and `setMapOpen`
  refuses to open an empty map, so C on the join screen (outside the name field) stays silent.
- **A line for phones in the handbook too:** "The map button (top right) shows the whole
  campus", next to the C line for keyboards.

- **Own tasks on the map, and a grey base map (asked for during the review).** The first
  version kept every task off the map. A team note asked for the own tasks on the map, to
  walk straight to them and to know what a task is before choosing it, and for a grey map
  where other players cannot be seen. So: `CampusMap.setTasks()`, `updateMapTasks()` and
  the `#map-tasks` list (numbers on the map, what and where in the list, which also works
  on phones without hovering), and greys instead of the area colours. The rule "never
  anyone else's" stays: the tasks come only from the own snapshot. Two parts of the test
  file changed with it: `tasks` left the list of names `campusmap.js` must never use (the
  map's `tasks`, everyone's stations, stays forbidden through the allowed map keys and its
  own test), and the identifier guard's own example uses `map["vents"]` instead.

## Limits
- **The task list shows the current station only.** A multi-step task says "step 1 of 2"
  but not where step 2 will be, like the to-do list (spec 012).
- **A task marker can cover a room name** where the station stands on it (the helpdesk in
  the Main Entrance, the nata in the Lower Courtyard); the list under the map still names it.
- **Names are measured once, when the map is built.** If the browser's font changes later
  (zoom does not, it scales the whole SVG), the names keep the sizes they got then.
- **Rooms are drawn by hand in the data.** Moving a wall in the grid can need a label's room
  moved too; the tests catch a room that crosses a wall or overlaps another.
- **"Meeting point" is centred in its room, not on the table.** The space right under the
  table is 4 tiles wide at most (a wall at column 30 in row 24), too narrow for "Meeting" at
  Hall D's size. Its room is columns 25 to 29, so the name sits one tile left of the table's
  centre.
- **The game world's labels did not move.** Only the map centres names; in the world each
  label still stands at its `x`/`y` (spec 009), with its new name.
- **Small text on phones.** At 375 px the plan is about 300 px wide; label names are about
  6 px high. They are readable but small; there is no zoom (out of scope).
- **The marker shows an examiner where they are, also inside a vent.** It is the examiner's
  own position on their own screen, like the camera that sits on the vent (spec 015).
- **The marker follows the prediction, 20 times a second,** and only while the map is open.
  It jumps in steps of one tick and is repaired by the server like the own character.
- **"You are in" knows only the seven `areas`.** In a place that is only a label (Hall B,
  Spine, …) or a corridor the line is hidden, as the HUD says "Corridor" there.
- **Game keys still work while the map is open,** like with the handbook: M at the table
  calls a meeting, and walking keys keep walking.
- **Checked by hand in a local 4-tab game** (one tab also at 375 × 812): C and the button open
  and close it, Esc, × and the background close it, H and C replace each other, M at the table
  called a meeting with the map open and the map stayed above the meeting screen, the marker
  moved with the own character in the own colour and was hidden in the meeting, "You are in"
  matched the room, the map markup of an examiner's and two students' tabs was the same, no
  console errors.
- **Checked with an examiner in a vent, a failed exam and the lights out** (4 tabs, local): the
  map markup (without the own marker) had the same SHA-256 on all four tabs: the expelled
  student (a ghost), two living students and the examiner sitting in the Student Services
  vent. No tab's map showed the vent, the failed exam, another player or the darkness; each
  showed only its own marker, the examiner's on the vent.
- **Checked a vote with the map** (local, a meeting from a report): a picked but unconfirmed
  card ("Vote for Eli?") was still picked after C and Esc; a cast vote stayed cast
  (`my_vote` unchanged, "You voted for Eli") after the button and the cross.
- **Checked the own tasks** (4 tabs, local, also at 375 px): no markers in the lobby; while
  playing, each tab showed three numbered markers on its own task places and the matching
  list, the examiner's fake tasks in the same form ("step 1 of 2" included).
- **Checked a finished task** (local): a student at the gate opened the map, started "Tap
  your student card at the gate" and solved it while the map stayed open. Without closing
  or reopening it, the gate's marker (number 2 of 3) disappeared, the list dropped its line,
  and the two tasks left were numbered 1 and 2 on the map and in the list.
- **Checked a finished step** (local): the examiner, whose certificate task is fake, opened
  the map at the Library printer and cleared the paper jam with the map still open. Marker
  3 moved from the Library (37.5, 22.5) to Student Services (39.5, 3.5) and its line became
  "Submit your Bachelor certificate · Student Services · step 2 of 2"; the other two
  markers stayed as they were. So a fake task moves on the map exactly like a real one.
- **Checked the centred names** (4 tabs, local): every name on the map at 0.9 (none had to
  be made smaller), both lecture halls on two lines inside their rooms, Spine and Carcavelos
  Beach turned, "Meeting point" on two lines under the table without crossing a wall, in
  the lobby, while playing and in a meeting; the game world shows no "Meeting point" text.
  **Not checked yet:** the deployed app and a real phone with touch.

## Files created or changed
- `web/campusmap.js`: new. `CampusMap.build(map)`, `CampusMap.setYou(point, color)` and
  `CampusMap.setTasks(list)`; a grey base map.
- `web/main.js`: `ui.mapButton`/`mapPanel`/`mapClose`/`mapWhere`/`mapSlot`; `setMapOpen()` and
  `updateMapWhere()`; the button, cross and background listeners; Esc and C in the keydown
  listener; `setHelpOpen()` closes the map; the map is built in the welcome branch;
  "You are in" in the state branch; the marker in `CampusScene.predictTick()`;
  `updateMapTasks()` and `ui.mapTasks` for the own tasks.
- `web/index.html`: the map button left of mute; `#map-panel` after `#help-panel`; the C line
  and a touch line in the handbook; the `#map-tasks` list; `<script src="campusmap.js">`
  between `music.js` and `main.js`.
- `web/style.css`: `.map-button`; `.panel` at 154 px (max-width `100vw - 178px`); `#hud`
  max-width `100vw - 168px`; the map card and the SVG's names, table, switch and marker in
  greys; the green task markers and the `.map-tasks` list.
- `server/campus.json`: "Upper Courtyard" and "Lower Courtyard" instead of two "Courtyard"
  areas; the nata task's area is "Lower Courtyard"; every label has a `room`; "Lecture hall
  B", "Lecture hall D", "CTT Student Hall"; the `only_on_map` labels "Meeting point" and
  "Light switch".
- `web/render.js`: the two courtyard checks match a name that ends with "Courtyard"; labels
  marked `only_on_map` are skipped.
- `tests/test_spec018.py`: new, 31 tests.
- `tests/test_campus.py`, `tests/test_game.py`, `tests/test_tasks.py`, `tests/test_spec015.py`:
  the courtyard names, and in `tests/test_campus.py` "CTT Student Hall" (see "Changes during
  implementation").
- `specs/018-campus-map.md`: these last sections.
=======
  - opening help closes the map and the other way round.

## Changes during implementation
(Filled in after implementation, like spec 016.)

## Limits
(Filled in after implementation, like spec 016.)

## Files created or changed
(Filled in after implementation, like spec 016.)
>>>>>>> Stashed changes
