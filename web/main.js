// Browser client: sends only the pressed direction, draws what the server sends.
// The server decides every position. To feel immediate, the own character is
// predicted locally with the same speed and wall rule (see REPEATS SERVER RULE).
// How things look (map, characters, failed exams, darkness) is in render.js.

"use strict";

const INTERPOLATION_DELAY = 100; // ms: draw other players this far in the past
const SNAP_DISTANCE_TILES = 2; // jump to the server position if further off than this
const ROLE_SCREEN_MS = 3000; // how long the role screen shows at the start
// REPEATS SERVER RULE: MIN_PLAYERS in server/game.py. Only for the hint; the server decides.
const MIN_PLAYERS = 4;

const ui = {
  joinScreen: document.getElementById("join-screen"),
  joinForm: document.getElementById("join-form"),
  nickname: document.getElementById("nickname"),
  joinButton: document.getElementById("join-button"),
  joinError: document.getElementById("join-error"),
  hud: document.getElementById("hud"),
  areaName: document.getElementById("area-name"),
  playerCount: document.getElementById("player-count"),
  toast: document.getElementById("toast"),
  disconnected: document.getElementById("disconnected"),
  lobby: document.getElementById("lobby"),
  lobbyPlayers: document.getElementById("lobby-players"),
  startButton: document.getElementById("start-button"),
  startHint: document.getElementById("start-hint"),
  roleScreen: document.getElementById("role-screen"),
  roleTitle: document.getElementById("role-title"),
  roleDetail: document.getElementById("role-detail"),
  roleBadge: document.getElementById("role-badge"),
  expelButton: document.getElementById("expel-button"),
  ghostBanner: document.getElementById("ghost-banner"),
  endScreen: document.getElementById("end-screen"),
  endTitle: document.getElementById("end-title"),
  endRoles: document.getElementById("end-roles"),
  restartButton: document.getElementById("restart-button"),
  restartHint: document.getElementById("restart-hint"),
};

let socket = null;
// {id, map, speed, tick_rate, player_half, expel_range, vision_radius} once joined
let welcome = null;
// Recent server states: {time, players: Map(id -> {name,x,y}), ghosts: Set(id)}
let snapshots = [];
let latestState = null; // the newest state message as the server sent it
let toastTimer = null;
let lastPhase = null; // "lobby", "playing" or "ended", from the latest state
let lobbyKey = ""; // what the lobby list currently shows, to redraw only on changes
let endKey = ""; // the same for the end screen
let roleTimer = null;
// Nicknames by player id. While playing, the server only sends the players in sight,
// so names seen earlier (everyone is visible in the lobby) are remembered here.
const knownNames = new Map();

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
    // Only a ghost (or everyone after the end) receives the ghost list; the living
    // do not even receive the ghosts' positions.
    snapshots.push({ time: performance.now(), players, ghosts: new Set(message.ghosts || []) });
    latestState = message;
    for (const p of message.players) knownNames.set(p.id, p.name);
    // Keep about one second of history.
    while (snapshots.length > welcome.tick_rate) snapshots.shift();
    updateHud(message);
    updatePhase(message);
  }
}

// --- HUD: current area and player count (spec 005) ----------------------------------

function updateHud(state) {
  // The server works out the area from the own position; no area means a corridor.
  setText(ui.areaName, state.area || "Corridor");
  // Only the lobby shows everyone: while playing, a living player just receives the
  // players within the vision radius, so a count would be wrong.
  ui.playerCount.hidden = state.phase !== "lobby";
  setText(ui.playerCount, `Players: ${state.players.length}/10`);
}

// A dot in the player's colour (the server's colour number) for the lobby and end lists.
function colorDot(state, playerId) {
  const dot = document.createElement("span");
  dot.className = "dot";
  dot.style.background = Render.colorCss(state.colors[playerId]);
  return dot;
}

// --- Lobby and roles --------------------------------------------------------------
// Everything here is drawn from the server's state; this browser only ever receives
// its own role (and, for an examiner, the fellow examiners' ids).

function updatePhase(state) {
  const justStarted = state.phase === "playing" && lastPhase !== "playing";
  lastPhase = state.phase;
  ui.lobby.hidden = state.phase !== "lobby";
  ui.endScreen.hidden = state.phase !== "ended";
  ui.ghostBanner.hidden = !(state.phase === "playing" && !state.alive);
  updateExpelButton(state);
  if (state.phase === "lobby") {
    ui.roleBadge.hidden = true;
    renderLobby(state);
    return;
  }
  if (state.phase === "ended") {
    ui.roleBadge.hidden = true;
    ui.roleScreen.hidden = true;
    renderEnd(state);
    return;
  }
  const role = describeRole(state);
  setText(ui.roleBadge, role.fellows ? `${role.title} · with ${role.fellows}` : role.title);
  if (justStarted) showRoleScreen(state.role, role);
}

