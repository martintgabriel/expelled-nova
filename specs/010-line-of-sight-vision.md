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
- **Cause (confirmed by measuring a running game):** not the size of the fog picture, which covered the whole map. The darkness had two layers: the fog, and tile shadows (`drawShadows`) that only reached 7 tiles around the player. Inside that 480 px square a hidden tile got both layers, outside it only the fog, so the map there was 2.4 times brighter. The square is as tall as the short side of the view, so its edge showed left and right on wide windows.
- **Built:** the darkness is one layer of one strength. A dark sheet covers the whole map with the lit area cut out of it; one round picture with the soft rim is drawn only inside the lit area. The camera never shows more than the map, so this holds at every window size. The radius glides when the lights go out and come back.

### Part 2 — Only walls block sight
- Tiles that block **sight** are separate from tiles that block **walking**:
  - **block sight and walking:** plain wall tiles, roofs (`roof`, `greenroof`, `solar`), tall shelves (`shelf`, `shopshelf`) and screens (`screen`; the Auditorium screen is part of its front wall);
  - **block walking only:** all other solid decor (tables, counters, desks, trees, sea, steps, piano, picnic tables, glass walls).
- The list lives in one place in `server/game.py`, next to `SOLID_DECOR` (`SIGHT_DECOR`). From it the server works out once which tiles block sight (`sight_grid()`: a second grid in the form of the map's grid, `#` blocks sight). The browser receives that grid as `sight_grid` in `welcome`, so both sides use the same rule. The map itself is sent unchanged.
- A tile that carries both low and tall decor blocks sight.

### Part 3 — Smooth line of sight
- **Server:**
  - A target (player or failed exam) is visible if it is within the vision radius and an unbroken straight line exists from the viewer's centre to the target's centre or to one of the corners of the target's square, without crossing a sight-blocking tile.
  - A line that only touches the corner of a tile is not blocked. A line along the face of a wall is not blocked either; a line along the joint between two wall tiles is.
  - The radius is measured between the two centres, as before. A corner inside the radius does not make a target visible whose centre is outside it.
  - Built as `Game.sight_clear()`: the line is cut at every grid line it crosses, and the middle of each piece tells which tile the piece lies in.
  - Ghosts, the meeting phase, the lobby and the end screen are unchanged: they see everything.
  - Lights-out still shrinks the radius for students.
  - Keep it fast enough for Render Free: report how long one server tick takes with 10 players, before and after this part.
- **Browser:**
  - The lit area is a visibility polygon: rays from the own character to the corners of nearby sight-blocking edges give straight shadow edges, clipped to the vision circle with a soft rim. Each corner gets three rays (straight at it, just left and just right of it); 48 evenly spread rays keep the area round where no wall is near.
  - A wall the light falls on is itself lit one tile deep, so walls show their face and do not cut into the own character's head.
  - No tile-shaped blocks remain.
  - Adjacent wall tiles are merged into longer edges once, when the map loads.
  - The polygon is only recomputed when the own character moves or the shown radius changes.
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
  - No existing test depended on furniture blocking sight. Three tests in `tests/test_spec008.py` changed because vision no longer goes from tile to tile: one starts its viewer a tile higher (a visible corner is now enough), and the two tests of the per-tile sets of visible tiles were removed (one has a successor in `tests/test_spec010.py`).
- `uv run pytest` passes; the output is pasted.
- The tick time with 10 players is reported before and after part 3.
  - Measured on a laptop, one tick including the 10 snapshots as JSON: before 0.69 ms (all in sight) and 0.58 ms (spread over the campus); after 0.55 ms and 0.37 ms. A tick may take 50 ms.
- **Manual check:**
  - window sizes 1280×800, 2560×1080 (ultra-wide) and 600 px wide, plus a phone in portrait and landscape: nothing of the map is brighter outside the darkness;
  - at corridor corners the shadows have straight edges;
  - tables, plants and the sea cast no shadow;
  - a player behind a wall appears exactly when the lit area reaches them;
  - lights out, the ghost view and the fade at start and end show no gaps.
- At the end, this spec is updated so it describes exactly what was built, including its limits.

## Limits of what was built
- **Seeing is not always mutual.** A player whose corner sticks out past a wall is seen by someone whose own square is fully hidden from them.
- **A light sliver narrower than a player.** A player standing in it with neither centre nor a corner in the light is not sent, although the floor around them is lit.
- **The lit area is drawn from the predicted position** of the own character, which can be a few pixels ahead of the position the server uses.
- **The server checks five points per target** (centre and four corners), not the whole square.
- **Shadow edges are hard**, not blurred, and the inverted mask that cuts the lit area out of the darkness needs WebGL (the game already runs on it).
- **Not tested automatically:** everything in the browser. It was checked in a running game by comparing pixels: nothing outside the vision circle brighter than the darkness at 2560×1080, 1280×800, 600×900, 390×844 and 844×390, during the fade and with the lights out; and the lit floor matched the server's rule at every sampled point.
