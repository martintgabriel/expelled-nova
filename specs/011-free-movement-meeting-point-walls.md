# Spec 011 — Free movement, meeting point and clear walls

This spec describes what was built. Where the result differs from the first version of the spec, "Changes during implementation" says how and why.

## Why
Playing felt cramped and unclear:
- players got stuck on every object;
- the bell was a placeholder instead of a meeting point like the emergency table in Among Us;
- walls had a visible "depth" that light shone into, and glass and walls were not clearly different.

This spec makes the map feel like the original game: free movement, one central meeting point, clear walls and clear glass. Builds on specs 001–010, especially 008 (bell, collision), 009 (map) and 010 (vision).

## What

### 1. Free movement
- **What blocks walking:** plain wall tiles, glass, the sea, roofs and screens. Nothing else.
- **Furniture is walked over:** tables, café, wooden and picnic tables, desks, study tables, counters, shelves, trees, steps, beanbags and the piano are drawn on the floor, under the characters.
- **Decor groups (`server/game.py`):**
  - `SOLID_DECOR` = `sea`, `solar`, `greenroof`, `roof`, `glasswall`, `screen`. They must lie on wall tiles (`#`).
  - `FURNITURE_DECOR` = `beanbag`, `counter`, `shelf`, `desk`, `studytable`, `table`, `cafetable`, `woodtable`, `shopshelf`, `foodcounter`, `piano`, `steps`, `picnic`, `tree`. They must lie on floor tiles (`.`).
  - `GROUND_DECOR` = `sand`, `paving`, `grass`, `terrace`, `pergola`, `glassroof`, `shopfloor`, `seats`. They may span walls and are painted on the floor tiles.
  - `FLOOR_DECOR` is furniture and ground together.
  - `validate_campus` rejects a solid kind on a floor tile and furniture on a wall tile, so a forgotten tile fails at server start.
- **Map data:** the 93 tiles under furniture in `server/campus.json` became floor tiles.
- **Sliding along walls:** each tick moves first along x, then along y (as before). So a diagonal walk into a wall slides along it and goes round the corner of a doorway.
- **Sliding round corners (new, `Game._slide`):** a straight walk that a wall stops looks up to `CORNER_SLIDE` px to both sides. If the way ahead is free there, the player moves sideways with what is left of the step and walks on.
  - `CORNER_SLIDE` = 10 px, half a player. Whoever stands at least half in front of a gap slips into it.
  - The nearest free side wins. The rest of the step goes sideways first, then forward.
  - In front of a plain wall no side is free: the player stops, as before.
  - A step never gets longer than `STEP`, and the slide never enters a wall.
  - It only helps a straight walk (one axis). A player who does not walk is never moved.
  - Ghosts are not affected: they ignore walls, and at the edge of the map no side is free.
- **Collision box:** unchanged, 20 × 20 px.
- **Browser prediction:** `walk`, `moveAxis` and `slide` in `web/main.js` repeat the server's rule. `welcome` carries `corner_slide`.

### 2. Meeting point instead of a bell
- **Object:** a round meeting table with a red emergency button, labelled "MEETING", drawn by `Render.makeMeetingPoint`. It lies on the floor and blocks nobody.
- **Place:** `"meeting_point": [24, 21]` in `campus.json` (the key `bell` is gone): the middle of the spine, 3.5 tiles east of the map's centre, where the spine, the Student Hall, the south Courtyard and the Library meet.
- **Calling a meeting (`Game.call_meeting`):** a living player at most `MEETING_RANGE` (48 px, 1.5 tiles) from the table's edge. The table's radius is `MEETING_TABLE_RADIUS` (40 px), so the reach is 88 px from its middle.
- **Unchanged rules of specs 006 and 008:** living players only, once per player per round, not in the lobby, not during a meeting, not after the end. A rejected call is not used up. A report still works anywhere next to a failed exam and does not use up the call. A map without a meeting point (the small test maps) calls from anywhere.
- **Names:**
  - message `{"type": "meeting"}` instead of `bell` (an old `bell` message gets "Unknown message type");
  - snapshot field `meeting_used` instead of `bell_used`;
  - meeting reason `"button"` instead of `"bell"`;
  - `welcome` carries `meeting_range` and `meeting_table_radius` instead of `bell_range`;
  - reasons: "Too far from the meeting table", "You have already called a meeting", "Ghosts cannot call a meeting".
