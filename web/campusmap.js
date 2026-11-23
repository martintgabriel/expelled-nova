// Campus map (spec 018): the whole campus as one SVG, for describing places in a meeting.
//
// Drawn once from the map the server sends in "welcome", and from nothing else: it reads
// only tile_size, grid, decor (sea and sand), areas, labels, meeting_point and
// light_switch, never the map's "tasks" (every player's stations). The base map is grey.
// Only two things change afterwards, both the player's own and both in colour: the "you are
// here" marker (setYou) and the numbered markers of the own open tasks (setTasks), which
// main.js takes from the own snapshot. Apart from those the map is the same for every
// player, every role, alive or ghost, lights on or off.
// All text is set with textContent, never as HTML.

const CampusMap = (() => {
  const SVG_NS = "http://www.w3.org/2000/svg";
  // The base map is grey, so the own marker and the own tasks are what stands out.
  const WALL = "#3b3e45"; // blocked tiles: walls and buildings
  const FLOOR = "#e6e5e1"; // walkable tiles: rooms and corridors
  const SEA = "#9a9ea4";
  const SAND = "#d3d1cb";
  const AREA_FILL = "#8c8f95"; // every area the same grey: the names tell them apart
  const AREA_EDGE = "#6d7077";
  const AREA_OPACITY = 0.25;
  const TASK_FONT = 0.85;
  // One size for every name on the map (areas, labels, the two places), in tiles.
  const NAME_FONT = 0.9;
  const LINE_HEIGHT = 1.05; // in font sizes, for names on two or more lines
  const PAD = 0.25; // room between a name and the edge of its box, in tiles
  const AREA_CLASS = "map-name map-area-name";
  const LABEL_CLASS = "map-name";
  const PLACE_CLASS = "map-name map-place";

  let tile = 32; // map pixels per tile, from the map
  let you = null; // the own marker, created by build()
  let taskLayer = null; // the own open tasks' markers, created by build()

  function node(name, attributes = {}) {
    const element = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
    return element;
  }

  function text(x, y, content, size, className) {
    const element = node("text", { x, y, "font-size": size, class: className });
    element.textContent = content;
    return element;
  }

  // How wide the browser draws a text, in tiles. Only works while the SVG is in the page
  // (build() puts it there, hidden, for exactly this).
  function measure(svg, content, size, className) {
    const probe = text(0, 0, content, size, className);
    svg.append(probe);
    const width = probe.getBBox().width;
    probe.remove();
    return width;
  }

  // Blocked tiles as one rectangle per run of "#" in a row, on a floor-coloured ground.
  function drawGrid(svg, grid, cols, rows) {
    const ground = node("g", { "shape-rendering": "crispEdges" });
    ground.append(node("rect", { x: 0, y: 0, width: cols, height: rows, fill: FLOOR }));
    grid.forEach((line, row) => {
      let start = -1;
      for (let col = 0; col <= line.length; col++) {
        const blocked = line[col] === "#";
        if (blocked && start < 0) start = col;
        if (!blocked && start >= 0) {
          ground.append(node("rect", { x: start, y: row, width: col - start, height: 1, fill: WALL }));
          start = -1;
        }
      }
    });
    svg.append(ground);
  }

  // Only the sea and the sand: the sea is "#" in the grid and would look like a wall.
  function drawBeach(svg, decor) {
    const colours = { sea: SEA, sand: SAND };
    const beach = node("g", { "shape-rendering": "crispEdges" });
    for (const piece of decor) {
      const fill = colours[piece.kind];
      if (fill) beach.append(node("rect", { x: piece.x, y: piece.y, width: piece.w, height: piece.h, fill }));
    }
    svg.append(beach);
  }

  function drawAreas(svg, areas) {
    for (const area of areas) {
      svg.append(
        node("rect", {
          x: area.x,
          y: area.y,
          width: area.w,
          height: area.h,
          fill: AREA_FILL,
          "fill-opacity": AREA_OPACITY,
          stroke: AREA_EDGE,
          "stroke-width": 0.15,
        }),
      );
    }
  }

  // Words onto lines no longer than `length`, as few lines as possible. A single word
  // longer than `length` gets a line of its own (drawName then makes it smaller).
  function wrap(svg, content, length, className) {
    const lines = [];
    for (const word of content.split(" ")) {
      const joined = lines.length ? `${lines[lines.length - 1]} ${word}` : null;
      if (joined && measure(svg, joined, NAME_FONT, className) <= length) lines[lines.length - 1] = joined;
      else lines.push(word);
    }
    return lines;
  }

  // One name centred in its box (an area, or a label's room), never past its edges: on
  // one line if it fits, else wrapped at the spaces, and only made smaller than NAME_FONT
  // if a single word or the lines together still do not fit. In a tall, narrow box (the
  // beach, the Spine) the name is written along it, turned 90 degrees to the left.
  function drawName(svg, content, box, className) {
    const along = box.h >= 2 * box.w;
    const length = (along ? box.h : box.w) - 2 * PAD; // room for one line
    const across = (along ? box.w : box.h) - 2 * PAD; // room for all lines together
    const lines = wrap(svg, content, length, className);
    const widest = Math.max(...lines.map((line) => measure(svg, line, NAME_FONT, className)));
    const size = Math.min(NAME_FONT, (NAME_FONT * length) / widest, across / (lines.length * LINE_HEIGHT));
    const cx = box.x + box.w / 2;
    const cy = box.y + box.h / 2;
    const group = node("g", along ? { transform: `rotate(-90 ${cx} ${cy})` } : {});
    lines.forEach((line, i) => {
      const y = cy + (i - (lines.length - 1) / 2) * size * LINE_HEIGHT;
      group.append(text(cx, y, line, size, className));
    });
    svg.append(group);
  }

  // Names last, so no rectangle covers them: every area's name in its rectangle, every
  // label in its room. The names of the meeting table and the light switch are labels too,
  // marked only_on_map (the game world draws those places itself).
  function drawNames(svg, parts) {
    for (const area of parts.areas) drawName(svg, area.name.toUpperCase(), area, AREA_CLASS);
    for (const label of parts.labels) {
      // A label without a room (an older map) gets a small box around its position.
      const box = label.room || { x: label.x - 3, y: label.y, w: 6, h: 1.5 };
      drawName(svg, label.text, box, label.only_on_map ? PLACE_CLASS : LABEL_CLASS);
    }
  }

  // The marks of the meeting table and the light switch: fixed parts of the campus.
  function drawPlaces(svg, meetingPoint, lightSwitch) {
    if (meetingPoint) {
      const [col, row] = meetingPoint;
      svg.append(node("circle", { cx: col + 0.5, cy: row + 0.5, r: 0.7, class: "map-table" }));
    }
    if (lightSwitch) {
      const [col, row] = lightSwitch;
      svg.append(node("rect", { x: col + 0.2, y: row + 0.2, width: 0.6, height: 0.6, class: "map-switch" }));
    }
  }

  function build(map) {
    tile = map.tile_size;
    const grid = map.grid;
    const rows = grid.length;
    const cols = Math.max(...grid.map((line) => line.length));
    const svg = node("svg", {
      viewBox: `0 0 ${cols} ${rows}`,
      class: "campus-map",
      "aria-label": "Map of the campus with every room, corridor and the beach",
    });
    svg.setAttribute("role", "img");
    // In the page but invisible while it is drawn, so the names can be measured.
    svg.style.position = "absolute";
    svg.style.visibility = "hidden";
    document.body.append(svg);
    const parts = {
      areas: map.areas || [],
      labels: map.labels || [],
      decor: map.decor || [],
      meetingPoint: map.meeting_point,
      lightSwitch: map.light_switch,
    };
    drawGrid(svg, grid, cols, rows);
    drawBeach(svg, parts.decor);
    drawAreas(svg, parts.areas);
    drawPlaces(svg, parts.meetingPoint, parts.lightSwitch);
    drawNames(svg, parts);
    svg.remove();
    svg.style.position = "";
    svg.style.visibility = "";
    taskLayer = node("g", { class: "map-tasks" });
    svg.append(taskLayer);
    you = node("g", { class: "map-you", visibility: "hidden" });
    you.append(node("circle", { r: 0.85, class: "map-you-ring" }));
    you.append(node("circle", { r: 0.5, class: "map-you-dot" }));
    svg.append(you);
    return svg;
  }

  // The own position in map pixels and the own colour, or null to hide the marker.
  function setYou(point, color) {
    if (!you) return;
    if (!point) {
      you.setAttribute("visibility", "hidden");
      return;
    }
    you.setAttribute("transform", `translate(${point.x / tile} ${point.y / tile})`);
    you.lastChild.setAttribute("fill", color || "#ffffff");
    you.setAttribute("visibility", "visible");
  }

  // The own open tasks, each {x, y} in map pixels, as numbered markers 1, 2, 3 … in the
  // order given (main.js lists them in the same order under the map). [] removes them.
  function setTasks(list) {
    if (!taskLayer) return;
    taskLayer.replaceChildren();
    list.forEach((task, i) => {
      const x = task.x / tile;
      const y = task.y / tile;
      taskLayer.append(node("circle", { cx: x, cy: y, r: 0.75, class: "map-task" }));
      taskLayer.append(text(x, y, String(i + 1), TASK_FONT, "map-task-number"));
    });
  }

  return { build, setYou, setTasks };
})();
