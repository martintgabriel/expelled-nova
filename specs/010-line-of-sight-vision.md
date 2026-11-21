# Spec 010 — Line-of-sight vision like Among Us

This spec describes what was built. Where the result differs from the first version of the spec, "Changes during implementation" says how and why.

## Why
Vision is the heart of a social-deduction game, and ours looked and felt wrong:
- the darkness ended left and right of the vision circle on wide windows, so the rest of the map was visible;
- shadows were tile-shaped blocks instead of straight shadow edges cast by walls;
- tables, plants and the sea blocked sight like walls.

This spec makes vision behave like in Among Us. The server stays the authority on what each player may see (spec 005, spec 008 part 7). Builds on specs 001–009.

## What (built and committed in this order)

### Part 1 — Darkness covers the whole screen (bug)
- **Requirement:** at any window size, aspect ratio and zoom, and on phones in portrait and landscape, nothing outside the vision area is shown brighter than the darkness. This also holds while the lights are out and while the darkness fades in or out.
- **Cause (confirmed by measuring a running game):** the darkness had two layers of different reach.
  - The fog picture (`makeFog`) was big enough: 2752 × 2752 px, more than the whole map.
  - The tile shadows (`drawShadows`) only reached 7 tiles around the player: a square of 480 px.
  - A hidden tile inside the square got both layers, a tile outside it only the fog. The map outside was 2.4 times brighter (pixel value 42 instead of 17).
  - The square is exactly as tall as the short side of the view, so its edge showed left and right on wide windows, and above and below on a portrait phone.
- **Built (`web/render.js`: `makeDarkness`, `updateDarkness`):** the darkness is one layer of one strength (86 %, so the map stays faintly visible). It has two parts that never overlap:
  - a dark sheet over the whole map with the lit area cut out of it. The camera never shows more than the map, so the sheet covers every window size;
  - one round picture, clear in the middle and as dark as the sheet from the vision radius on. It follows the own character and is drawn only inside the lit area, so it gives the vision circle its soft rim.
- **Lights out:** the same picture is stretched to the radius the server sends. The shown radius glides to it, so the circle shrinks and grows smoothly.
- **Fade:** both parts fade in and out together (start, end, becoming a ghost).
- **Unchanged:** the marks of the own tasks, the task ring and the light-switch mark are drawn above the darkness, so they still show in the dark.

### Part 2 — Only walls block sight
- Tiles that block **sight** are separate from tiles that block **walking**:
  - **block sight and walking:** plain wall tiles, roofs (`roof`, `greenroof`, `solar`), tall shelves (`shelf`, `shopshelf`) and screens (`screen`);
  - **block walking only:** all other solid decor: `sea`, `glasswall`, `counter`, `foodcounter`, `desk`, `studytable`, `table`, `cafetable`, `woodtable`, `piano`, `steps`, `picnic`, `tree`.
- **One list:** `SIGHT_DECOR` in `server/game.py`, next to `SOLID_DECOR`.
- **One grid, worked out once:** `sight_grid(campus)` returns a second grid in the form of the map's grid: `#` blocks sight, `.` does not. The game keeps it as `Game.sight`. Walking still uses the map's own grid.
- **Browser:** the `welcome` message carries the grid as `sight_grid`, so both sides use the same rule. The map itself is sent unchanged.
- **Details:**
  - a wall tile that carries both low and tall decor blocks sight (the campus has no such tile);
  - floor decor painted around a wall tile does not open it;
  - on a map without decor every wall blocks sight.
- **On the campus:** 160 wall tiles no longer block sight. Players see each other across the Student Hall's glass walls, the trees, the desks and the welcome desk. The Auditorium screen stays closed: it is part of the Auditorium's front wall.

### Part 3 — Smooth line of sight
- **Server (`server/game.py`):**
  - A target (player or failed exam) is visible if its centre is within the vision radius, measured between the two centres, and one straight line from the viewer's centre is clear: to the target's centre or to one of the four corners of its 20 px square.
  - A corner inside the radius does not make a target visible whose centre is outside it.
  - `Game.sight_clear(x0, y0, x1, y1)` decides whether a line is clear. It cuts the line at every grid line it crosses; each piece then lies in one tile, and the middle of the piece tells which. A piece in a sight-blocking tile blocks the line.
  - A line that only touches the corner of a tile is not blocked. A line along the face of a wall is not blocked either. A line along the joint between two wall tiles is blocked.
  - Ghosts, the meeting phase, the lobby and the end screen are unchanged: they see everything.
  - Lights-out still shrinks the radius for students only.
  - The tile-to-tile rule of spec 008 part 7 (`line_between`, `_visible_tiles` and its kept results) is removed.