- **Meeting positions (`Game._meeting_spots`):** all players, ghosts too, stand on a circle of `MEETING_CIRCLE` (64 px) around the table's middle.
  - Evenly spaced, in join order: the first player north of the table, the others clockwise.
  - With 10 players the 20 px squares do not overlap (neighbours are 39.6 px apart).
  - On the campus every place is free floor for 1 to 10 players.
  - A place that is not free floor (only on a map too tight for the circle) is left out: that player stays where they are.
  - A map without a meeting point moves nobody. The Auditorium is no meeting room any more (`MEETING_ROOM` and `_meeting_tiles` are removed).
- **Browser:**
  - the button "Call a meeting" shows near the table; after use it stays as "Meeting already called";
  - in a meeting every character's eyes turn to the table (`lookAt` in `Render.animateCharacter`); the server sends no facing;
  - the meeting card sits at the right side (at the bottom on a window higher than wide), and the camera shows the table in the part of the window the card leaves free (`frameMeeting` in `web/main.js`), so everyone standing around it is visible;
  - the card's background is much lighter than before (30 % instead of 55 %).
- **After the meeting** everyone walks on from their place at the table.

### 3. Clear walls, clear glass
- **Server (`sight_grid`, `SIGHT_DECOR`):** a wall tile blocks sight unless it is glass or sea. `SIGHT_DECOR` = `roof`, `greenroof`, `solar`, `screen`. Furniture stands on floor tiles and never blocks sight (before, shelves did).
- **Opaque walls (`web/render.js`):**
  - every tile that blocks sight is one flat block in one colour, with a dark line exactly where the wall ends and a lighter line just inside it. `drawMap` takes the server's sight grid for this;
  - the ground outside the campus is such a tile too, so it has the same colour as the walls (before, it was darker than a wall);
  - the glass facade with columns that every wall showed towards the floor is removed;
  - the lit area ends at the wall's face: the "one tile deep" light of spec 010 is removed;
  - the darkness leaves wall tiles out (`wallRects`), so a wall looks the same in light and in darkness and never darkens the cap or name of a character below it;
  - roofs keep a faint mark on the flat top (solar panels, green roof), screens their display.
- **Glass panes (`drawGlassPane`):**
  - a thin light blue line with a white highlight along the middle of the tile, with a slim post where the pane ends;
  - the grounds of both sides meet under it (for example lawn above, hall floor below);
  - glass does not block sight, so the light goes through and the room behind is lit within the vision radius.

### 4. Map review
Every change to `server/campus.json`, with its reason:

| Change | Reason |
|---|---|
| 93 furniture tiles `#` → `.` | Section 1: furniture no longer blocks. |
| `bell` [21, 22] → `meeting_point` [24, 21] | Section 2. The middle of the spine is where all routes cross. |
| Wall → floor on (26, 19), (26, 20), (26, 23) | Room for the meeting circle: it needs 5 × 5 free tiles (x 22–26, y 19–23). The spine wall towards the Library is one tile thick there; the Library door is (27, 21–22). |
| Glass → floor on (22, 21) | Same. The south glass pane of the Student Hall is x 13–21 now. |
| Beanbag on (23, 20) removed | It lay under the meeting table. |
| Screen of the Main Entrance from (28, 2–5) to the wall on (30, 5–6); (28, 2–5) became floor | A wall of its own in a room: it stood in front of the door to Student Services and left a corridor of one tile behind it. |
| Doorway (5, 13) widened to (5–6, 13) | Lecture hall B to the north Courtyard: one tile was too narrow. |
| Doorway (15, 12–13) widened to (14–15, 12–13) | Hall B to the north Courtyard. |
| Doorway (20, 12–13) widened to (19–20, 12–13) | Hall B to the north Courtyard. |
| Doorway (5, 25) widened to (5–6, 25) | South Courtyard to lecture hall D. |
| Doorway (20, 25–26) widened to (19–20, 25–26) | South Courtyard to Hall D. |
| Passage (18, 30–33) widened to (17–18, 30–33) | Hall D to Hall E: a corridor of one tile, four tiles long. |
| Green roofs shortened: row 12 x 8–14 → 8–13 and x 16–19 → 16–18; row 25 x 6–19 → 7–18; row 30 x 8–17 → 8–16. Roof (17, 32–33) removed | They follow the widened doorways. |

