// Browser client: sends only the pressed direction, draws what the server sends.
// The server decides every position. To feel immediate, the own character is
// predicted locally in the server's own ticks, with the same step and wall rule
// (see REPEATS SERVER RULE), and repaired from the server's position (spec 008, part 1).
// How things look (map, characters, failed exams, darkness) is in render.js.

"use strict";

const INTERPOLATION_DELAY = 100; // ms: draw other players this far in the past
const SNAP_DISTANCE_TILES = 2; // jump to the server position if further off than this
// Own movement (spec 008, part 1). The server's answer is always a little old, so it is
// compared with where this browser predicted itself during the last TRAIL_TICKS ticks.
const TRAIL_TICKS = 8; // 8 ticks = 400 ms: longer than a round trip to the server
const MIN_CORRECTION = 0.5; // px: smaller differences are only the rounding of positions
const BLEND_RATE = 8; // per second: how fast the drawn character glides after a repair
const MAX_TICKS_PER_FRAME = 5; // after a very long frame (hidden tab), do not replay it all
const ROLE_SCREEN_MS = 3000; // how long the role screen shows at the start
// REPEATS SERVER RULE: MIN_PLAYERS in server/game.py. Only for the hint; the server decides.
const MIN_PLAYERS = 4;
// REPEATS SERVER RULE: EXPEL_COOLDOWN/DOOR_COOLDOWN/SABOTAGE_COOLDOWN in server/game.py.
// Only to size the cooldown ring's sweep; the server is the only one that counts down.
const EXPEL_COOLDOWN = 20;
const DOOR_COOLDOWN = 3;
const SABOTAGE_COOLDOWN = 30;
const RING_CIRCUMFERENCE = 2 * Math.PI * 35; // matches r="35" on .ring-sweep in index.html

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
  lobbyCount: document.getElementById("lobby-count"),
  lobbyPlayers: document.getElementById("lobby-players"),
  inviteButton: document.getElementById("invite-button"),
  inviteScreen: document.getElementById("invite-screen"),
  inviteUrl: document.getElementById("invite-url"),
  inviteClose: document.getElementById("invite-close"),
  startButton: document.getElementById("start-button"),
  startHint: document.getElementById("start-hint"),
  roleScreen: document.getElementById("role-screen"),
  roleTitle: document.getElementById("role-title"),
  roleDetail: document.getElementById("role-detail"),
  roleBadge: document.getElementById("role-badge"),
  actions: document.getElementById("actions"),
  expelButton: document.getElementById("expel-button"),
  taskButton: document.getElementById("task-button"),
  doorItem: document.getElementById("door-item"),
  doorButtons: document.getElementById("door-buttons"),
  doorActionButton: document.getElementById("door-action-button"),
  fixButton: document.getElementById("fix-button"),
  controlMove: document.getElementById("control-move"),
  controlExpel: document.getElementById("control-expel"),
  controlReport: document.getElementById("control-report"),
  controlUse: document.getElementById("control-use"),
  controlUseLabel: document.getElementById("control-use-label"),
  controlDoor: document.getElementById("control-door"),
  controlSabotage: document.getElementById("control-sabotage"),
  sabotageButton: document.getElementById("sabotage-button"),
  lightsBanner: document.getElementById("lights-banner"),
  switchArea: document.getElementById("switch-area"),
  taskBar: document.getElementById("task-bar"),
  taskBarFill: document.getElementById("task-bar-fill"),
  taskList: document.getElementById("task-list"),
  taskItems: document.getElementById("task-items"),
  joke: document.getElementById("joke"),
  jokeTitle: document.getElementById("joke-title"),
  jokeText: document.getElementById("joke-text"),
  minigamePanel: document.getElementById("minigame-panel"),
  minigameTitle: document.getElementById("minigame-title"),
  minigameHint: document.getElementById("minigame-hint"),
  minigameNote: document.getElementById("minigame-note"),
  minigameContent: document.getElementById("minigame-content"),
  minigameClose: document.getElementById("minigame-close"),
  reportButton: document.getElementById("report-button"),
  meetingButton: document.getElementById("meeting-button"),
  ghostBanner: document.getElementById("ghost-banner"),
  ghostTitle: document.getElementById("ghost-title"),
  meetingScreen: document.getElementById("meeting-screen"),
  meetingCard: document.getElementById("meeting-card"),
  meetingTitle: document.getElementById("meeting-title"),
  meetingTimer: document.getElementById("meeting-timer"),
  meetingReason: document.getElementById("meeting-reason"),
  meetingPlayers: document.getElementById("meeting-players"),
  skipButton: document.getElementById("skip-button"),
  meetingStatus: document.getElementById("meeting-status"),
  endScreen: document.getElementById("end-screen"),
  endTitle: document.getElementById("end-title"),
  endRoles: document.getElementById("end-roles"),
  restartButton: document.getElementById("restart-button"),
  restartHint: document.getElementById("restart-hint"),
};

// --- Hints and key labels by input device, not by screen width (spec 007) -----------

for (const el of document.querySelectorAll(".hint-keyboard")) el.hidden = Controls.isTouch;
for (const el of document.querySelectorAll(".hint-touch")) el.hidden = !Controls.isTouch;
for (const el of document.querySelectorAll(".key-hint")) el.hidden = Controls.isTouch;

// --- Invite players: QR code and URL, lobby only (spec 007) -------------------------

ui.inviteUrl.textContent = `${location.origin}/`;
ui.inviteButton.addEventListener("click", () => (ui.inviteScreen.hidden = false));
ui.inviteClose.addEventListener("click", () => (ui.inviteScreen.hidden = true));

let socket = null;
// {id, map, sight_grid, speed, tick_rate, step, player_half, corner_slide, expel_range, report_range,
// meeting_range, meeting_table_radius, task_range, switch_range, vision_radius,
// lights_out_radius} once joined
let welcome = null;
// Recent server states: {time, players: Map(id -> {name,x,y}), ghosts: Set(id)}
let snapshots = [];
let latestState = null; // the newest state message as the server sent it
let toastTimer = null;
let lastPhase = null; // "lobby", "playing", "meeting" or "ended", from the latest state
let lobbyKey = ""; // what the lobby list currently shows, to redraw only on changes
let endKey = ""; // the same for the end screen
let meetingKey = ""; // the same for the meeting screen
let rosterIds = []; // every player id seen in the lobby this round, for the meeting grid
let pendingVote = null; // a candidate id or "skip" picked but not yet confirmed (spec 014)
let votingArgs = null; // the latest {state, meeting}, so a confirm/cancel tap can redraw
// the grid at once, without waiting for the server's next state
let roleTimer = null;
let sentSurfing = false; // this player was voted out in this round
// Nicknames and colour numbers by player id. While playing, the server only sends the
// players in sight (and the living never receive ghosts), so the ones seen earlier
// (everyone is visible in the lobby) are remembered here.
const knownNames = new Map();
const knownColors = new Map();

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
    if (welcome) {
      showToast(message.reason);
      meetingKey = ""; // redraw the meeting screen: re-enables the vote buttons
    } else {
      showJoinError(message.reason);
    }
  } else if (message.type === "state" && welcome) {
    const players = new Map(message.players.map((p) => [p.id, p]));
    // Only a ghost (or everyone after the end) receives the ghost list; the living
    // do not even receive the ghosts' positions.
    snapshots.push({ time: performance.now(), players, ghosts: new Set(message.ghosts || []) });
    latestState = message;
    for (const p of message.players) knownNames.set(p.id, p.name);
    for (const [id, color] of Object.entries(message.colors)) knownColors.set(id, color);
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
  dot.style.background = Render.colorCss(playerColor(state, playerId));
  return dot;
}

// A player's nickname, also for players out of sight or voted out.
function nameOf(playerId) {
  return knownNames.get(playerId) ?? "A player";
}

function playerColor(state, playerId) {
  return state.colors[playerId] ?? knownColors.get(playerId);
}

// A small original character (spec 014), echoing the one drawn on the map (render.js) at a
// glance: a round body in the player's colour, a graduation cap and two eyes. Used for the
// lobby chips and the meeting cards; a ghost is drawn greyed out with CSS (.ghost), not here.
function characterChip(colorNumber, size = 32) {
  const svg = svgEl("svg", { viewBox: "0 0 40 40", width: size, height: size, class: "chip-figure" });
  const fill = Render.colorCss(colorNumber);
  svg.append(
    svgEl("circle", { cx: 20, cy: 23, r: 14, fill, stroke: "#16181d", "stroke-width": 2 }),
    svgEl("path", { d: "M6 15 L20 8 L34 15 L20 19 Z", fill: "#2d313b", stroke: "#596072", "stroke-width": 1 }),
    svgEl("circle", { cx: 15.5, cy: 22, r: 2.3, fill: "#fff" }),
    svgEl("circle", { cx: 24.5, cy: 22, r: 2.3, fill: "#fff" }),
    svgEl("circle", { cx: 15.5, cy: 22.4, r: 0.9, fill: "#16181d" }),
    svgEl("circle", { cx: 24.5, cy: 22.4, r: 0.9, fill: "#16181d" }),
  );
  return svg;
}

// The host's original symbol (spec 014): a ring with an upward chevron, no text or emoji.
function hostSymbol() {
  const svg = svgEl("svg", { viewBox: "0 0 16 16", width: 14, height: 14, class: "host-symbol", role: "img", "aria-label": "host" });
  svg.append(
    svgEl("circle", { cx: 8, cy: 8, r: 7, fill: "none", stroke: "currentColor", "stroke-width": 1.5 }),
    svgEl("path", {
      d: "M4.5 9.5 L8 5.5 L11.5 9.5",
      fill: "none",
      stroke: "currentColor",
      "stroke-width": 1.5,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
    }),
  );
  return svg;
}

