// Hats (spec 022): ten original hats, defined once as simple shapes and drawn both on the
// map (Phaser graphics, render.js) and in the small SVG figures (main.js). Coordinates are
// in figure units with (0, 0) at the top of the head; negative y is up. The head is a
// circle of radius 11, so x runs from about -11 to 11 across it.
// Shapes: rect {x, y, w, h, r}, poly {p: [[x, y], ...]}, circle {x, y, r},
// ellipse {x, y, w, h}; every shape has a colour c (0xRRGGBB). Loaded before render.js.

"use strict";

const Hats = (() => {
  const LIST = [
    {
      name: "Graduation cap",
      shapes: [
        { t: "rect", x: -6.5, y: -0.5, w: 13, h: 5, r: 2, c: 0x23262e },
        { t: "poly", p: [[-12, -1], [0, -5], [12, -1], [0, 3]], c: 0x2d313b },
        { t: "rect", x: 0, y: -1.6, w: 7.8, h: 1.2, c: 0xf2b33d },
        { t: "rect", x: 7.2, y: -1.2, w: 1.2, h: 5.5, c: 0xf2b33d },
        { t: "circle", x: 7.8, y: 5, r: 1.5, c: 0xf2b33d },
      ],
    },
    {
      name: "Beanie",
      shapes: [
        { t: "ellipse", x: 0, y: -0.5, w: 21, h: 13, c: 0x2e7dd1 },
        { t: "rect", x: -10.5, y: 1.5, w: 21, h: 4.5, r: 2, c: 0x1f5fa8 },
        { t: "circle", x: 0, y: -7.5, r: 2.8, c: 0xf4f4f4 },
      ],
    },
    {
      name: "Top hat",
      shapes: [
        { t: "rect", x: -6.5, y: -14, w: 13, h: 14, r: 1, c: 0x1b1d22 },
        { t: "rect", x: -6.5, y: -4.5, w: 13, h: 2.5, c: 0xc0392b },
        { t: "rect", x: -11, y: -1, w: 22, h: 3, r: 1.5, c: 0x1b1d22 },
      ],
    },
    {
      name: "Cowboy hat",
      shapes: [
        { t: "ellipse", x: 0, y: 0.5, w: 31, h: 6, c: 0x8b5a2b },
        { t: "poly", p: [[-7, 0], [-6.5, -9], [-2, -7], [0, -9], [2, -7], [6.5, -9], [7, 0]], c: 0x9c6b3a },
        { t: "rect", x: -7, y: -3, w: 14, h: 2, c: 0x5a3a1a },
      ],
    },
    {
      name: "Crown",
      shapes: [
        { t: "poly", p: [[-9, 1.5], [-9.5, -8], [-5, -3], [0, -10.5], [5, -3], [9.5, -8], [9, 1.5]], c: 0xf2c230 },
        { t: "circle", x: 0, y: -2, r: 1.6, c: 0xe5484d },
        { t: "circle", x: -5.5, y: -0.5, r: 1.2, c: 0x3a86ff },
        { t: "circle", x: 5.5, y: -0.5, r: 1.2, c: 0x3a86ff },
      ],
    },
    {
      name: "Party hat",
      shapes: [
        { t: "poly", p: [[-7, 1.5], [0, -16], [7, 1.5]], c: 0x8e5bd9 },
        { t: "circle", x: -2.5, y: -3, r: 1.3, c: 0xf5d547 },
        { t: "circle", x: 2, y: -8, r: 1.1, c: 0x2ec4b6 },
        { t: "circle", x: 3, y: -1, r: 1.2, c: 0xff7ab6 },
        { t: "circle", x: 0, y: -16, r: 2.3, c: 0xf5d547 },
      ],
    },
    {
      name: "Chef's hat",
      shapes: [
        { t: "circle", x: -5, y: -7, r: 5.2, c: 0xd5d7db },
        { t: "circle", x: 5, y: -7, r: 5.2, c: 0xd5d7db },
        { t: "circle", x: 0, y: -9.5, r: 5.7, c: 0xd5d7db },
        { t: "circle", x: -5, y: -7, r: 4.5, c: 0xffffff },
        { t: "circle", x: 5, y: -7, r: 4.5, c: 0xffffff },
        { t: "circle", x: 0, y: -9.5, r: 5, c: 0xffffff },
        { t: "rect", x: -7.5, y: -5, w: 15, h: 7, r: 1, c: 0xf4f4f4 },
      ],
    },
    {
      name: "Baseball cap",
      shapes: [
        { t: "ellipse", x: 0, y: -0.5, w: 21, h: 12, c: 0x2b4c9b },
        { t: "ellipse", x: 8, y: 2.5, w: 15, h: 4.5, c: 0x1f3a7a },
        { t: "circle", x: 0, y: -6.4, r: 1.3, c: 0x1f3a7a },
      ],
    },
    {
      name: "Beret",
      shapes: [
        { t: "ellipse", x: 1.5, y: -2, w: 25, h: 8.5, c: 0xb3263a },
        { t: "rect", x: 1, y: -8, w: 1.4, h: 3, c: 0xb3263a },
      ],
    },
    {
      name: "Laurel wreath",
      shapes: [
        ...[[-10.5, 2], [-9.5, -2], [-7, -5.5], [-3.5, -7.5]].flatMap(([x, y], i) => [
          { t: "circle", x, y, r: 2.4, c: i % 2 ? 0x3f8a3b : 0x5fae55 },
          { t: "circle", x: -x, y, r: 2.4, c: i % 2 ? 0x5fae55 : 0x3f8a3b },
        ]),
        { t: "circle", x: 0, y: -8, r: 1.6, c: 0xe8c547 },
      ],
    },
  ];

  function hatOf(number) {
    return LIST[number] || LIST[0];
  }

  // On the map: draw into a Phaser Graphics object, with the head top at y = `top`.
  function drawPhaser(graphics, number, top) {
    for (const s of hatOf(number).shapes) {
      graphics.fillStyle(s.c);
      if (s.t === "rect") {
        if (s.r) graphics.fillRoundedRect(s.x, top + s.y, s.w, s.h, s.r);
        else graphics.fillRect(s.x, top + s.y, s.w, s.h);
      } else if (s.t === "poly") {
        graphics.fillPoints(s.p.map(([x, y]) => ({ x, y: top + y })), true);
      } else if (s.t === "circle") {
        graphics.fillCircle(s.x, top + s.y, s.r);
      } else if (s.t === "ellipse") {
        graphics.fillEllipse(s.x, top + s.y, s.w, s.h);
      }
    }
  }

  // In an SVG figure: a <g> with the hat, its head top at (cx, top), scaled by `scale`.
  function svg(number, cx, top, scale) {
    const NS = "http://www.w3.org/2000/svg";
    const make = (tag, attrs) => {
      const el = document.createElementNS(NS, tag);
      for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
      return el;
    };
    const hex = (c) => "#" + c.toString(16).padStart(6, "0");
    const group = make("g", { transform: `translate(${cx} ${top}) scale(${scale})` });
    for (const s of hatOf(number).shapes) {
      const fill = hex(s.c);
      if (s.t === "rect") group.append(make("rect", { x: s.x, y: s.y, width: s.w, height: s.h, rx: s.r || 0, fill }));
      else if (s.t === "poly") group.append(make("polygon", { points: s.p.map((pt) => pt.join(",")).join(" "), fill }));
      else if (s.t === "circle") group.append(make("circle", { cx: s.x, cy: s.y, r: s.r, fill }));
      else if (s.t === "ellipse") group.append(make("ellipse", { cx: s.x, cy: s.y, rx: s.w / 2, ry: s.h / 2, fill }));
    }
    return group;
  }

  return { COUNT: LIST.length, names: LIST.map((hat) => hat.name), drawPhaser, svg };
})();
