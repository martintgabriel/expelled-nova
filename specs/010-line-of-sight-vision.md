# Spec 010 — Line-of-sight vision like Among Us

## Why
Vision is the heart of a social-deduction game, and ours still looks and feels wrong:
- the darkness ends left and right of the vision circle on wide windows, so the rest of the map is visible;
- shadows are tile-shaped blocks instead of straight shadow edges cast by walls;
- tables, plants and the sea block sight like walls.

This spec makes vision behave like in Among Us. The server stays the authority on what each player may see (spec 005, spec 008 part 7). Builds on specs 001–009.

## What (implement in this order; commit after each part)

### Part 1 — Darkness covers the whole screen (bug)
- **Requirement:** at any window size, aspect ratio and zoom, and on phones in portrait and landscape, nothing outside the vision area is shown brighter than the darkness. This also holds while the lights are out and while the darkness fades in or out.
- **Cause to confirm first:** the fog in `web/render.js` is one square picture of fixed size (`makeFog`, `FOG_TEXTURE_SIZE`) centred on the player. On wide windows the camera shows more than the square covers.

### Part 2 — Only walls block sight
- Tiles that block **sight** are separate from tiles that block **walking**:
  - **block sight and walking:** plain wall tiles, roofs (`roof`, `greenroof`, `solar`), tall shelves (`shelf`, `shopshelf`) and screens (`screen`; the Auditorium screen is part of its front wall);
  - **block walking only:** all other solid decor (tables, counters, desks, trees, sea, steps, piano, picnic tables, glass walls).
- The list lives in one place in `server/game.py`, next to `SOLID_DECOR`. The browser receives it with the map, so both sides use the same rule.

### Part 3 — Smooth line of sight
- **Server:**
  - A target (player or failed exam) is visible if it is within the vision radius and an unbroken straight line exists from the viewer's centre to the target's centre or to one of the corners of the target's square, without crossing a sight-blocking tile.
  - A line that only touches the corner of a tile is not blocked.
  - Ghosts, the meeting phase, the lobby and the end screen are unchanged: they see everything.
  - Lights-out still shrinks the radius for students.
  - Keep it fast enough for Render Free: report how long one server tick takes with 10 players, before and after this part.
- **Browser:**
  - The lit area is a visibility polygon: rays from the own character to the corners of nearby sight-blocking edges give straight shadow edges, clipped to the vision circle with a soft rim.
  - No tile-shaped blocks remain.
  - Adjacent wall tiles are merged into longer edges once, when the map loads.
  - The polygon is only recomputed when the own character moves.
  - It replaces the tile shadows (`drawShadows`) and the fixed-size fog.
  - Outside the lit area the map stays faintly visible for orientation, like today.

## Out of scope
Changes to the map layout, movement, tasks, meetings or any other mechanic; sound.

## Done when
- **Tests for `server/game.py`,** written first and failing before the change:
  - a table, a tree and the sea between two players do not block sight; a wall and a roof do;
  - a line that only touches a wall corner is not blocked;
  - a player whose centre is hidden but one of whose corners is visible is sent;
  - just inside the radius is visible, just outside is not;
  - a ghost, and everyone during a meeting, still sees everything;
  - lights out: a student's radius shrinks, an examiner's does not.
- Existing tests change only where the rule changed (furniture no longer blocks sight), with the reason stated.
- `uv run pytest` passes; the output is pasted.
- The tick time with 10 players is reported before and after part 3.
- **Manual check:**
  - window sizes 1280×800, 2560×1080 (ultra-wide) and 600 px wide, plus a phone in portrait and landscape: nothing of the map is brighter outside the darkness;
  - at corridor corners the shadows have straight edges;
  - tables, plants and the sea cast no shadow;
  - a player behind a wall appears exactly when the lit area reaches them;
  - lights out, the ghost view and the fade at start and end show no gaps.
- At the end, this spec is updated so it describes exactly what was built, including its limits.
