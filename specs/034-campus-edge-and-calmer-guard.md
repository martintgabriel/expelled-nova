# Spec 034 — Campus edge and a calmer Segway guard

## Why
Two playtest findings.

1. **The own character leaves the middle of the screen at the edge of the map.** The
   camera is bounded to the map (`camera.setBounds(0, 0, width, height)` in
   `CampusScene.create()`), so near the edge it stops following and the character walks
   towards the edge of the window. On the beach and along the west side the character
   even ends up behind the to-do list. Every other part of the game assumes the character
   sits in the middle (vision circle, edge arrows, joystick reach), so the camera should
   always follow it. Beyond the map there is then something to see: more sea next to the
   beach, a green meadow around the rest of the campus, as if the campus stood in the
   landscape, with the outer border drawn as a thin campus wall instead of a thick block.
2. **The Segway guard looks buggy.** He drives at `GUARD_SPEED = 1.6 * SPEED` (256 px/s)
   and is only sent while he is inside the player's own sight (spec 027), so he crosses
   the vision circle in about a second and pops in and out. The client may also make this
   worse: `updateGuard()` interpolates about 100 ms in the past, but `syncGuard()` creates
   and destroys the sprite from the latest snapshot, and `updateGuard()` falls back to
   `latestState.guard` when the interpolated snapshot has no guard. That mixes two points
   in time and can make him jump forwards and then back when he comes into sight.

Builds on specs 001–033, in particular spec 005/010/011 (camera zoom, darkness, line of
sight), spec 009/026 (the campus drawing), spec 015 (the beach and sea) and spec 027
(the guard).

## What

### Part A: the camera always follows, the campus has surroundings
- **Camera:** the own character stays in the middle of the screen everywhere, also at the
  map's edge. The camera is no longer bounded to the map (or is bounded to the map plus
  the surroundings below, whichever is simpler and keeps the meeting view of spec 018/029
  working). `Render.cameraZoom()` keeps its rule that the window never shows more than one
  map's width or height, so the surroundings never need to be larger than half the map on
  each side.
- **Surroundings, drawn once in `render.js`:** a band around the map, wide enough that the
  window never shows the empty backdrop at any window size or zoom:
  - **sea** next to the sea and beach side of the campus (where the map's own edge tiles
    are `sea` decor), with the same look as the existing sea, so the sea simply continues;
  - **a green meadow** everywhere else, with a few trees from the existing tree drawing,
    so it reads as the land around the university. No new decor kinds in the map data.
- **A thin campus wall instead of a thick block:** where the grid's outer border is a
  thick block of `#` only because the grid needs an edge (blocked tiles connected to the
  map edge that are not part of a building: no `roof`, `greenroof`, `glassroof`, `solar`
  or other building decor on them), those tiles are drawn as meadow or sea too, with a
  thin wall line where they meet walkable floor. Buildings that stand at the edge keep
  their look. Whether a tile is drawn this way is decided in `render.js` from the grid and
  decor only.
- **Collision and sight do not change:** `server/campus.json`'s grid and the server's
  `blocked`/`sight_clear` stay exactly as they are. The meadow and sea outside are only
  looks; nobody can walk there, exactly as before.
- **Darkness covers the surroundings:** the dark sheet of `makeDarkness()` grows to the
  map plus the surroundings, so the land outside is as dark as anything else out of sight
  ("the camera never shows more than the map" in its comment is no longer true and is
  updated). The lit area is unchanged (rays still stop at the map), so outside the map is
  always under the fog, also looking out over the sea.
- **Nothing else moves:** the campus map overlay (spec 018/026) is unchanged, edge arrows
  (spec 015) still point at task places inside the map, the meeting view still centres
  the meeting table.

### Part B: a calmer guard
- **Slower:** `GUARD_SPEED = 1.2 * SPEED` (192 px/s) instead of `1.6 * SPEED`. He stays
  faster than any player, which spec 027 needs ("nobody can simply outrun or escort him").
  The pause chance, pause length, cone and vision radius stay as they are.