// --- Controls as pictograms (spec 008, part 9) --------------------------------------------
// The keycaps in the HUD (index.html, style.css). A key is shown exactly while its action
// button is shown, so the HUD never promises an action that is not possible right now.
// Called after the buttons were updated. On touch devices the whole group is hidden and
// the joystick hint shows instead (chosen by input device at the top of this file).

function updateControls(state) {
  ui.controlMove.hidden = state.phase === "meeting" || state.phase === "ended"; // nobody moves
  ui.controlExpel.hidden = ui.expelButton.hidden;
  ui.controlReport.hidden = ui.reportButton.hidden;
  ui.controlUse.hidden = ui.taskButton.hidden && ui.fixButton.hidden;
  setText(ui.controlUseLabel, ui.fixButton.hidden ? "task" : "fix lights");
  ui.controlDoor.hidden = ui.doorButtons.children.length === 0;
  ui.controlSabotage.hidden = ui.sabotageButton.hidden;
}

// --- Lobby and roles --------------------------------------------------------------
// Everything here is drawn from the server's state; this browser only ever receives
// its own role (and, for an examiner, the fellow examiners' ids).

function updatePhase(state) {
  // Only at the start of a game: play resuming after a meeting shows no role screen.
  const justStarted = state.phase === "playing" && lastPhase === "lobby";
  lastPhase = state.phase;
  ui.lobby.hidden = state.phase !== "lobby";
  if (state.phase !== "lobby") ui.inviteScreen.hidden = true;
  ui.endScreen.hidden = state.phase !== "ended";
  ui.meetingScreen.hidden = state.phase !== "meeting";
  Controls.setHidden(state.phase === "meeting"); // must not cover the meeting screen
  if (state.phase === "lobby") sentSurfing = false;
  const result = state.meeting && state.meeting.result;
  if (result && result.surfing === welcome.id) sentSurfing = true;
  ui.ghostBanner.hidden = !(state.phase === "playing" && !state.alive);
  setText(ui.ghostTitle, sentSurfing ? "You have been sent surfing" : "You have been expelled");
  // The whole action bar only during a round (spec 014): a slot's own hidden/disabled
  // state below only has to track the player's role and momentary availability, not phase.
  ui.actions.hidden = state.phase !== "playing";
  updateExpelButton(state);
  updateReportAndMeeting(state);
  updateTasks(state);
  updateMinigame(state);
  updateDoors(state);
  updateLights(state);
  updateControls(state);
  if (state.phase === "lobby") {
    ui.roleBadge.hidden = true;
    renderLobby(state);
    return;
  }
  if (state.phase === "meeting") {
    ui.roleScreen.hidden = true;
    renderMeeting(state);
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
  // The whole lobby's roster, remembered for the meeting grid (spec 014): a living
  // player's state never lists a ghost, so "who is missing from `meeting.living`" is read
  // against this list, captured here since the lobby is the one phase everyone sees
  // everyone in.
  rosterIds = state.players.map((p) => p.id);
  setText(ui.lobbyCount, `${state.players.length}/10`);

  // Redraw the list only when players or host change (states arrive 20 times a second).
  const key = JSON.stringify([state.host, state.colors, state.players.map((p) => [p.id, p.name])]);
  if (key !== lobbyKey) {
    lobbyKey = key;
    ui.lobbyPlayers.replaceChildren(
      ...state.players.map((p) => {
        const item = document.createElement("li");
        item.className = "lobby-chip";
        item.append(characterChip(playerColor(state, p.id), 36));
        const name = document.createElement("span");
        name.className = "lobby-chip-name";
        name.append(p.name); // appended as text: never read as HTML
        if (p.id === state.host) name.append(hostSymbol());
        if (p.id === welcome.id) name.append(tag("you", "you"));
        item.append(name);
        return item;
      }),
    );
  }
  const isHost = state.host === welcome.id;
  const enough = state.players.length >= MIN_PLAYERS;
  ui.startButton.hidden = !isHost;
  ui.startButton.disabled = !enough;
  setText(ui.startButton, enough ? "Start game" : `Need ${MIN_PLAYERS - state.players.length} more players`);
  let hint = "";
  if (!isHost) hint = enough ? "Waiting for the host to start" : `Need at least ${MIN_PLAYERS} players`;
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
    ui.roleBadge.hidden = lastPhase !== "playing" && lastPhase !== "meeting";
  }, ROLE_SCREEN_MS);
}

function setText(element, text) {
  if (element.textContent !== text) element.textContent = text;
}

// The action bar's own rendered height (spec 014), for render.js's edge arrows: the bar's
// height depends on the role (3 slots for a student, 6 for an examiner) and the window
// size, so this reads the real thing instead of guessing a fixed margin.
function actionsBottomMargin() {
  if (ui.actions.hidden) return 150;
  const rect = ui.actions.getBoundingClientRect();
  return window.innerHeight - rect.top + 16;
}

// --- The shared action button component (spec 014) ----------------------------------
// One round button per in-round action, always in the same slot for a role: main.js never
// hides one because it is momentarily out of reach, only disables it and explains why, as
// both the title (desktop hover) and the aria-label (screen readers).

function setActionReason(button, reason, defaultLabel) {
  const title = reason || "";
  if (button.title !== title) button.title = title;
  const label = reason || defaultLabel;
  if (button.getAttribute("aria-label") !== label) button.setAttribute("aria-label", label);
}

// A timed cooldown (expel, staff door, lights off): the ring sweeps back to full as
// `secondsLeft` counts down to 0, with the number in the middle. `secondsLeft` is always
// the server's own value; `totalSeconds` only sizes the sweep.
function setCooldownRing(button, secondsLeft, totalSeconds) {
  const ring = button.querySelector(".ring-sweep");
  const cooldown = button.querySelector(".action-cooldown");
  if (!ring) return;
  if (secondsLeft > 0) {
    const fraction = Math.min(1, secondsLeft / totalSeconds);
    ring.style.strokeDasharray = `${RING_CIRCUMFERENCE} ${RING_CIRCUMFERENCE}`;
    ring.style.strokeDashoffset = `${RING_CIRCUMFERENCE * (1 - fraction)}`;
    ring.style.opacity = "1";
    setText(cooldown, String(secondsLeft));
  } else {
    ring.style.opacity = "0";
    setText(cooldown, "");
  }
}