In numbers: 113 tiles changed, all from `#` to `.` (93 under furniture, 4 for the meeting circle, 4 under the old screen, 12 for doorways). The areas, spawns, tasks, staff doors, light switch and labels are unchanged.

Checked and left as it is:
- no wall tile stands alone;
- both glass panes run along the Student Hall, each with floor on both sides; no glass in a room;
- no wall cuts through a corridor;
- the beach stays a path of one tile; its openings to the Courtyards stay one tile (the slide makes them easy to enter);
- no task place, spawn, staff door or the light switch moved: all are reachable.

## Out of scope
New rooms or areas, new mechanics, sound, changes to tasks or roles.

## Done when
- **Tests for `server/game.py`,** written first, in the new file `tests/test_spec011.py` (147 tests):
  - Section 1 (55 tests): furniture is floor decor; every piece of furniture on the campus stands on floor; walking across a table, a tree, a café table and a desk; walls, glass, the sea, roofs and screens still block; a diagonal walk slides along a wall and through a doorway; a straight walk up to 10 px off slips through a doorway, 11 px off stops; the slide is never faster than walking and never enters a wall; every gap of one tile on the campus is passed in both directions from up to 16 px off; `welcome` carries `corner_slide`. 37 failed before the change; the other 18 describe what was already true (walls block, diagonal sliding).
  - Section 2 (45 tests): the meeting point and no bell; calling at the table, at exactly the reach, by an examiner; rejected far away, one pixel beyond, by a ghost, a second time, in the lobby, during a meeting, after the end, each leaving everything unchanged; the report still works anywhere; 4 to 10 players stand evenly on the circle on free floor without overlapping; a tight map; a map without a meeting point; the WebSocket messages. All 45 failed before the change.
  - Section 3 (31 tests): glass does not block sight but blocks walking; a plain wall, roofs and screens block both; furniture never blocks sight; on the campus players see each other through both glass panes and over the bookshelf, and walls hide them. Only the test that reads `render.js` failed before: the server's split was already there since spec 010, and section 1 had moved the furniture.
  - Section 4 (16 tests): every spawn, task place, staff door, the light switch, the meeting point and every floor tile can be reached from the first spawn; no wall tile stands alone; every glass pane is thin with floor on both sides; the doorways between the parts of the campus are at least two tiles wide; the way into Student Services is a straight walk; screens hang on walls. 8 failed before the map review.
- **Existing tests** changed only where a rule changed, each with its reason in a comment:
  - furniture: `tests/test_campus.py` (the lists of solid and floor kinds; a roof instead of a tree as the solid kind on a floor tile, plus furniture on a wall tile) and `tests/test_spec010.py` (the two lists of kinds; glass instead of a table in three tests; the bookshelf no longer hides anyone; the Gym roof instead of the standing screen);
  - bell → meeting point: `game.bell` → `game.call_meeting`, `"bell"` → `"meeting"` / `"button"`, `bell_used` → `meeting_used`, `bell_range` → `meeting_range`, the map key and the three reasons, in `tests/test_spec008.py`, `tests/test_meeting.py`, `tests/test_tasks.py`, `tests/test_spec010.py` and `tests/test_campus.py`. In `tests/test_spec008.py` the range tests measure from the table's edge, and the meeting point lies in the spine instead of a Courtyard. Most helper and test names kept their old names;
  - meeting positions: the Auditorium seat tests in `tests/test_campus.py`, `tests/test_meeting.py` (two) and `tests/test_spec008.py` (one) now check the circle around the table; the seating order of a tiny Auditorium has no rule left and became "an Auditorium without a meeting point moves nobody".
