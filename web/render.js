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
  const CORRIDOR = 0x5b606b;
  const WALL_TOP = 0x30343f;
  const WALL_FRONT = 0x1c1f26; // the side of a wall that faces the viewer
  const WALL_EDGE = 0x4b5161; // light line where a wall meets the floor
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
  const FOG_TEXTURE_SIZE = 1024;

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

  // Draws the campus from the server's map data and returns its size in pixels.
  function drawMap(scene, map) {
    const t = map.tile_size;
    const rows = map.grid.length;
    const cols = map.grid[0].length;
    const isFloor = (row, col) => row >= 0 && row < rows && map.grid[row][col] === ".";
    const g = scene.add.graphics();

    // Floor: corridor colour everywhere, then each area in its own colour.
    g.fillStyle(CORRIDOR).fillRect(0, 0, cols * t, rows * t);
    for (const area of map.areas) {
      g.fillStyle(Phaser.Display.Color.HexStringToColor(area.color).color);
      g.fillRect(area.x * t, area.y * t, area.w * t, area.h * t);
    }
    // Every second floor tile a touch lighter: a tiled floor instead of a flat colour.
    g.fillStyle(0xffffff, 0.03);
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        if (isFloor(row, col) && (row + col) % 2 === 0) g.fillRect(col * t, row * t, t, t);
      }
    }

    // Walls on top. A wall with floor below it shows its front face and casts a shadow.
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        if (isFloor(row, col)) continue;
        const x = col * t;
        const y = row * t;
        g.fillStyle(WALL_TOP).fillRect(x, y, t, t);
        if (isFloor(row + 1, col)) {
          g.fillStyle(WALL_FRONT).fillRect(x, y + t * 0.6, t, t * 0.4);
          g.fillStyle(0x000000, 0.22).fillRect(x, y + t, t, t * 0.22);
        }
        g.fillStyle(WALL_EDGE);
        if (isFloor(row + 1, col)) g.fillRect(x, y + t * 0.6 - 2, t, 2);
        if (isFloor(row - 1, col)) g.fillRect(x, y, t, 2);
        if (isFloor(row, col - 1)) g.fillRect(x, y, 2, t);
        if (isFloor(row, col + 1)) g.fillRect(x + t - 2, y, 2, t);
      }
    }

    for (const area of map.areas) {
      scene.add
        .text((area.x + area.w / 2) * t, (area.y + 0.5) * t, area.name.toUpperCase(), {
          fontFamily: FONT,
          fontSize: "12px",
          fontStyle: "bold",
          color: "#ffffff",
          resolution: TEXT_RESOLUTION,
        })
        .setLetterSpacing(2)
        .setOrigin(0.5, 0)
        .setAlpha(0.6);
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

  // --- Darkness outside the vision radius ----------------------------------------------

  // One big square picture that is clear in the middle and dark everywhere else. It is
  // painted once with a canvas gradient and then follows the own character.
  // `reach` is how far it must extend from the player to cover the whole map.
  // This is only the look: the server does not even send what is outside the radius.
  // `key` names the picture: there is one for the normal radius and one for lights out.
  function makeFog(scene, radius, reach, key = "fog") {
    const size = FOG_TEXTURE_SIZE;
    const texture = scene.textures.createCanvas(key, size, size);
    const context = texture.getContext();
    const centre = size / 2;
    const scale = centre / reach; // texture pixels per map pixel
    const gradient = context.createRadialGradient(
      centre, centre, radius * FOG_CLEAR * scale,
      centre, centre, radius * FOG_FULL * scale,
    );
    gradient.addColorStop(0, "rgba(8, 10, 14, 0)");
    gradient.addColorStop(0.55, `rgba(8, 10, 14, ${FOG_ALPHA * 0.45})`);
    gradient.addColorStop(1, `rgba(8, 10, 14, ${FOG_ALPHA})`);
    context.fillStyle = gradient;
    context.fillRect(0, 0, size, size);
    texture.refresh();
    return scene.add.image(0, 0, key).setDisplaySize(reach * 2, reach * 2).setDepth(10).setAlpha(0);
  }

  // --- Darkness behind walls (spec 008, part 7) ------------------------------------------

  const SHADOW_ALPHA = 0.72;

  // One drawing layer for the tiles the own character cannot see. It lies on the floor,
  // over the bell and the hatches and under the players (the server only sends players
  // who stand on visible tiles).
  function makeShadows(scene) {
    return scene.add.graphics().setDepth(0.9);
  }

  // Darkens every tile around (col, row) that is not in `visible`, a Set of "col,row"
  // worked out by main.js with the server's rule. `visible` = null: no darkness at all.
  function drawShadows(shadows, map, col, row, reach, visible) {
    shadows.clear();
    if (!visible) return;
    const t = map.tile_size;
    shadows.fillStyle(0x080a0e, SHADOW_ALPHA);
    for (let r = row - reach - 1; r <= row + reach + 1; r++) {
      for (let c = col - reach - 1; c <= col + reach + 1; c++) {
        if (!visible.has(`${c},${r}`)) shadows.fillRect(c * t, r * t, t, t);
      }
    }
  }

  // Call every frame: keeps the darkness centred on (x, y) and fades it in or out.
  function updateFog(fog, x, y, on) {
    fog.setPosition(x, y);
    const alpha = fog.alpha + ((on ? 1 : 0) - fog.alpha) * 0.12;
    fog.setAlpha(Math.abs(alpha - (on ? 1 : 0)) < 0.01 ? (on ? 1 : 0) : alpha);
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
    makeFog,
    updateFog,
    makeShadows,
    drawShadows,
  };
})();