// The one-shot "call a meeting" action: the server only ever sends `meeting_used` as a
// flag, never a countdown, so the ring is either fully drawn (used, for the rest of the
// round) or not drawn at all — never a number in the middle.
function setUsedRing(button, used) {
  const ring = button.querySelector(".ring-sweep");
  if (!ring) return;
  ring.style.strokeDasharray = `${RING_CIRCUMFERENCE} ${RING_CIRCUMFERENCE}`;
  ring.style.strokeDashoffset = used ? "0" : `${RING_CIRCUMFERENCE}`;
  ring.style.opacity = used ? "1" : "0";
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
  // Hidden only by role, for the whole round (spec 014): a ghost examiner still sees its
  // own fixed EXPEL slot, just greyed out, instead of it disappearing.
  ui.expelButton.hidden = state.role !== "examiner";
  if (ui.expelButton.hidden) return;
  const alive = state.phase === "playing" && state.alive;
  const cooldown = alive ? state.expel_cooldown : 0;
  const target = alive ? expelTarget(state) : null;
  ui.expelButton.disabled = !alive || cooldown > 0 || !target;
  let reason = "";
  if (!alive) reason = "Ghosts cannot expel";
  else if (cooldown > 0) reason = `Ready in ${cooldown} s`;
  else if (!target) reason = "Nobody in range";
  else reason = `Expel ${target.name}`; // the full reason, e.g. on hover; the label stays "Expel"
  setActionReason(ui.expelButton, reason, "Expel");
  setCooldownRing(ui.expelButton, cooldown, EXPEL_COOLDOWN);
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
    // The task win is the only way a round ends with every task done (spec 004).
    const progress = state.task_progress;
    const byTasks = state.winner === "students" && progress.total > 0 && progress.done === progress.total;
    let title = state.winner === "students" ? "Students win!" : "Examiners win!";
    if (byTasks) title = "All tasks done: students win";
    ui.endTitle.textContent = title;
    ui.endScreen.dataset.winner = state.winner;
    const ghosts = new Set(state.ghosts || []);
    ui.endRoles.replaceChildren(
      ...state.players.map((p) => {
        const role = state.roles[p.id];
        const item = document.createElement("li");
        item.append(colorDot(state, p.id), p.name); // appended as text: never read as HTML
        item.append(tag(role === "examiner" ? "Examiner" : "Student", role));
        // "ghost", not "expelled": a ghost may also have been voted out (spec 006).
        if (ghosts.has(p.id)) item.append(tag("ghost", "ghost"));
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

// --- Report, meeting table, meeting and vote (spec 006, spec 011) --------------------
// The buttons are only a convenience: the server checks phase, range and votes again.

function isLivingAndPlaying(state) {
  return state.phase === "playing" && state.alive;
}

// Nearest failed exam within report range of the latest server position.
function reportTarget(state) {
  if (!isLivingAndPlaying(state)) return null;
  const me = state.players.find((p) => p.id === welcome.id);
  if (!me) return null;
  let best = null;
  let bestDistance = welcome.report_range;
  for (const exam of state.failed_exams) {
    const distance = Math.hypot(exam.x - me.x, exam.y - me.y);
    if (distance <= bestDistance) {
      best = exam;
      bestDistance = distance;
    }
  }
  return best;
}

// The middle of the meeting table in map pixels, or null on a map without one.
function meetingTable() {
  const place = welcome.map.meeting_point;
  if (!place) return null;
  const t = welcome.map.tile_size;
  return { x: (place[0] + 0.5) * t, y: (place[1] + 0.5) * t };
}

// A meeting is called only at the meeting table (spec 011): is the latest server position
// within meeting_range of the table's edge? A map without a table calls from anywhere.
// REPEATS SERVER RULE: Game.call_meeting() in server/game.py. Only for the button.
function nearMeetingTable(state) {
  const table = meetingTable();
  if (!table) return true;
  const me = state.players.find((p) => p.id === welcome.id);
  if (!me) return false;
  const reach = welcome.meeting_table_radius + welcome.meeting_range;
  return Math.hypot(table.x - me.x, table.y - me.y) <= reach;
}

function updateReportAndMeeting(state) {
  // Both fixed slots, for every role (spec 014): the server never restricts report or
  // meeting by role either (only by being alive and, for meeting, at the table).
  ui.reportButton.hidden = false;
  ui.meetingButton.hidden = false;
  const alive = isLivingAndPlaying(state);
  const target = alive ? reportTarget(state) : null;
  ui.reportButton.disabled = !target;
  let reportReason = "";
  if (!alive) reportReason = "Ghosts cannot report";
  else if (!target) reportReason = "No failed exam within reach";
  setActionReason(ui.reportButton, reportReason, "Report");

  const near = alive && nearMeetingTable(state);
  const used = Boolean(state.meeting_used);
  ui.meetingButton.disabled = !alive || used || !near;
  let meetingReason = "";
  if (!alive) meetingReason = "Ghosts cannot call a meeting";
  else if (used) meetingReason = "Already used this round";
  else if (!near) meetingReason = "Go to the meeting table";
  setActionReason(ui.meetingButton, meetingReason, "Call a meeting");
  setUsedRing(ui.meetingButton, used);
}

function tryReport() {
  if (!latestState || !isLivingAndPlaying(latestState)) return;
  const exam = reportTarget(latestState);
  if (!exam) {
    showToast("No failed exam within reach");
    return;
  }
  send({ type: "report", exam: exam.id });
}

ui.reportButton.addEventListener("click", () => {
  tryReport();
  ui.reportButton.blur();
});

ui.meetingButton.addEventListener("click", () => {
  send({ type: "meeting" });
  ui.meetingButton.blur();
});

function renderMeeting(state) {
  const meeting = state.meeting;
  setText(ui.meetingTimer, `${meeting.seconds_left} s`);
  const result = meeting.result;
  // Redraw only when something on the screen changes; the timer is updated above, so a
  // redraw does not replace the cards under the mouse every second.
  const key = JSON.stringify([{ ...meeting, seconds_left: null }, state.alive]);
  if (key === meetingKey) return;
  meetingKey = key;
  pendingVote = null; // a real change from the server always clears a half-made pick

  const caller = nameOf(meeting.called_by); // added as text: never read as HTML
  ui.meetingReason.textContent =
    meeting.reason === "report" ? `${caller} found a failed exam` : `${caller} called a meeting`;
  if (result) renderResult(state, result);
  else renderVoting(state, meeting);
}

function canActuallyVote(state, meeting) {
  return state.alive && meeting.my_vote === null;
}

// One card in the 2-column grid (spec 014): a small original character in the player's
// colour, their name, a "you" marker and a "VOTED" stamp once they have voted. Ghosts are
// greyed out and not votable. Tapping a votable card opens a confirm/cancel step inside
// it, instead of sending the vote straight away.
function buildPlayerCard(state, playerId, { isGhost, hasVoted, canVote }) {
  const card = document.createElement("div");
  card.className = "meeting-player-card" + (isGhost ? " ghost" : "");
  card.append(characterChip(playerColor(state, playerId), 40));
  const name = document.createElement("span");
  name.className = "player-name";
  name.append(nameOf(playerId)); // appended as text: never read as HTML
  if (playerId === welcome.id) name.append(tag("you", "you"));
  card.append(name);
  if (hasVoted) {
    const stamp = document.createElement("span");
    stamp.className = "voted-stamp";
    stamp.textContent = "VOTED";
    card.append(stamp);
  }

  if (isGhost) {
    card.setAttribute("aria-disabled", "true");
    card.title = "Ghosts cannot vote";
    return card;
  }
  if (!canVote) {
    card.classList.add("disabled");
    return card;
  }
  card.setAttribute("role", "button");
  card.tabIndex = 0;
  const select = () => {
    pendingVote = playerId;
    buildVotingGrid();
  };
  card.addEventListener("click", select);
  card.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select();
    }
  });

  if (pendingVote === playerId) {
    card.classList.add("pending");
    card.append(confirmStep(`Vote for ${nameOf(playerId)}?`, "Vote", () => castVote(playerId)));
  }
  return card;
}

// The confirm/cancel step shown inside a card once it is tapped (spec 014): a short prompt
// and two buttons, never sent until "Confirm" is tapped.
function confirmStep(prompt, confirmLabel, onConfirm) {
  const wrap = document.createElement("div");
  const line = document.createElement("span");
  line.className = "confirm-prompt";
  line.textContent = prompt;
  const row = document.createElement("div");
  row.className = "confirm-row";
  const confirmButton = document.createElement("button");
  confirmButton.type = "button";
  confirmButton.textContent = confirmLabel;
  confirmButton.addEventListener("click", (event) => {
    event.stopPropagation();
    onConfirm();
  });
  const cancelButton = document.createElement("button");
  cancelButton.type = "button";
  cancelButton.className = "cancel-vote";
  cancelButton.textContent = "Cancel";
  cancelButton.addEventListener("click", (event) => {
    event.stopPropagation();
    pendingVote = null;
    buildVotingGrid();
  });
  row.append(confirmButton, cancelButton);
  wrap.append(line, row);
  return wrap;
}

// The "Skip vote" card: `ui.skipButton` is one persistent element (its id and click
// listener never change, see below), only its content is rebuilt every time the grid is.
function buildSkipCard(canVote) {
  const card = ui.skipButton;
  card.hidden = false;
  card.className = "meeting-player-card skip-card" + (pendingVote === "skip" ? " pending" : "") + (!canVote ? " disabled" : "");
  card.setAttribute("aria-disabled", String(!canVote));
  card.replaceChildren();
  const icon = svgEl("svg", { viewBox: "0 0 24 24", class: "action-icon", "aria-hidden": "true" });
  icon.append(
    svgEl("path", {
      d: "M5 12h13M12 6l6 6-6 6",
      fill: "none",
      stroke: "currentColor",
      "stroke-width": 2,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
    }),
  );
  const label = document.createElement("span");
  label.className = "player-name";
  label.textContent = "Skip vote";
  card.append(icon, label);
  if (pendingVote === "skip") card.append(confirmStep("Skip this vote?", "Skip", () => castVote("skip")));
  return card;
}

// Rebuilds the whole grid from the latest known state/meeting (`votingArgs`): called both
// for a real change from the server (renderVoting) and right away for a local pick or a
// cancel (buildPlayerCard/buildSkipCard/the skip click below), so the confirm step shows
// at once instead of waiting for the next "state" message.
function buildVotingGrid() {
  const { state, meeting } = votingArgs;
  ui.meetingPlayers.classList.remove("locked");
  const canVote = canActuallyVote(state, meeting);
  const voted = new Set(meeting.voted);
  const living = new Set(meeting.living);
  // A living player's state never lists a ghost (server/game.py); `state.ghosts` only
  // exists for a ghost viewer (or after the end). Otherwise, a known player missing from
  // `meeting.living` has to be a ghost: nobody leaves a running game any other way.
  const ghostIds = (state.ghosts ?? rosterIds).filter((id) => !living.has(id));

  const cards = meeting.living.map((playerId) =>
    buildPlayerCard(state, playerId, {
      isGhost: false,
      hasVoted: voted.has(playerId),
      // No confirm step on the own card: the server rejects a vote for yourself (spec
      // 008, part 2).
      canVote: canVote && playerId !== welcome.id,
    }),
  );
  for (const playerId of ghostIds) {
    cards.push(buildPlayerCard(state, playerId, { isGhost: true, hasVoted: false, canVote: false }));
  }
  cards.push(buildSkipCard(canVote));
  ui.meetingPlayers.replaceChildren(...cards);

  ui.meetingStatus.classList.remove("verdict");
  let status = "Tap a player or skip, then confirm.";
  if (!state.alive) status = "Ghosts cannot vote";
  else if (meeting.my_vote === "skip") status = "You skipped";
  else if (meeting.my_vote) status = `You voted for ${nameOf(meeting.my_vote)}`;
  ui.meetingStatus.textContent = status;
}

function renderVoting(state, meeting) {
  setText(ui.meetingTitle, "Meeting: who is an examiner?");
  votingArgs = { state, meeting };
  buildVotingGrid();
}

// `count` small dots, one per vote (spec 014) — only a count, never an identity: the
// server does not tell a client who voted for whom (R2, docs/brd.md).
function voteDots(count) {
  const wrap = document.createElement("span");
  wrap.className = "vote-dots";
  for (let i = 0; i < count; i++) {
    const dot = document.createElement("span");
    dot.className = "vote-dot";
    wrap.append(dot);
  }
  return wrap;
}

function renderResult(state, result) {
  setText(ui.meetingTitle, "Result");
  const cards = Object.entries(result.votes).map(([playerId, count]) => {
    const card = document.createElement("div");
    card.className = "meeting-player-card";
    card.append(characterChip(playerColor(state, playerId), 40));
    const name = document.createElement("span");
    name.className = "player-name";
    name.append(nameOf(playerId)); // appended as text: never read as HTML
    if (playerId === welcome.id) name.append(tag("you", "you"));
    if (playerId === result.surfing) name.append(tag("sent surfing", "surfing"));
    card.append(name);
    const votesLabel = document.createElement("span");
    votesLabel.className = "count";
    votesLabel.textContent = count === 1 ? "1 vote" : `${count} votes`;
    card.append(votesLabel, voteDots(count));
    return card;
  });
  const skipCard = document.createElement("div");
  skipCard.className = "meeting-player-card skip-card";
  const skipLabel = document.createElement("span");
  skipLabel.className = "player-name";
  skipLabel.textContent = "Skipped";
  const skipCount = document.createElement("span");
  skipCount.className = "count";
  skipCount.textContent = String(result.skips);
  skipCard.append(skipLabel, skipCount);
  ui.meetingPlayers.classList.remove("locked");
  ui.meetingPlayers.replaceChildren(...cards, skipCard);
  ui.skipButton.hidden = true;
  ui.meetingStatus.classList.add("verdict");
  ui.meetingStatus.textContent = result.surfing
    ? `${nameOf(result.surfing)} was sent surfing`
    : "Nobody was sent surfing";
}

function castVote(target) {
  // Lock the grid until the server's answer: the next state shows the vote, a rejection
  // comes back as a toast and unlocks it (handleMessage resets meetingKey on an error).
  pendingVote = null;
  ui.meetingPlayers.classList.add("locked");
  for (const button of ui.meetingScreen.querySelectorAll("button")) button.disabled = true;
  send({ type: "vote", target });
}

// One persistent listener for the skip card's own click (not inside buildSkipCard, which
// reruns on every redraw and would otherwise pile up a new listener each time): picks
// "skip" as the pending choice, same as tapping a player card.
ui.skipButton.addEventListener("click", () => {
  if (!votingArgs || pendingVote === "skip") return;
  const { state, meeting } = votingArgs;
  if (!canActuallyVote(state, meeting)) return;
  pendingVote = "skip";
  buildVotingGrid();
});

// --- Tasks (spec 004) ----------------------------------------------------------------
// The server deals, times and counts the tasks. This only shows them and sends "task";
// the button is a convenience, the server checks the place and the task again.

const JOKE_MS = 4000; // how long the joke of a finished task shows
let taskKey = ""; // what the task list currently shows, to redraw only on changes
let lastDoing = null; // the task id the previous state had in `doing`, to notice it ending
let doingSince = 0; // performance.now() when the running task was first seen
let doingSeconds = 0; // how long that task takes in all
let wasAlive = true; // `alive` in the previous state
let jokeTimer = null;

// Examiners get the same tasks as students now, drawn fake from the same pool (spec 012,
// part 3): nothing here tells the two roles apart, so an examiner's panel, markers and
// button look exactly like a student's. Only a ghost examiner cannot do tasks; a ghost
// student still can (R4).
function isTaskPlayer(state) {
  return state.phase === "playing" && (state.role === "student" || state.alive);
}

// Nearest own open task within task_range of the latest server position.
function taskTarget(state) {
  if (!isTaskPlayer(state) || state.doing) return null;
  const me = state.players.find((p) => p.id === welcome.id);
  if (!me) return null;
  let best = null;
  let bestDistance = welcome.task_range;
  for (const task of state.tasks) {
    if (task.done) continue;
    const distance = Math.hypot(task.x - me.x, task.y - me.y);
    if (distance <= bestDistance) {
      best = task;
      bestDistance = distance;
    }
  }
  return best;
}

function updateTasks(state) {
  const inRound = state.phase === "playing" || state.phase === "meeting";

  // The shared bar, for everyone.
  const progress = state.task_progress;
  ui.taskBar.hidden = !(inRound && progress && progress.total > 0);
  if (!ui.taskBar.hidden) {
    ui.taskBarFill.style.width = `${(100 * progress.done) / progress.total}%`;
    ui.taskBar.setAttribute("aria-valuemax", progress.total);
    ui.taskBar.setAttribute("aria-valuenow", progress.done);
  }

  // The own task list, for students. Titles are added as text, never as HTML. A multi-step
  // task (spec 012, part 4) shows "Step n/m: <title>" for its current station; the key
  // includes `step`/`title` too, so the list rebuilds when a step finishes and the next
  // station's title takes over, even though `id`/`done` stay the same.
  const tasks = state.tasks || [];
  ui.taskList.hidden = !(inRound && tasks.length > 0);
  const key = JSON.stringify(tasks.map((task) => [task.id, task.done, task.step, task.title]));
  if (key !== taskKey) {
    taskKey = key;
    ui.taskItems.replaceChildren(
      ...tasks.map((task) => {
        const item = document.createElement("li");
        if (task.done) item.className = "done";
        const area = document.createElement("span");
        area.className = "task-area";
        area.textContent = task.area;
        const label = task.step ? `Step ${task.step}/${task.steps}: ${task.title}` : task.title;
        item.append(label, area);
        return item;
      }),
    );
  }
  // The fixed USE slot (spec 014): a living student's USE slot shows "fix the lights"
  // instead while that is possible (tryUse() gives fix the same priority), so the slot
  // never shows both at once; everyone else always sees "task" in it.
  const showFix = state.role === "student" && canFix(state);
  ui.taskButton.hidden = showFix;
  if (!ui.taskButton.hidden) {
    const inRound = state.phase === "playing";
    const player = inRound && isTaskPlayer(state);
    const target = player ? taskTarget(state) : null;
    ui.taskButton.disabled = !player || Boolean(state.doing) || !target;
    let reason = "";
    if (inRound && !player) reason = "Ghosts cannot do tasks";
    else if (state.doing) reason = "Already doing something";
    else if (!target) reason = "None of your tasks is within reach";
    setActionReason(ui.taskButton, reason, "Use");
  }

  // A task that was running in the previous state and is not any more: done or cancelled.
  const doing = state.doing ? state.doing.task : null;
  if (doing && doing !== lastDoing) {
    doingSince = performance.now();
    doingSeconds = state.doing.seconds_left;
  }
  if (lastDoing && !doing) {
    const finished = tasks.find((task) => task.id === lastDoing && task.done);
    // A wrong-but-valid answer never gets here (the task keeps running); task_note is set
    // here only by a time-out or an explicit "Close" (task_cancel), which is the more exact
    // reason than the phase/alive guesses below (spec 012, part 2).
    if (finished) showJoke(finished);
    else if (state.task_note) showToast(state.task_note);
    else if (state.phase === "meeting") showToast("Task cancelled: a meeting started");
    else if (wasAlive && !state.alive)
      showToast(`Task cancelled: you were ${sentSurfing ? "sent surfing" : "expelled"}`);
    else if (state.phase === "playing") showToast("Task cancelled: you walked away");
  }
  lastDoing = doing;
  wasAlive = state.alive;
}

function showJoke(task) {
  ui.jokeTitle.textContent = `Done: ${task.title}`;
  ui.jokeText.textContent = task.joke;
  ui.joke.hidden = false;
  clearTimeout(jokeTimer);
  jokeTimer = setTimeout(() => (ui.joke.hidden = true), JOKE_MS);
}

function tryTask() {
  if (!latestState || !isTaskPlayer(latestState) || latestState.doing) return;
  const task = taskTarget(latestState);
  if (!task) {
    showToast("None of your tasks is within reach");
    return;
  }
  send({ type: "task", task: task.id });
}

ui.taskButton.addEventListener("click", () => {
  tryTask();
  ui.taskButton.blur();
});

// --- Mini-game panel (spec 012) ---------------------------------------------------------
// One panel shell for every mini-game kind; the server is the only judge of a value, this
// only shows the challenge and sends "task_input"/"task_cancel". It opens when the own
// `doing.challenge` first appears and closes when `doing` goes back to null (done, cancelled
// or timed out) — CampusScene.predictTick() also stops sending "input" messages while it is
// open, so tapping the panel never walks the character by accident. Builds the content for
// every one of the six kinds: "card" (gate), "cable" (socket), "seagull" (nata), "ticket"
// (certificate, step 2), "translate" (helpdesk) and "paper_jam" (print, and certificate
// step 1).
let minigameKey = ""; // task id + challenge, so the content rebuilds only when it changes
let minigameNoteShown = ""; // the task_note last shown, so an unchanged one does not flash

// One short line at the top of the panel, set as text (never HTML): what to do, for every
// kind, including the three still built from a placeholder below (spec 012).
const MINIGAME_HINTS = {
  card: "Type the number on your card.",
  cable: "Drag the matching cable into the projector.",
  seagull: "Tap the seagull 5 times.",
  ticket: "Press when your number is called.",
  translate: "Pick the right translation.",
  paper_jam: "Clear all 3 paper jams.",
};

const NATA_EATEN_MS = 1200; // how long the "gone" tart stays up after a seagull time-out
let nataEatenTimer = null;
let nataEaten = false; // showing the tart gone for a moment, instead of just closing the panel
let lastSeagullChallenge = null; // kept only to still show the final hit count while eaten

// The own running challenge, or null: a plain-wait station (no mini-game) has `doing` but
// no `doing.challenge`, and must not open the panel.
function minigameChallenge(state) {
  return state && state.doing && state.doing.challenge ? state.doing : null;
}

function updateMinigame(state) {
  const doing = minigameChallenge(state);

  if (doing && nataEaten) {
    // A new challenge started before the "eaten" view's own timer closed the panel.
    nataEaten = false;
    clearTimeout(nataEatenTimer);
  }
  if (doing && doing.challenge.kind === "seagull") lastSeagullChallenge = doing.challenge;

  // The seagull time-out clears `doing` in the very same snapshot that sets this note
  // (spec 012, part 2: task_note is not tick-scoped), so there is no tick where the panel
  // is open with this note already set. Catch the transition here instead, and hold the
  // panel open a moment longer to show the tart gone, rather than it just vanishing.
  if (!doing && !nataEaten && lastSeagullChallenge && state.task_note === "A seagull took it.") {
    nataEaten = true;
    ui.minigamePanel.hidden = false;
    setText(ui.minigameTitle, "Protect your pastel de nata");
    setText(ui.minigameHint, MINIGAME_HINTS.seagull);
    ui.minigameNote.hidden = true;
    renderSeagullEaten(lastSeagullChallenge);
    clearTimeout(nataEatenTimer);
    nataEatenTimer = setTimeout(() => {
      nataEaten = false;
      lastSeagullChallenge = null;
      ui.minigamePanel.hidden = true;
    }, NATA_EATEN_MS);
    return;
  }
  if (nataEaten) return; // the timer above owns the panel until it fires

  ui.minigamePanel.hidden = !doing;
  if (!doing) {
    minigameKey = "";
    minigameNoteShown = "";
    lastSeagullChallenge = null;
    return;
  }
  const task = (state.tasks || []).find((t) => t.id === doing.task);
  setText(ui.minigameTitle, task ? task.title : "");
  setText(ui.minigameHint, MINIGAME_HINTS[doing.challenge.kind] || "");
  const key = JSON.stringify([doing.task, doing.challenge]);
  if (key !== minigameKey) {
    minigameKey = key;
    renderChallenge(doing.task, doing.challenge);
  }
  const note = state.task_note || "";
  if (note !== minigameNoteShown) {
    minigameNoteShown = note;
    setText(ui.minigameNote, note);
    ui.minigameNote.hidden = !note;
  }
}

function sendTaskInput(taskId, value) {
  send({ type: "task_input", task: taskId, value });
}

// Texts are added as text, never as HTML (existing rule); every tap target below also
// answers a mouse click.
function renderChallenge(taskId, challenge) {
  ui.minigameContent.replaceChildren();
  if (challenge.kind === "card") renderCard(taskId, challenge);
  else if (challenge.kind === "cable") renderCable(taskId, challenge);
  else if (challenge.kind === "seagull") renderSeagull(taskId, challenge);
  else if (challenge.kind === "ticket") renderTicket(taskId, challenge);
  else if (challenge.kind === "translate") renderTranslate(taskId, challenge);
  else if (challenge.kind === "paper_jam") renderPaperJam(taskId, challenge);
}

// certificate, step 2 — "Now serving": press "That's me!" exactly when your number comes up.
function renderTicket(taskId, challenge) {
  const number = document.createElement("p");
  number.className = "minigame-number";
  number.textContent = String(challenge.number);
  const counter = document.createElement("p");
  counter.className = "minigame-hits";
  counter.textContent = `Now serving: ${challenge.counter}`;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "That's me!";
  button.addEventListener("click", () => sendTaskInput(taskId, true));
  ui.minigameContent.append(number, counter, button);
}

// helpdesk — "Só em português": pick the right English translation of the Portuguese sentence.
function renderTranslate(taskId, challenge) {
  const sentence = document.createElement("p");
  sentence.className = "minigame-sentence";
  sentence.textContent = challenge.sentence;
  const options = document.createElement("div");
  options.className = "minigame-options";
  challenge.options.forEach((option, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = option;
    button.addEventListener("click", () => sendTaskInput(taskId, index));
    options.append(button);
  });
  ui.minigameContent.append(sentence, options);
}

// print, and certificate step 1 — "Paper jam": tap the 3 jammed cells of a 3x3 grid; the
// others never reveal whether they hide a jam, found or not.
function renderPaperJam(taskId, challenge) {
  const cleared = new Set(challenge.cleared || []);
  const status = document.createElement("p");
  status.className = "minigame-hits";
  status.textContent = `Cleared: ${cleared.size}/3`;
  const grid = document.createElement("div");
  grid.className = "minigame-grid";
  grid.style.gridTemplateColumns = "repeat(3, 1fr)";
  for (let i = 0; i < 9; i++) {
    const button = document.createElement("button");
    button.type = "button";
    const isCleared = cleared.has(i);
    button.textContent = isCleared ? "✓" : "";
    button.disabled = isCleared;
    button.addEventListener("click", () => sendTaskInput(taskId, i));
    grid.append(button);
  }
  ui.minigameContent.append(status, grid);
}

// gate — "Tap your card": copy the shown number back on a number pad.
function renderCard(taskId, challenge) {
  const number = document.createElement("p");
  number.className = "minigame-number";
  number.textContent = challenge.number;
  const form = document.createElement("form");
  const input = document.createElement("input");
  input.type = "number";
  input.inputMode = "numeric";
  input.min = "0";
  input.max = "99999";
  input.required = true;
  input.setAttribute("aria-label", "Card number");
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = "Tap card";
  form.append(input, submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendTaskInput(taskId, input.value.padStart(5, "0"));
  });
  ui.minigameContent.append(number, form);
  input.focus();
}