- `uv run pytest` passes: 786 tests.
- **Check in a running game** (4 browser tabs on one laptop):
  - walked the spine from the Main Entrance to the meeting point, through the Student Hall over its study tables up to its glass pane, and across the Main Entrance up to the door of Student Services, without getting stuck (the walk through that door is covered by a test, not by this check);
  - called a meeting at the table with 4 players: everyone stands around it, looks at it, and stays visible next to the card on a wide window (1280 × 800) and an upright one (800 × 962);
  - walls are flat blocks with an edge line and look the same in light and in darkness; no light inside them;
  - from the Student Hall both Courtyards are lit through the glass; the posts at the ends of the panes cast straight shadows;
  - the darkness still covers everything outside the lit area at 1280 × 800, 390 × 844 and 844 × 390;
  - the browser's prediction gave exactly the server's positions for 22,893 walks of 25 ticks each (every floor tile, eight directions, up to 16 px off the middle).
- **Tick time with 10 players** all walking, including the 10 snapshots as JSON: 1.1 ms on average, 2.9 ms at worst (a tick may take 50 ms).
- **Still to check by hand:** a real phone, a full round with 10 players (the circle of 10 was only tested on the server), the ghost view, lights out with the new walls, the result screen of a vote, slipping into a doorway by hand, and free walking through the Courtyards, the Food Court and the Library.

## Changes during implementation
- **The map changed for the meeting circle.** No place in the middle of the map had 5 × 5 free tiles. Three wall tiles and one glass tile at the spine became floor (see section 4).
- **Shelves are furniture too.** The first version said "shelves in the middle of rooms". Both shelves of the campus are walked over, the shop's shelf along its wall included, so one rule covers all furniture. They no longer block sight.
- **Screens count as walls.** The first version did not name them. They block walking and sight, as in spec 010, and now always hang on a wall.
- **The collision box stayed.** A smaller box was allowed but not needed: the slide solved doorways, and no existing movement test had to change.
- **The message and field names changed** with the bell (`meeting`, `meeting_used`, `button`), so no "bell" is left in the server, the map or the browser.
- **Doorways of one tile were widened to two** between halls, lecture halls and Courtyards. Not in the first version's list of examples, but "doorways that are too narrow".
- **The meeting card moved** to the side or the bottom, and the camera frames the table. Otherwise the card would cover the circle.
- **Walls are left out of the darkness** instead of being drawn twice. This is how "the same in light and in darkness" was built.

## Limits
- **Glass blocks its whole tile.** The pane is drawn thin, but a player stops 16 px before the line on either side.
- **The slide helps straight walks only,** up to 10 px. A diagonal walk slides along walls as before, at the speed of one axis.
- **Characters walk over everything on the floor,** trees and counters included. Furniture is never drawn above a character.
- **The meeting table is no obstacle.** Players can stand on it and on its button.
- **The circle touches two pieces of furniture.** With 7, 8 or 9 players one place overlaps the tile of the study table on (22, 19) by up to 12 px, and with 8 players one overlaps the wooden table on (22, 23) by 7 px. The character then stands on the table's edge.
- **Facing the table is drawing only.** The server stores no facing; the browser turns the eyes.
- **Walls show in the dark.** Because walls are not darkened, the layout of the whole campus is visible in the dark (it was faintly visible before, too). Players and failed exams are still only sent by the server when in sight.
- **Roofs differ a little.** Solar and green roofs keep a faint mark on top, so not every wall tile is exactly the same picture.
- **A tight map breaks the circle.** A player whose place is in a wall stays where they are. The campus has room for all 10.
- **On an upright phone the meeting card takes up to 60 % of the height;** with many players its list scrolls.
- **`docs/brd.md` still says "bell" and "Auditorium"** in the user journey and EX07. The requirements document was not changed by this spec.
- **No automatic browser tests.** Everything in `web/` was checked in a running game; four tests read the files (the slide, the meeting button, no bell left, walls and glass).
