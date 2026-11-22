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
  expelButton: document.getElementById("expel-button"),
  taskButton: document.getElementById("task-button"),
  doorButtons: document.getElementById("door-buttons"),
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
const EXPEL_KEY_HINT = Controls.isTouch ? "" : " (E)";

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
  dot.style.background = Render.colorCss(state.colors[playerId] ?? knownColors.get(playerId));
  return dot;
}

// A player's nickname, also for players out of sight or voted out.
function nameOf(playerId) {
  return knownNames.get(playerId) ?? "A player";
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
    ui.roleBadge.hidden = lastPhase !== "playing" && lastPhase !== "meeting";
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
  let label = `Expel${EXPEL_KEY_HINT} · nobody in range`;
  if (cooldown > 0) label = `Expel${EXPEL_KEY_HINT} · ready in ${cooldown} s`;
  else if (target) label = `Expel ${target.name}${EXPEL_KEY_HINT}`; // textContent: never read as HTML
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
  ui.reportButton.hidden = !reportTarget(state);
  ui.meetingButton.hidden = !(isLivingAndPlaying(state) && nearMeetingTable(state));
  ui.meetingButton.disabled = state.meeting_used;
  setText(ui.meetingButton, state.meeting_used ? "Meeting already called" : "Call a meeting");
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
  // redraw does not replace the buttons under the mouse every second.
  const key = JSON.stringify([{ ...meeting, seconds_left: null }, state.alive]);
  if (key === meetingKey) return;
  meetingKey = key;

  const caller = nameOf(meeting.called_by); // added as text: never read as HTML
  ui.meetingReason.textContent =
    meeting.reason === "report" ? `${caller} found a failed exam` : `${caller} called a meeting`;
  if (result) renderResult(state, result);
  else renderVoting(state, meeting);
}

function meetingRow(state, playerId) {
  const item = document.createElement("li");
  const who = document.createElement("span");
  who.append(colorDot(state, playerId), nameOf(playerId)); // as text: never read as HTML
  if (playerId === welcome.id) who.append(tag("you", "you"));
  item.append(who);
  return { item, who };
}

function renderVoting(state, meeting) {
  setText(ui.meetingTitle, "Meeting: who is an examiner?");
  const canVote = state.alive && meeting.my_vote === null;
  const voted = new Set(meeting.voted);
  ui.meetingPlayers.replaceChildren(
    ...meeting.living.map((playerId) => {
      const { item, who } = meetingRow(state, playerId);
      if (voted.has(playerId)) who.append(tag("voted", "voted"));
      // No button on the own row: the server rejects a vote for yourself (spec 008, part 2).
      if (state.alive && playerId !== welcome.id) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Vote";
        button.disabled = !canVote;
        button.addEventListener("click", () => castVote(playerId));
        item.append(button);
      }
      return item;
    }),
  );
  ui.skipButton.hidden = !state.alive; // ghosts get the screen without buttons
  ui.skipButton.disabled = !canVote;
  ui.meetingStatus.classList.remove("verdict");
  let status = "Vote for a player or skip.";
  if (!state.alive) status = "Ghosts cannot vote";
  else if (meeting.my_vote === "skip") status = "You skipped";
  else if (meeting.my_vote) status = `You voted for ${nameOf(meeting.my_vote)}`;
  ui.meetingStatus.textContent = status;
}

function renderResult(state, result) {
  setText(ui.meetingTitle, "Result");
  const rows = Object.entries(result.votes).map(([playerId, count]) => {
    const { item, who } = meetingRow(state, playerId);
    if (playerId === result.surfing) who.append(tag("sent surfing", "surfing"));
    const votes = document.createElement("span");
    votes.className = "count";
    votes.textContent = count === 1 ? "1 vote" : `${count} votes`;
    item.append(votes);
    return item;
  });
  const skips = document.createElement("li");
  const skipCount = document.createElement("span");
  skipCount.className = "count";
  skipCount.textContent = String(result.skips);
  skips.append("Skipped", skipCount);
  ui.meetingPlayers.replaceChildren(...rows, skips);
  ui.skipButton.hidden = true;
  ui.meetingStatus.classList.add("verdict");
  ui.meetingStatus.textContent = result.surfing
    ? `${nameOf(result.surfing)} was sent surfing`
    : "Nobody was sent surfing";
}

function castVote(target) {
  // Disable the buttons until the server's answer: the next state shows the vote,
  // a rejection comes back as a toast and re-enables them.
  for (const button of ui.meetingScreen.querySelectorAll("button")) button.disabled = true;
  send({ type: "vote", target });
}

ui.skipButton.addEventListener("click", () => castVote("skip"));

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
  ui.taskButton.hidden = !taskTarget(state);

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

const SABOTAGE_KEY_HINT = Controls.isTouch ? "" : " (Q)";
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
  ui.fixButton.hidden = !canFix(state);

  // Examiners: the sabotage button with the shared cooldown.
  ui.sabotageButton.hidden = !(isLivingExaminer(state) && welcome.map.light_switch);
  if (!ui.sabotageButton.hidden) {
    const cooldown = state.sabotage_cooldown;
    ui.sabotageButton.disabled = dark || cooldown > 0;
    let label = `Lights off${SABOTAGE_KEY_HINT}`;
    if (dark) label = "The lights are off";
    else if (cooldown > 0) label = `Lights off${SABOTAGE_KEY_HINT} · ready in ${cooldown} s`;
    setText(ui.sabotageButton, label);
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

function updateDoors(state) {
  const here = doorUnder(state);
  const cooldown = here ? state.door_cooldown : 0;
  const key = here ? `${here.id}:${cooldown}` : "";
  if (key === doorKey) return;
  doorKey = key;
  const targets = here ? doorTargets(here) : [];
  ui.doorButtons.replaceChildren(
    ...targets.map((door, index) => {
      const button = document.createElement("button");
      button.type = "button";
      const hint = index === 0 && !Controls.isTouch ? " (V)" : "";
      // Names come from the map and are added as text, never as HTML.
      button.textContent = cooldown > 0 ? `${door.name} · ready in ${cooldown} s` : `Staff door: ${door.name}${hint}`;
      button.disabled = cooldown > 0;
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
    this.syncEdgeArrows(latestState.tasks || [], lastPhase === "meeting");
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
  syncEdgeArrows(tasks, inMeeting) {
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
      Render.updateEdgeArrow(this.edgeArrows.get(id), task, camera);
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