// socket — "Get your slides on the projector": drag (or tap, then tap) the cable whose plug
// shape matches the projector's port, 3 rounds in a row. Nothing here is secret: the server
// still decides, but the browser can honestly tell a match from a mismatch itself, since it
// already has every piece of the challenge (spec 012). Original shapes, drawn as inline SVG
// polygons, no image files.
const PLUG_SHAPES = {
  HDMI: { tag: "polygon", points: "10,46 50,46 50,24 40,14 20,14 10,24" },
  "USB-C": { tag: "rect", x: 8, y: 20, width: 44, height: 20, rx: 10 },
  VGA: { tag: "polygon", points: "12,18 48,18 44,46 16,46" },
  DisplayPort: { tag: "polygon", points: "12,14 40,14 48,22 48,46 12,46" },
  "Mini DisplayPort": { tag: "polygon", points: "18,20 34,20 40,26 40,42 18,42" },
};

function plugShape(type, attrs) {
  const spec = PLUG_SHAPES[type];
  const { tag, ...shapeAttrs } = spec;
  return svgEl(tag, { ...shapeAttrs, ...attrs });
}

// Restarts a CSS animation even if it is already running (a fast double tap/drop).
function playAnimation(el, className) {
  el.classList.remove(className);
  void el.getBoundingClientRect();
  el.classList.add(className);
}