- **No jumping when he comes into sight:** the guard is drawn from the interpolated
  snapshots only, at the same point in time as every other player. If the interpolated
  snapshots do not have him yet, he is not drawn yet; `latestState.guard` is not mixed in.
  His sprite is created when he first appears in the interpolated view and removed when he
  is gone from it, so he never jumps forwards and back.
- **Fading instead of popping:** when he comes into sight he fades in over about 150 ms;
  when he leaves it he fades out over about 150 ms at the last position the player was
  sent. The fade-out shows nothing the player was not already sent, so it reveals nothing.
- Fix the root cause found in the code. If the check in step 1 shows that the jump has
  a different cause than the one described in "Why", fix that cause and write down why.

## Out of scope
Changing the grid, collision or sight; making the surroundings walkable; new map areas;
changing the guard's route, waypoints, cone, pause rules or the catch rule of spec 027;
sound for the guard; zoom or other camera changes.

## Done when
- **Tests first (AGENTS.md):** `tests/test_spec034.py`, written and shown to fail before
  the implementation, in the style of the earlier spec tests:
  - `GUARD_SPEED` is `1.2 * SPEED`, and still greater than `SPEED`;
  - all guard tests of spec 027 still pass unchanged (route, catch, start distance);
  - `main.js` no longer bounds the camera to the map alone, and the own character is
    followed everywhere;
  - `render.js` draws the surroundings (sea and meadow) once, from the grid and decor
    only, and the dark sheet covers map plus surroundings;
  - the guard is drawn only from interpolated snapshots (no `latestState.guard` in
    `updateGuard()`), with a fade in and out;
  - no server change other than `GUARD_SPEED`; `server/campus.json` is unchanged;
  - all earlier tests still pass (`uv run pytest`, output pasted into this spec).
- **A manual check list** (two browser tabs, one at phone width with touch emulation):
  - walking along every edge of the campus (north, east, south, the beach in the west),
    the own character stays in the middle of the screen, never behind the to-do list;
  - beyond the edge there is sea next to the beach and meadow everywhere else, never the
    empty dark backdrop, at laptop and phone width, also while zoomed in or out by
    resizing the window;
  - the outer border looks like a thin wall where it is not a building;
  - nobody can walk onto the meadow or into the sea, exactly as before;
  - out of sight, the surroundings are dark like the rest; the campus map overlay looks
    the same as before;
  - the guard drives visibly slower, comes into sight with a short fade and no jump, and
    leaves it with a short fade; a caught expel still works as in spec 027.

## Changes during implementation
- **Which border tiles count as "not a building".** The rule in "What" (blocked, connected to
  the map edge, no building decor) also matched the walls between rooms that touch the edge
  (for example between the Spine, the Food Court and the Library, or the wall at (34, 1)):
  486 tiles, which would have turned into meadow inside the campus. Agreed with the team:
  a tile also needs **no floor tile among its 8 neighbours**. That leaves 286 tiles; every
  wall next to floor stays a wall, so the campus keeps a 1-tile wall all round (drawn with
  the usual edge line on the meadow side) instead of a thin line. `glassroof` is a floor decor
  kind and never lies on a blocked tile, so it plays no part. The rule is `outsideTiles()` in
  `web/render.js`, mirrored in `tests/test_spec034.py`.
- **The light over the sea.** The sea does not block sight, so the light from the beach ran
  out of the map (invisible before, because nothing was drawn there). Agreed: in the browser
  only, `sightEdges()` now treats outside the grid as blocking, so the light stops at the
  map's edge and everything outside stays under the fog. The server's sight is unchanged.
- **The meadow tiles inside the grid** are still walls in the sight grid, so `wallRects()` now
  leaves them out; otherwise they would never darken.
