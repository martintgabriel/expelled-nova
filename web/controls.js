// Touch joystick (spec 007): a round control at the bottom left, shown only on devices
// whose main pointer is a finger. Drawn with HTML/CSS, no images (see style.css).
// Offers one function, Controls.direction(), that main.js combines with the keyboard
// in readKeys() and sends with the throttled send.
// Loaded as a plain script after render.js and before main.js (no build step).

"use strict";

const Controls = (() => {
  const SIZE = 120; // px, the joystick's diameter
  const RADIUS = SIZE / 2;
  const DEAD_ZONE = 0.25; // fraction of the radius: inside this, the direction is (0, 0)
  // The 8 directions, 45° apart, starting at "right" and going clockwise (screen y is down).
  const DIRECTIONS = [
    [1, 0],
    [1, 1],
    [0, 1],
    [-1, 1],
    [-1, 0],
    [-1, -1],
    [0, -1],
    [1, -1],
  ];

  const isTouch = matchMedia("(pointer: coarse)").matches;

  let held = false;
  let current = { dx: 0, dy: 0 };
  let activePointerId = null;
  let base = null;
  let knob = null;

  function build() {
    base = document.createElement("div");
    base.id = "joystick";
    knob = document.createElement("div");
    knob.id = "joystick-knob";
    base.append(knob);
    document.body.append(base);

    base.addEventListener("pointerdown", onPointerDown);
    base.addEventListener("pointermove", onPointerMove);
    base.addEventListener("pointerup", onRelease);
    base.addEventListener("pointercancel", onRelease);
  }

  function onPointerDown(event) {
    if (activePointerId !== null) return; // one finger on the joystick at a time
    activePointerId = event.pointerId;
    base.setPointerCapture(activePointerId);
    held = true;
    updateFromEvent(event);
    event.preventDefault();
  }

  function onPointerMove(event) {
    if (event.pointerId !== activePointerId) return;
    updateFromEvent(event);
    event.preventDefault();
  }

  function onRelease(event) {
    if (event.pointerId !== activePointerId) return;
    release();
  }

  // Lifting the finger, a cancelled touch, losing focus or the screen locking: stop.
  function release() {
    activePointerId = null;
    held = false;
    current = { dx: 0, dy: 0 };
    if (knob) knob.style.transform = "translate(0, 0)";
  }

  function updateFromEvent(event) {
    const rect = base.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = event.clientX - cx;
    const dy = event.clientY - cy;
    const distance = Math.hypot(dx, dy);

    if (distance < DEAD_ZONE * RADIUS) {
      current = { dx: 0, dy: 0 };
      knob.style.transform = "translate(0, 0)";
      return;
    }
    const angle = Math.atan2(dy, dx);
    const index = (((Math.round(angle / (Math.PI / 4)) % 8) + 8) % 8);
    const [sx, sy] = DIRECTIONS[index];
    current = { dx: sx, dy: sy };

    const knobDistance = Math.min(distance, RADIUS);
    const knobX = (dx / distance) * knobDistance;
    const knobY = (dy / distance) * knobDistance;
    knob.style.transform = `translate(${knobX}px, ${knobY}px)`;
  }

  if (isTouch) {
    build();
    window.addEventListener("blur", release);
    document.addEventListener("visibilitychange", () => document.hidden && release());
  }

  return {
    isTouch,
    // The current direction ({dx, dy}, each -1, 0 or 1), or null while not held.
    direction() {
      return held ? current : null;
    },
    // Hidden during meetings: the joystick must not cover the meeting screen.
    setHidden(hidden) {
      if (base) base.hidden = hidden;
      if (hidden) release();
    },
  };
})();