function renderLobby(state) {
  // Redraw the list only when players or host change (states arrive 20 times a second).
  const key = JSON.stringify([state.host, state.colors, state.players.map((p) => [p.id, p.name])]);
  if (key !== lobbyKey) {
    lobbyKey = key;
    ui.lobbyPlayers.replaceChildren(
      ...state.players.map((p) => {
        const item = document.createElement("li");
        item.append(colorDot(state, p.id), p.name); // appended as text: never read as HTML
        if (p.id === state.host) item.append(tag("host", "host"));
        if (p.id === welcome.id) item.append(tag("you", "you"));
        return item;
      }),
    );
  }
  const isHost = state.host === welcome.id;
  const enough = state.players.length >= MIN_PLAYERS;
  ui.startButton.hidden = !isHost;
  ui.startButton.disabled = !enough;
  let hint = "";
  if (!enough) hint = `Need at least ${MIN_PLAYERS} players`;
  else if (!isHost) hint = "Waiting for the host to start";
  setText(ui.startHint, hint);
}

function tag(text, kind) {
  const span = document.createElement("span");
  span.className = `tag ${kind}`;
  span.textContent = text;
  return span;
}

function describeRole(state) {
  if (state.role === "examiner") {
    // A fellow examiner may be out of sight, so the name comes from the remembered ones.
    const fellows = (state.fellow_examiners || []).map((id) => knownNames.get(id) ?? id).join(", ");
    return { title: "You are an Undercover Examiner", fellows };
  }
  return { title: "You are a Student", fellows: "" };
}

function showRoleScreen(roleName, role) {
  ui.roleTitle.textContent = role.title;
  if (roleName === "examiner") {
    ui.roleDetail.textContent = role.fellows
      ? `Fellow examiner: ${role.fellows}`
      : "You are the only examiner.";
  } else {
    ui.roleDetail.textContent = "Stay enrolled and find out who the examiners are.";
  }
  ui.roleScreen.dataset.role = roleName;
  ui.roleScreen.hidden = false;
  ui.roleBadge.hidden = true;
  clearTimeout(roleTimer);
  roleTimer = setTimeout(() => {
    ui.roleScreen.hidden = true;
    ui.roleBadge.hidden = lastPhase !== "playing";
  }, ROLE_SCREEN_MS);
}

function setText(element, text) {
  if (element.textContent !== text) element.textContent = text;
}

ui.startButton.addEventListener("click", () => {
  // The server checks host, phase and player count; a rejection comes back as a toast.
  send({ type: "start" });
  ui.startButton.blur(); // keys go back to walking
});

// --- Expel, ghosts and the end screen (spec 003) ------------------------------------
// The button is only a convenience: the server checks range and cooldown again.

function isLivingExaminer(state) {
  return state.phase === "playing" && state.role === "examiner" && state.alive;
}

// Nearest living student within range, from the latest server positions. A living
// examiner does not receive ghosts, and fellow examiners are known, so every other
// player in the list is a living student.
function expelTarget(state) {
  if (!isLivingExaminer(state)) return null;
  const me = state.players.find((p) => p.id === welcome.id);
  if (!me) return null;
  const fellows = new Set(state.fellow_examiners || []);
  let best = null;
  let bestDistance = welcome.expel_range;
  for (const p of state.players) {
    if (p.id === welcome.id || fellows.has(p.id)) continue;
    const distance = Math.hypot(p.x - me.x, p.y - me.y);
    if (distance <= bestDistance) {
      best = p;
      bestDistance = distance;
    }
  }
  return best;
}

function updateExpelButton(state) {
  ui.expelButton.hidden = !isLivingExaminer(state);
  if (ui.expelButton.hidden) return;
  const cooldown = state.expel_cooldown;
  const target = expelTarget(state);
  ui.expelButton.disabled = cooldown > 0 || !target;
  let label = "Expel (E) · nobody in range";
  if (cooldown > 0) label = `Expel (E) · ready in ${cooldown} s`;
  else if (target) label = `Expel ${target.name} (E)`; // textContent: never read as HTML
  setText(ui.expelButton, label);
}

function tryExpel() {
  if (!latestState || !isLivingExaminer(latestState)) return;
  if (latestState.expel_cooldown > 0) {
    showToast(`Cooldown: ${latestState.expel_cooldown} s left`);
    return;
  }
  const target = expelTarget(latestState);
  if (!target) {
    showToast("No student in range");
    return;
  }
  send({ type: "expel", target: target.id });
}

function renderEnd(state) {
  // Redraw only when something on the end screen changes.
  const key = JSON.stringify([state.winner, state.roles, state.ghosts, state.colors, state.players.map((p) => [p.id, p.name])]);
  if (key !== endKey) {
    endKey = key;
    ui.endTitle.textContent = state.winner === "students" ? "Students win!" : "Examiners win!";
    ui.endScreen.dataset.winner = state.winner;
    const ghosts = new Set(state.ghosts || []);
    ui.endRoles.replaceChildren(
      ...state.players.map((p) => {
        const role = state.roles[p.id];
        const item = document.createElement("li");
        item.append(colorDot(state, p.id), p.name); // appended as text: never read as HTML
        item.append(tag(role === "examiner" ? "Examiner" : "Student", role));
        if (ghosts.has(p.id)) item.append(tag("expelled", "expelled"));
        if (p.id === welcome.id) item.append(tag("you", "you"));
        return item;
      }),
    );
  }
  const isHost = state.host === welcome.id;
  ui.restartButton.hidden = !isHost;
  setText(ui.restartHint, isHost ? "" : "Waiting for the host to start a new round");
}