function renderCable(taskId, challenge) {
  const wrap = document.createElement("div");
  wrap.className = "minigame-cable";

  const status = document.createElement("p");
  status.className = "minigame-cable-status";
  status.textContent = `Round ${challenge.round}/3 · Wrong tries ${challenge.wrong}/2`;

  const projectorSvg = svgEl("svg", { viewBox: "0 0 60 60", width: "120", height: "120", class: "cable-plug" });
  projectorSvg.append(plugShape(challenge.port, { class: "plug-shape port-shape" }));
  const projector = document.createElement("div");
  projector.className = "projector";
  projector.append(projectorSvg);

  const cablesRow = document.createElement("div");
  cablesRow.className = "cable-row";

  function attempt(index, cableEl) {
    if (challenge.cables[index] === challenge.port) playAnimation(projectorSvg, "plugged");
    else playAnimation(cableEl, "shake");
    sendTaskInput(taskId, { cable: index });
  }

  projector.addEventListener("dragover", (event) => event.preventDefault());
  projector.addEventListener("drop", (event) => {
    event.preventDefault();
    const index = Number(event.dataTransfer.getData("text/plain"));
    attempt(index, cablesRow.children[index]);
  });
  projector.addEventListener("click", () => {
    const selected = cablesRow.querySelector(".cable.selected");
    if (!selected) return;
    selected.classList.remove("selected");
    attempt(Number(selected.dataset.index), selected);
  });

  challenge.cables.forEach((type, index) => {
    const cableEl = document.createElement("div");
    cableEl.className = "cable";
    cableEl.draggable = true;
    cableEl.tabIndex = 0;
    cableEl.dataset.index = String(index);
    cableEl.setAttribute("role", "button");
    cableEl.setAttribute("aria-label", `${type} cable`);
    const svg = svgEl("svg", { viewBox: "0 0 60 60", width: "56", height: "56", class: "cable-plug" });
    svg.append(plugShape(type, { class: "plug-shape" }));
    const label = document.createElement("span");
    label.className = "cable-name";
    label.textContent = type;
    cableEl.append(svg, label);
    cableEl.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", String(index));
      cableEl.classList.add("dragging");
    });
    cableEl.addEventListener("dragend", () => cableEl.classList.remove("dragging"));
    cableEl.addEventListener("click", () => {
      const alreadySelected = cableEl.classList.contains("selected");
      cablesRow.querySelectorAll(".cable.selected").forEach((el) => el.classList.remove("selected"));
      if (!alreadySelected) cableEl.classList.add("selected");
    });
    cablesRow.append(cableEl);
  });

  wrap.append(status, projector, cablesRow);
  ui.minigameContent.append(wrap);
}

