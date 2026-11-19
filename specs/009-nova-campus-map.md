# Spec 009: The Nova campus map

## Why
The BRD promises "a stylised Nova campus" with "about six recognisable areas". Today the map is a test level: six coloured boxes on a 40 × 26 grid that nobody in the demo audience would recognise as Nova. This spec redraws the campus with the real structure of the building in Carcavelos, straightened to fit a tile grid: the Main Entrance with Student Services at the north end, the long main corridor (the "spine") running south to the Grand Auditorium, four wings to the west (Hall B, Student Hall, Hall D, Hall E) with courtyards between them, and the Food Court, Library, Gym and EDP Plaza on the east side. The six areas keep their names, so the game rules, the meeting room and the task rooms of spec 004 keep working. Covers BRD "First release" (one campus map with about six recognisable areas) and "name, characters and graphics are our own". Builds on spec 001 (grid, walls, spawns), spec 005 (`render.js`, `area_at`, vision), spec 006 (Auditorium as meeting room), spec 004 (task places) and spec 008 (bell, staff doors and light switch positions in `campus.json`).

The layout was worked out by the team from the official Nova SBE campus tour and from looking around the campus. No map or photo from Google or Nova is used or added to the repository (BRD scope boundaries, AGENTS.md). Hall names are letters or plain words; no sponsor or company names.

## What

### 1. Layout
- **Size:** the grid grows from 40 × 26 to **42 × 43 tiles** (still 32 px per tile). The complete new `server/campus.json` is in Appendix A and replaces the old file as it is.
- **Orientation:** north is up. The real spine runs diagonally; here it runs straight from north to south.
- **Building parts** (columns `x`, rows `y`, both inclusive):

  | Part | Tiles | What it is |
  |---|---|---|
  | Main Entrance | x 16–29, y 1–6 | Welcome desk, four trees in planters, a big screen standing vertically on the right. Spawn area. Opens south onto the spine. |
  | Student Services | x 31–39, y 1–6 | Service counter. Door to the Main Entrance at x 30, y 3–4. |
  | Spine | x 23–25, y 7–37 | The main corridor. Every wing, the Food Court, the Library, both courtyards, the plaza and the Auditorium open onto it. A piano stands at its west side, between Hall B and the north courtyard. |
  | Hall B | hallway x 3–22, y 9–11; lecture hall x 3–7, y 8–12 | Long wing. Lecture hall with rows of desks at the west end. |
  | Courtyard (north) | x 3–22, y 14–16 | Lawn with trees and a row of wooden tables with chairs. |
  | Student Hall | x 13–22, y 18–20 | Short wing with glass walls on both long sides and four rows of white study tables. Open to the lawn at its west end (x 12) and to the spine at its east end. No doors to the courtyards in between. |
  | Lawn | x 3–11, y 17–21 | Joins both courtyards west of the Student Hall. |
  | Courtyard (south) | x 3–22, y 22–24 | Terrace under a white lattice pergola with beanbags, white tables and wooden tables. |
  | Hall D | hallway x 3–22, y 27–29; lecture hall x 3–7, y 26–30 | Long wing. Lecture hall at the west end. |
  | Hall E | hallway x 12–22, y 34–36 | Short wing near the sea. Open at its west end to the lawn path. |
  | Beach | x 1, y 9–35 | Sand along the west edge. Joins the west ends of Hall B, both courtyards, Hall D and the lawn path. Water to its left along the whole map edge (not walkable). |
  | Food Court | x 28–38, y 9–15 | Glass roof. Small shop along the top wall (2 rows), cafeteria counter on the right wall, café tables with chairs bottom left. Door to the spine at x 26–27, y 11–13. |
  | Library | x 28–37, y 18–25 | Bookshelves and long white tables. Door to the spine at x 26–27, y 21–22. |
  | Gym | x 31–40, y 28–30 | Solid building (roof only). |
  | EDP Plaza | x 26–40, y 28–36 | Outdoor paving with trees, red seating steps and picnic tables. Opens to the spine. |
  | Auditorium | x 23–35, y 38–41 | Big screen on the front wall (x 27–32, y 37). Entrances at the front: from the spine (front left) and from the plaza (x 34–35, y 37). Three rows of seats behind a free front aisle face the screen. |