- **The guard's jump had more than one cause** (step 1, "fix the root cause"):
  1. as described in "Why": `updateGuard()` mixed `latestState.guard` (now) into snapshots drawn
     100 ms in the past, and `syncGuard()` created and removed him from the newest state;
  2. his facing was never interpolated, so the cone snapped at 20 Hz;
  3. a server bug in `server/guard.py`: when a pause ended, his target was still the waypoint
     he stood on, so the next tick counted as arriving again with `came_from` = that waypoint.
     He could then turn straight back the way he came and roll a second pause at once. The
     pause sweep also started at the phase of the global tick, so the cone could jump up to
     25 degrees the moment he stopped.

  All three are fixed. Agreed with the team, this is the one server change besides
  `GUARD_SPEED`: after a pause he leaves exactly as if he had not paused, and the sweep
  starts at the heading he arrived with. Route, waypoints, cone, pause chance and length
  and the catch rule are unchanged.
- **Drawing the surroundings cheaply.** The band is about 6,000 tiles. Instead of drawing them
  one by one (the map's Graphics object is redrawn every frame), the meadow and the sea are
  each one small picture painted once and repeated (Phaser TileSprite): one sprite for the
  meadow and one per row of sea.
- The meeting view is spec 011's `frameMeeting()` (not 018/029); it needed no change.

## Limits
- The surroundings reach half the map's size beyond each edge. That covers every window
  because `cameraZoom()` never shows more than the map; a later zoom change that shows more
  would need a wider band.
- The meadow picture repeats every 8 tiles, so its three trees form a loose pattern.
- Where the sea meets the meadow outside the map the border is straight, along the map's
  edge tiles.
- The guard still turns to his next leg within one tick on the server; the browser only
  smooths it over the 50 ms between two snapshots.
- Manual check (local, in the app's browser pane at laptop width and at phone width 375 px,
  with three idle test players so a round could start), done:
  - walking to the north, west (beach), south (Auditorium) and east edges in a round (north
    and west also in the lobby), the own character stays in the middle of the screen, never
    behind the to-do list;
  - beyond the edge: sea next to the beach, meadow with trees everywhere else, never the empty
    backdrop; the outer border is the campus wall;
  - in a round the land and sea outside are dark; at the beach the light ends in a straight
    line at the map's edge;
  - the guard drives at 9.6 px per tick (192 px/s) in the received states and is drawn with
    his cone when in sight;
  - no errors in the browser console.
- Not checked by hand: that the fade and the absence of a jump are visible to the eye (only
  the code and its tests cover them), and a caught expel live in the browser (the catch rule
  is unchanged and covered by the spec 027 tests).

## Files created or changed
- `server/game.py`: `GUARD_SPEED = 1.2 * SPEED`.
- `server/guard.py`: `step_guard()` leaves a waypoint properly after a pause (new `_depart()`),
  the sweep is counted from the pause's start (new `GuardState.paused_at`).
- `web/render.js`: `surroundSize()`, `outsideTiles()`, `drawWaves()`, `drawTree()`,
  `seaTexture()`/`meadowTexture()`/`surroundTexture()`, `drawSurroundings()` inside `drawMap()`
  (which no longer paints the backdrop and skips outside tiles as walls), `makeDarkness()`
  (bigger dark sheet), `wallRects()` (leaves outside tiles out), `sightEdges()` (outside the
  grid blocks the light), `setGuardAlpha()`.
- `web/main.js`: no `camera.setBounds`; `updateGuard()` draws only from interpolated snapshots,
  with a 150 ms fade (`GUARD_FADE_MS`) and a smooth facing (`blendAngle()`); `syncGuard()` removed.
- `tests/test_spec034.py`: new.
- `specs/034-campus-edge-and-calmer-guard.md`: these sections.

## Test output
```
$ uv run pytest -q
1340 passed, 1 warning in 60.80s (0:01:00)
```
(The warning is Starlette's existing note about `httpx`, unrelated to this spec.)