// nata — "Protect your pastel de nata": tap the seagull's cell before it jumps away. The
// tart itself is original artwork, a small inline SVG (no image files, spec 012).
const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) el.setAttribute(name, value);
  return el;
}

// `eaten`: the time-out look, the tart gone and a few crumbs left.
function renderNataTart(eaten) {
  const svg = svgEl("svg", { viewBox: "0 0 80 80", width: "72", height: "72", class: "nata-tart" });
  if (eaten) {
    svg.append(
      svgEl("ellipse", { cx: 40, cy: 58, rx: 20, ry: 5, fill: "#b9793a", opacity: "0.3" }),
      svgEl("circle", { cx: 30, cy: 56, r: 3, fill: "#e9c27a" }),
      svgEl("circle", { cx: 48, cy: 60, r: 2.5, fill: "#b9793a" }),
      svgEl("circle", { cx: 40, cy: 50, r: 2, fill: "#7a4a16" }),
    );
  } else {
    svg.append(
      svgEl("ellipse", { cx: 40, cy: 46, rx: 34, ry: 26, fill: "#e9c27a", stroke: "#b9793a", "stroke-width": 3 }),
      svgEl("ellipse", { cx: 40, cy: 40, rx: 26, ry: 19, fill: "#e8a33d" }),
      svgEl("ellipse", {
        cx: 40, cy: 40, rx: 26, ry: 19, fill: "none",
        stroke: "#8a5a1e", "stroke-width": 1.5, "stroke-dasharray": "3 4",
      }),
      svgEl("ellipse", { cx: 30, cy: 33, rx: 7, ry: 5, fill: "#7a4a16", opacity: "0.55" }),
      svgEl("ellipse", { cx: 50, cy: 37, rx: 5, ry: 4, fill: "#7a4a16", opacity: "0.45" }),
    );
  }
  return svg;
}

// A brief wobble on a hit; restarted even on a fast double tap.
function flinchTart(svg) {
  svg.classList.remove("hit");
  void svg.getBBox();
  svg.classList.add("hit");
}

function renderSeagull(taskId, challenge) {
  const tart = renderNataTart(false);
  const hits = document.createElement("p");
  hits.className = "minigame-hits";
  hits.textContent = `Hits: ${challenge.hits}/5`;
  const grid = document.createElement("div");
  grid.className = "minigame-grid";
  grid.style.gridTemplateColumns = "repeat(3, 1fr)";
  for (let i = 0; i < 9; i++) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = i === challenge.cell ? "\u{1F426}" : "";
    button.addEventListener("click", () => {
      if (i === challenge.cell) flinchTart(tart);
      sendTaskInput(taskId, i);
    });
    grid.append(button);
  }
  ui.minigameContent.append(tart, hits, grid);
}

// The seagull time-out view: the tart gone, the hit count frozen at its last value, no grid.
function renderSeagullEaten(challenge) {
  ui.minigameContent.replaceChildren();
  const tart = renderNataTart(true);
  const hits = document.createElement("p");
  hits.className = "minigame-hits";
  hits.textContent = `Hits: ${challenge.hits}/5`;
  const gone = document.createElement("p");
  gone.textContent = "A seagull took it.";
  ui.minigameContent.append(tart, hits, gone);
}

ui.minigameClose.addEventListener("click", () => {
  if (latestState && latestState.doing) send({ type: "task_cancel", task: latestState.doing.task });
  ui.minigameClose.blur();
});

// --- Lights sabotage (spec 008, part 8) -------------------------------------------------
// The server turns the lights off and on and shortens what a student receives. This shows
// it and sends "sabotage" and "fix"; the buttons are a convenience, the server checks again.

let wasFixing = false; // `fixing` in the previous state, to notice it starting and ending
let fixSince = 0; // performance.now() when the running fix was first seen
let fixSeconds = 0; // how long fixing takes in all

function isLivingStudent(state) {
  return state.phase === "playing" && state.role === "student" && state.alive;
}

// Can this player start fixing now: a living student in the dark, within switch_range of
// the latest server position, and not busy.
function canFix(state) {
  if (!isLivingStudent(state) || state.lights_on || state.fixing || state.doing) return false;
  const me = state.players.find((p) => p.id === welcome.id);
  if (!me) return false;
  const t = welcome.map.tile_size;
  const [col, row] = welcome.map.light_switch;
  return Math.hypot((col + 0.5) * t - me.x, (row + 0.5) * t - me.y) <= welcome.switch_range;
}

// The name of the area the switch is in, for the banner (from the map's areas).
function switchAreaName() {
  const [col, row] = welcome.map.light_switch;
  const area = welcome.map.areas.find((a) => col >= a.x && col < a.x + a.w && row >= a.y && row < a.y + a.h);
  return area ? area.name : "the corridor";
}

function updateLights(state) {
  const dark = state.phase === "playing" && state.lights_on === false;
  ui.lightsBanner.hidden = !(dark && isLivingStudent(state));
  if (!ui.lightsBanner.hidden) setText(ui.switchArea, switchAreaName());

  // "Fix the lights" and "task" are one shared USE slot (spec 014): this button only takes
  // over from #task-button (updateTasks) while fixing is actually possible, the same
  // priority tryUse() gives it, so the slot never shows both at once. Once shown it is
  // always available, by definition of canFix(), so there is nothing to grey out here.
  ui.fixButton.hidden = state.role !== "student" || !welcome.map.light_switch || !canFix(state);
  if (!ui.fixButton.hidden) {
    ui.fixButton.disabled = false;
    setActionReason(ui.fixButton, "", "Fix the lights");
  }

  // The fixed LIGHTS OFF slot: examiners only, for the whole round.
  ui.sabotageButton.hidden = state.role !== "examiner" || !welcome.map.light_switch;
  if (!ui.sabotageButton.hidden) {
    const alive = state.phase === "playing" && state.alive;
    const cooldown = alive ? state.sabotage_cooldown : 0;
    ui.sabotageButton.disabled = !alive || dark || cooldown > 0;
    let reason = "";
    if (!alive) reason = "Ghosts cannot sabotage";
    else if (dark) reason = "The lights are already off";
    else if (cooldown > 0) reason = `Ready in ${cooldown} s`;
    setActionReason(ui.sabotageButton, reason, "Lights off");
    setCooldownRing(ui.sabotageButton, cooldown, SABOTAGE_COOLDOWN);
  }

  // Fixing that was running in the previous state and is not any more.
  const fixing = Boolean(state.fixing);
  if (fixing && !wasFixing) {
    fixSince = performance.now();
    fixSeconds = state.fixing.seconds_left;
  }
  if (wasFixing && !fixing && dark) {
    showToast(state.alive ? "Fixing cancelled: you moved away from the switch" : "Fixing cancelled: you were expelled");
  }
  wasFixing = fixing;
}

function trySabotage() {
  if (!latestState || !isLivingExaminer(latestState)) return;
  if (latestState.lights_on === false) {
    showToast("The lights are already off");
    return;
  }
  if (latestState.sabotage_cooldown > 0) {
    showToast(`Lights cooldown: ${latestState.sabotage_cooldown} s left`);
    return;
  }
  send({ type: "sabotage" });
}

// Key F: fix the lights at the switch, otherwise do a task (no task place is that close).
function tryUse() {
  if (latestState && canFix(latestState)) send({ type: "fix" });
  else tryTask();
}

ui.fixButton.addEventListener("click", () => {
  send({ type: "fix" });
  ui.fixButton.blur();
});

ui.sabotageButton.addEventListener("click", () => {
  trySabotage();
  ui.sabotageButton.blur();
});

// --- Staff doors (spec 008, part 6) ---------------------------------------------------
// The buttons are only a convenience: the server checks role, door and cooldown again.

let doorKey = ""; // what the door buttons currently show, to redraw only on changes

// The staff door under the latest server position of a living examiner, or null.
// REPEATS SERVER RULE: Game._door_under() in server/game.py (the centre is on the tile).
function doorUnder(state) {
  if (!isLivingExaminer(state)) return null;
  const me = state.players.find((p) => p.id === welcome.id);
  if (!me) return null;
  const t = welcome.map.tile_size;
  const col = Math.floor(me.x / t);
  const row = Math.floor(me.y / t);
  return (welcome.map.staff_doors || []).find((door) => door.x === col && door.y === row) || null;
}

// The other doors of the network, starting with the one after `here` in the map's list,
// so pressing V again and again goes round all of them.
function doorTargets(here) {
  const doors = welcome.map.staff_doors;
  const at = doors.indexOf(here);
  return [...doors.slice(at + 1), ...doors.slice(0, at)];
}

// A small arrow (spec 014), rotated in world space to point from `me` toward `door`.
function doorArrow(me, door) {
  const t = welcome.map.tile_size;
  const dx = (door.x + 0.5) * t - me.x;
  const dy = (door.y + 0.5) * t - me.y;
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
  const svg = svgEl("svg", { viewBox: "0 0 24 24", width: 14, height: 14, class: "door-arrow", "aria-hidden": "true" });
  const g = svgEl("g", { transform: `rotate(${angle} 12 12)` });
  g.append(
    svgEl("path", {
      d: "M4 12h13M12 6l6 6-6 6",
      fill: "none",
      stroke: "currentColor",
      "stroke-width": 2,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
    }),
  );
  svg.append(g);
  return svg;
}