- **No dead ends:** every wing has an exit at both ends (the west ends join the beach, the lawn or the lawn path), so players can run in loops. Not a single floor tile has only one floor neighbour.
- **Furniture, trees, counters and the screens block movement:** they are wall tiles (`#`) in the grid, so the server's existing wall check handles them. Nothing about movement changes in `game.py`.
- **Areas:** the same six names as before. "Courtyard" appears **twice** (one entry per courtyard, same name). `area_at` keeps returning the first area that contains the point. The spine, the halls, the beach, the lawn and the plaza belong to no area: the HUD shows "Corridor" there, as today.

  | name | x | y | w | h | color |
  |---|---|---|---|---|---|
  | Main Entrance | 16 | 1 | 14 | 6 | #c2187a |
  | Student Services | 31 | 1 | 9 | 6 | #9c1d6e |
  | Food Court | 28 | 9 | 11 | 7 | #e3a514 |
  | Library | 28 | 18 | 10 | 8 | #6aa84f |
  | Courtyard | 3 | 14 | 20 | 3 | #5f8a3a |
  | Courtyard | 3 | 22 | 20 | 3 | #5f8a3a |
  | Auditorium | 23 | 38 | 13 | 4 | #e8731a |

- **Spawns** (all in the Main Entrance, on floor tiles, none on a tree or the screen): `[18,4] [20,4] [22,4] [24,4] [26,4] [19,6] [21,6] [23,6] [25,6] [27,6]`.

### 2. Map data: `decor` and `labels`
- `server/campus.json` gets two new lists. They only change how the map looks. The server uses neither for any rule; it checks them when the map is loaded (see below) and sends them with the rest of the map in `welcome`, as today.
- **`decor`:** each entry is `{"kind", "x", "y", "w", "h"}`, a rectangle of tiles with one look.
  - **Solid kinds** (every tile of the rectangle must be a wall tile `#`): `sea`, `solar`, `greenroof`, `roof`, `glasswall`, `counter`, `shelf`, `desk`, `studytable`, `table`, `cafetable`, `woodtable`, `shopshelf`, `foodcounter`, `piano`, `screen`, `steps`, `picnic`, `tree`.
  - **Floor kinds** (painted only on the floor tiles inside the rectangle; wall tiles inside it are skipped): `sand`, `paving`, `grass`, `terrace`, `pergola`, `glassroof`, `shopfloor`, `seats`, `beanbag`.
  - A wall tile without decor is drawn as a building wall. A wall tile with no floor tile among its 8 neighbours is drawn as dark ground outside the campus.
- **`labels`:** each entry is `{"text", "x", "y"}` (tile coordinates, may be fractions): names drawn on the map for places that are not areas, e.g. "Hall B", "Student Hall", "Beach", "EDP Plaza". Area names are drawn from `areas` as today.
- **Checked when loading:** a new function `validate_campus(campus)` in `server/game.py` is called by `load_map()` and raises a `ValueError` with a short reason if:
  - a `decor` entry has an unknown `kind`;
  - a `decor` entry is missing one of `x`, `y`, `w`, `h`, has a value that is not a whole number, or `w`/`h` below 1;
  - a `decor` entry lies partly outside the grid;
  - a solid kind covers a floor tile;
  - a `labels` entry has no text, text longer than 24 characters, or a position outside the grid.

  A broken map then fails at server start and in the tests, not in the middle of a demo. A map without `decor` or `labels` stays valid (the small test maps in `tests/` have none).

### 3. Drawing (`web/render.js`)
- All drawing stays in `render.js` and keeps the rules of spec 005: shapes and text only, no image, font or sound file, nothing downloaded, no dependency added. Texts from `labels` are added as text, never as HTML.
- The static map (floor, walls, decor, area names, labels) is drawn **once** when the scene starts, not every frame, so it stays smooth on phones.
- **Floor:** light grey polished concrete with soft reflections; inside an area a soft tint of the area's `color`.
- **Walls:** light grey roof. A wall next to floor shows a glass facade toward the floor (light blue band with slim white columns) and a short shadow.
- **Decor looks:**
  - `sea`: blue with small waves; a white foam line where it touches the sand;
  - `sand`: light sand colour with small pebbles and an occasional shell;
  - `paving`: warm stone tiles; `grass`: green with short blades; `terrace`: light concrete;
  - `pergola`: a white diagonal steel lattice with its shadow, over the terrace;
  - `glassroof`: thin white roof beams over the floor;
  - `shopfloor`: red tint; `shopshelf`: a shelf with colourful products;
  - `seats`: auditorium seats with the backrest on the south side (facing the screen), a free aisle in the middle column;
  - `beanbag`: a round beanbag in red, yellow, green or blue;
  - `solar`: dark blue panels; `greenroof`: green roof with a slanted metal railing; `roof`: white;
  - `glasswall`: a thin glass wall with white frame and mullions;
  - `counter`: light wood; `foodcounter`: wooden counter with trays of food; `shelf`: dark wood with book spines;
  - `desk`: white lecture desk with chairs; `studytable`: long white square-edged study table with chairs on both sides;
  - `table`: round white table; `cafetable`: round white table with four orange chairs; `woodtable`: square wooden table with four wooden chairs;
  - `piano`: black grand piano; `screen`: dark frame with a blue display (vertical in the Main Entrance, horizontal with a soft glow in the Auditorium);
  - `steps`: red seating steps; `picnic`: wooden picnic table; `tree`: round crown with a soft shadow.
