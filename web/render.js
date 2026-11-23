// All drawing code (spec 005): the map, the characters, the failed exams, the meeting table, the
// vents, the light switch, the task places and the darkness.
// Everything is drawn here from simple shapes and text: there are no image files.
// main.js decides WHAT to draw from the server's state; this file decides HOW it looks.
// Loaded as a plain script after Phaser and before main.js (no build step).

"use strict";

const Render = (() => {
  // --- Look settings ---------------------------------------------------------------

  // The server sends a colour number 0-9 per player; this is what each number looks like.
  const PLAYER_COLORS = [
    0xe5484d, // 0 red
    0xf08a24, // 1 orange
    0xf5d547, // 2 yellow
    0x4cb963, // 3 green
    0x2ec4b6, // 4 teal
    0x3a86ff, // 5 blue
    0x8e5bd9, // 6 purple
    0xff7ab6, // 7 pink
    0xa9714b, // 8 brown
    0xe9ecef, // 9 white
  ];
  const UNKNOWN_COLOR = 0x9aa0aa; // if the server ever sends a number we do not know

  const OUTLINE = 0x16181d;
  const BACKDROP = 0x14161b; // behind and around the map
  const FONT = "system-ui, -apple-system, 'Segoe UI', sans-serif";
  const OWN_NAME_COLOR = "#f2b33d"; // the accent colour of the page (style.css)

  // Screens with a high pixel density get a bigger canvas, so shapes and text stay sharp.
  // Capped at 2 to keep phones fast.
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  const TEXT_RESOLUTION = 4; // text is drawn 4x and scaled down: sharp at every zoom
  const MAX_ZOOM = 3;
  const FIGURE_SCALE = 1.2; // characters are drawn this much bigger than the server's square
  const VIEW_MARGIN = 1.25; // the vision circle fills 1 / 1.25 = 80 % of the shorter side

  // Darkness outside the vision radius: clear up to 70 % of the radius, then fading,
  // fully dark just past the radius. The map stays faintly visible for orientation.
  const FOG_CLEAR = 0.7;
  const FOG_FULL = 1.02;
  const FOG_ALPHA = 0.86;
  const FOG_COLOR = 0x080a0e;
  const RIM_REACH = 2.5; // the rim picture reaches this many radii from the own character
  const RIM_TEXTURE_SIZE = 512;
  // The lit area (spec 010, part 3): rays from the own character to the corners of walls.
  const LIT_REACH = 1.1; // rays end this many radii out, where the rim is fully dark already
  const FAN_RAYS = 48; // evenly spread rays, so the lit area is round where no wall is near
  const RAY_NUDGE = 0.0001; // radians: one more ray just left and right of every wall corner

  // --- Colours -----------------------------------------------------------------------

  function colorOf(number) {
    return PLAYER_COLORS[number] ?? UNKNOWN_COLOR;
  }

  // The same colour as a CSS value, for the dots in the lobby and end lists.
  function colorCss(number) {
    return "#" + colorOf(number).toString(16).padStart(6, "0");
  }

  // A darker version of a colour (factor 0-1), used for the feet.
  function shade(color, factor) {
    const red = Math.round(((color >> 16) & 255) * factor);
    const green = Math.round(((color >> 8) & 255) * factor);
    const blue = Math.round((color & 255) * factor);
    return (red << 16) | (green << 8) | blue;
  }

  // --- Camera ------------------------------------------------------------------------

  // Zoom so the vision circle fills most of the window, but never so far out that the
  // window shows more than the map.
  function cameraZoom(mapWidth, mapHeight, visionRadius) {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const fit = Math.min(width, height) / (visionRadius * 2 * VIEW_MARGIN);
    const cover = Math.max(width / mapWidth, height / mapHeight);
    return Math.max(cover, Math.min(fit, MAX_ZOOM)) * pixelRatio;
  }

  // --- Map ---------------------------------------------------------------------------
  // Spec 009: the Nova campus. The grid says where one can walk. The optional "decor" list
  // says how tiles look and "labels" name places that are not areas. Spec 011 sorts the
  // decor into three groups (the same as in server/game.py):
  //   solid kinds lie on wall tiles: the sea, glass, roofs and screens;
  //   ground kinds colour the floor: grass, paving, sand, ...;
  //   furniture stands on floor tiles and is walked over: tables, desks, trees, ...
  // A wall tile that blocks sight (the server's sight grid) is drawn as a flat block with a
  // sharp edge line; glass is a thin pane on the floor. Drawn once when the scene starts.

  const FLOOR_A = 0xf0f1f2; // polished concrete, two shades for a tiled look
  const FLOOR_B = 0xe8eaec;
  const WALL_TOP = 0x343a46; // an opaque wall seen from above: one flat colour
  const WALL_EDGE = 0x5d6679; // the line along every side where a wall ends
  const GLASS = 0xa6dcf7;
  const GLASS_LINE = 0x3f8fb8;
  const SOLID_ORDER = ["sea", "solar", "greenroof", "roof", "glasswall", "screen"];
  const GROUND_ORDER = ["shopfloor", "sand", "paving", "grass", "terrace", "pergola", "glassroof", "seats"];
  const FURNITURE_ORDER = [
    "beanbag", "steps", "counter", "shelf", "desk", "studytable", "table", "cafetable", "woodtable",
    "shopshelf", "foodcounter", "piano", "picnic", "tree", "surfboard",
  ];
  const OUTDOOR_FLOOR = { paving: [0xd2c4aa, 0xcabb9f], grass: [0x86b45a, 0x86b45a], terrace: [0xe9e6df, 0xe1ddd4] };
  const BEANBAG_COLORS = [0xd9412e, 0xf2b632, 0x4caf50, 0xd9412e, 0x2f80c3];
  const PRODUCT_COLORS = [0xe53935, 0x43a047, 0xfdd835, 0x1e88e5, 0xfb8c00, 0x8e24aa];
  const BOOK_COLORS = [0xc0392b, 0xe6b33a, 0x2e86c1, 0xf4f1e8, 0x27ae60];
  // Surfboards (spec 015): [board, stripe] colour pairs, picked by the board's tile.
  const BOARD_COLORS = [
    [0xff6b5e, 0xfff3d6], [0x2ec4b6, 0xfff3d6], [0xf5d547, 0xe5484d],
    [0x8e5bd9, 0xf5d547], [0xfff3d6, 0x3a86ff], [0xff7ab6, 0x2ec4b6],
  ];

  // A small seeded random generator, so speckles and books look the same on every screen.
  function seeded(seed) {
    let state = seed >>> 0;
    return () => {
      state = (state + 0x6d2b79f5) >>> 0;
      let value = state;
      value = Math.imul(value ^ (value >>> 15), value | 1);
      value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
      return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Draws the campus from the server's map data and returns its size in pixels.
  // `sight` is the server's sight grid from "welcome": "#" marks a tile that blocks sight.
  function drawMap(scene, map, sight) {
    const t = map.tile_size;
    const rows = map.grid.length;
    const cols = map.grid[0].length;
    const inside = (col, row) => row >= 0 && row < rows && col >= 0 && col < cols;
    const isFloor = (col, row) => inside(col, row) && map.grid[row][col] === ".";
    const isOpaque = (col, row) => inside(col, row) && sight[row][col] === "#";
    const random = seeded(7);
    const pick = (list) => list[Math.floor(random() * list.length)];
    const g = scene.add.graphics();
    const u = t / 52; // the shapes below were designed on a 52 px tile

    const areaAt = (col, row) =>
      map.areas.find((a) => col >= a.x && col < a.x + a.w && row >= a.y && row < a.y + a.h);

    // Which decor kinds lie on each tile ("col,row" -> [kinds]).
    const kinds = new Map();
    for (const entry of map.decor || []) {
      const solid = SOLID_ORDER.includes(entry.kind);
      for (let row = entry.y; row < entry.y + entry.h; row++) {
        for (let col = entry.x; col < entry.x + entry.w; col++) {
          if (solid === isFloor(col, row)) continue; // solid on walls, the other kinds on floor
          const key = col + "," + row;
          if (!kinds.has(key)) kinds.set(key, []);
          kinds.get(key).push(entry.kind);
        }
      }
    }
    const kindsAt = (col, row) => kinds.get(col + "," + row) || [];
    const has = (col, row, kind) => kindsAt(col, row).includes(kind);

    const rect = (col, row, color, alpha = 1) => g.fillStyle(color, alpha).fillRect(col * t, row * t, t, t);
    const tint = (col, row) => {
      const area = areaAt(col, row);
      if (area && !area.name.endsWith("Courtyard")) rect(col, row, Phaser.Display.Color.HexStringToColor(area.color).color, 0.31);
    };
    // Calls draw(col, row, x, y) for every tile, row by row.
    const eachTile = (draw) => {
      for (let row = 0; row < rows; row++) for (let col = 0; col < cols; col++) draw(col, row, col * t, row * t);
    };

    g.fillStyle(BACKDROP).fillRect(0, 0, cols * t, rows * t);

    // 1. Floor: polished concrete, the area's tint, then the ground decor.
    eachTile((col, row, x, y) => {
      if (!isFloor(col, row)) return;
      rect(col, row, (col + row) % 2 ? FLOOR_A : FLOOR_B);
      if ((col * 7 + row * 3) % 5 === 0) {
        g.lineStyle(3 * u, 0xffffff, 0.5).lineBetween(x + 6 * u, y + t - 8 * u, x + t - 10 * u, y + 8 * u);
      }
      tint(col, row);
      const here = kindsAt(col, row);
      for (const kind of GROUND_ORDER) if (here.includes(kind)) drawGround(kind, col, row, x, y);
    });

    function drawGround(kind, col, row, x, y) {
      if (kind === "shopfloor") {
        rect(col, row, 0xc42828, 0.27);
        g.lineStyle(1, 0xa01e1e, 0.35).strokeRect(x, y, t, t);
      } else if (kind === "sand") {
        rect(col, row, (col + row) % 2 ? 0xead6a6 : 0xe6d19e);
        g.fillStyle(0xcdb47c);
        for (let i = 0; i < 7; i++) g.fillCircle(x + (3 + random() * 46) * u, y + (3 + random() * 46) * u, 1.6 * u);
        // A shell here and there (not one per tile of a row: the beach is five tiles wide now).
        if ((col * 5 + row * 3) % 13 === 0) g.fillStyle(0xf6efe2).fillEllipse(x + 34 * u, y + 33 * u, 8 * u, 6 * u);
      } else if (kind in OUTDOOR_FLOOR) {
        rect(col, row, OUTDOOR_FLOOR[kind][(col + row) % 2]);
        if (kind === "grass") {
          g.lineStyle(2 * u, 0x5f8f3c);
          for (let i = 0; i < 4; i++) {
            const bx = x + (4 + random() * 42) * u;
            const by = y + (8 + random() * 40) * u;
            g.lineBetween(bx, by, bx + 2 * u, by - 7 * u);
          }
        }
      } else if (kind === "pergola") {
        // A white steel lattice seen from above, with its shadow on the terrace.
        for (let o = -52; o < 52; o += 13) {
          g.lineStyle(2 * u, 0x464646, 0.18).lineBetween(x + o * u, y, x + (o + 52) * u, y + t);
          g.lineStyle(2 * u, 0xffffff, 0.9).lineBetween(x + (o + 4) * u, y, x + (o + 56) * u, y + t);
          g.lineStyle(1, 0xffffff, 0.65).lineBetween(x + (o + 52) * u, y, x + o * u, y + t);
        }
      } else if (kind === "glassroof") {
        g.lineStyle(3 * u, 0xffffff, 0.8).lineBetween(x, y, x + t, y);
        g.lineStyle(2 * u, 0xffffff, 0.5).lineBetween(x, y, x, y + t);
      } else if (kind === "seats") {
        if (col !== 33) { // the free aisle in the middle of the Auditorium
          // A seat facing north (towards the screen): backrest at the bottom.
          g.fillStyle(0x5f8a4a).fillRect(x + 6 * u, y + 6 * u, t - 12 * u, t - 20 * u);
          g.fillStyle(0x3f6331).fillRect(x + 6 * u, y + t - 16 * u, t - 12 * u, 10 * u);
        }
      }
    }

    // 2. The sea and the glass panes: wall tiles one can look across.
    eachTile((col, row, x, y) => {
      if (isFloor(col, row) || isOpaque(col, row)) return;
      if (has(col, row, "glasswall")) drawGlassPane(col, row, x, y);
      else drawSea(col, row, x, y);
    });

    function drawSea(col, row, x, y) {
      rect(col, row, 0x2f6f9f);
      g.lineStyle(2 * u, 0x7fb3d8);
      for (let i = 0; i < 2; i++) {
        const wy = y + (14 + i * 22 + (random() * 6 - 3)) * u;
        g.beginPath();
        g.arc(x + 14 * u, wy + 5 * u, 10 * u, Phaser.Math.DegToRad(200), Phaser.Math.DegToRad(340));
        g.strokePath();
      }
      if (isFloor(col + 1, row)) {
        // Foam where the water meets the beach.
        g.fillStyle(0x4f8fbf).fillRect(x + t - 10 * u, y, 10 * u, t);
        g.fillStyle(0xe9f3f8);
        for (let o = 0; o < 52; o += 12) g.fillEllipse(x + t - 8 * u, y + (o + 5) * u, 12 * u, 10 * u);
      }
      // The same along the north and south ends of the beach (spec 015: the beach is a bay).
      for (const [dr, edge] of [[1, t - 10 * u], [-1, 0]]) {
        if (!isFloor(col, row + dr)) continue;
        g.fillStyle(0x4f8fbf).fillRect(x, y + edge, t, 10 * u);
        g.fillStyle(0xe9f3f8);
        for (let o = 0; o < 52; o += 12) g.fillEllipse(x + (o + 5) * u, y + edge + (dr > 0 ? 8 : 2) * u, 10 * u, 12 * u);
      }
    }

    // The ground of the floor tile (col, row), painted into the rectangle x, y, w, h.
    function paintGround(col, row, x, y, w, h) {
      const outdoor = ["grass", "terrace", "paving"].find((kind) => has(col, row, kind));
      g.fillStyle(outdoor ? OUTDOOR_FLOOR[outdoor][0] : FLOOR_A).fillRect(x, y, w, h);
      const area = areaAt(col, row);
      if (!outdoor && area && !area.name.endsWith("Courtyard")) {
        g.fillStyle(Phaser.Display.Color.HexStringToColor(area.color).color, 0.31).fillRect(x, y, w, h);
      }
    }

    // A glass pane (spec 011): thin and clearly see-through. The grounds of the two sides
    // meet under it; the pane is a light blue line with a white highlight along the middle
    // of the tile and a slim post where the pane ends. It still blocks the whole tile.
    function drawGlassPane(col, row, x, y) {
      // Floor above and below: the pane runs from left to right. Otherwise from top to bottom.
      const level = isFloor(col, row - 1) && isFloor(col, row + 1);
      const half = t / 2;
      if (level) {
        paintGround(col, row - 1, x, y, t, half);
        paintGround(col, row + 1, x, y + half, t, half);
      } else {
        paintGround(col - 1, row, x, y, half, t);
        paintGround(col + 1, row, x + half, y, half, t);
      }
      // bar(along, across, length, thickness): a rectangle along the pane's direction.
      const bar = (along, across, length, thickness) =>
        level ? g.fillRect(x + along, y + across, length, thickness) : g.fillRect(x + across, y + along, thickness, length);
      const thick = 6;
      const top = half - thick / 2;
      g.fillStyle(0x000000, 0.14);
      bar(0, top + thick + 1, t, 2); // a faint shadow
      g.fillStyle(GLASS, 0.6);
      bar(0, top, t, thick); // the glass: the ground shows through
      g.fillStyle(GLASS_LINE);
      bar(0, top - 1, t, 1);
      bar(0, top + thick, t, 1);
      g.fillStyle(0xffffff, 0.95);
      bar(0, top + 1, t, 1.5); // the highlight
      const before = level ? has(col - 1, row, "glasswall") : has(col, row - 1, "glasswall");
      const after = level ? has(col + 1, row, "glasswall") : has(col, row + 1, "glasswall");
      for (const [end, at] of [[!before, 0], [!after, t - 4]]) {
        if (!end) continue;
        g.fillStyle(GLASS_LINE);
        bar(at, top - 3, 4, thick + 6);
        g.fillStyle(0xf4f8fb);
        bar(at + 1, top - 2, 2, thick + 4); // the post at the end of the pane
      }
    }

    // 3. Furniture and plants on the floor: players walk over them (spec 011).
    eachTile((col, row, x, y) => {
      if (!isFloor(col, row)) return;
      const here = kindsAt(col, row);
      for (const kind of FURNITURE_ORDER) if (here.includes(kind)) drawFurniture(kind, col, row, x, y);
    });

    function drawFurniture(kind, col, row, x, y) {
      if (kind === "beanbag") {
        g.fillStyle(0x000000, 0.2).fillEllipse(x + 28 * u, y + 30 * u, 38 * u, 36 * u);
        g.fillStyle(BEANBAG_COLORS[(col * 3 + row) % 5]).fillEllipse(x + 25 * u, y + 25 * u, 38 * u, 36 * u);
        g.fillStyle(0xffffff, 0.27).fillEllipse(x + 22 * u, y + 22 * u, 14 * u, 12 * u);
      } else if (kind === "counter") {
        g.fillStyle(0xd8c49a).fillRect(x, y + 8 * u, t, t - 16 * u);
        g.fillStyle(0xa88c5c).fillRect(x, y + t - 14 * u, t, 6 * u);
      } else if (kind === "shelf") {
        g.fillStyle(0x5b3b22).fillRect(x + 2 * u, y + 6 * u, t - 4 * u, t - 12 * u);
        for (let i = 0; i < 6; i++) g.fillStyle(pick(BOOK_COLORS)).fillRect(x + (5 + i * 7) * u, y + 10 * u, 4 * u, t - 20 * u);
      } else if (kind === "desk") {
        g.fillStyle(0xf5f3ee).fillRect(x, y + 10 * u, t, t - 24 * u);
        g.lineStyle(2 * u, 0xb9b3a6).strokeRect(x, y + 10 * u, t, t - 24 * u);
        g.fillStyle(0x6e6e6e);
        for (let i = 0; i < 2; i++) g.fillCircle(x + (13 + i * 22) * u, y + t - 7 * u, 5 * u);
      } else if (kind === "studytable") {
        const top = !has(col, row - 1, "studytable");
        const bottom = !has(col, row + 1, "studytable");
        g.fillStyle(0x6b7078);
        for (const cy of [t / 4, (3 * t) / 4]) {
          g.fillRoundedRect(x - 4 * u, y + cy - 7 * u, 11 * u, 14 * u, 3 * u);
          g.fillRoundedRect(x + t - 8 * u, y + cy - 7 * u, 11 * u, 14 * u, 3 * u);
        }
        const y0 = y + (top ? 4 * u : 0);
        const y1 = y + t - (bottom ? 4 * u : 0);
        g.fillStyle(0xffffff).fillRect(x + 7 * u, y0, t - 15 * u, y1 - y0);
        g.lineStyle(2 * u, 0xb9bcc0).strokeRect(x + 7 * u, y0, t - 15 * u, y1 - y0);
        g.fillStyle(0xd9dde2).fillRect(x + 10 * u, y + 12 * u, 10 * u, 8 * u); // laptop
        g.fillStyle(0xf5e6a8).fillRect(x + 28 * u, y + 30 * u, 8 * u, 8 * u); // notes
      } else if (kind === "table" || kind === "cafetable") {
        if (kind === "cafetable") {
          g.fillStyle(0xe07b39);
          for (const [cx, cy] of [[26, 5], [26, 47], [5, 26], [47, 26]]) g.fillCircle(x + cx * u, y + cy * u, 6 * u);
        }
        g.fillStyle(0x000000, 0.18).fillEllipse(x + 28 * u, y + 29 * u, 34 * u, 34 * u);
        g.fillStyle(0xfafafa).fillCircle(x + t / 2, y + t / 2, 16 * u);
        g.lineStyle(2 * u, 0xb8b1a3).strokeCircle(x + t / 2, y + t / 2, 16 * u);
      } else if (kind === "woodtable") {
        g.fillStyle(0x8a5a33);
        g.fillRoundedRect(x + 19 * u, y, 14 * u, 9 * u, 2 * u);
        g.fillRoundedRect(x + 19 * u, y + t - 9 * u, 14 * u, 9 * u, 2 * u);
        g.fillRoundedRect(x, y + 19 * u, 9 * u, 14 * u, 2 * u);
        g.fillRoundedRect(x + t - 9 * u, y + 19 * u, 9 * u, 14 * u, 2 * u);
        g.fillStyle(0x000000, 0.18).fillRect(x + 10 * u, y + 12 * u, t - 18 * u, t - 18 * u);
        g.fillStyle(0xb07a45).fillRect(x + 9 * u, y + 9 * u, t - 19 * u, t - 19 * u);
        g.lineStyle(2 * u, 0x7a4f2a).strokeRect(x + 9 * u, y + 9 * u, t - 19 * u, t - 19 * u);
      } else if (kind === "shopshelf") {
        g.fillStyle(0xe9e6e0).fillRect(x + 2 * u, y + 8 * u, t - 4 * u, t - 16 * u);
        g.lineStyle(2 * u, 0x9a9690).strokeRect(x + 2 * u, y + 8 * u, t - 4 * u, t - 16 * u);
        for (let i = 0; i < 5; i++) {
          for (let j = 0; j < 2; j++) g.fillStyle(pick(PRODUCT_COLORS)).fillRect(x + (6 + i * 9) * u, y + (12 + j * 14) * u, 6 * u, 10 * u);
        }
      } else if (kind === "foodcounter") {
        g.fillStyle(0xd8c49a).fillRect(x + 6 * u, y, t - 6 * u, t);
        g.fillStyle(0xa88c5c).fillRect(x + 6 * u, y, 6 * u, t);
        for (let j = 0; j < 2; j++) {
          const ty = y + (6 + j * 24) * u;
          g.fillStyle(0xf5f5f5).fillRoundedRect(x + 16 * u, ty, t - 22 * u, 18 * u, 4 * u);
          g.fillStyle(pick([0xe07b39, 0x7cb342, 0xc62828])).fillCircle(x + 25 * u, ty + 9 * u, 5 * u);
          g.fillStyle(0xf2c94c).fillCircle(x + 36 * u, ty + 9 * u, 4 * u);
        }
      } else if (kind === "piano") {
        g.fillStyle(0x141414).fillRoundedRect(x + 4 * u, y + 4 * u, t - 9 * u, t - 9 * u, 8 * u);
        g.fillStyle(0xf2f2f2).fillRect(x + 6 * u, y + t - 14 * u, t - 13 * u, 6 * u);
      } else if (kind === "steps") {
        rect(col, row, 0xcabb9f);
        const colors = [0xb5543c, 0xc8664b, 0xd97a5c];
        for (let i = 0; i < 3; i++) g.fillStyle(colors[i]).fillRect(x, y + (i * t) / 3, t, t / 3 - 2 * u);
      } else if (kind === "picnic") {
        g.fillStyle(0x8a5a33).fillRect(x + 4 * u, y + 14 * u, t - 9 * u, t - 28 * u);
        g.fillStyle(0x6e4628).fillRect(x + 4 * u, y + 6 * u, t - 9 * u, 4 * u);
        g.fillRect(x + 4 * u, y + t - 10 * u, t - 9 * u, 4 * u);
      } else if (kind === "tree") {
        g.fillStyle(0x000000, 0.24).fillEllipse(x + 31 * u, y + 32 * u, 46 * u, 44 * u);
        g.fillStyle(0x3f7d34).fillCircle(x + 24 * u, y + 24 * u, 22 * u);
        g.fillStyle(0x5c9c48).fillCircle(x + 18 * u, y + 15 * u, 8 * u);
      } else if (kind === "surfboard") {
        drawSurfboards(col, row, x, y);
      }
    }

    // Surfboards on the beach (spec 015), three looks chosen by the tile so the same map
    // always shows the same boards: lying on the sand, two leaning on a wooden rack, and
    // one stuck upright in the sand. Boards are a little longer than their tile.
    function drawSurfboards(col, row, x, y) {
      const cx = x + t / 2;
      const cy = y + t / 2;
      const look = (col + row) % 3;
      const colors = (n) => BOARD_COLORS[(col * 5 + row * 3 + n) % BOARD_COLORS.length];
      // One board seen from above: centre, length, width, angle in degrees, colours.
      const board = (bx, by, length, width, angle, [fill, stripe]) => {
        const a = Phaser.Math.DegToRad(angle);
        const cos = Math.cos(a);
        const sin = Math.sin(a);
        // The outline of a board: pointed nose, round tail, as points along its length.
        const shape = (grow) => {
          const points = [];
          for (let i = 0; i <= 16; i++) {
            const f = i / 16; // 0 = tail, 1 = nose
            const half = (width / 2 + grow) * Math.sin(Math.PI * Math.pow(f, 0.75)) ** 0.8;
            points.push([(f - 0.5) * (length + grow * 2), half]);
          }
          const outline = [...points, ...points.map(([px, py]) => [px, -py]).reverse()];
          return outline.map(([px, py]) => ({ x: bx + px * cos - py * sin, y: by + px * sin + py * cos }));
        };
        g.fillStyle(0x000000, 0.2).fillPoints(shape(0).map((p) => ({ x: p.x + 2 * u, y: p.y + 3 * u })), true);
        g.fillStyle(OUTLINE).fillPoints(shape(1.5 * u), true);
        g.fillStyle(fill).fillPoints(shape(0), true);
        // A stripe down the middle and a small fin near the tail.
        g.lineStyle(2.5 * u, stripe).lineBetween(
          bx - cos * length * 0.36, by - sin * length * 0.36, bx + cos * length * 0.4, by + sin * length * 0.4,
        );
        g.fillStyle(OUTLINE).fillCircle(bx - cos * length * 0.38, by - sin * length * 0.38, 1.8 * u);
      };
      if (look === 0) {
        board(cx, cy, 62 * u, 17 * u, -28, colors(0)); // lying on the sand
      } else if (look === 1) {
        // A wooden rack with two boards leaning against it.
        g.fillStyle(0x000000, 0.18).fillRect(x + 4 * u, y + 30 * u, 46 * u, 6 * u);
        board(cx - 10 * u, cy - 2 * u, 58 * u, 15 * u, -74, colors(0));
        board(cx + 9 * u, cy - 2 * u, 58 * u, 15 * u, -104, colors(1));
        g.fillStyle(0x6e4628).fillRect(x + 2 * u, y + 24 * u, 48 * u, 5 * u);
        g.fillStyle(0x8a5a33).fillRect(x + 2 * u, y + 24 * u, 48 * u, 2 * u);
        for (const px of [3, 45]) g.fillStyle(0x4f3219).fillRect(x + px * u, y + 20 * u, 5 * u, 13 * u);
      } else {
        // Stuck upright in the sand: a long shadow, the board, a mound of sand at its foot.
        g.fillStyle(0x000000, 0.2).fillEllipse(cx + 16 * u, cy + 15 * u, 34 * u, 8 * u);
        board(cx, cy - 8 * u, 56 * u, 16 * u, -90, colors(0));
        g.fillStyle(0xd9c38c).fillEllipse(cx, cy + 19 * u, 30 * u, 12 * u);
        g.fillStyle(0xead6a6).fillEllipse(cx - 2 * u, cy + 17 * u, 20 * u, 7 * u);
      }
    }

    // 4. Opaque walls (spec 011): every tile that blocks sight is one flat block in one
    // colour. Roofs and screens only add a faint mark on top. The darkness leaves these
    // tiles out (see wallRects), so a wall looks the same in light and in darkness.
    eachTile((col, row, x, y) => {
      if (!isOpaque(col, row)) return;
      rect(col, row, WALL_TOP);
      if (has(col, row, "solar")) {
        g.fillStyle(0x27467c, 0.4).fillRect(x + 3 * u, y + 3 * u, t - 6 * u, t - 6 * u);
        g.lineStyle(1, 0x6f8fc7, 0.35).lineBetween(x + t / 2, y + 3 * u, x + t / 2, y + t - 3 * u);
        g.lineBetween(x + 3 * u, y + t / 2, x + t - 3 * u, y + t / 2);
      } else if (has(col, row, "greenroof")) {
        rect(col, row, 0x4f8a3c, 0.22);
        g.fillStyle(0x6faa55, 0.35);
        for (let i = 0; i < 3; i++) g.fillCircle(x + (8 + random() * 36) * u, y + (8 + random() * 36) * u, 3 * u);
      } else if (has(col, row, "screen")) {
        drawScreen(col, row, x, y);
      }
    });

    function drawScreen(col, row, x, y) {
      if (has(col - 1, row, "screen") || has(col + 1, row, "screen")) {
        // The big screen on the Auditorium's front wall, glowing onto the aisle.
        const left = has(col - 1, row, "screen") ? 0 : 6 * u;
        const right = has(col + 1, row, "screen") ? 0 : 6 * u;
        g.fillStyle(0x12151a).fillRect(x + left, y + t - 20 * u, t - left - right, 14 * u);
        g.fillStyle(0x3d8bd4).fillRect(x + left * 1.6, y + t - 16 * u, t - (left + right) * 1.6, 10 * u);
        g.fillStyle(0x78b4f0, 0.18).fillRect(x, y + t, t, 10 * u);
      } else {
        // A screen hanging on a wall that runs from top to bottom (Main Entrance).
        const top = has(col, row - 1, "screen") ? 0 : 6 * u;
        const bottom = has(col, row + 1, "screen") ? 0 : 6 * u;
        g.fillStyle(0x12151a).fillRect(x + 12 * u, y + top, t - 24 * u, t - top - bottom);
        g.fillStyle(0x3d8bd4).fillRect(x + 16 * u, y + top * 1.6, t - 32 * u, t - (top + bottom) * 1.6);
      }
    }

    // The edge line: a dark line exactly where the wall ends and a lighter one just inside
    // it, on every side that meets floor, glass or the sea. Drawn after all the tops.
    const edge = 2;
    eachTile((col, row, x, y) => {
      if (!isOpaque(col, row)) return;
      const open = (dc, dr) => inside(col + dc, row + dr) && !isOpaque(col + dc, row + dr);
      for (const [color, from, size] of [[WALL_EDGE, 0, edge + 1], [OUTLINE, 0, 1]]) {
        g.fillStyle(color);
        if (open(0, -1)) g.fillRect(x, y + from, t, size);
        if (open(0, 1)) g.fillRect(x, y + t - from - size, t, size);
        if (open(-1, 0)) g.fillRect(x + from, y, size, t);
        if (open(1, 0)) g.fillRect(x + t - from - size, y, size, t);
        // Where two walls meet in an inside corner, the line turns the corner.
        for (const [dc, dr] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
          if (open(dc, dr) && !open(dc, 0) && !open(0, dr)) {
            g.fillRect(dc < 0 ? x : x + t - size, dr < 0 ? y : y + t - size, size, size);
          }
        }
      }
    });

    // 5. Names: the areas (from "areas") and other places (from "labels").
    const nameStyle = (size) => ({
      fontFamily: FONT,
      fontSize: size,
      fontStyle: "bold",
      color: "#ffffff",
      stroke: "#1d1f24",
      strokeThickness: 3,
      resolution: TEXT_RESOLUTION,
    });
    for (const area of map.areas) {
      scene.add
        .text((area.x + area.w / 2) * t, (area.y + area.h - 0.8) * t, area.name.toUpperCase(), nameStyle("12px")) // bottom edge: furniture stands at the top
        .setLetterSpacing(1)
        .setOrigin(0.5, 0)
        .setAlpha(0.9);
    }
    for (const label of map.labels || []) {
      if (label.only_on_map) continue; // spec 018: the campus map's names of the table and the switch
      scene.add
        .text(label.x * t, label.y * t, label.text.toUpperCase(), nameStyle("10px")) // added as text, never HTML
        .setLetterSpacing(1)
        .setOrigin(0.5, 0)
        .setAlpha(0.85);
    }
    return { width: cols * t, height: rows * t };
  }

  // --- Characters --------------------------------------------------------------------

  // Our own figure: a round body in the player's colour with eyes, two feet, a
  // graduation cap and the nickname above. `half` is half the size of the player on
  // the server. The figure is drawn a little bigger than that (FIGURE_SCALE) so it reads
  // well; it may overlap a wall by a few pixels, the server's square never does.
  // Returns a container; move it with setPosition() and call animateCharacter() each frame.
  function makeCharacter(scene, { name, color, isOwn, half }) {
    const fill = colorOf(color);
    const radius = half + 1;

    const shadow = scene.add.ellipse(0, (half + 2) * FIGURE_SCALE, radius * 2.1, 8, 0x000000, 0.28);
    // Outlines are a dark shape behind a slightly smaller coloured one: smoother than a stroke.
    const footY = half - 0.5;
    const feet = [-1, 1].map((side) =>
      scene.add.container(side * 4.5, footY, [
        scene.add.ellipse(0, 0, 10, 8, OUTLINE),
        scene.add.ellipse(0, 0, 7, 5, shade(fill, 0.62)),
      ]),
    );
    const outline = scene.add.circle(0, 0, radius + 1.5, OUTLINE);
    const body = scene.add.circle(0, 0, radius, fill);
    const shine = scene.add.ellipse(-4.5, -5.5, 6, 3.5, 0xffffff, 0.35).setAngle(-28);
    const eyes = [-1, 1].map((side) => scene.add.ellipse(side * 3.7, -1, 5.2, 6.6, 0xffffff));
    const pupils = [-1, 1].map((side) => scene.add.circle(side * 3.7, -0.6, 1.6, OUTLINE));

    // Graduation cap: a band on the head, a flat board on top and a yellow tassel.
    const cap = scene.add.graphics();
    const top = -radius;
    cap.fillStyle(0x23262e).fillRoundedRect(-6.5, top - 0.5, 13, 5, 2);
    cap.fillStyle(0x2d313b);
    cap.fillPoints(
      [
        { x: -radius - 1, y: top - 1 },
        { x: 0, y: top - 5 },
        { x: radius + 1, y: top - 1 },
        { x: 0, y: top + 3 },
      ],
      true,
    );
    cap.lineStyle(1, 0x596072).lineBetween(-radius - 1, top - 1, 0, top - 5);
    cap.lineBetween(0, top - 5, radius + 1, top - 1);
    cap.lineStyle(1.2, 0xf2b33d).lineBetween(0, top - 1, 7.5, top - 0.5);
    cap.lineBetween(7.5, top - 0.5, 8, top + 4);
    cap.fillStyle(0xf2b33d).fillCircle(8, top + 5, 1.5);

    // Everything that bobs and floats together, apart from the shadow and the name.
    const figure = scene.add.container(0, 0, [...feet, outline, body, shine, ...eyes, ...pupils, cap]);
    figure.setScale(FIGURE_SCALE);

    const label = scene.add
      .text(0, (top - 7) * FIGURE_SCALE, name, {
        fontFamily: FONT,
        fontSize: "11px",
        fontStyle: "bold",
        color: isOwn ? OWN_NAME_COLOR : "#ffffff",
        stroke: "#101216",
        strokeThickness: 3,
        resolution: TEXT_RESOLUTION,
      })
      .setOrigin(0.5, 1);

    const sprite = scene.add.container(0, 0, [shadow, figure, label]);
    sprite.setDepth(isOwn ? 2 : 1);
    // The parts animateCharacter() moves, and where the eyes currently look.
    sprite.look = { shadow, feet, outline, figure, eyes, pupils, footY, faceX: 0, faceY: 0 };
    return sprite;
  }

  // Call every frame. dx and dy are the walking direction (-1, 0 or 1 each);
  // `time` is the game time in milliseconds. `lookAt` is optional: a direction {x, y}
  // of any length the eyes turn to instead (in a meeting: towards the meeting table).
  function animateCharacter(sprite, { dx, dy, ghost, lookAt }, time) {
    const look = sprite.look;
    const walking = dx !== 0 || dy !== 0;

    // Eyes turn smoothly towards the walking direction and stay there when standing.
    let faceX = dx;
    let faceY = dy;
    if (lookAt) {
      const length = Math.hypot(lookAt.x, lookAt.y) || 1;
      faceX = lookAt.x / length;
      faceY = lookAt.y / length;
    }
    if (walking || lookAt) {
      look.faceX += (faceX - look.faceX) * 0.25;
      look.faceY += (faceY - look.faceY) * 0.25;
    }
    look.eyes.forEach((eye, i) => eye.setPosition((i ? 1 : -1) * 3.7 + look.faceX * 1.6, -1 + look.faceY));
    look.pupils.forEach((pupil, i) =>
      pupil.setPosition((i ? 1 : -1) * 3.7 + look.faceX * 2.8, -0.6 + look.faceY * 2.2),
    );

    // Feet step in turn while walking; the body bobs a little with each step.
    const swing = walking ? Math.sin(time / 70) : 0;
    look.feet[0].setY(look.footY + swing * 1.8);
    look.feet[1].setY(look.footY - swing * 1.8);

    if (ghost) {
      // A ghost is half-transparent, has no feet, outline or shadow and floats up and down.
      sprite.setAlpha(0.5);
      look.figure.setY(-3 + Math.sin(time / 380) * 2);
    } else {
      sprite.setAlpha(1);
      look.figure.setY(walking ? -Math.abs(swing) * 0.9 : 0);
    }
    look.shadow.setVisible(!ghost);
    look.outline.setVisible(!ghost);
    look.feet.forEach((foot) => foot.setVisible(!ghost));
  }

  // --- Failed exams ------------------------------------------------------------------

  // The "6/20" sheet a student leaves on the floor.
  function makeExam(scene, exam) {
    // The sheet is wider than the "6/20" text (about 18 px), so the mark never sticks out
    // over the floor, where red on a red floor would be hard to read.
    const shadow = scene.add.rectangle(1.5, 2, 22, 25, 0x000000, 0.25);
    const sheet = scene.add.rectangle(0, 0, 22, 25, 0xffffff).setStrokeStyle(1, 0x8a8f99);
    const lines = scene.add.graphics();
    lines.fillStyle(0xb9bec8);
    for (const y of [-8.5, 5, 8]) lines.fillRect(-7, y, 14, 1);
    const mark = scene.add
      .text(0, -1.5, "6/20", {
        fontFamily: FONT,
        fontSize: "7px",
        fontStyle: "bold",
        color: "#d62828",
        resolution: TEXT_RESOLUTION,
      })
      .setOrigin(0.5);
    const container = scene.add.container(exam.x, exam.y, [shadow, sheet, lines, mark]);
    return container.setAngle(-10).setDepth(0.5); // on the floor, under the players
  }

  // --- Meeting point (spec 011) -----------------------------------------------------------

  // A round meeting table with a red emergency button on the tile the server's map names
  // ("meeting_point": [col, row]). `radius` is the table's radius on the server
  // (welcome.meeting_table_radius). It lies on the floor: players walk over it.
  function makeMeetingPoint(scene, map, radius) {
    const t = map.tile_size;
    const [col, row] = map.meeting_point;
    const g = scene.add.graphics();
    g.fillStyle(0x000000, 0.22).fillEllipse(3, 5, radius * 2 + 4, radius * 2 + 2); // shadow
    // Outlines are dark shapes behind slightly smaller coloured ones, as for the characters.
    g.fillStyle(OUTLINE).fillCircle(0, 0, radius);
    g.fillStyle(0xaab4c2).fillCircle(0, 0, radius - 1.5); // the rim
    g.fillStyle(0xe6ebf1).fillCircle(0, 0, radius - 5); // the table top
    g.fillStyle(0xffffff, 0.55).fillEllipse(-radius * 0.35, -radius * 0.45, radius * 0.7, radius * 0.3);
    // The emergency button: a yellow and black base with a red dome.
    g.fillStyle(OUTLINE).fillCircle(0, -4, 14.5);
    g.fillStyle(0xf5d547).fillCircle(0, -4, 13);
    g.fillStyle(OUTLINE);
    for (let i = 0; i < 8; i += 2) g.slice(0, -4, 13, (i * Math.PI) / 4, ((i + 1) * Math.PI) / 4).fillPath();
    g.fillStyle(OUTLINE).fillCircle(0, -4, 9.5);
    g.fillStyle(0xd62828).fillCircle(0, -4, 8);
    g.fillStyle(0xff7a6b).fillCircle(0, -5, 5.5);
    g.fillStyle(0xffffff, 0.6).fillEllipse(-2.5, -7.5, 5, 2.5);
    const label = scene.add
      .text(0, 14, "MEETING", {
        fontFamily: FONT,
        fontSize: "9px",
        fontStyle: "bold",
        color: "#23262e",
        resolution: TEXT_RESOLUTION,
      })
      .setLetterSpacing(1.5)
      .setOrigin(0.5, 0);
    // On the floor: over a failed exam, under the players.
    return scene.add.container((col + 0.5) * t, (row + 0.5) * t, [g, label]).setDepth(0.6);
  }

  // --- Vents (spec 015) -----------------------------------------------------------------

  // A hatch in the floor on a tile the server's map names ("vents"). Everyone sees the
  // hatches; only examiners can climb in. The lid slides aside while the hatch is open.
  function makeVent(scene, map, vent) {
    const t = map.tile_size;
    const hole = scene.add.graphics();
    hole.fillStyle(OUTLINE).fillRoundedRect(-13, -13, 26, 26, 4);
    hole.fillStyle(0x0b0c10).fillRoundedRect(-10.5, -10.5, 21, 21, 3); // the dark shaft
    // Two eyes in the dark: only shown to the examiner who sits in this vent.
    const eyes = scene.add.graphics();
    eyes.fillStyle(0xffffff).fillEllipse(-4, 0, 5.5, 7).fillEllipse(4, 0, 5.5, 7);
    eyes.fillStyle(OUTLINE).fillCircle(-3.4, 0.6, 1.7).fillCircle(4.6, 0.6, 1.7);
    const lid = scene.add.graphics();
    lid.fillStyle(OUTLINE).fillRoundedRect(-12.5, -12.5, 25, 25, 4);
    lid.fillStyle(0x6a7183).fillRoundedRect(-11, -11, 22, 22, 3); // the metal plate
    lid.fillStyle(0x23262e);
    for (const y of [-7.5, -1.5, 4.5]) lid.fillRect(-8, y, 16, 3); // three slats
    lid.fillStyle(0xf2b33d).fillCircle(8, -8, 1.6); // a small handle
    const hatch = scene.add.container((vent.x + 0.5) * t, (vent.y + 0.5) * t, [hole, eyes, lid]).setDepth(0.4);
    hatch.parts = { lid, eyes, slide: 0 };
    return hatch;
  }

  // Call every frame. `open`: the server says this hatch shows open (someone just climbed
  // in or out). `occupied`: the own character sits inside: the lid stays ajar and its eyes
  // look out. The lid glides between closed (0) and fully aside (1).
  function updateVent(hatch, { open, occupied }, time) {
    const { lid, eyes } = hatch.parts;
    const target = open ? 1 : occupied ? 0.55 : 0;
    hatch.parts.slide += (target - hatch.parts.slide) * 0.3;
    const slide = hatch.parts.slide;
    lid.setPosition(slide * 15, slide * -12).setAngle(slide * 24);
    eyes.setVisible(occupied && slide > 0.2);
    if (occupied) eyes.setX(Math.sin(time / 600) * 1.5); // looking left and right
  }

  // --- Light switch (spec 008, part 8) ---------------------------------------------------

  // The switch on the tile the server's map names ("light_switch"), and a flashing mark
  // above it that only shows while the lights are off. The mark is drawn above the
  // darkness, so students find the switch.
  function makeSwitch(scene, map) {
    const t = map.tile_size;
    const x = (map.light_switch[0] + 0.5) * t;
    const y = (map.light_switch[1] + 0.5) * t;
    const plate = scene.add.graphics();
    plate.fillStyle(OUTLINE).fillRoundedRect(-8, -11, 16, 22, 3);
    plate.fillStyle(0xe9ecef).fillRoundedRect(-6.5, -9.5, 13, 19, 2);
    plate.fillStyle(0x9aa0aa).fillRoundedRect(-2.5, -5, 5, 10, 1.5); // the lever's slot
    plate.fillStyle(0x23262e).fillRoundedRect(-2.5, -5, 5, 5, 1.5); // the lever, up
    scene.add.container(x, y, [plate]).setDepth(0.6);

    const bolt = scene.add.graphics();
    bolt.fillStyle(OUTLINE, 0.9).fillCircle(0, 0, 12);
    bolt.lineStyle(2, 0xf5d547).strokeCircle(0, 0, 12);
    bolt.fillStyle(0xf5d547).fillPoints(
      [
        { x: 2, y: -8 },
        { x: -5, y: 1 },
        { x: -1, y: 1 },
        { x: -2, y: 8 },
        { x: 5, y: -2 },
        { x: 1, y: -2 },
      ],
      true,
    );
    return scene.add.container(x, y - 26, [bolt]).setDepth(11).setVisible(false);
  }

  // Call every frame with the mark from makeSwitch(): shown and flashing while `off`,
  // faint while the own character stands at the switch (`near`), so it does not cover the name.
  function updateSwitch(mark, off, time, near) {
    mark.setVisible(off);
    if (off) mark.setAlpha(near ? 0.25 : 0.65 + 0.35 * Math.sin(time / 180));
  }

  // --- Tasks (spec 004) -------------------------------------------------------------------

  const TASK_COLOR = 0x4cb963; // the green of the task button and bar (style.css)

  // Task places (spec 015): every task station of the map is an object that belongs to
  // its task's story, drawn on the floor under the characters. Which object is chosen by the
  // station's mini-game kind, so the map needs no extra data. Everyone sees the objects;
  // only a player's own open ones glow (see makeTaskGlow).
  const TASK_OBJECTS = {
    paper_jam: drawPrinter, // "Print ..." in the Library
    ticket: drawTicketMachine, // "Submit your Bachelor certificate" at Student Services
    translate: drawHelpdeskSign, // "Ask the Helpdesk for help"
    cable: drawProjector, // "Get your slides on the projector"
    card: drawCardGate, // "Tap your student card at the gate"
    seagull: drawNataPlate, // "Eat your pastel de nata in the sun"
  };

  // Every station of the map's tasks as {x, y, minigame} in tiles (a task without "steps"
  // is one station itself).
  function taskStations(map) {
    return (map.tasks || []).flatMap((task) => task.steps || [task]);
  }

  function makeTaskPlace(scene, map, station) {
    const t = map.tile_size;
    const g = scene.add.graphics();
    const parts = [g];
    const draw = TASK_OBJECTS[station.minigame] || drawClipboard;
    draw(g, (text, x, y, size, color) => {
      parts.push(
        scene.add
          .text(x, y, text, { fontFamily: FONT, fontSize: size, fontStyle: "bold", color, resolution: TEXT_RESOLUTION })
          .setOrigin(0.5),
      );
    });
    return scene.add.container((station.x + 0.5) * t, (station.y + 0.5) * t, parts).setDepth(0.45);
  }

  // Each object is drawn around (0, 0) within about 28 x 28 px: a soft shadow, a dark
  // outline shape, then the coloured shapes on top (as for the characters).
  function drawPrinter(g) {
    g.fillStyle(0x000000, 0.22).fillRoundedRect(-11, -5, 26, 19, 4);
    g.fillStyle(0xffffff).fillRect(-7, -14, 14, 9); // the paper going in
    g.lineStyle(1, 0x8a8f99).strokeRect(-7, -14, 14, 9);
    g.fillStyle(OUTLINE).fillRoundedRect(-13, -8, 26, 19, 4);
    g.fillStyle(0xd9dde4).fillRoundedRect(-11.5, -6.5, 23, 16, 3); // the body
    g.fillStyle(0x596072).fillRect(-9, -3, 18, 3); // the slot
    g.fillStyle(0xffffff).fillRect(-7, 2, 14, 7); // a printed page, half out
    g.fillStyle(0xb9bec8).fillRect(-5, 4, 10, 1).fillRect(-5, 6, 7, 1);
    g.fillStyle(0xe5484d).fillCircle(8.5, -4.5, 1.6); // the red "paper jam" light
  }

  function drawTicketMachine(g, text) {
    g.fillStyle(0x000000, 0.22).fillRoundedRect(-8, -10, 20, 26, 4);
    g.fillStyle(OUTLINE).fillRoundedRect(-10, -13, 20, 26, 4);
    g.fillStyle(0xb3261e).fillRoundedRect(-8.5, -11.5, 17, 23, 3); // the red kiosk
    g.fillStyle(0x14161b).fillRoundedRect(-6.5, -9.5, 13, 8, 1.5); // "now serving" display
    g.fillStyle(0xfff3d6).fillRect(-4, 2, 8, 9); // the ticket coming out
    g.lineStyle(1, 0xb9a773).lineBetween(-2.5, 5, 2.5, 5).lineBetween(-2.5, 7.5, 2.5, 7.5);
    g.fillStyle(0x14161b).fillRect(-5.5, 0.5, 11, 2);
    text("A12", 0, -5.5, "7px", "#7dff9a");
  }

  function drawHelpdeskSign(g, text) {
    g.fillStyle(0x000000, 0.22).fillEllipse(2, 12, 20, 6);
    g.fillStyle(0x596072).fillRect(-1, 2, 2, 10); // the stand
    g.fillStyle(OUTLINE).fillRoundedRect(-6, 10, 12, 4, 2);
    g.fillStyle(OUTLINE).fillCircle(0, -4, 11.5);
    g.fillStyle(0x1f5fd4).fillCircle(0, -4, 10); // the blue info sign
    g.fillStyle(0xffffff, 0.25).fillEllipse(-3, -8, 9, 4);
    text("?", 0, -4, "15px", "#ffffff");
  }

  function drawProjector(g) {
    g.fillStyle(0x78b4f0, 0.28).fillTriangle(0, -6, -12, -16, 12, -16); // the light it throws
    g.fillStyle(0x000000, 0.22).fillRoundedRect(-10, -3, 24, 15, 4);
    g.fillStyle(OUTLINE).fillRoundedRect(-12, -6, 24, 15, 4);
    g.fillStyle(0xe9ecef).fillRoundedRect(-10.5, -4.5, 21, 12, 3); // the body
    g.fillStyle(OUTLINE).fillCircle(-4, 1.5, 5);
    g.fillStyle(0x3d8bd4).fillCircle(-4, 1.5, 3.6); // the lens
    g.fillStyle(0xffffff, 0.7).fillCircle(-5.2, 0.3, 1.2);
    g.fillStyle(0x9aa0aa).fillRect(4, -2, 5, 1.5).fillRect(4, 1, 5, 1.5).fillRect(4, 4, 5, 1.5); // air slits
    // The loose cable: a short wavy line ending in a plug.
    g.lineStyle(2, OUTLINE);
    g.beginPath();
    g.moveTo(9, 8);
    g.lineTo(11, 12);
    g.lineTo(7, 14);
    g.lineTo(11, 16);
    g.strokePath();
    g.fillStyle(0xf2b33d).fillRect(9.5, 15, 4, 3);
  }

  function drawCardGate(g) {
    g.fillStyle(0x000000, 0.22).fillRoundedRect(-12, 6, 28, 7, 3);
    for (const x of [-13, 7]) {
      g.fillStyle(OUTLINE).fillRoundedRect(x, -11, 7, 22, 2.5);
      g.fillStyle(0x9aa0aa).fillRoundedRect(x + 1.2, -9.8, 4.6, 19.6, 1.5); // the two posts
    }
    g.fillStyle(OUTLINE).fillRect(-7, -2.5, 15, 5);
    g.fillStyle(0xf5d547).fillRect(-7, -1.5, 15, 3); // the yellow arm
    g.fillStyle(OUTLINE).fillRect(-3, -1.5, 2.5, 3).fillRect(2.5, -1.5, 2.5, 3);
    g.fillStyle(0x14161b).fillRoundedRect(7.8, -9, 5.4, 7, 1); // the card reader
    g.fillStyle(0x4cb963).fillCircle(10.5, -5.5, 1.6); // "beep": the green light
  }

  function drawNataPlate(g) {
    g.fillStyle(0x000000, 0.2).fillEllipse(2, 4, 26, 22);
    g.fillStyle(OUTLINE).fillCircle(0, 0, 12.5);
    g.fillStyle(0xffffff).fillCircle(0, 0, 11); // the plate
    g.lineStyle(1, 0xc9d2de).strokeCircle(0, 0, 8.5);
    g.fillStyle(0xb9793a).fillCircle(0, 0, 7); // the pastry
    g.fillStyle(0xe8a33d).fillCircle(0, 0, 5.4); // the custard
    g.fillStyle(0x7a4a16, 0.7).fillCircle(-1.6, -1.2, 1.5).fillCircle(1.8, 1.4, 1.2); // burnt spots
  }

  // A station without a mini-game (only the small test maps): a clipboard.
  function drawClipboard(g) {
    g.fillStyle(OUTLINE).fillRoundedRect(-9, -11, 18, 22, 3);
    g.fillStyle(0xb07a45).fillRoundedRect(-7.5, -9.5, 15, 19, 2);
    g.fillStyle(0xffffff).fillRect(-5.5, -6, 11, 13);
    g.fillStyle(0x596072).fillRoundedRect(-3.5, -11.5, 7, 4, 1.5);
  }

  // The soft green glow on one of the player's own open task places (spec 015; it replaces
  // the "!" mark). It is drawn above the darkness, so it also shows outside the vision
  // radius: a player's own tasks are no secret. A finished task loses it (main.js).
  function makeTaskGlow(scene, task) {
    const g = scene.add.graphics();
    for (const [radius, alpha] of [[24, 0.1], [20, 0.12], [16, 0.16]]) g.fillStyle(TASK_COLOR, alpha).fillCircle(0, 0, radius);
    g.lineStyle(2, TASK_COLOR, 0.95).strokeRoundedRect(-16, -16, 32, 32, 8);
    return scene.add.container(task.x, task.y, [g]).setDepth(11);
  }

  // Call every frame: the glow breathes slowly, and is faint while the own character
  // stands at the place (`near`), so it does not cover the face.
  function updateTaskGlow(glow, time, near) {
    const breath = 0.5 + 0.5 * Math.sin(time / 320);
    glow.setAlpha(near ? 0.2 + 0.15 * breath : 0.6 + 0.4 * breath);
  }

  // The ring around the own character while a task runs, with the seconds left below.
  function makeTaskRing(scene) {
    const arc = scene.add.graphics();
    const label = scene.add
      .text(0, 27, "", {
        fontFamily: FONT,
        fontSize: "11px",
        fontStyle: "bold",
        color: "#ffffff",
        stroke: "#101216",
        strokeThickness: 3,
        resolution: TEXT_RESOLUTION,
      })
      .setOrigin(0.5, 0);
    const ring = scene.add.container(0, 0, [arc, label]).setDepth(12).setVisible(false);
    ring.parts = { arc, label };
    return ring;
  }

  // Call every frame. `fraction` is how much of the task is done (0-1), or null: no ring.
  function updateTaskRing(ring, x, y, fraction, secondsLeft) {
    ring.setVisible(fraction !== null);
    if (fraction === null) return;
    ring.setPosition(x, y);
    const { arc, label } = ring.parts;
    const start = -Math.PI / 2; // 12 o'clock
    arc.clear();
    arc.lineStyle(6, 0x101216, 0.75).strokeCircle(0, 0, 23);
    arc.lineStyle(4, TASK_COLOR).beginPath();
    arc.arc(0, 0, 23, start, start + Math.PI * 2 * fraction, false);
    arc.strokePath();
    label.setText(`${secondsLeft} s`);
  }

  // --- Edge arrows (spec 012) ---------------------------------------------------------------
  // A small arrow at the screen's edge for an own open task place the camera cannot currently
  // see (the map marker above is enough once it can) — just the arrowhead shape, no task
  // title or other text next to it. Clamped inside a safe rectangle, inset from the camera's
  // visible area (`camera.worldView`) by a margin that clears the joystick and the action
  // buttons (style.css) on every window size. The margin is given in CSS pixels and turned
  // into world units by dividing by the camera's own zoom, which already includes
  // `pixelRatio` (see cameraZoom()), so the arrow stays the same size on screen regardless of
  // zoom.
  const ARROW_SIDE_MARGIN = 54;
  const ARROW_TOP_MARGIN = 54;
  // Clears the joystick (left) and the action bar (right). The action bar's own height
  // depends on the player's role and the window size (spec 014: up to 6 round buttons for
  // an examiner, 3 for a student), so updateEdgeArrow() takes the real one from main.js and
  // only falls back to this fixed value before the bar exists.
  const ARROW_BOTTOM_MARGIN = 150;
  const ARROW_SIZE = 16; // the arrowhead's half-length, in screen px

  function makeEdgeArrow(scene) {
    const g = scene.add.graphics();
    g.fillStyle(OUTLINE, 0.9);
    g.beginPath();
    g.moveTo(ARROW_SIZE, 0);
    g.lineTo(-ARROW_SIZE * 0.6, -ARROW_SIZE * 0.75);
    g.lineTo(-ARROW_SIZE * 0.6, ARROW_SIZE * 0.75);
    g.closePath();
    g.fillPath();
    g.lineStyle(2, TASK_COLOR, 1).strokePath();
    const arrow = scene.add.container(0, 0, [g]).setDepth(13).setVisible(false);
    arrow.parts = { g };
    return arrow;
  }

  // Call every frame for an own open task. Shows the arrow, clamped just inside the camera's
  // visible area, only while the task's place is outside that area. `bottomMargin` (CSS
  // px) is the action bar's own measured height plus a gap, from main.js; ARROW_BOTTOM_MARGIN
  // is only the fallback before that bar exists.
  function updateEdgeArrow(arrow, task, camera, bottomMargin = ARROW_BOTTOM_MARGIN) {
    const view = camera.worldView;
    const inView = task.x >= view.x && task.x <= view.right && task.y >= view.y && task.y <= view.bottom;
    arrow.setVisible(!inView);
    if (inView) return;

    const scale = 1 / camera.zoom;
    const left = view.x + ARROW_SIDE_MARGIN * scale;
    const right = view.right - ARROW_SIDE_MARGIN * scale;
    const top = view.y + ARROW_TOP_MARGIN * scale;
    const bottom = view.bottom - bottomMargin * scale;
    const cx = (left + right) / 2;
    const cy = (top + bottom) / 2;
    const angle = Math.atan2(task.y - cy, task.x - cx);
    const dx = Math.cos(angle);
    const dy = Math.sin(angle);
    // Where the ray from the centre, at this angle, meets the safe rectangle's border.
    const tx = dx === 0 ? Infinity : (dx > 0 ? right - cx : left - cx) / dx;
    const ty = dy === 0 ? Infinity : (dy > 0 ? bottom - cy : top - cy) / dy;
    const t = Math.min(tx, ty);
    arrow.setPosition(cx + dx * t, cy + dy * t);
    arrow.setScale(scale);
    arrow.parts.g.setRotation(angle);
  }

  // --- Darkness outside the lit area (spec 005, spec 010, spec 011) -------------------------
  // This is only the look: the server does not even send what the player cannot see.
  //
  // The darkness has ONE strength everywhere and is made of two parts that never overlap:
  //   dark: a plain dark sheet over the whole map, with the lit area and the walls cut
  //         out of it;
  //   rim:  a round picture, clear in the middle and just as dark as the sheet from the
  //         vision radius on. It follows the own character and is drawn only inside the
  //         lit area, so it gives the vision circle its soft edge.
  // The camera never shows more than the map, so the sheet covers every window size.
  //
  // The lit area is what the own character has a straight line of sight to: a shape with
  // straight shadow edges behind walls (see castRays). It ends at the face of a wall: no
  // light shines into a wall (spec 011). Glass and the sea do not block sight, so the light
  // goes through them. `lit` holds that shape. It is never drawn itself: it only cuts.
  //
  // Walls are neither lit nor darkened (spec 011): `cut` holds the lit area plus every
  // wall tile that blocks sight, and the dark sheet is drawn everywhere but there. So a
  // wall looks the same in light and in darkness, and never hides the cap or the name of
  // a character standing right below it.
  // `sight` is the server's sight grid from "welcome": "#" marks a tile that blocks sight.
  function makeDarkness(scene, map, sight, radius) {
    const t = map.tile_size;
    const lit = scene.make.graphics({}, false);
    const cut = scene.make.graphics({}, false);
    const dark = scene.add.rectangle(0, 0, sight[0].length * t, sight.length * t, FOG_COLOR, FOG_ALPHA);
    dark.setOrigin(0).setDepth(10).setAlpha(0);
    dark.setMask(cut.createGeometryMask().setInvertAlpha(true)); // everywhere but the cut

    // The rim picture is painted once for a radius of 1 and stretched to the radius in use.
    const size = RIM_TEXTURE_SIZE;
    const texture = scene.textures.createCanvas("rim", size, size);
    const context = texture.getContext();
    const centre = size / 2;
    const scale = centre / RIM_REACH; // texture pixels per vision radius
    const gradient = context.createRadialGradient(
      centre, centre, FOG_CLEAR * scale,
      centre, centre, FOG_FULL * scale,
    );
    const [red, green, blue] = [FOG_COLOR >> 16, (FOG_COLOR >> 8) & 255, FOG_COLOR & 255];
    gradient.addColorStop(0, `rgba(${red}, ${green}, ${blue}, 0)`);
    gradient.addColorStop(0.55, `rgba(${red}, ${green}, ${blue}, ${FOG_ALPHA * 0.45})`);
    gradient.addColorStop(1, `rgba(${red}, ${green}, ${blue}, ${FOG_ALPHA})`);
    context.fillStyle = gradient;
    context.fillRect(0, 0, size, size);
    texture.refresh();
    const rim = scene.add.image(0, 0, "rim").setDepth(10).setAlpha(0);
    rim.setMask(lit.createGeometryMask()); // only inside the lit area

    // `radius` is the radius shown right now: it glides to the one the server sends.
    // `drawnFor` remembers the place and radius the lit area was last worked out for.
    const edges = sightEdges(sight, t);
    return { lit, cut, dark, rim, radius, edges, walls: wallRects(sight, t), drawnFor: "" };
  }

  // The wall tiles that block sight as rectangles {x, y, width, height} in map pixels, one
  // per unbroken run of tiles in a row. Worked out once per map.
  function wallRects(sight, t) {
    const rects = [];
    sight.forEach((line, row) => {
      let start = null;
      for (let col = 0; col <= line.length; col++) {
        const wall = col < line.length && line[col] === "#";
        if (wall && start === null) start = col;
        if (!wall && start !== null) {
          rects.push({ x: start * t, y: row * t, width: (col - start) * t, height: t });
          start = null;
        }
      }
    });
    return rects;
  }

  // The straight edges that stop sight: every side on which a sight-blocking tile meets a
  // tile that does not block. Sides that continue each other are merged into one long edge
  // {x1, y1, x2, y2} (in map pixels, x1 <= x2 and y1 <= y2). Worked out once per map.
  function sightEdges(sight, t) {
    const rows = sight.length;
    const cols = sight[0].length;
    const blocks = (col, row) => row >= 0 && row < rows && col >= 0 && col < cols && sight[row][col] === "#";
    const edges = [];
    // Horizontal edges lie on the grid line above row `row`, vertical ones left of `col`.
    for (let row = 0; row <= rows; row++) {
      let start = null;
      for (let col = 0; col <= cols; col++) {
        const isEdge = col < cols && blocks(col, row - 1) !== blocks(col, row);
        if (isEdge && start === null) start = col;
        if (!isEdge && start !== null) {
          edges.push({ x1: start * t, y1: row * t, x2: col * t, y2: row * t });
          start = null;
        }
      }
    }
    for (let col = 0; col <= cols; col++) {
      let start = null;
      for (let row = 0; row <= rows; row++) {
        const isEdge = row < rows && blocks(col - 1, row) !== blocks(col, row);
        if (isEdge && start === null) start = row;
        if (!isEdge && start !== null) {
          edges.push({ x1: col * t, y1: start * t, x2: col * t, y2: row * t });
          start = null;
        }
      }
    }
    return edges;
  }

  // Rays from (x, y) in all directions that matter: FAN_RAYS evenly spread ones and, for
  // both ends of every nearby edge, one straight at the end and one just left and right of
  // it (the last two decide whether the light stops at the corner or passes it). Each ray
  // ends at the nearest edge it hits, or after `reach` pixels. Returns where the rays end,
  // in order around the circle, as {x, y}.
  function castRays(edges, x, y, reach) {
    const near = edges.filter(
      (e) => e.x2 >= x - reach && e.x1 <= x + reach && e.y2 >= y - reach && e.y1 <= y + reach,
    );
    const angles = [];
    for (let i = 0; i < FAN_RAYS; i++) angles.push((i / FAN_RAYS) * 2 * Math.PI - Math.PI);
    for (const e of near) {
      for (const [cornerX, cornerY] of [[e.x1, e.y1], [e.x2, e.y2]]) {
        const angle = Math.atan2(cornerY - y, cornerX - x);
        for (const nudged of [angle - RAY_NUDGE, angle, angle + RAY_NUDGE]) {
          // Kept between -PI and PI, so sorting puts the rays in order around the circle.
          angles.push(Math.atan2(Math.sin(nudged), Math.cos(nudged)));
        }
      }
    }
    angles.sort((a, b) => a - b);
    return angles.map((angle) => {
      const dx = Math.cos(angle);
      const dy = Math.sin(angle);
      let distance = reach;
      for (const e of near) {
        // Edges are horizontal or vertical, so a ray meets one where it crosses its line.
        if (e.y1 === e.y2) {
          const d = (e.y1 - y) / dy;
          const at = x + dx * d;
          if (d > 0 && d < distance && at >= e.x1 && at <= e.x2) distance = d;
        } else {
          const d = (e.x1 - x) / dx;
          const at = y + dy * d;
          if (d > 0 && d < distance && at >= e.y1 && at <= e.y2) distance = d;
        }
      }
      return { x: x + dx * distance, y: y + dy * distance };
    });
  }

  // Works out the lit area around (x, y): a triangle from (x, y) to every two neighbouring
  // ray ends. Together they are the visibility polygon, with straight shadow edges where a
  // ray passes a wall corner, ending exactly at the faces of the walls. It is drawn into
  // `lit` (for the rim) and, together with the wall tiles, into `cut` (for the dark sheet).
  function drawLitArea(darkness, x, y) {
    const { lit, cut } = darkness;
    const ends = castRays(darkness.edges, x, y, darkness.radius * LIT_REACH);
    lit.clear().fillStyle(0xffffff);
    cut.clear().fillStyle(0xffffff);
    ends.forEach((a, i) => {
      const b = ends[(i + 1) % ends.length];
      lit.fillTriangle(x, y, a.x, a.y, b.x, b.y);
      cut.fillTriangle(x, y, a.x, a.y, b.x, b.y);
    });
    for (const wall of darkness.walls) cut.fillRect(wall.x, wall.y, wall.width, wall.height);
  }

  // Call every frame with the own character's place: keeps the rim centred on it, lets
  // the shown radius glide to `radius` (lights out and back on) and fades the whole
  // darkness in or out. The lit area is only worked out again when the own character has
  // moved or the shown radius has changed. Without darkness (ghost, lobby, end) the last
  // lit area stays, so the darkness can fade out.
  function updateDarkness(darkness, x, y, radius, on) {
    const { dark, rim } = darkness;
    const gap = radius - darkness.radius;
    darkness.radius = Math.abs(gap) < 0.5 ? radius : darkness.radius + gap * 0.12;
    const side = darkness.radius * RIM_REACH * 2;
    rim.setPosition(x, y).setDisplaySize(side, side);
    const target = on ? 1 : 0;
    const alpha = rim.alpha + (target - rim.alpha) * 0.12;
    const shown = Math.abs(alpha - target) < 0.01 ? target : alpha;
    rim.setAlpha(shown);
    dark.setAlpha(shown);
    const drawnFor = `${x},${y},${darkness.radius}`;
    if (on && drawnFor !== darkness.drawnFor) {
      darkness.drawnFor = drawnFor;
      drawLitArea(darkness, x, y);
    }
  }

  return {
    BACKDROP,
    pixelRatio,
    colorCss,
    cameraZoom,
    drawMap,
    makeCharacter,
    animateCharacter,
    makeExam,
    makeMeetingPoint,
    makeVent,
    updateVent,
    makeSwitch,
    updateSwitch,
    taskStations,
    makeTaskPlace,
    makeTaskGlow,
    updateTaskGlow,
    makeTaskRing,
    updateTaskRing,
    makeEdgeArrow,
    updateEdgeArrow,
    makeDarkness,
    updateDarkness,
  };
})();