function updateDoors(state) {
  // The fixed DOOR slot: examiners only, for the whole round (spec 014).
  ui.doorItem.hidden = state.role !== "examiner";
  if (ui.doorItem.hidden) {
    doorKey = "";
    return;
  }
  const alive = state.phase === "playing" && state.alive;
  const here = alive ? doorUnder(state) : null;
  const cooldown = here ? state.door_cooldown : 0;
  ui.doorActionButton.disabled = !alive || !here || cooldown > 0;
  let reason = "";
  if (!alive) reason = "Ghosts cannot use staff doors";
  else if (!here) reason = "Not at a staff door";
  else if (cooldown > 0) reason = `Ready in ${cooldown} s`;
  setActionReason(ui.doorActionButton, reason, "Staff door");
  setCooldownRing(ui.doorActionButton, cooldown, DOOR_COOLDOWN);

  const key = here ? `${here.id}:${cooldown}:${alive}` : `none:${alive}`;
  if (key === doorKey) return;
  doorKey = key;
  const targets = here ? doorTargets(here) : [];
  const me = state.players.find((p) => p.id === welcome.id);
  ui.doorButtons.replaceChildren(
    ...targets.map((door) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "door-card";
      if (me) button.append(doorArrow(me, door));
      button.append(door.name); // appended as text: never read as HTML
      const disabled = cooldown > 0;
      button.disabled = disabled;
      if (disabled) button.title = `Ready in ${cooldown} s`;
      button.addEventListener("click", () => send({ type: "door", to: door.id }));
      return button;
    }),
  );
}

// Key V: travel to the next door of the network.
function tryDoor() {
  const here = latestState && doorUnder(latestState);
  if (!here) return;
  if (latestState.door_cooldown > 0) {
    showToast(`Staff door cooldown: ${latestState.door_cooldown} s left`);
    return;
  }
  send({ type: "door", to: doorTargets(here)[0].id });
}

