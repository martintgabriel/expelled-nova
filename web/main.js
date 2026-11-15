// Browser client: sends only the pressed direction, draws what the server sends.
// The server decides every position. To feel immediate, the own character is
// predicted locally with the same speed and wall rule (see REPEATS SERVER RULE).

"use strict";

const INTERPOLATION_DELAY = 100; // ms: draw other players this far in the past
const SNAP_DISTANCE_TILES = 2; // jump to the server position if further off than this

const ui = {
  joinScreen: document.getElementById("join-screen"),
  joinForm: document.getElementById("join-form"),
  nickname: document.getElementById("nickname"),
  joinButton: document.getElementById("join-button"),
  joinError: document.getElementById("join-error"),
  hud: document.getElementById("hud"),
  playerCount: document.getElementById("player-count"),
  toast: document.getElementById("toast"),
  disconnected: document.getElementById("disconnected"),
};

let socket = null;
let welcome = null; // {id, map, speed, tick_rate, player_half} once joined
let snapshots = []; // recent server states: {time, players: Map(id -> {name,x,y})}
let toastTimer = null;

// --- Connection -----------------------------------------------------------------

function connect() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${location.host}/ws`);
  socket.addEventListener("message", (event) => handleMessage(JSON.parse(event.data)));
  socket.addEventListener("close", () => {
    if (welcome) {
      ui.disconnected.hidden = false;
    } else {
      showJoinError("Cannot reach the server. Try again.");
      socket = null;
    }
  });
  return new Promise((resolve) => socket.addEventListener("open", resolve, { once: true }));
}

function send(message) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(message));
  }
}

function handleMessage(message) {
  if (message.type === "welcome") {
    welcome = message;
    ui.joinScreen.hidden = true;
    ui.hud.hidden = false;
    startGame();
  } else if (message.type === "error") {
    if (welcome) showToast(message.reason);
    else showJoinError(message.reason);
  } else if (message.type === "state" && welcome) {
    const players = new Map(message.players.map((p) => [p.id, p]));
    snapshots.push({ time: performance.now(), players });
    // Keep about one second of history.
    while (snapshots.length > welcome.tick_rate) snapshots.shift();
    ui.playerCount.textContent = `Players: ${players.size}/10`;
  }
}

// --- Join form ------------------------------------------------------------------

ui.joinForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  ui.joinError.textContent = "";
  ui.joinButton.disabled = true;
  try {
    if (!socket) await connect();
    // The server validates the nickname and answers with "welcome" or "error".
    send({ type: "join", name: ui.nickname.value });
  } finally {
    ui.joinButton.disabled = false;
  }
});

function showJoinError(reason) {
  ui.joinError.textContent = reason;
  ui.nickname.focus();
}

function showToast(text) {
  ui.toast.textContent = text;
  ui.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (ui.toast.hidden = true), 3000);
}

// --- Wall check -------------------------------------------------------------------

// REPEATS SERVER RULE: same as Game.blocked() in server/game.py.
function blocked(map, half, x, y) {
  const t = map.tile_size;
  const left = Math.floor((x - half) / t);
  const right = Math.floor((x + half) / t - 1e-9);
  const top = Math.floor((y - half) / t);
  const bottom = Math.floor((y + half) / t - 1e-9);
  for (let row = top; row <= bottom; row++) {
    for (let col = left; col <= right; col++) {
      if (row < 0 || row >= map.grid.length || col < 0 || col >= map.grid[row].length) return true;
      if (map.grid[row][col] === "#") return true;
    }
  }
  return false;
}

// REPEATS SERVER RULE: same as Game._move_axis() in server/game.py
// (move in pieces of at most 1 px, stop at the first piece that hits a wall).
function moveAxis(pos, mx, my) {
  let remaining = Math.abs(mx) + Math.abs(my);
  const sx = Math.sign(mx);
  const sy = Math.sign(my);
  while (remaining > 0) {
    const part = Math.min(1, remaining);
    const nx = pos.x + sx * part;
    const ny = pos.y + sy * part;
    if (blocked(welcome.map, welcome.player_half, nx, ny)) return;
    pos.x = nx;
    pos.y = ny;
    remaining -= part;
  }
}

// --- Phaser scene -----------------------------------------------------------------

class CampusScene extends Phaser.Scene {
  constructor() {
    super("campus");
    this.sprites = new Map(); // id -> container (circle + name)
    this.lastSent = { dx: 0, dy: 0 };
    this.predicted = null; // own position as predicted by this browser
  }

  create() {
    const map = welcome.map;
    const t = map.tile_size;
    const width = map.grid[0].length * t;
    const height = map.grid.length * t;

    // Map: corridor floor, coloured areas, then walls on top. All from server data.
    const g = this.add.graphics();
    g.fillStyle(0x6b6f78).fillRect(0, 0, width, height);
    for (const area of map.areas) {
      g.fillStyle(Phaser.Display.Color.HexStringToColor(area.color).color);
      g.fillRect(area.x * t, area.y * t, area.w * t, area.h * t);
    }
    g.fillStyle(0x23252b);
    map.grid.forEach((row, r) => {
      [...row].forEach((cell, c) => {
        if (cell === "#") g.fillRect(c * t, r * t, t, t);
      });
    });
    for (const area of map.areas) {
      this.add
        .text((area.x + area.w / 2) * t, (area.y + 0.6) * t, area.name, {
          fontFamily: "system-ui, sans-serif",
          fontSize: "16px",
          color: "#ffffff",
        })
        .setOrigin(0.5, 0)
        .setAlpha(0.8);
    }

    this.cameras.main.setBounds(0, 0, width, height);
    this.cameras.main.setBackgroundColor("#1d1f24");

    this.keys = this.input.keyboard.addKeys("W,A,S,D,UP,DOWN,LEFT,RIGHT");

    // When the tab loses focus, stop walking (otherwise the server keeps moving us).
    const stop = () => this.sendDirection(0, 0);
    window.addEventListener("blur", stop);
    document.addEventListener("visibilitychange", () => document.hidden && stop());
  }

  sendDirection(dx, dy) {
    if (dx !== this.lastSent.dx || dy !== this.lastSent.dy) {
      this.lastSent = { dx, dy };
      send({ type: "input", dx, dy });
    }
  }

  readKeys() {
    const k = this.keys;
    const dx = (k.D.isDown || k.RIGHT.isDown ? 1 : 0) - (k.A.isDown || k.LEFT.isDown ? 1 : 0);
    const dy = (k.S.isDown || k.DOWN.isDown ? 1 : 0) - (k.W.isDown || k.UP.isDown ? 1 : 0);
    return { dx, dy };
  }

  update(time, deltaMs) {
    if (snapshots.length === 0) return;
    const { dx, dy } = this.readKeys();
    this.sendDirection(dx, dy);

    const latest = snapshots[snapshots.length - 1].players;
    this.syncSprites(latest);
    this.updateOwn(latest.get(welcome.id), dx, dy, deltaMs / 1000);
    this.updateOthers(latest);
  }

  // Create sprites for new players, remove sprites of players who left.
  syncSprites(latest) {
    for (const [id, p] of latest) {
      if (!this.sprites.has(id)) this.sprites.set(id, this.makeSprite(p.name, id === welcome.id));
    }
    for (const [id, sprite] of this.sprites) {
      if (!latest.has(id)) {
        sprite.destroy();
        this.sprites.delete(id);
      }
    }
  }

  makeSprite(name, isOwn) {
    const half = welcome.player_half;
    const body = this.add.circle(0, 0, half, isOwn ? 0xf2b33d : 0x9fd3ff);
    body.setStrokeStyle(2, 0x1d1f24);
    const label = this.add
      .text(0, -half - 6, name, {
        fontFamily: "system-ui, sans-serif",
        fontSize: "13px",
        color: "#ffffff",
        stroke: "#000000",
        strokeThickness: 3,
      })
      .setOrigin(0.5, 1);
    const sprite = this.add.container(0, 0, [body, label]);
    sprite.setDepth(isOwn ? 2 : 1);
    if (isOwn) this.cameras.main.startFollow(sprite, true, 0.15, 0.15);
    return sprite;
  }

  // Own character: predict locally every frame, the server position wins.
  updateOwn(server, dx, dy, dt) {
    const sprite = this.sprites.get(welcome.id);
    if (!server || !sprite) return;
    if (!this.predicted) this.predicted = { x: server.x, y: server.y };
    const pos = this.predicted;

    if (dx !== 0 || dy !== 0) {
      // REPEATS SERVER RULE: fixed speed, diagonal normalised (Game.step()).
      const length = Math.hypot(dx, dy);
      const distance = welcome.speed * Math.min(dt, 0.1);
      moveAxis(pos, (dx / length) * distance, 0);
      moveAxis(pos, 0, (dy / length) * distance);
    }

    const error = Math.hypot(server.x - pos.x, server.y - pos.y);
    if (error > SNAP_DISTANCE_TILES * welcome.map.tile_size) {
      pos.x = server.x; // too far apart: trust the server immediately
      pos.y = server.y;
    } else if (dx === 0 && dy === 0) {
      const ease = 1 - Math.exp(-10 * dt); // standing still: glide to the server position
      pos.x += (server.x - pos.x) * ease;
      pos.y += (server.y - pos.y) * ease;
    }
    sprite.setPosition(pos.x, pos.y);
  }

  // Other players: draw them slightly in the past, blending between two server states.
  updateOthers(latest) {
    const renderTime = performance.now() - INTERPOLATION_DELAY;
    let older = snapshots[0];
    let newer = snapshots[snapshots.length - 1];
    for (let i = 0; i < snapshots.length - 1; i++) {
      if (snapshots[i].time <= renderTime && snapshots[i + 1].time >= renderTime) {
        older = snapshots[i];
        newer = snapshots[i + 1];
        break;
      }
    }
    const span = newer.time - older.time;
    const f = span > 0 ? Phaser.Math.Clamp((renderTime - older.time) / span, 0, 1) : 1;

    for (const [id, sprite] of this.sprites) {
      if (id === welcome.id) continue;
      const b = newer.players.get(id) || latest.get(id);
      const a = older.players.get(id) || b;
      sprite.setPosition(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f);
    }
  }
}

function startGame() {
  new Phaser.Game({
    type: Phaser.AUTO,
    parent: "game",
    backgroundColor: "#1d1f24",
    scale: { mode: Phaser.Scale.RESIZE, width: window.innerWidth, height: window.innerHeight },
    scene: CampusScene,
  });
}