- The darkness outside the vision radius (spec 005) is drawn on top as before, so the map stays faintly visible for orientation.
- The camera, the characters, the HUD and the panels do not change.

### 4. Task places of spec 004
Spec 004 places its tasks on tiles of the old map. On the new map they move to these tiles (same ids, areas, texts and durations):

| id | Area | Tile |
|---|---|---|
| `certificate` | Student Services | 35, 3 |
| `helpdesk` | Main Entrance | 20, 3 (in front of the welcome desk) |
| `print` | Library | 37, 20 |
| `coffee` | Food Court | 37, 12 (in front of the cafeteria counter) |
| `eduroam` | Courtyard | 12, 15 |
| `socket` | Auditorium | 30, 40 |
| `gate` | Main Entrance | 24, 6 (where the spine begins) |
| `nata` | Courtyard | 19, 23 |

Whichever of spec 004 and spec 009 is merged second uses these tiles: if `tasks` is already in `campus.json`, this spec moves them; if not, spec 004 takes them from here.

### 5. Positions for spec 008 (bell, staff doors, light switch)
Spec 008 stores three kinds of positions in `server/campus.json`. On the new map they go to these floor tiles:

| Key | Tile(s) | Where |
|---|---|---|
| `bell` | 24, 21 | Middle of the spine, the centre of the map |
| `staff_doors` | 3, 10 · 3, 28 · 36, 25 · 39, 35 | Lecture hall of Hall B, lecture hall of Hall D, Library (bottom right corner), EDP Plaza (south-east corner) |
| `light_switch` | 38, 5 | Student Services, right wall |

If spec 008 uses other key names, its names win and only the tiles come from here. Whichever of spec 008 and spec 009 is merged second puts these entries into the new `campus.json` (Appendix A does not contain them yet, because spec 008 is not merged).

## Out of scope
- New area names (spine, halls, beach, plaza) and showing them in the HUD.
- Several floors, stairs, lifts.
- Walking on the water, the park or the parking area (not part of the map).
- The rules of the bell, staff doors, lights sabotage and line of sight (spec 008); this spec only gives their positions on the new map. The Segway guard (F1).
- Animated decor (moving waves, swaying trees), sound.
- Any change to the rules of movement, roles, expel, tasks, meetings, votes, vision or colours.
- Images of the real campus in the repository.

## Done when
- Tests in a new file `tests/test_campus.py`, written first and red before the implementation.
  - Accepted (the real campus map):
    - the grid is 42 × 43, rectangular, only `#` and `.`, with walls all around;
    - the area names are exactly the six known names; "Courtyard" appears in two entries; every area rectangle lies inside the grid;
    - every floor tile of the map is reachable from the first spawn;
    - no floor tile has exactly one floor neighbour (no dead ends);
    - every spawn is a floor tile in the Main Entrance; no two spawns share a tile;
    - `area_at` returns "Courtyard" for a tile in each courtyard and nothing for the spine (24, 20), the beach (1, 20) and the plaza (30, 32);
    - the Auditorium seats `MAX_PLAYERS` players: `_meeting_tiles()` gives at least 10 different floor tiles and its first 10 are never neighbours;
    - the longest walk from the first spawn to any floor tile is at most 60 tiles (12 seconds at the current speed);
    - `validate_campus` accepts the real map and a map without `decor` and `labels`;
    - once spec 008 is merged: the bell, every staff door and the light switch are floor tiles reachable from the first spawn; none of them is a spawn or a task tile; the light switch lies in Student Services.
  - Rejected (each raises `ValueError` with a reason):
    - a `decor` entry with an unknown kind;
    - a missing `w`, a `w` of 0 and a value that is not a whole number;
    - a rectangle that reaches past the right or bottom edge;
    - a solid kind (`tree`) on a floor tile;
    - a label with empty text, with 25 characters, and outside the grid.
  - Edge cases:
    - a floor kind (`paving`) whose rectangle contains wall tiles is valid;
    - a solid kind exactly on the last wall column and row of the grid is valid;
    - a label with exactly 24 characters is valid.