- **Browser (`web/render.js`):**
  - **Edges, once per map (`sightEdges`):** every side on which a sight-blocking tile meets a tile that does not block is an edge. Sides that continue each other are merged into one long edge (152 edges on the campus).
  - **Rays (`castRays`):** from the own character to both ends of every nearby edge, with one more ray just left and just right of each end, plus 48 evenly spread rays that keep the area round where no wall is near. A ray ends at the nearest edge it hits, or at 1.1 times the radius, where the rim is fully dark already.
  - **Lit area (`drawLitArea`):** the ray ends, in order around the circle, form the visibility polygon. It has straight shadow edges where a ray passes a wall corner. No tile-shaped blocks remain.
  - **Walls:** a wall the light falls on is itself lit one tile deep, along exactly the stretch the light reaches.
  - **When:** the lit area is only worked out again when the own character has moved or the shown radius has changed (about 0.24 ms each time on a laptop).
  - It replaces the tile shadows (`drawShadows`) and the fixed-size fog (`makeFog`). The browser's copy of the tile rule (`lineBetween`, `visibleTiles` in `web/main.js`) is removed.
  - Outside the lit area the map stays faintly visible for orientation.

## Out of scope
Changes to the map layout, movement, tasks, meetings or any other mechanic; sound.

## Done when
- **Tests for `server/game.py`,** written first and failing before the change. All are in the new file `tests/test_spec010.py` (86 tests):
  - a table, a tree and the sea between two players do not block sight (and no other low decor kind does); a wall, a roof, a shelf and a screen do;
  - every solid decor kind still blocks walking;
  - `welcome` carries the server's sight grid; a `sight_grid` sent by a browser is ignored;
  - a line that only touches a wall corner is not blocked; a line a hundredth of a pixel inside it is;
  - a player or failed exam whose centre is hidden but one of whose corners is visible is sent; one with centre and all corners hidden is not;
  - exactly at the radius is visible, one pixel beyond is not;
  - a ghost, and everyone during a meeting, in the lobby and after the end, still sees everything;
  - lights out: a student's radius shrinks, an examiner's does not.
  - Before the change, 24 of the 58 tests of part 2 and 20 of the 28 tests of part 3 failed. The others describe what was already true (walls hide, furniture blocks walking, the radius, ghosts, meetings, lights out).
- **Existing tests** changed only where the rule changed, all in `tests/test_spec008.py`, each with its reason in a comment:
  - `test_a_hidden_player_appears_when_the_viewer_walks_past_the_end_of_the_wall`: the viewer starts one tile higher, because a visible corner is now enough to be seen;
  - `test_vision_between_tiles_is_the_same_in_both_directions_everywhere_on_the_campus`: removed, there are no sets of visible tiles any more. Its successor in `tests/test_spec010.py` checks that centre lines are the same in both directions;
  - `test_the_visible_tiles_of_a_tile_are_worked_out_only_once`: removed, nothing is kept per tile any more;
  - no existing test depended on furniture blocking sight.
- `uv run pytest` passes: 665 tests.
- **Tick time with 10 players** (one tick including the 10 snapshots as JSON, measured several times on a laptop; a tick may take 50 ms):
  - before part 3: 0.6–0.7 ms on average;
  - after part 3: 0.5–0.8 ms on average with everyone in sight of each other, 0.4–0.6 ms with the players spread over the campus; no single tick above 4 ms;
  - the difference is within what the measurement varies from run to run.
- **Check in a running game.** Done by comparing pixels with and without the darkness:
  - window sizes 2560×1080, 1280×800, 600×900, 390×844 and 844×390: nothing outside the vision circle is brighter than the darkness, also half-way through the fade, with the lights out and while the circle shrinks;
  - at corridor corners the shadows have straight edges; the piano, the tables and the trees cast none;
  - the lit floor matched the server's rule at all 1,434 sampled points around a corridor corner, so a player appears when the lit area reaches one of their corners.
- **Still to check by hand:** the ghost view, a real phone, and the fade at the real start and end of a round (the fade above was set by hand).

## Changes during implementation
- **The cause in part 1 was a different one.** The first version blamed the fixed size of the fog picture. The picture was big enough; the edge came from the tile-shadow layer (see part 1).
- **Screens block sight.** The first version listed them as walking-only. The Auditorium screen fills 6 of the 8 wall tiles of the Auditorium's front wall, so players on the plaza would have seen into the Auditorium through a wall.
- **The browser receives the grid, not the list.** The server sends which tiles block sight (`sight_grid`) instead of the list of decor kinds, so the browser does not have to repeat the rule.
- **Walls are lit one tile deep.** Not in the first version. Without it, a wall above the own character darkened its cap and name.
- **Hidden tiles near the player are darker than before.** They now have the same darkness as everything outside the circle (before, they were a little brighter).
- **The radius glides** when the lights go out and come back, instead of two pictures cross-fading.

## Limits
- **Seeing is not always mutual.** A player whose corner sticks out past a wall is seen by someone whose own square is fully hidden from them.
- **Five points per target.** The server checks the centre and the four corners, not the whole square. A player standing in a sliver of light narrower than their body, with none of the five points in it, is not sent although the floor around them is lit.
- **Predicted position.** The lit area is drawn from the predicted position of the own character, which can be a few pixels ahead of the position the server uses.
- **Hard shadow edges.** The edges are sharp, not blurred.
- **WebGL.** Cutting the lit area out of the darkness uses an inverted mask, which needs WebGL (the game already runs on it). Without WebGL the darkness would be drawn wrongly.
- **No automatic browser tests.** Everything in `web/` was checked in a running game only; two tests read the files to make sure the old code is gone and the browser uses the server's grid.
- **Unused field.** `welcome` still carries `lights_out_radius`. The browser no longer needs it, because every snapshot carries the radius in use.
