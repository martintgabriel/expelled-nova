# Spec 005 — Look: own characters, colours, current area and vision radius

## Why
The game works, but it still looks like a test: every other player is the same blue dot, the whole map is always visible and nothing tells you where you are. For the demo, players must recognise each other at a glance, and the tension of the game needs limited vision: you only know what happens near you. Covers the "vision is limited to a radius" part of BRD EX02 and "name, characters and graphics are our own" (First release, Scope boundaries). Builds on specs 001–003 (movement, `snapshot_for`, ghosts, failed exams).

Limited vision is a rule, not decoration, so the server enforces it (AGENTS.md: "The server sends each player only what that player may know"). A browser that only darkened the screen would still receive every position, and a changed client could show them.

## What
- **Colours (server):** at join, each player gets a colour number 0–9: the lowest number that nobody in the game has. With at most 10 players, no two players share a colour. The player keeps it until they leave (through start, expel, end and a new round); a player who leaves frees their number. A browser cannot choose or change it.
- **Colours in the snapshot:** every snapshot has `colors`, a map from player id to colour number, for exactly the players listed in `players`. A player entry itself stays `{id, name, x, y}`. The actual palette (which number is which colour) is drawing and lives in `web/render.js`.
- **Vision radius (server):** `VISION_TILES = 6`, so the radius is 6 tiles (192 px on the campus map), measured between centres. Exactly at the radius still counts as visible. While the phase is `playing`, a living player's snapshot contains only:
  - the player themself (always);
  - the other living players within the radius;
  - the failed exams within the radius.

  Everything else in the snapshot is unchanged. Not affected: a ghost still sees everyone and every failed exam; in `lobby` and `ended` everyone sees everyone. An examiner still gets the ids of the fellow examiners, but their positions only when they are in sight. This narrows one line of spec 003 ("Failed exams are visible to everyone") to "everyone within vision".
- **Vision is a plain circle:** walls do not block it (accepted limit, see Out of scope). The `welcome` message carries `vision_radius` in pixels, so the browser darkens at exactly the distance the server uses.
- **Current area (server):** `Game.area_at(x, y)` returns the name of the campus area whose rectangle contains the point, or nothing in a corridor. Every snapshot has `area`: the area of the player's own position.
- **Browser, new file `web/render.js`:** all drawing code lives here: the map, the characters, the failed exams and the darkness. `web/main.js` keeps the connection, the panels, the keyboard input and the movement prediction, and calls `render.js`. It is a plain script loaded between Phaser and `main.js` (no build step). Drawing code that other specs add later also goes into `render.js`.
  - **Characters:** our own round figure, drawn from simple shapes in the player's colour: round body, two eyes that look in the walking direction, two small feet that step while walking, a graduation cap, a soft shadow. Ten colours that are easy to tell apart. Examiners look exactly like students. Ghosts stay half-transparent, float and have no feet.
  - **Nickname** above each character; the own nickname is highlighted so you find yourself quickly.
  - **Current area** at the top of the screen (in the HUD), from the snapshot's `area`; "Corridor" when the server sends none.
  - **Darkness:** while playing and alive, everything outside the vision radius is darkened with a soft edge; the map stays faintly visible for orientation. No darkness in the lobby, after the end or for ghosts.
  - **Camera:** zooms so the vision circle fills most of the window, and draws at the screen's pixel density (at most 2), so shapes and text stay sharp on phones and laptops.
  - **Map:** drawn from the same server data as before (`campus.json` is not changed), just cleaner: floor tiles, walls with a front face and a shadow, area names.
  - **Lobby and end screen:** a dot in the player's colour next to each name.
  - **Player count:** the HUD shows "Players: n/10" only in the lobby, because a living player no longer receives everyone while playing. For the same reason the browser remembers nicknames by id (for the fellow examiner's name in the role badge).
- **All self-drawn:** shapes and text only. No image, font or sound file is added; nothing is downloaded; no dependency is added.

## Out of scope
The real campus map (its own spec; `server/campus.json` stays as it is), staff doors, vision blocked by walls (line of sight), choosing your own colour, sound, animations beyond walking and floating, task places (spec 004), meeting and voting screens (spec 006), phone controls (spec 007). Existing rules (movement, roles, expel, win, restart) do not change.

## Done when
- Tests in a new file `tests/test_look.py`, written first and red before the implementation.
  - Accepted:
    - the first players get the colours 0, 1, 2, …; ten players get ten different colours;
    - `colors` in a snapshot lists exactly the players in `players`; player entries are still exactly `{id, name, x, y}`;
    - while playing, a living player sees a living player 5 tiles away, and a failed exam within the radius;
    - `area_at` returns the area's name inside an area; the snapshot's `area` follows the player's own position; on the campus map every spawn point is in "Main Entrance".
  - Rejected (nothing changes):
    - a browser cannot pick a colour: a `color` field in the join message is ignored;
    - a browser cannot widen its vision: extra fields in an input message change nothing in what it receives;
    - a rejected join (invalid or duplicate nickname, full game, game already running) uses up no colour and changes nobody's colour;
    - while playing, a living player's snapshot does not contain a player or a failed exam outside the radius, neither in `players` nor in `colors`.
  - Edge cases:
    - exactly at the radius: visible; one pixel further: not; the radius is a circle (5 tiles right and 5 tiles down is outside);
    - a player always sees themself, also when alone in sight;
    - a hidden player appears when one walks towards them (`step()`);
    - a ghost sees everyone and every failed exam; in `lobby` and `ended` everyone sees everyone at any distance;
    - a fellow examiner out of sight is listed in `fellow_examiners` but not in `players`;
    - a player who leaves frees their colour for the next player; everyone else keeps theirs; colours survive start, expel, end and a new round;
    - `area_at` on the first and last tile of an area, one tile outside, and in a corridor (nothing);
    - `vision_radius` is `VISION_TILES` × tile size (192 on the campus map).
- WebSocket tests (same file): two clients receive the same `colors` and `vision_radius` in `welcome`; in a started game, a player placed far away disappears from a living player's state but still sees themself.
- Static tests (same file): `render.js` is served and loaded between Phaser and `main.js`; `web/` contains no image files.
- `uv run pytest` passes; the output is pasted. Existing tests still pass unchanged.
- Manual check with 4 browser windows locally:
  - every window shows a different colour for each player, the same colour in all windows, with the nickname above;
  - the area name at the top changes when walking from the Main Entrance through a corridor into another area;
  - after the start, the map is dark outside a circle of about 6 tiles; a player who walks away disappears at its edge and reappears when coming back;
  - an expelled player sees the whole map and everyone again;
  - shapes and text look sharp on a phone-sized window and a laptop window.