- One WebSocket test: the `welcome` message contains `map.decor` and `map.labels` with the same number of entries as `campus.json`.
- **One existing test line changes, and only this one:** in `tests/test_look.py` the far-away player is placed in the Library with `far.x, far.y = 37.5 * TILE, 23.5 * TILE` instead of `2.5 * TILE, 2.5 * TILE` (tile (2, 2) is now outside the building). Every other existing test still passes unchanged, including `test_campus_map_is_valid`, the reachability test, the spawn tests and the Auditorium seating test.
- `uv run pytest` passes; the output is pasted.
- Manual check with 4 browser windows locally:
  - the map shows the Main Entrance, the spine, the four halls, both courtyards, the beach with the water, the Food Court, the Library, the plaza and the Auditorium;
  - tables, shelves, counters, trees and screens block walking; nobody can walk onto the water;
  - every hall can be left at both ends;
  - walking from the Main Entrance into each area changes the area name in the HUD; the spine and the halls show "Corridor";
  - a bell sends everyone into the Auditorium, each on their own seat facing the screen;
  - the map looks sharp and runs smoothly on a phone-sized window and a laptop window.

## Appendix A: `server/campus.json`

```json
{
  "tile_size": 32,
  "grid": [
    "##########################################",
    "################..............#.........##",
    "################..####.#..#.#.#..#####..##",
    "#################...........#...........##",
    "################............#...........##",
    "################............#.#.........##",
    "#################.............#.........##",
    "#######################...################",
    "###.....###############...################",
    "#...###...................##...#####...###",
    "#.........................##...........###",
    "#...###...............................####",
    "#.#.....#######.####.##......#.#......####",
    "#.###.#########.####.##...............####",
    "#.#.......................##.#.#.#.....###",
    "#.......#....#.#.#.#.#....##...........###",
    "#.#.......................################",
    "#.#.........###########...################",
    "#.#......#...#..#..#..#...##..........####",
    "#.#...#......#..#..#..#...##..######..####",
    "#.#.......................##..........####",
    "#.#.........###########...............####",
    "#.#...........................######..####",
    "#.........#..#.##....##...##..........####",
    "#.#.......................##..######..####",
    "#.###.##############.##...##..........####",
    "#.#.....############.##...################",
    "#...###...................################",
    "#..............................###########",
    "#...###........................###########",
    "#.#.....##########.####........###########",
    "#.################.####.....#............#",
    "#.#........#######.####..................#",
    "#.#..#.....#.....#.####......#.......#####",
    "#....................................#####",
    "#.......#.......................#........#",
    "###........#..........................#..#",
    "#######################...########..######",
    "#######################.............######",
    "#######################.............######",
    "#######################.............######",
    "########################...........#######",
    "##########################################"
  ],
  "areas": [
    {"name": "Main Entrance", "x": 16, "y": 1, "w": 14, "h": 6, "color": "#c2187a"},
    {"name": "Student Services", "x": 31, "y": 1, "w": 9, "h": 6, "color": "#9c1d6e"},
    {"name": "Food Court", "x": 28, "y": 9, "w": 11, "h": 7, "color": "#e3a514"},
    {"name": "Library", "x": 28, "y": 18, "w": 10, "h": 8, "color": "#6aa84f"},
    {"name": "Courtyard", "x": 3, "y": 14, "w": 20, "h": 3, "color": "#5f8a3a"},
    {"name": "Courtyard", "x": 3, "y": 22, "w": 20, "h": 3, "color": "#5f8a3a"},
    {"name": "Auditorium", "x": 23, "y": 38, "w": 13, "h": 4, "color": "#e8731a"}
  ],
  "spawns": [[18, 4], [20, 4], [22, 4], [24, 4], [26, 4], [19, 6], [21, 6], [23, 6], [25, 6], [27, 6]],
  "decor": [
    {"kind": "sea", "x": 0, "y": 0, "w": 1, "h": 43},
    {"kind": "sea", "x": 1, "y": 0, "w": 1, "h": 8},
    {"kind": "sea", "x": 1, "y": 36, "w": 1, "h": 7},
    {"kind": "sand", "x": 1, "y": 9, "w": 1, "h": 27},
    {"kind": "paving", "x": 26, "y": 28, "w": 15, "h": 10},
    {"kind": "grass", "x": 3, "y": 14, "w": 20, "h": 3},
    {"kind": "grass", "x": 3, "y": 17, "w": 9, "h": 5},
    {"kind": "grass", "x": 3, "y": 32, "w": 8, "h": 5},
    {"kind": "terrace", "x": 3, "y": 22, "w": 20, "h": 3},
    {"kind": "pergola", "x": 3, "y": 22, "w": 20, "h": 3},
    {"kind": "glassroof", "x": 23, "y": 7, "w": 3, "h": 30},
    {"kind": "glassroof", "x": 28, "y": 10, "w": 11, "h": 6},
    {"kind": "shopfloor", "x": 30, "y": 9, "w": 7, "h": 2},
    {"kind": "seats", "x": 24, "y": 39, "w": 11, "h": 2},
    {"kind": "seats", "x": 25, "y": 41, "w": 9, "h": 1},
    {"kind": "beanbag", "x": 23, "y": 20, "w": 1, "h": 1},
    {"kind": "beanbag", "x": 9, "y": 22, "w": 1, "h": 1},
    {"kind": "beanbag", "x": 15, "y": 22, "w": 1, "h": 1},
    {"kind": "beanbag", "x": 7, "y": 23, "w": 1, "h": 1},
    {"kind": "beanbag", "x": 18, "y": 23, "w": 1, "h": 1},
    {"kind": "beanbag", "x": 12, "y": 24, "w": 1, "h": 1},
    {"kind": "beanbag", "x": 20, "y": 24, "w": 1, "h": 1},
    {"kind": "beanbag", "x": 25, "y": 26, "w": 1, "h": 1},
    {"kind": "solar", "x": 3, "y": 7, "w": 20, "h": 1},
    {"kind": "greenroof", "x": 8, "y": 12, "w": 7, "h": 1},
    {"kind": "greenroof", "x": 16, "y": 12, "w": 4, "h": 1},
    {"kind": "greenroof", "x": 21, "y": 12, "w": 2, "h": 1},
    {"kind": "greenroof", "x": 3, "y": 25, "w": 2, "h": 1},
    {"kind": "greenroof", "x": 6, "y": 25, "w": 14, "h": 1},
    {"kind": "greenroof", "x": 21, "y": 25, "w": 2, "h": 1},
    {"kind": "greenroof", "x": 8, "y": 30, "w": 10, "h": 1},
    {"kind": "roof", "x": 31, "y": 28, "w": 10, "h": 3},
    {"kind": "roof", "x": 17, "y": 32, "w": 1, "h": 2},
    {"kind": "roof", "x": 19, "y": 32, "w": 4, "h": 2},
    {"kind": "roof", "x": 11, "y": 37, "w": 7, "h": 1},
    {"kind": "glasswall", "x": 13, "y": 17, "w": 10, "h": 1},
    {"kind": "glasswall", "x": 13, "y": 21, "w": 10, "h": 1},
    {"kind": "counter", "x": 18, "y": 2, "w": 4, "h": 1},
    {"kind": "counter", "x": 33, "y": 2, "w": 5, "h": 1},
    {"kind": "shelf", "x": 30, "y": 19, "w": 6, "h": 1},
    {"kind": "desk", "x": 4, "y": 9, "w": 3, "h": 1},
    {"kind": "desk", "x": 4, "y": 11, "w": 3, "h": 1},
    {"kind": "desk", "x": 30, "y": 22, "w": 6, "h": 1},
    {"kind": "desk", "x": 30, "y": 24, "w": 6, "h": 1},
    {"kind": "desk", "x": 4, "y": 27, "w": 3, "h": 1},
    {"kind": "desk", "x": 4, "y": 29, "w": 3, "h": 1},
    {"kind": "studytable", "x": 13, "y": 18, "w": 1, "h": 2},
    {"kind": "studytable", "x": 16, "y": 18, "w": 1, "h": 2},
    {"kind": "studytable", "x": 19, "y": 18, "w": 1, "h": 2},
    {"kind": "studytable", "x": 22, "y": 18, "w": 1, "h": 2},
    {"kind": "table", "x": 10, "y": 23, "w": 1, "h": 1},
    {"kind": "table", "x": 16, "y": 23, "w": 1, "h": 1},
    {"kind": "cafetable", "x": 29, "y": 12, "w": 1, "h": 1},
    {"kind": "cafetable", "x": 31, "y": 12, "w": 1, "h": 1},
    {"kind": "cafetable", "x": 29, "y": 14, "w": 1, "h": 1},
    {"kind": "cafetable", "x": 31, "y": 14, "w": 1, "h": 1},
    {"kind": "cafetable", "x": 33, "y": 14, "w": 1, "h": 1},
    {"kind": "woodtable", "x": 13, "y": 15, "w": 1, "h": 1},
    {"kind": "woodtable", "x": 15, "y": 15, "w": 1, "h": 1},
    {"kind": "woodtable", "x": 17, "y": 15, "w": 1, "h": 1},
    {"kind": "woodtable", "x": 19, "y": 15, "w": 1, "h": 1},
    {"kind": "woodtable", "x": 21, "y": 15, "w": 1, "h": 1},
    {"kind": "woodtable", "x": 13, "y": 23, "w": 1, "h": 1},
    {"kind": "woodtable", "x": 15, "y": 23, "w": 1, "h": 1},
    {"kind": "woodtable", "x": 21, "y": 23, "w": 1, "h": 1},
    {"kind": "woodtable", "x": 22, "y": 23, "w": 1, "h": 1},
    {"kind": "shopshelf", "x": 31, "y": 9, "w": 5, "h": 1},
    {"kind": "foodcounter", "x": 38, "y": 11, "w": 1, "h": 3},
    {"kind": "piano", "x": 22, "y": 13, "w": 1, "h": 1},
    {"kind": "screen", "x": 28, "y": 2, "w": 1, "h": 4},
    {"kind": "screen", "x": 27, "y": 37, "w": 6, "h": 1},
    {"kind": "steps", "x": 37, "y": 33, "w": 1, "h": 2},
    {"kind": "steps", "x": 38, "y": 33, "w": 1, "h": 2},
    {"kind": "steps", "x": 39, "y": 33, "w": 1, "h": 2},
    {"kind": "steps", "x": 40, "y": 33, "w": 1, "h": 2},
    {"kind": "picnic", "x": 29, "y": 33, "w": 1, "h": 1},
    {"kind": "picnic", "x": 32, "y": 35, "w": 1, "h": 1},
    {"kind": "tree", "x": 23, "y": 2, "w": 1, "h": 1},
    {"kind": "tree", "x": 26, "y": 2, "w": 1, "h": 1},
    {"kind": "tree", "x": 16, "y": 3, "w": 1, "h": 1},
    {"kind": "tree", "x": 16, "y": 6, "w": 1, "h": 1},
    {"kind": "tree", "x": 8, "y": 15, "w": 1, "h": 1},
    {"kind": "tree", "x": 9, "y": 18, "w": 1, "h": 1},
    {"kind": "tree", "x": 6, "y": 19, "w": 1, "h": 1},
    {"kind": "tree", "x": 28, "y": 31, "w": 1, "h": 1},
    {"kind": "tree", "x": 5, "y": 33, "w": 1, "h": 1},
    {"kind": "tree", "x": 8, "y": 35, "w": 1, "h": 1},
    {"kind": "tree", "x": 38, "y": 36, "w": 1, "h": 1}
  ],
  "labels": [
    {"text": "Hall B", "x": 12, "y": 10},
    {"text": "Student Hall", "x": 17.5, "y": 20},
    {"text": "Hall D", "x": 12, "y": 28},
    {"text": "Hall E", "x": 18, "y": 35},
    {"text": "Spine", "x": 24, "y": 30.4},
    {"text": "Beach", "x": 1.2, "y": 20},
    {"text": "EDP Plaza", "x": 33.5, "y": 31.6},
    {"text": "Gym", "x": 36, "y": 28.9},
    {"text": "Shop", "x": 33, "y": 10},
    {"text": "Cafeteria", "x": 37.4, "y": 10.1},
    {"text": "Lecture hall", "x": 5, "y": 7.9},
    {"text": "Lecture hall", "x": 5, "y": 30.9},
    {"text": "Welcome desk", "x": 20, "y": 1.05}
  ]
}
```