ui.doorActionButton.addEventListener("click", () => {
  tryDoor();
  ui.doorActionButton.blur();
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
// With walls = false (a ghost) only leaving the map counts.
function blocked(map, half, x, y, walls = true) {
  const t = map.tile_size;
  const left = Math.floor((x - half) / t);
  const right = Math.floor((x + half) / t - 1e-9);
  const top = Math.floor((y - half) / t);
  const bottom = Math.floor((y + half) / t - 1e-9);
  for (let row = top; row <= bottom; row++) {
    for (let col = left; col <= right; col++) {
      if (row < 0 || row >= map.grid.length || col < 0 || col >= map.grid[row].length) return true;
      if (walls && map.grid[row][col] === "#") return true;
    }
  }
  return false;
}

// REPEATS SERVER RULE: same as Game._move_axis() in server/game.py
// (move in pieces of at most 1 px, stop at the first piece that hits a wall; returns the
// distance that was not walked). The own character ignores walls as a ghost; the server
// sends `alive` with every state.
function moveAxis(pos, mx, my) {
  const walls = latestState.alive;
  let remaining = Math.abs(mx) + Math.abs(my);
  const sx = Math.sign(mx);
  const sy = Math.sign(my);
  while (remaining > 0) {
    const part = Math.min(1, remaining);
    const nx = pos.x + sx * part;
    const ny = pos.y + sy * part;
    if (blocked(welcome.map, welcome.player_half, nx, ny, walls)) return remaining;
    pos.x = nx;
    pos.y = ny;
    remaining -= part;
  }
  return 0;
}

// REPEATS SERVER RULE: same as Game._walk() in server/game.py: one fixed step per tick,
// diagonal normalised, first the x axis and then the y axis; a straight walk that a wall
// stops slides round the wall's corner.
function walk(pos, dx, dy) {
  const length = Math.hypot(dx, dy);
  const leftX = moveAxis(pos, (dx / length) * welcome.step, 0);
  const leftY = moveAxis(pos, 0, (dy / length) * welcome.step);
  if (dy === 0 && leftX > 0) slide(pos, dx, 0, leftX);
  else if (dx === 0 && leftY > 0) slide(pos, 0, dy, leftY);
}

// REPEATS SERVER RULE: same as Game._slide() in server/game.py (spec 011): if the way
// ahead is free at most welcome.corner_slide px to one side, move there with what is left
// of the step and walk on. The nearest free side wins.
function slide(pos, dx, dy, distance) {
  const walls = latestState.alive;
  for (let offset = 1; offset <= welcome.corner_slide; offset++) {
    for (const side of [-1, 1]) {
      const sideX = side * Math.abs(dy);
      const sideY = side * Math.abs(dx);
      const aheadX = pos.x + dx + sideX * offset;
      const aheadY = pos.y + dy + sideY * offset;
      if (!blocked(welcome.map, welcome.player_half, aheadX, aheadY, walls)) {
        const slid = Math.min(distance, offset);
        moveAxis(pos, sideX * slid, sideY * slid);
        moveAxis(pos, dx * (distance - slid), dy * (distance - slid));
        return;
      }
    }
  }
}

// --- Phaser scene -----------------------------------------------------------------

class CampusScene extends Phaser.Scene {
  constructor() {
    super("campus");
    this.sprites = new Map(); // id -> character from Render.makeCharacter()
    this.exams = new Map(); // failed exam id -> sheet from Render.makeExam()
    this.taskMarkers = new Map(); // own open task id -> mark from Render.makeTaskMarker()
    this.edgeArrows = new Map(); // own open task id -> arrow from Render.makeEdgeArrow()
    this.lastSent = { dx: 0, dy: 0 };
    // The own character, predicted in whole server ticks (see updateOwn).
    this.predicted = null; // position after the newest predicted tick
    this.previous = null; // position one tick earlier: the character is drawn between the two
    this.trail = []; // the last TRAIL_TICKS predicted positions, oldest first
    this.tickTime = 0; // seconds of frame time not yet used up by a tick
    this.drawOffset = { x: 0, y: 0 }; // how far the picture still is from the prediction
    this.minigameWasOpen = false; // the mini-game panel's open/closed state one tick ago
  }

  create() {
    // The map is drawn from the server's data; the darkness covers what the own character
    // has no line of sight to. The vision radius and the tiles that block sight come from
    // the server ("welcome"), so the lit area matches what the server sends.
    const { width, height } = Render.drawMap(this, welcome.map, welcome.sight_grid);
    if (welcome.map.meeting_point) Render.makeMeetingPoint(this, welcome.map, welcome.meeting_table_radius);
    for (const door of welcome.map.staff_doors || []) Render.makeDoor(this, welcome.map, door);
    this.taskRing = Render.makeTaskRing(this);
    this.darkness = Render.makeDarkness(this, welcome.map, welcome.sight_grid, welcome.vision_radius);
    this.switchMark = welcome.map.light_switch ? Render.makeSwitch(this, welcome.map) : null;

    const camera = this.cameras.main;
    camera.setBounds(0, 0, width, height);
    camera.setBackgroundColor(Render.BACKDROP);
    const fitCamera = () => camera.setZoom(Render.cameraZoom(width, height, welcome.vision_radius));
    fitCamera();
    this.scale.on("resize", fitCamera);

    this.keys = this.input.keyboard.addKeys("W,A,S,D,UP,DOWN,LEFT,RIGHT,E,R,F,V,Q");
    // On the key event itself, so even a very short tap counts (tryExpel checks the role).
    this.keys.E.on("down", () => tryExpel());
    this.keys.R.on("down", () => tryReport());
    this.keys.F.on("down", () => tryUse());
    this.keys.Q.on("down", () => trySabotage());
    this.keys.V.on("down", () => tryDoor());

    // When the tab loses focus, stop walking (otherwise the server keeps moving us).
    const stop = () => this.sendDirection(0, 0);
    window.addEventListener("blur", stop);
    document.addEventListener("visibilitychange", () => document.hidden && stop());
  }

  // Sends the direction if it changed. Called once per predicted tick, so at most
  // tick_rate times a second (far below the server's rate limit), and the direction sent
  // is always the one the prediction uses.
  sendDirection(dx, dy) {
    if (dx === this.lastSent.dx && dy === this.lastSent.dy) return;
    this.lastSent = { dx, dy };
    send({ type: "input", dx, dy });
  }

  // A held joystick wins over the keys (readKeys still runs on a laptop with no joystick).
  readKeys() {
    const joystick = Controls.direction();
    if (joystick) return joystick;
    const k = this.keys;
    const dx = (k.D.isDown || k.RIGHT.isDown ? 1 : 0) - (k.A.isDown || k.LEFT.isDown ? 1 : 0);
    const dy = (k.S.isDown || k.DOWN.isDown ? 1 : 0) - (k.W.isDown || k.UP.isDown ? 1 : 0);
    return { dx, dy };
  }

  update(time, deltaMs) {
    if (snapshots.length === 0) return;
    const newest = snapshots[snapshots.length - 1];
    const latest = newest.players;
    this.syncSprites(latest);
    this.syncExams(latestState.failed_exams);
    this.updateOwn(latest.get(welcome.id), deltaMs / 1000);
    this.updateOthers(latest);
    // In a meeting everyone looks at the meeting table (spec 011).
    const table = lastPhase === "meeting" ? meetingTable() : null;
    for (const [id, sprite] of this.sprites) {
      const lookAt = table ? { x: table.x - sprite.x, y: table.y - sprite.y } : null;
      Render.animateCharacter(sprite, { ...sprite.walk, ghost: newest.ghosts.has(id), lookAt }, time);
    }
    this.frameMeeting(table, this.sprites.get(welcome.id));

    // Darkness only for the living while playing: ghosts, the lobby and the end screen
    // show the whole map (the server sends them everything as well).
    const own = this.sprites.get(welcome.id);
    const limited = lastPhase === "playing" && latestState.alive;
    // The server says how far this player sees right now: less for a student in the dark.
    const radius = limited ? latestState.vision_radius : welcome.vision_radius;
    if (own) Render.updateDarkness(this.darkness, own.x, own.y, radius, limited);
    if (this.switchMark) {
      const off = lastPhase === "playing" && latestState.lights_on === false;
      const t = welcome.map.tile_size;
      const [col, row] = welcome.map.light_switch;
      const near = own && Math.hypot((col + 0.5) * t - own.x, (row + 0.5) * t - own.y) <= welcome.switch_range;
      Render.updateSwitch(this.switchMark, off, time, near);
    }

    // Tasks: marks on the own open task places and the ring while one runs. The ring
    // moves smoothly from the time the task was first seen; the seconds are the server's.
    this.syncTaskMarkers(latestState.tasks || [], own);
    this.syncEdgeArrows(latestState.tasks || [], lastPhase === "meeting", actionsBottomMargin());
    const doing = lastPhase === "playing" ? latestState.doing : null;
    const fixing = lastPhase === "playing" ? latestState.fixing : null;
    if (own && doing) {
      const fraction = Math.min(1, (performance.now() - doingSince) / (doingSeconds * 1000));
      Render.updateTaskRing(this.taskRing, own.x, own.y, fraction, doing.seconds_left);
    } else if (own && fixing) {
      // Fixing the lights uses the same ring.
      const fraction = Math.min(1, (performance.now() - fixSince) / (fixSeconds * 1000));
      Render.updateTaskRing(this.taskRing, own.x, own.y, fraction, fixing.seconds_left);
    } else {
      Render.updateTaskRing(this.taskRing, 0, 0, null);
    }
  }

  // In a meeting the card covers part of the window. The camera then shows the meeting
  // table in the middle of the part that stays free: left of the card, or above it on a
  // window higher than wide (style.css). Outside a meeting it follows the own character.
  frameMeeting(table, own) {
    const camera = this.cameras.main;
    if (!table || !own) {
      camera.setFollowOffset(0, 0);
      return;
    }
    const card = ui.meetingCard.getBoundingClientRect();
    const upright = window.innerHeight > window.innerWidth;
    const freeX = upright ? window.innerWidth / 2 : card.left / 2;
    const freeY = upright ? card.top / 2 : window.innerHeight / 2;
    // From window pixels to map pixels: the canvas has pixelRatio times the window's pixels.
    const scale = Render.pixelRatio / camera.zoom;
    const shiftX = (window.innerWidth / 2 - freeX) * scale;
    const shiftY = (window.innerHeight / 2 - freeY) * scale;
    // The camera looks at (own - offset): that is the table, moved by the shift.
    camera.setFollowOffset(own.x - table.x - shiftX, own.y - table.y - shiftY);
  }

  // One mark per own open task; a finished task (and a new round) removes its mark.
  // A mark fades while the own character stands at it, so it does not cover the face.
  // Repositioned every frame: a multi-step task's mark must follow its current station once
  // an earlier step is done (spec 012, part 4), the only place this task entry's x/y mean.
  syncTaskMarkers(tasks, own) {
    const open = new Map(tasks.filter((task) => !task.done).map((task) => [task.id, task]));
    for (const [id, task] of open) {
      if (!this.taskMarkers.has(id)) this.taskMarkers.set(id, Render.makeTaskMarker(this, task));
      const marker = this.taskMarkers.get(id);
      marker.setPosition(task.x, task.y);
      const near = own && Math.hypot(task.x - own.x, task.y - own.y) <= welcome.task_range;
      marker.setAlpha(near ? 0.3 : 1);
    }
    for (const [id, marker] of this.taskMarkers) {
      if (!open.has(id)) {
        marker.destroy();
        this.taskMarkers.delete(id);
      }
    }
  }

  // Edge arrows (spec 012): one per own open task, pointing off-screen places out. Hidden
  // during a meeting, the same way the camera stops following the own character then
  // (frameMeeting draws the table instead).
  syncEdgeArrows(tasks, inMeeting, bottomMargin) {
    const open = new Map(tasks.filter((task) => !task.done).map((task) => [task.id, task]));
    for (const [id, arrow] of this.edgeArrows) {
      if (!open.has(id)) {
        arrow.destroy();
        this.edgeArrows.delete(id);
      }
    }
    if (inMeeting) {
      for (const arrow of this.edgeArrows.values()) arrow.setVisible(false);
      return;
    }
    const camera = this.cameras.main;
    for (const [id, task] of open) {
      if (!this.edgeArrows.has(id)) this.edgeArrows.set(id, Render.makeEdgeArrow(this));
      Render.updateEdgeArrow(this.edgeArrows.get(id), task, camera, bottomMargin);
    }
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

  // Own character: predicted in the server's own ticks, repaired from the server's
  // position (the server wins), drawn smoothly in between.
  updateOwn(server, dt) {
    const sprite = this.sprites.get(welcome.id);
    if (!server || !sprite) return;
    if (!this.predicted) this.resetPrediction(server);

    const tick = 1 / welcome.tick_rate;
    this.tickTime = Math.min(this.tickTime + dt, MAX_TICKS_PER_FRAME * tick);
    while (this.tickTime >= tick) {
      this.tickTime -= tick;
      this.predictTick();
    }
    this.repair(server);

    // What is left of the last repair fades out, so a repair is a glide and not a jump.
    const fade = Math.exp(-BLEND_RATE * dt);
    this.drawOffset.x *= fade;
    this.drawOffset.y *= fade;
    const at = this.betweenTicks();
    sprite.setPosition(at.x + this.drawOffset.x, at.y + this.drawOffset.y);
    sprite.walk = { ...this.lastSent };
  }

  // One tick of the own character, exactly as the server will move it.
  predictTick() {
    let dx = 0;
    let dy = 0;
    // The mini-game panel open/closed, client-side only: the server still accepts movement
    // during a task exactly as before (spec 012, part 2), so nothing breaks if a message
    // does slip through, but tapping the panel must not also walk the character.
    const minigameOpen = Boolean(minigameChallenge(latestState));
    if (minigameOpen && !this.minigameWasOpen) this.sendDirection(0, 0); // stop right away
    this.minigameWasOpen = minigameOpen;
    if (lastPhase === "ended" || lastPhase === "meeting" || minigameOpen) {
      // The server rejects movement now (or, for the panel, this browser stops sending it).
      // Sending and predicting nothing keeps the own character where the server put it.
      this.lastSent = { dx: 0, dy: 0 };
    } else {
      ({ dx, dy } = this.readKeys());
      this.sendDirection(dx, dy);
    }
    this.previous = { ...this.predicted };
    if (dx !== 0 || dy !== 0) walk(this.predicted, dx, dy);
    this.trail.push({ ...this.predicted });
    if (this.trail.length > TRAIL_TICKS) this.trail.shift();
  }

  // Where the own character is between the last two predicted ticks: the prediction
  // runs 20 times a second, the screen is drawn more often.
  betweenTicks() {
    const part = this.tickTime * welcome.tick_rate; // 0 to 1
    return {
      x: this.previous.x + (this.predicted.x - this.previous.x) * part,
      y: this.previous.y + (this.predicted.y - this.previous.y) * part,
    };
  }

  // Start predicting again from the server's position.
  resetPrediction(server) {
    this.predicted = { x: server.x, y: server.y };
    this.previous = { ...this.predicted };
    this.trail = [{ ...this.predicted }];
  }

  // The server's position must lie on the trail this browser predicted. If it does not,
  // the prediction was wrong at that point: move the whole prediction by the difference.
  repair(server) {
    let near = this.trail[0];
    let error = Infinity;
    for (const point of this.trail) {
      const distance = Math.hypot(server.x - point.x, server.y - point.y);
      if (distance < error) {
        near = point;
        error = distance;
      }
    }
    if (error < MIN_CORRECTION) return;

    const shown = this.betweenTicks();
    const moved = error > SNAP_DISTANCE_TILES * welcome.map.tile_size; // meeting, new round
    const wantX = server.x - near.x;
    const wantY = server.y - near.y;
    // The repair uses the wall rule of walking, so it never ends inside a wall.
    const before = { ...this.predicted };
    moveAxis(this.predicted, wantX, 0);
    moveAxis(this.predicted, 0, wantY);
    const doneX = this.predicted.x - before.x;
    const doneY = this.predicted.y - before.y;
    if (moved || Math.hypot(wantX - doneX, wantY - doneY) > welcome.step) {
      // Put somewhere else by the server, or a wall is in the way of the repair.
      this.resetPrediction(server);
    } else {
      this.previous = { x: this.previous.x + doneX, y: this.previous.y + doneY };
      for (const point of this.trail) {
        point.x += doneX;
        point.y += doneY;
      }
    }
    // The picture stays where it was and glides to the repaired position (updateOwn);
    // only a move by the server is shown at once.
    const now = this.betweenTicks();
    this.drawOffset = moved
      ? { x: 0, y: 0 }
      : { x: this.drawOffset.x + shown.x - now.x, y: this.drawOffset.y + shown.y - now.y };
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
      let a = older.players.get(id) || b;
      // A player the server moved (staff door, meeting) is not drawn gliding across the map.
      if (Math.hypot(b.x - a.x, b.y - a.y) > SNAP_DISTANCE_TILES * welcome.map.tile_size) a = b;
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
