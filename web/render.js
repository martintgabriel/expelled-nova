// All drawing code (spec 005): the map, the characters, the failed exams, the bell, the staff
// doors, the light switch, the task markers and the darkness.
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
  // Spec 009: the Nova campus. The grid says where one can walk; the optional "decor" list
  // says how tiles look (solid kinds sit on wall tiles, floor kinds are painted on floor
  // tiles) and "labels" name places that are not areas. Drawn once when the scene starts.

  const FLOOR_A = 0xf0f1f2; // polished concrete, two shades for a tiled look
  const FLOOR_B = 0xe8eaec;
  const OUTSIDE = 0x2f3439; // around the campus: not part of the game
  const ROOF = 0xc3c6c8; // a building wall seen from above
  const GLASS = 0x9cc3d6;
  const GLASS_EDGE = 0xc9dde7;
  const SOLID_ORDER = [
    "sea", "solar", "greenroof", "roof", "glasswall", "counter", "shelf", "desk", "studytable",
    "table", "cafetable", "woodtable", "shopshelf", "foodcounter", "piano", "screen", "steps",
    "picnic", "tree",
  ];
  const FLOOR_ORDER = ["shopfloor", "sand", "paving", "grass", "terrace", "pergola", "glassroof", "seats", "beanbag"];
  const OUTDOOR_FLOOR = { paving: [0xd2c4aa, 0xcabb9f], grass: [0x86b45a, 0x86b45a], terrace: [0xe9e6df, 0xe1ddd4] };
  const BEANBAG_COLORS = [0xd9412e, 0xf2b632, 0x4caf50, 0xd9412e, 0x2f80c3];
  const PRODUCT_COLORS = [0xe53935, 0x43a047, 0xfdd835, 0x1e88e5, 0xfb8c00, 0x8e24aa];
  const BOOK_COLORS = [0xc0392b, 0xe6b33a, 0x2e86c1, 0xf4f1e8, 0x27ae60];

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
  function drawMap(scene, map) {
    const t = map.tile_size;
    const rows = map.grid.length;
    const cols = map.grid[0].length;
    const isFloor = (col, row) => row >= 0 && row < rows && col >= 0 && col < cols && map.grid[row][col] === ".";
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
          if (solid === isFloor(col, row)) continue; // solid on walls, floor kinds on floor
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
      if (area && area.name !== "Courtyard") rect(col, row, Phaser.Display.Color.HexStringToColor(area.color).color, 0.31);
    };
    // The ground under a tree or table outdoors: the paving, grass or terrace next to it.
    const groundNear = (col, row) => {
      for (const [dc, dr] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        for (const kind of ["paving", "grass", "terrace"]) if (has(col + dc, row + dr, kind)) return kind;
      }
      return null;
    };

    g.fillStyle(BACKDROP).fillRect(0, 0, cols * t, rows * t);

    // 1. Floor: polished concrete, the area's tint, then the floor decor.
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        if (!isFloor(col, row)) continue;
        const x = col * t;
        const y = row * t;
        rect(col, row, (col + row) % 2 ? FLOOR_A : FLOOR_B);
        if ((col * 7 + row * 3) % 5 === 0) {
          g.lineStyle(3 * u, 0xffffff, 0.5).lineBetween(x + 6 * u, y + t - 8 * u, x + t - 10 * u, y + 8 * u);
        }
        tint(col, row);
        const here = kindsAt(col, row);
        for (const kind of FLOOR_ORDER) {
          if (!here.includes(kind)) continue;
          drawFloorDecor(kind, col, row, x, y);
        }
      }
    }

    function drawFloorDecor(kind, col, row, x, y) {
      if (kind === "shopfloor") {
        rect(col, row, 0xc42828, 0.27);
        g.lineStyle(1, 0xa01e1e, 0.35).strokeRect(x, y, t, t);
      } else if (kind === "sand") {
        rect(col, row, (col + row) % 2 ? 0xead6a6 : 0xe6d19e);
        g.fillStyle(0xcdb47c);
        for (let i = 0; i < 7; i++) g.fillCircle(x + (3 + random() * 46) * u, y + (3 + random() * 46) * u, 1.6 * u);
        if (row % 6 === 2) g.fillStyle(0xf6efe2).fillEllipse(x + 34 * u, y + 33 * u, 8 * u, 6 * u);
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
        if (col !== 29) {
          // A seat facing north (towards the screen): backrest at the bottom.
          g.fillStyle(0x5f8a4a).fillRect(x + 6 * u, y + 6 * u, t - 12 * u, t - 20 * u);
          g.fillStyle(0x3f6331).fillRect(x + 6 * u, y + t - 16 * u, t - 12 * u, 10 * u);
        }
      } else if (kind === "beanbag") {
        g.fillStyle(0x000000, 0.2).fillEllipse(x + 28 * u, y + 30 * u, 38 * u, 36 * u);
        g.fillStyle(BEANBAG_COLORS[(col * 3 + row) % 5]).fillEllipse(x + 25 * u, y + 25 * u, 38 * u, 36 * u);
        g.fillStyle(0xffffff, 0.27).fillEllipse(x + 22 * u, y + 22 * u, 14 * u, 12 * u);
      }
    }

    // 2. Walls: building walls with glass facades, the outside, and the solid decor.
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        if (isFloor(col, row)) continue;
        const x = col * t;
        const y = row * t;
        const kind = SOLID_ORDER.find((k) => has(col, row, k));
        if (kind) {
          drawSolidDecor(kind, col, row, x, y);
          continue;
        }
        let near = false;
        for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) near = near || isFloor(col + dc, row + dr);
        if (!near) {
          rect(col, row, OUTSIDE);
          continue;
        }
        rect(col, row, ROOF);
        if (isFloor(col, row + 1)) {
          // A glass facade facing the floor below, with slim white columns and a shadow.
          const top = y + t * 0.55;
          g.fillStyle(GLASS).fillRect(x, top, t, y + t - top);
          g.fillStyle(0xffffff).fillRect(x, top - 1, t, 3 * u);
          g.fillRect(x + 6 * u, top, 3 * u, y + t - top);
          g.fillRect(x + t - 8 * u, top, 3 * u, y + t - top);
          g.fillStyle(0x000000, 0.12).fillRect(x, y + t, t, 9 * u);
        }
        g.fillStyle(GLASS_EDGE);
        if (isFloor(col, row - 1)) g.fillRect(x, y, t, 4 * u);
        if (isFloor(col - 1, row)) g.fillRect(x, y, 4 * u, t);
        if (isFloor(col + 1, row)) g.fillRect(x + t - 5 * u, y, 5 * u, t);
      }
    }

    function drawSolidDecor(kind, col, row, x, y) {
      const furniture = () => {
        // Furniture stands on the room's floor.
        rect(col, row, FLOOR_A);
        tint(col, row);
      };
      const outdoor = () => {
        const ground = groundNear(col, row);
        if (ground) rect(col, row, OUTDOOR_FLOOR[ground][0]);
        else furniture();
      };
      if (kind === "sea") {
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
      } else if (kind === "solar") {
        rect(col, row, 0x9aa0a8);
        g.fillStyle(0x253a66).fillRect(x + 3 * u, y + 3 * u, t - 6 * u, t - 6 * u);
        g.lineStyle(2 * u, 0x5b7cbf).lineBetween(x + t / 2, y + 3 * u, x + t / 2, y + t - 3 * u);
        g.lineBetween(x + 3 * u, y + t / 2, x + t - 3 * u, y + t / 2);
      } else if (kind === "greenroof") {
        rect(col, row, 0x7da35a);
        g.fillStyle(0x6a9149);
        for (let i = 0; i < 4; i++) g.fillCircle(x + (6 + random() * 40) * u, y + (6 + random() * 40) * u, 3 * u);
        g.lineStyle(2 * u, 0xd8dcdf);
        for (let o = 0; o < 52; o += 9) g.lineBetween(x + o * u, y + t - 2 * u, x + (o + 6) * u, y + t - 10 * u);
        g.lineBetween(x, y + t - 10 * u, x + t, y + t - 10 * u);
      } else if (kind === "roof") {
        rect(col, row, 0xecebe6);
        g.fillStyle(0xd6d4cd).fillRect(x, y, t, 3 * u);
      } else if (kind === "glasswall") {
        rect(col, row, 0xeef2f4);
        g.fillStyle(0xa9d3e6).fillRect(x, y + 14 * u, t, t - 29 * u);
        g.fillStyle(0xffffff).fillRect(x, y + 13 * u, t, 3 * u);
        g.fillRect(x, y + t - 16 * u, t, 3 * u);
        g.fillRect(x + t / 2 - 2 * u, y + 12 * u, 3 * u, t - 25 * u);
        g.lineStyle(2 * u, 0xffffff, 0.7).lineBetween(x + 6 * u, y + t - 18 * u, x + 16 * u, y + 17 * u);
      } else if (kind === "counter") {
        furniture();
        g.fillStyle(0xd8c49a).fillRect(x, y + 8 * u, t, t - 16 * u);
        g.fillStyle(0xa88c5c).fillRect(x, y + t - 14 * u, t, 6 * u);
      } else if (kind === "shelf") {
        furniture();
        g.fillStyle(0x5b3b22).fillRect(x + 2 * u, y + 6 * u, t - 4 * u, t - 12 * u);
        for (let i = 0; i < 6; i++) g.fillStyle(pick(BOOK_COLORS)).fillRect(x + (5 + i * 7) * u, y + 10 * u, 4 * u, t - 20 * u);
      } else if (kind === "desk") {
        furniture();
        g.fillStyle(0xf5f3ee).fillRect(x, y + 10 * u, t, t - 24 * u);
        g.lineStyle(2 * u, 0xb9b3a6).strokeRect(x, y + 10 * u, t, t - 24 * u);
        g.fillStyle(0x6e6e6e);
        for (let i = 0; i < 2; i++) g.fillCircle(x + (13 + i * 22) * u, y + t - 7 * u, 5 * u);
      } else if (kind === "studytable") {
        furniture();
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
        if (kind === "table") outdoor();
        else furniture();
        if (kind === "cafetable") {
          g.fillStyle(0xe07b39);
          for (const [cx, cy] of [[26, 5], [26, 47], [5, 26], [47, 26]]) g.fillCircle(x + cx * u, y + cy * u, 6 * u);
        }
        g.fillStyle(0x000000, 0.18).fillEllipse(x + 28 * u, y + 29 * u, 34 * u, 34 * u);
        g.fillStyle(0xfafafa).fillCircle(x + t / 2, y + t / 2, 16 * u);
        g.lineStyle(2 * u, 0xb8b1a3).strokeCircle(x + t / 2, y + t / 2, 16 * u);
      } else if (kind === "woodtable") {
        outdoor();
        g.fillStyle(0x8a5a33);
        g.fillRoundedRect(x + 19 * u, y, 14 * u, 9 * u, 2 * u);
        g.fillRoundedRect(x + 19 * u, y + t - 9 * u, 14 * u, 9 * u, 2 * u);
        g.fillRoundedRect(x, y + 19 * u, 9 * u, 14 * u, 2 * u);
        g.fillRoundedRect(x + t - 9 * u, y + 19 * u, 9 * u, 14 * u, 2 * u);
        g.fillStyle(0x000000, 0.18).fillRect(x + 10 * u, y + 12 * u, t - 18 * u, t - 18 * u);
        g.fillStyle(0xb07a45).fillRect(x + 9 * u, y + 9 * u, t - 19 * u, t - 19 * u);
        g.lineStyle(2 * u, 0x7a4f2a).strokeRect(x + 9 * u, y + 9 * u, t - 19 * u, t - 19 * u);
      } else if (kind === "shopshelf") {
        furniture();
        rect(col, row, 0xc42828, 0.27);
        g.fillStyle(0xe9e6e0).fillRect(x + 2 * u, y + 8 * u, t - 4 * u, t - 16 * u);
        g.lineStyle(2 * u, 0x9a9690).strokeRect(x + 2 * u, y + 8 * u, t - 4 * u, t - 16 * u);
        for (let i = 0; i < 5; i++) {
          for (let j = 0; j < 2; j++) g.fillStyle(pick(PRODUCT_COLORS)).fillRect(x + (6 + i * 9) * u, y + (12 + j * 14) * u, 6 * u, 10 * u);
        }
      } else if (kind === "foodcounter") {
        furniture();
        g.fillStyle(0xd8c49a).fillRect(x + 6 * u, y, t - 6 * u, t);
        g.fillStyle(0xa88c5c).fillRect(x + 6 * u, y, 6 * u, t);
        for (let j = 0; j < 2; j++) {
          const ty = y + (6 + j * 24) * u;
          g.fillStyle(0xf5f5f5).fillRoundedRect(x + 16 * u, ty, t - 22 * u, 18 * u, 4 * u);
          g.fillStyle(pick([0xe07b39, 0x7cb342, 0xc62828])).fillCircle(x + 25 * u, ty + 9 * u, 5 * u);
          g.fillStyle(0xf2c94c).fillCircle(x + 36 * u, ty + 9 * u, 4 * u);
        }
      } else if (kind === "piano") {
        furniture();
        g.fillStyle(0x141414).fillRoundedRect(x + 4 * u, y + 4 * u, t - 9 * u, t - 9 * u, 8 * u);
        g.fillStyle(0xf2f2f2).fillRect(x + 6 * u, y + t - 14 * u, t - 13 * u, 6 * u);
      } else if (kind === "screen") {
        const horizontal = has(col - 1, row, "screen") || has(col + 1, row, "screen");
        if (horizontal) {
          // The big screen on the Auditorium's front wall, glowing onto the aisle.
          rect(col, row, ROOF);
          const left = has(col - 1, row, "screen") ? 0 : 6 * u;
          const right = has(col + 1, row, "screen") ? 0 : 6 * u;
          g.fillStyle(0x1e2228).fillRect(x + left, y + t - 20 * u, t - left - right, 14 * u);
          g.fillStyle(0x3d8bd4).fillRect(x + left * 1.6, y + t - 16 * u, t - (left + right) * 1.6, 10 * u);
          g.fillStyle(0x78b4f0, 0.18).fillRect(x, y + t - 6 * u, t, 16 * u);
        } else {
          furniture();
          const top = has(col, row - 1, "screen") ? 0 : 6 * u;
          const bottom = has(col, row + 1, "screen") ? 0 : 6 * u;
          g.fillStyle(0x1e2228).fillRect(x + 12 * u, y + top, t - 24 * u, t - top - bottom);
          g.fillStyle(0x3d8bd4).fillRect(x + 16 * u, y + top * 1.6, t - 32 * u, t - (top + bottom) * 1.6);
        }
      } else if (kind === "steps") {
        rect(col, row, 0xcabb9f);
        const colors = [0xb5543c, 0xc8664b, 0xd97a5c];
        for (let i = 0; i < 3; i++) g.fillStyle(colors[i]).fillRect(x, y + (i * t) / 3, t, t / 3 - 2 * u);
      } else if (kind === "picnic") {
        rect(col, row, 0xcabb9f);
        g.fillStyle(0x8a5a33).fillRect(x + 4 * u, y + 14 * u, t - 9 * u, t - 28 * u);
        g.fillStyle(0x6e4628).fillRect(x + 4 * u, y + 6 * u, t - 9 * u, 4 * u);
        g.fillRect(x + 4 * u, y + t - 10 * u, t - 9 * u, 4 * u);
      } else if (kind === "tree") {
        outdoor();
        g.fillStyle(0x000000, 0.24).fillEllipse(x + 31 * u, y + 32 * u, 46 * u, 44 * u);
        g.fillStyle(0x3f7d34).fillCircle(x + 24 * u, y + 24 * u, 22 * u);
        g.fillStyle(0x5c9c48).fillCircle(x + 18 * u, y + 15 * u, 8 * u);
      }
    }

    // 3. Names: the areas (from "areas") and other places (from "labels").
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
  // `time` is the game time in milliseconds.
  function animateCharacter(sprite, { dx, dy, ghost }, time) {
    const look = sprite.look;
    const walking = dx !== 0 || dy !== 0;

    // Eyes turn smoothly towards the walking direction and stay there when standing.
    if (walking) {
      look.faceX += (dx - look.faceX) * 0.25;
      look.faceY += (dy - look.faceY) * 0.25;
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

  // --- Emergency bell (spec 008, part 4) -------------------------------------------------

  // A brass bell on the tile the server's map names ("bell": [col, row]).
  function makeBell(scene, map) {
    const t = map.tile_size;
    const [col, row] = map.bell;
    const brass = 0xf2b33d;
    const darkBrass = 0xc98a17;
    const body = (grow) => [
      { x: -8 - grow, y: -3 },
      { x: 8 + grow, y: -3 },
      { x: 11 + grow, y: 7 + grow },
      { x: -11 - grow, y: 7 + grow },
    ];
    const g = scene.add.graphics();
    g.fillStyle(0x000000, 0.28).fillEllipse(1, 11, 28, 8); // shadow on the floor
    // Outlines are dark shapes behind slightly smaller coloured ones, as for the characters.
    g.fillStyle(OUTLINE).fillCircle(0, -12, 3.5).fillCircle(0, -3, 9.5).fillPoints(body(1.5), true);
    g.fillCircle(0, 9.5, 3.8);
    g.fillStyle(darkBrass).fillCircle(0, -12, 2); // the knob it hangs from
    g.fillStyle(brass).fillCircle(0, -3, 8).fillPoints(body(0), true);
    g.fillStyle(darkBrass).fillRect(-11, 4.5, 22, 2.5); // rim
    g.fillStyle(0xffffff, 0.4).fillEllipse(-3.5, -3, 3, 8); // shine
    g.fillStyle(darkBrass).fillCircle(0, 9.5, 2.3); // clapper
    const label = scene.add
      .text(0, 14, "BELL", {
        fontFamily: FONT,
        fontSize: "8px",
        fontStyle: "bold",
        color: "#ffffff",
        resolution: TEXT_RESOLUTION,
      })
      .setLetterSpacing(1.5)
      .setOrigin(0.5, 0)
      .setAlpha(0.75);
    // On the floor: over a failed exam, under the players.
    return scene.add.container((col + 0.5) * t, (row + 0.5) * t, [g, label]).setDepth(0.6);
  }

  // --- Staff doors (spec 008, part 6) ----------------------------------------------------

  // A hatch in the floor on a tile the server's map names ("staff_doors"). Everyone sees
  // the hatches; only examiners can use them.
  function makeDoor(scene, map, door) {
    const t = map.tile_size;
    const g = scene.add.graphics();
    g.fillStyle(OUTLINE).fillRoundedRect(-13, -13, 26, 26, 4);
    g.fillStyle(0x6a7183).fillRoundedRect(-11, -11, 22, 22, 3); // the metal plate
    g.fillStyle(0x23262e);
    for (const y of [-7.5, -1.5, 4.5]) g.fillRect(-8, y, 16, 3); // three slats
    g.fillStyle(0xf2b33d).fillCircle(8, -8, 1.6); // a small handle
    return scene.add.container((door.x + 0.5) * t, (door.y + 0.5) * t, [g]).setDepth(0.4);
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

  // The mark on one of the player's own open task places. It is drawn above the darkness,
  // so it also shows outside the vision radius: a player's own tasks are no secret.
  function makeTaskMarker(scene, task) {
    const g = scene.add.graphics();
    g.fillStyle(OUTLINE, 0.85).fillCircle(0, 0, 11);
    g.lineStyle(2, TASK_COLOR).strokeCircle(0, 0, 11);
    const mark = scene.add
      .text(0, 0, "!", {
        fontFamily: FONT,
        fontSize: "14px",
        fontStyle: "bold",
        color: "#4cb963",
        resolution: TEXT_RESOLUTION,
      })
      .setOrigin(0.5);
    return scene.add.container(task.x, task.y, [g, mark]).setDepth(11);
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

  // --- Darkness outside the lit area (spec 005; one layer since spec 010, part 1) ---------
  // This is only the look: the server does not even send what the player cannot see.
  //
  // The darkness has ONE strength everywhere and is made of two parts that never overlap:
  //   dark: a plain dark sheet over the whole map, with the lit shape cut out of it;
  //   rim:  a round picture, clear in the middle and just as dark as the sheet from the
  //         vision radius on. It follows the own character and is drawn only inside the
  //         lit shape, so it gives the vision circle its soft edge.
  // The camera never shows more than the map, so the sheet covers every window size.
  // `lit` is the lit shape. It is never drawn itself: it only cuts the two parts.
  function makeDarkness(scene, mapWidth, mapHeight, radius) {
    const lit = scene.make.graphics({}, false);
    const dark = scene.add.rectangle(0, 0, mapWidth, mapHeight, FOG_COLOR, FOG_ALPHA);
    dark.setOrigin(0).setDepth(10).setAlpha(0);
    dark.setMask(lit.createGeometryMask().setInvertAlpha(true)); // everywhere but the lit shape

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
    rim.setMask(lit.createGeometryMask()); // only inside the lit shape

    // `radius` is the radius shown right now: it glides to the one the server sends.
    return { lit, dark, rim, radius };
  }

  // The lit shape as tiles: `visible` is a Set of "col,row" worked out by main.js with the
  // server's rule. The shape must stay within RIM_REACH radii of the own character.
  function drawLitTiles(darkness, map, visible) {
    const t = map.tile_size;
    darkness.lit.clear().fillStyle(0xffffff);
    for (const tile of visible) {
      const [col, row] = tile.split(",").map(Number);
      darkness.lit.fillRect(col * t, row * t, t, t);
    }
  }

  // Call every frame: keeps the rim centred on (x, y), lets the shown radius glide to
  // `radius` (lights out and back on) and fades the whole darkness in or out.
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
    makeBell,
    makeDoor,
    makeSwitch,
    updateSwitch,
    makeTaskMarker,
    makeTaskRing,
    updateTaskRing,
    makeDarkness,
    drawLitTiles,
    updateDarkness,
  };
})();