ui.expelButton.addEventListener("click", () => {
  tryExpel();
  ui.expelButton.blur();
});

ui.restartButton.addEventListener("click", () => {
  // The server checks host and phase; a rejection comes back as a toast.
  send({ type: "restart" });
  ui.restartButton.blur();
});

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
    this.sprites = new Map(); // id -> character from Render.makeCharacter()
    this.exams = new Map(); // failed exam id -> sheet from Render.makeExam()
    this.lastSent = { dx: 0, dy: 0 };
    this.predicted = null; // own position as predicted by this browser
  }

  create() {
    // The map is drawn from the server's data; the darkness covers it outside the
    // vision radius (which the server sent in "welcome").
    const { width, height } = Render.drawMap(this, welcome.map);
    this.fog = Render.makeFog(this, welcome.vision_radius, Math.max(width, height));

    const camera = this.cameras.main;
    camera.setBounds(0, 0, width, height);
    camera.setBackgroundColor(Render.BACKDROP);
    const fitCamera = () => camera.setZoom(Render.cameraZoom(width, height, welcome.vision_radius));
    fitCamera();
    this.scale.on("resize", fitCamera);

    this.keys = this.input.keyboard.addKeys("W,A,S,D,UP,DOWN,LEFT,RIGHT,E");
    // On the key event itself, so even a very short tap counts (tryExpel checks the role).
    this.keys.E.on("down", () => tryExpel());

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
    let dx = 0;
    let dy = 0;
    if (lastPhase === "ended") {
      // The server rejects movement now and has already stopped everyone.
      this.lastSent = { dx: 0, dy: 0 };
    } else {
      ({ dx, dy } = this.readKeys());
      this.sendDirection(dx, dy);
    }

    const newest = snapshots[snapshots.length - 1];
    const latest = newest.players;
    this.syncSprites(latest);
    this.syncExams(latestState.failed_exams);
    this.updateOwn(latest.get(welcome.id), dx, dy, deltaMs / 1000);
    this.updateOthers(latest);
    for (const [id, sprite] of this.sprites) {
      Render.animateCharacter(sprite, { ...sprite.walk, ghost: newest.ghosts.has(id) }, time);
    }

    // Darkness only for the living while playing: ghosts, the lobby and the end screen
    // show the whole map (the server sends them everything as well).
    const own = this.sprites.get(welcome.id);
    if (own) Render.updateFog(this.fog, own.x, own.y, lastPhase === "playing" && latestState.alive);
  }

  // Failed exams ("6/20") lie on the floor until the next round. While playing, the
  // living only receive the ones within their vision radius.
  syncExams(exams) {
    const ids = new Set(exams.map((e) => e.id));
    for (const exam of exams) {
      if (!this.exams.has(exam.id)) this.exams.set(exam.id, Render.makeExam(this, exam));
    }
    for (const [id, container] of this.exams) {
      if (!ids.has(id)) {
        container.destroy();
        this.exams.delete(id);
      }
    }
  }

  // Create characters for players who are new or came into sight, remove those who
  // left or went out of sight.
  syncSprites(latest) {
    for (const [id, p] of latest) {
      if (this.sprites.has(id)) continue;
      const isOwn = id === welcome.id;
      const sprite = Render.makeCharacter(this, {
        name: p.name,
        color: latestState.colors[id],
        isOwn,
        half: welcome.player_half,
      });
      sprite.setPosition(p.x, p.y);
      sprite.walk = { dx: 0, dy: 0 }; // walking direction, for the animation
      if (isOwn) this.cameras.main.startFollow(sprite, false, 0.15, 0.15);
      this.sprites.set(id, sprite);
    }
    for (const [id, sprite] of this.sprites) {
      if (!latest.has(id)) {
        sprite.destroy();
        this.sprites.delete(id);
      }
    }
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
    sprite.walk = { dx, dy };
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
      // Walking direction for the animation: where they moved between the two states.
      sprite.walk = { dx: direction(b.x - a.x), dy: direction(b.y - a.y) };
    }
  }
}

// -1, 0 or 1 for a distance in pixels; less than half a pixel counts as standing still.
function direction(distance) {
  return Math.abs(distance) < 0.5 ? 0 : Math.sign(distance);
}

function startGame() {
  // The canvas has pixelRatio times as many pixels as the window and is shown scaled
  // back down, so the game stays sharp on phones and high-density laptop screens.
  const ratio = Render.pixelRatio;
  const size = () => [Math.round(window.innerWidth * ratio), Math.round(window.innerHeight * ratio)];
  const [width, height] = size();
  const game = new Phaser.Game({
    type: Phaser.AUTO,
    parent: "game",
    backgroundColor: Render.BACKDROP,
    scale: { mode: Phaser.Scale.NONE, width, height, zoom: 1 / ratio },
    scene: CampusScene,
  });
  window.addEventListener("resize", () => game.scale.resize(...size()));
}
