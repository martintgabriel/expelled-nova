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
// REPEATS SERVER RULE: EXPEL_COOLDOWN/VENT_COOLDOWN/SABOTAGE_COOLDOWN in server/game.py.
// Only to size the cooldown ring's sweep; the server is the only one that counts down.
const EXPEL_COOLDOWN = 20;
const VENT_COOLDOWN = 3;
const VENT_KEY_WINDOW_MS = 80; // two arrow keys pressed this close together count as a diagonal
const SABOTAGE_COOLDOWN = 30;
const FOOTSTEP_TICKS = 6; // ticks between two footstep sounds while walking (spec 016)
const BEACH_RANGE_TILES = 6; // the waves fade out this many tiles from the sea (spec 017)
const RING_CIRCUMFERENCE = 2 * Math.PI * 35; // matches r="35" on .ring-sweep in index.html

const ui = {
  joinScreen: document.getElementById("join-screen"),
  joinForm: document.getElementById("join-form"),
  nickname: document.getElementById("nickname"),
  hatPrev: document.getElementById("hat-prev"),
  hatNext: document.getElementById("hat-next"),
  hatName: document.getElementById("hat-name"),
  colorSwatches: document.getElementById("color-swatches"),
  idPhotoHat: document.getElementById("id-photo-hat"),
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
  lobbySettings: document.getElementById("lobby-settings"),
  inviteButton: document.getElementById("invite-button"),
  inviteScreen: document.getElementById("invite-screen"),
  inviteUrl: document.getElementById("invite-url"),
  inviteClose: document.getElementById("invite-close"),
  startButton: document.getElementById("start-button"),
  startHint: document.getElementById("start-hint"),
  roleScreen: document.getElementById("role-screen"),
  roleTitle: document.getElementById("role-title"),
  roleDetail: document.getElementById("role-detail"),
  roleKicker: document.getElementById("role-kicker"),
  roleMotto: document.getElementById("role-motto"),
  roleStamp: document.getElementById("role-stamp"),
  roleBadge: document.getElementById("role-badge"),
  actions: document.getElementById("actions"),
  expelButton: document.getElementById("expel-button"),
  taskButton: document.getElementById("task-button"),
  doorItem: document.getElementById("door-item"),
  doorButtons: document.getElementById("door-buttons"),
  doorActionButton: document.getElementById("door-action-button"),
  doorActionLabel: document.getElementById("door-action-label"),
  fixButton: document.getElementById("fix-button"),
  controlMove: document.getElementById("control-move"),
  controlExpel: document.getElementById("control-expel"),
  controlReport: document.getElementById("control-report"),
  controlMeeting: document.getElementById("control-meeting"),
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
  endKicker: document.getElementById("end-kicker"),
  endText: document.getElementById("end-text"),
  endStamp: document.getElementById("end-stamp"),
  endSecurityNote: document.getElementById("end-security-note"),
  restartButton: document.getElementById("restart-button"),
  restartHint: document.getElementById("restart-hint"),
  helpButton: document.getElementById("help-button"),
  helpPanel: document.getElementById("help-panel"),
  helpClose: document.getElementById("help-close"),
  muteButton: document.getElementById("mute-button"),
  volumeSlider: document.getElementById("volume-slider"),
  soundPanel: document.getElementById("sound-panel"),
  soundClose: document.getElementById("sound-close"),
  musicSwitch: document.getElementById("music-switch"),
  effectsSwitch: document.getElementById("effects-switch"),
  mapButton: document.getElementById("map-button"),
  mapPanel: document.getElementById("map-panel"),
  mapClose: document.getElementById("map-close"),
  mapWhere: document.getElementById("map-where"),
  mapSlot: document.getElementById("map-slot"),
  mapTasks: document.getElementById("map-tasks"),
};

// --- Hints and key labels by input device, not by screen width (spec 007) -----------

for (const el of document.querySelectorAll(".hint-keyboard")) el.hidden = Controls.isTouch;
for (const el of document.querySelectorAll(".hint-touch")) el.hidden = !Controls.isTouch;
for (const el of document.querySelectorAll(".key-hint")) el.hidden = Controls.isTouch;

// --- Invite players: QR code and URL, lobby only (spec 007) -------------------------

ui.inviteUrl.textContent = `${location.origin}/`;
ui.inviteButton.addEventListener("click", () => {
  Sound.play("click");
  ui.inviteScreen.hidden = false;
});
ui.inviteClose.addEventListener("click", () => {
  Sound.play("click");
  ui.inviteScreen.hidden = true;
});

// --- How to play (spec 015): the "?" button, key H, closed with Esc or the cross ----------
// Only in the browser: it shows static text from index.html and does not pause the game.

function setHelpOpen(open) {
  if (open) setMapOpen(false); // one overlay at a time (spec 018)
  if (open) setSoundOpen(false); // the handbook would cover the sound panel (spec 028)
  ui.helpPanel.hidden = !open;
  ui.helpButton.setAttribute("aria-expanded", String(open));
  if (open) ui.helpClose.focus();
  else ui.helpButton.blur(); // keys go back to walking
}

ui.helpButton.addEventListener("click", () => {
  Sound.play("click");
  setHelpOpen(ui.helpPanel.hidden);
});
ui.helpClose.addEventListener("click", () => {
  Sound.play("click");
  setHelpOpen(false);
});
// A click on the dimmed background (not on the card) closes it too.
ui.helpPanel.addEventListener("click", (event) => {
  if (event.target === ui.helpPanel) setHelpOpen(false);
});
// --- Campus map (spec 018): the map button, key C, closed with Esc, the cross or a click
// next to the card. Only in the browser, like the handbook: it does not pause the game.
// campusmap.js draws it once from welcome.map; later main.js only gives it the own position.

function setMapOpen(open) {
  if (open && ui.mapSlot.childElementCount === 0) return; // no map before the welcome message
  if (open) setHelpOpen(false); // one overlay at a time
  if (open) setSoundOpen(false);
  ui.mapPanel.hidden = !open;
  ui.mapButton.setAttribute("aria-expanded", String(open));
  if (open) {
    updateMapWhere(latestState);
    updateMapTasks(latestState);
    ui.mapClose.focus();
  } else {
    ui.mapButton.blur(); // keys go back to walking
  }
}

// "You are in: <area>" under the map's title: the own area from the own snapshot, only
// while playing, hidden in a corridor (no area) and in the lobby, a meeting or at the end.
function updateMapWhere(state) {
  const area = state && state.phase === "playing" ? state.area : null;
  ui.mapWhere.hidden = !area;
  if (area) setText(ui.mapWhere, `You are in: ${area}`);
}

// The own open tasks on the map: green numbered markers on their places and, under the map,
// the same numbers with what each task is and where, so a player knows a task before
// walking to it. Only from the own snapshot (state.tasks is never anyone else's; an
// examiner's are fake but look exactly the same), and only while playing.
let mapTaskKey = ""; // what the map shows now, to redraw only on a change
function updateMapTasks(state) {
  const open = state && state.phase === "playing" ? (state.tasks || []).filter((task) => !task.done) : [];
  const key = JSON.stringify(open.map((task) => [task.id, task.step, task.x, task.y, task.title]));
  if (key === mapTaskKey) return;
  mapTaskKey = key;
  CampusMap.setTasks(open);
  ui.mapTasks.replaceChildren(
    ...open.map((task) => {
      const item = document.createElement("li");
      const step = task.steps ? ` · step ${task.step} of ${task.steps}` : "";
      item.textContent = `${task.title} · ${task.area}${step}`;
      return item;
    }),
  );
  ui.mapTasks.hidden = open.length === 0;
}

ui.mapButton.addEventListener("click", () => {
  Sound.play("click");
  setMapOpen(ui.mapPanel.hidden);
});
ui.mapClose.addEventListener("click", () => {
  Sound.play("click");
  setMapOpen(false);
});
ui.mapPanel.addEventListener("click", (event) => {
  if (event.target === ui.mapPanel) setMapOpen(false);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !ui.soundPanel.hidden) {
    setSoundOpen(false);
    return;
  }
  if (event.key === "Escape" && !ui.helpPanel.hidden) {
    setHelpOpen(false);
    return;
  }
  if (event.key === "Escape" && !ui.mapPanel.hidden) {
    setMapOpen(false);
    return;
  }
  // Not while typing (the nickname, a mini-game's number) and not with a modifier key.
  const typing = event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement;
  if (typing || event.ctrlKey || event.metaKey || event.altKey || event.repeat) return;
  if (event.key === "h" || event.key === "H") setHelpOpen(ui.helpPanel.hidden);
  if (event.key === "c" || event.key === "C") setMapOpen(ui.mapPanel.hidden);
});

// --- Sound settings (spec 028): one speaker button, one small panel ----------------------
// The speaker button next to "?" (index.html: it keeps the id "mute-button" of spec 016)
// opens a small panel with every sound control: the background music (music.js), the one
// volume for music and effects, and the sound effects (sound.js). Sound and music live
// entirely in those two files, which also remember each choice per browser; this only shows
// and changes their state.

function setSoundOpen(open) {
  ui.soundPanel.hidden = !open;
  ui.muteButton.setAttribute("aria-expanded", String(open));
  if (!open) ui.muteButton.blur(); // keys go back to walking
}

function setSwitch(button, on) {
  button.setAttribute("aria-checked", String(on));
  button.textContent = on ? "On" : "Off";
}

// The switches, the slider and the muted mark, from the two modules' own state. Muted means
// the music is off or the volume is 0: then the speaker is struck through, on the button
// and in the panel.
function updateSoundSettings() {
  setSwitch(ui.musicSwitch, Music.isOn());
  setSwitch(ui.effectsSwitch, Sound.effectsOn());
  ui.volumeSlider.value = String(Math.round(Sound.getVolume() * 100));
  const struck = !Music.isOn() || Sound.getVolume() === 0;
  // SVG elements have no `hidden` property, so the attribute itself is switched.
  for (const strike of document.querySelectorAll(".sound-strike")) strike.toggleAttribute("hidden", !struck);
  let label = "Sound settings";
  if (Sound.getVolume() === 0) label += " (volume is 0)";
  else if (!Music.isOn()) label += " (music is off)";
  ui.muteButton.setAttribute("aria-label", label);
  ui.muteButton.title = label;
}
updateSoundSettings();

ui.muteButton.addEventListener("click", () => {
  Sound.play("click");
  setSoundOpen(ui.soundPanel.hidden);
});
ui.soundClose.addEventListener("click", () => {
  Sound.play("click");
  setSoundOpen(false);
});
// A click or tap anywhere else closes the panel too. In the capture phase, so it also
// hears a press that the map or the joystick keeps to itself.
document.addEventListener(
  "pointerdown",
  (event) => {
    if (ui.soundPanel.hidden) return;
    if (ui.soundPanel.contains(event.target) || ui.muteButton.contains(event.target)) return;
    setSoundOpen(false);
  },
  true,
);

ui.musicSwitch.addEventListener("click", () => {
  Sound.play("click");
  Music.toggle();
  updateSoundSettings();
});
ui.effectsSwitch.addEventListener("click", () => {
  Sound.setEffectsOn(!Sound.effectsOn());
  Sound.play("click"); // only heard when the effects were just switched on: it confirms them
  updateSoundSettings();
});
// Volume (spec 020): one slider for effects and music together.
ui.volumeSlider.addEventListener("input", () => {
  Sound.setVolume(Number(ui.volumeSlider.value) / 100);
  updateSoundSettings();
});
ui.volumeSlider.addEventListener("change", () => {
  Sound.play("click"); // a sample of the new volume
  ui.volumeSlider.blur(); // arrow keys go back to walking
});

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
let lastHost = null; // the host id in the previous lobby state, to notice a hand-over
let lastHudBottom = 0; // the HUD's bottom edge in px, as last given to the stylesheet
let endKey = ""; // the same for the end screen
let meetingKey = ""; // the same for the meeting screen
let rosterIds = []; // every player id seen in the lobby this round, for the meeting grid
let pendingVote = null; // a candidate id or "skip" picked but not yet confirmed (spec 014)
let votingArgs = null; // the latest {state, meeting}, so a confirm/cancel tap can redraw
// the grid at once, without waiting for the server's next state
let roleTimer = null;
let sentSurfing = false; // this player was voted out in this round
// Sound (spec 016): state these sounds need to tell "just happened" from "already true".
let wasAliveForExpelSound = true; // `alive` one state ago, to catch the moment it flips
let pendingExpel = false; // an expel was sent and not yet confirmed or rejected
let knownVoted = new Set(); // voters already played a sound for, this meeting
// Sound (spec 017): the same idea for the new sounds.
let wasLightsOn = true; // `lights_on` one state ago
let lastCountdown = null; // `meeting.seconds_left` one state ago
let heardOpenVents = new Set(); // hatch ids that showed open one state ago
// Nicknames and colour numbers by player id. While playing, the server only sends the
// players in sight (and the living never receive ghosts), so the ones seen earlier
// (everyone is visible in the lobby) are remembered here.
const knownNames = new Map();
const knownColors = new Map();
const knownHats = new Map(); // spec 022: player id -> hat number, also for players out of sight

// --- The look on the ID card (spec 022): hat and colour, sent with "join" -------------
// Remembered per browser; the server checks both again (range, colour not taken).
const LOOK_KEY = "expelled-nova-look";
const look = loadLook();

function loadLook() {
  try {
    const saved = JSON.parse(localStorage.getItem(LOOK_KEY) || "{}");
    const hat = Number.isInteger(saved.hat) && saved.hat >= 0 && saved.hat < Hats.COUNT ? saved.hat : 0;
    const color = Number.isInteger(saved.color) && saved.color >= 0 && saved.color < 10 ? saved.color : null;
    return { hat, color };
  } catch {
    return { hat: 0, color: null }; // storage unavailable or broken: the defaults
  }
}

function saveLook() {
  try {
    localStorage.setItem(LOOK_KEY, JSON.stringify(look));
  } catch {
    // storage unavailable: the look just does not survive a reload
  }
}

// Spec 028: the colours other players already have, as {colour number: that player's
// name}. Asked from the server while the join screen shows (refreshTakenColors below).
let takenColors = {};
const TAKEN_COLORS_MS = 1500; // how often the join screen asks again

function renderLook() {
  ui.hatName.textContent = Hats.names[look.hat];
  ui.idPhotoHat.replaceChildren(Hats.svg(look.hat, 20, 13, 14 / 11));
  const photoBody = ui.idPhotoHat.parentNode.querySelector("circle");
  photoBody.setAttribute("fill", look.color === null ? "#e5484d" : Render.colorCss(look.color));
  for (const swatch of ui.colorSwatches.children) {
    const value = swatch.dataset.color === "any" ? null : Number(swatch.dataset.color);
    // Spec 028: a colour someone already has is crossed out and dimmed (style.css), not
    // clickable, and says whose it is. The name only ever becomes an attribute's text.
    const owner = value === null ? undefined : takenColors[value];
    const taken = owner !== undefined;
    swatch.disabled = taken;
    swatch.classList.toggle("taken", taken);
    let label = "Any free colour";
    if (value !== null) label = taken ? `Taken by ${owner}` : `Colour ${value + 1}`;
    swatch.setAttribute("aria-label", label);
    swatch.title = label;
    swatch.classList.toggle("active", value === look.color);
    swatch.setAttribute("aria-pressed", String(value === look.color));
  }
}

// Spec 028: keeps the picker up to date while the join screen shows, so a colour is crossed
// out as soon as someone picks it and free again when they leave. Only for showing: the
// server still rejects a taken colour on "join" (spec 022).
async function refreshTakenColors() {
  if (welcome || document.hidden) return; // the picker is only on the join screen
  let taken;
  try {
    const response = await fetch("/taken-colors", { cache: "no-store" });
    if (!response.ok) return;
    taken = (await response.json()).taken;
  } catch {
    return; // server not reachable: the picker keeps what it shows; joining asks the server anyway
  }
  if (!taken || typeof taken !== "object") return;
  const changed = JSON.stringify(taken) !== JSON.stringify(takenColors);
  takenColors = taken;
  // The own pick is taken (someone was faster): back to "Any". Not saved, so the favourite
  // colour is offered again the next time it is free.
  const lostPick = look.color !== null && takenColors[look.color] !== undefined;
  if (lostPick) look.color = null;
  if (changed || lostPick) renderLook(); // asked every moment: redraw only on a change
}
// A tab that was in the background did not ask: catch up as soon as it shows again.
document.addEventListener("visibilitychange", refreshTakenColors);

function stepHat(delta) {
  look.hat = (look.hat + delta + Hats.COUNT) % Hats.COUNT;
  saveLook();
  renderLook();
}

ui.hatPrev.addEventListener("click", () => stepHat(-1));
ui.hatNext.addEventListener("click", () => stepHat(1));

for (const value of ["any", 0, 1, 2, 3, 4, 5, 6, 7, 8, 9]) {
  const swatch = document.createElement("button");
  swatch.type = "button";
  swatch.className = "swatch" + (value === "any" ? " swatch-any" : "");
  swatch.dataset.color = String(value);
  if (value === "any") swatch.textContent = "Any";
  else swatch.style.background = Render.colorCss(value);
  // renderLook() gives every swatch its aria-label and title (free, or "Taken by ...").
  swatch.addEventListener("click", () => {
    look.color = value === "any" ? null : value;
    saveLook();
    renderLook();
  });
  ui.colorSwatches.append(swatch);
}
renderLook();
refreshTakenColors();
const takenColorsTimer = setInterval(refreshTakenColors, TAKEN_COLORS_MS);

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
    clearInterval(takenColorsTimer); // joined: the colour picker is gone (spec 028)
    ui.mapSlot.append(CampusMap.build(welcome.map)); // once: opening the map never rebuilds it
    ui.mapButton.hidden = false;
    ui.joinScreen.hidden = true;
    ui.hud.hidden = false;
    startGame();
  } else if (message.type === "error") {
    if (welcome) {
      showToast(message.reason);
      meetingKey = ""; // redraw the meeting screen: re-enables the vote buttons
      pendingExpel = false; // the expel was rejected: no sound for it (spec 016)
    } else {
      showJoinError(message.reason);
      refreshTakenColors(); // e.g. "Colour is already taken": show it in the picker at once
    }
  } else if (message.type === "state" && welcome) {
    const players = new Map(message.players.map((p) => [p.id, p]));
    // Only a ghost (or everyone after the end) receives the ghost list; the living
    // do not even receive the ghosts' positions.
    // Spec 027: "guard" is missing whenever he is out of this player's own sight (or does
    // not exist), kept here per snapshot so updateGuard() can interpolate him like any player.
    snapshots.push({ time: performance.now(), players, ghosts: new Set(message.ghosts || []), guard: message.guard || null });
    latestState = message;
    for (const p of message.players) knownNames.set(p.id, p.name);
    for (const [id, color] of Object.entries(message.colors)) knownColors.set(id, color);
    for (const [id, hat] of Object.entries(message.hats || {})) knownHats.set(id, hat);
    // Keep about one second of history.
    while (snapshots.length > welcome.tick_rate) snapshots.shift();
    updateHud(message);
    updatePhase(message);
    if (!ui.mapPanel.hidden) {
      updateMapWhere(message);
      updateMapTasks(message);
    }
  }
}

// --- HUD: current area and player count (spec 005) ----------------------------------

function updateHud(state) {
  // Spec 026: the campus map is dimmed exactly when the own world goes dark.
  CampusMap.setDark(state.phase === "playing" && state.lights_on === false && state.role === "student" && state.alive);
  // The server works out the area from the own position; no area means a corridor.
  setText(ui.areaName, state.area || "Corridor");
  // Only the lobby shows everyone: while playing, a living player just receives the
  // players within the vision radius, so a count would be wrong.
  ui.playerCount.hidden = state.phase !== "lobby";
  setText(ui.playerCount, `Players: ${state.players.length}/10`);
  // The HUD wraps onto more lines on a narrow window. The panels under it (style.css)
  // start below its real bottom edge instead of a guessed height.
  const hudBottom = Math.round(ui.hud.getBoundingClientRect().bottom);
  if (hudBottom !== lastHudBottom) {
    lastHudBottom = hudBottom;
    document.documentElement.style.setProperty("--hud-bottom", `${hudBottom}px`);
  }
}

// A player's nickname, also for players out of sight or voted out.
function nameOf(playerId) {
  return knownNames.get(playerId) ?? "A player";
}

// Spec 028: is this player a fellow examiner of this browser's player? The server sends
// `fellow_examiners` to examiners only, so on a student's page this is always false and
// every name keeps its normal colour.
function isFellowExaminer(state, playerId) {
  return (state.fellow_examiners || []).includes(playerId);
}

// Spec 028: the tone of a player's name on this browser's screen.
// - The own name tells the own side: "examiner" (red) or "student" (green); in the lobby
//   there is no role yet, so no tone.
// - Another player's name is "examiner" (red) only for a fellow examiner, which only an
//   examiner's snapshot lists. Every other name has no tone and keeps its normal colour,
//   also at the end of a round: nobody learns from a name who else is a student.
function nameTone(state, playerId) {
  if (playerId === welcome.id) return state.role || null;
  return isFellowExaminer(state, playerId) ? "examiner" : null;
}

// Gives a name element its tone's colour (style.css: .name-examiner, .name-student).
function markName(element, state, playerId) {
  const tone = nameTone(state, playerId);
  if (!tone) return;
  element.classList.add(`name-${tone}`);
  if (playerId !== welcome.id) element.title = "Fellow examiner";
}

function playerColor(state, playerId) {
  return state.colors[playerId] ?? knownColors.get(playerId);
}

// Spec 022: the hat, like the colour also for players out of sight.
function playerHat(state, playerId) {
  return (state.hats && state.hats[playerId]) ?? knownHats.get(playerId) ?? 0;
}

// A small original character (spec 014), echoing the one drawn on the map (render.js) at a
// glance: a round body in the player's colour, a graduation cap and two eyes. Used for the
// lobby chips and the meeting cards; a ghost is drawn greyed out with CSS (.ghost), not here.
function characterChip(colorNumber, size = 32, hat = 0) {
  const svg = svgEl("svg", { viewBox: "0 0 40 40", width: size, height: size, class: "chip-figure" });
  const fill = Render.colorCss(colorNumber);
  svg.append(
    svgEl("circle", { cx: 20, cy: 23, r: 14, fill, stroke: "#16181d", "stroke-width": 2 }),
    svgEl("circle", { cx: 15.5, cy: 22, r: 2.3, fill: "#fff" }),
    svgEl("circle", { cx: 24.5, cy: 22, r: 2.3, fill: "#fff" }),
    svgEl("circle", { cx: 15.5, cy: 22.4, r: 0.9, fill: "#16181d" }),
    svgEl("circle", { cx: 24.5, cy: 22.4, r: 0.9, fill: "#16181d" }),
    Hats.svg(hat, 20, 9, 14 / 11), // spec 022: this head (r 14, top at y 9) is 14/11 of the map's
  );
  svg.style.overflow = "visible"; // tall hats may stick out of the 40x40 box
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
  ui.controlMeeting.hidden = ui.meetingButton.hidden || ui.meetingButton.disabled;
  ui.controlUse.hidden = ui.taskButton.hidden && ui.fixButton.hidden;
  setText(ui.controlUseLabel, ui.fixButton.hidden ? "task" : "fix lights");
  ui.controlDoor.hidden = ui.doorItem.hidden || ui.doorActionButton.disabled;
  ui.controlSabotage.hidden = ui.sabotageButton.hidden;
}

// --- Lobby and roles --------------------------------------------------------------
// Everything here is drawn from the server's state; this browser only ever receives
// its own role (and, for an examiner, the fellow examiners' ids).

function updatePhase(state) {
  // Only at the start of a game: play resuming after a meeting shows no role screen.
  const previousPhase = lastPhase;
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

  // A meeting starting (button or report), for everyone: a gong, once, right on the phase
  // change, the same moment the meeting screen itself appears. Also resets the set of
  // voters this browser has already played a sound for (see renderMeeting).
  if (state.phase === "meeting" && previousPhase !== "meeting") {
    Sound.play("meetingChime");
    // A report also sounds the alarm, for everyone at once (spec 017).
    if (state.meeting && state.meeting.reason === "report") Sound.play("reportAlarm");
    // Spec 027: a security catch sounds its own short alarm, for everyone at once.
    if (state.meeting && state.meeting.reason === "security") Sound.play("securityAlarm");
    knownVoted = new Set();
  }
  // The end of a round, once, for everyone (spec 017). Spec 020: the sound tells which
  // side won, the same for every player: `winner` is "students" or "examiners".
  if (state.phase === "ended" && previousPhase !== "ended") {
    if (state.winner === "students") Sound.play("studentsWin");
    else Sound.play("examinersWin");
  }
  updateMusic(state);
  // The lights going out or coming back, for everyone at once (spec 017). Only while the
  // round goes on: a meeting turns the lights back on too, and that plays only the gong.
  if (previousPhase === "playing" && state.phase === "playing" && state.lights_on !== wasLightsOn) {
    if (state.lights_on === false) Sound.play("lightsOut");
    else Sound.play("lightsOn");
  }
  wasLightsOn = state.lights_on;
  checkVentSounds(state);
  // Expel (spec 016): the paper-rip sound is purely local to the two players it belongs to.
  // The expelled player's own `alive` flips to false while still in the "playing" phase
  // (a meeting vote-out instead flips it during the "meeting" phase, so that case never
  // matches here); the expelling examiner's side is handled by checkExpelSound below.
  if (state.phase === "playing" && previousPhase === "playing" && wasAliveForExpelSound && !state.alive) {
    Sound.play("expel");
    Sound.play("expelVoice"); // spec 020: "Expelled!"
  }
  wasAliveForExpelSound = state.alive;
  checkExpelSound(state);
  // The whole action bar only during a round (spec 014): a slot's own hidden/disabled
  // state below only has to track the player's role and momentary availability, not phase.
  ui.actions.hidden = state.phase !== "playing";
  updateExpelButton(state);
  updateReportAndMeeting(state);
  updateTasks(state);
  updateMinigame(state);
  updateVents(state);
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

// The background music's mood (spec 017), from `phase` and `lights_on` only: every player
// receives both alike, so the music is the same for every role and for ghosts and tells the
// people sitting next to a phone nothing about its player.
function updateMusic(state) {
  if (state.phase === "lobby") Music.setMood("lobby");
  else if (state.phase === "playing" && state.lights_on === false) Music.setMood("dark");
  else if (state.phase === "playing") Music.setMood("playing");
  else Music.setMood("off"); // meeting (the gong and the silence) and ended (the jingle)
}

// Vent hatches (spec 017): one clank when a hatch newly shows open in this browser's own
// `open_vents`. The server lists only the hatches in sight, by id only, and the examiner's
// own vent is in their own list too, so the examiner hears exactly what a bystander hears.
// Moving between vents opens no hatch, so it makes no sound.
function checkVentSounds(state) {
  const open = state.phase === "playing" ? state.open_vents || [] : [];
  if (open.some((id) => !heardOpenVents.has(id))) Sound.play("ventHatch");
  heardOpenVents = new Set(open);
}

function renderLobby(state) {
  // The whole lobby's roster, remembered for the meeting grid (spec 014): a living
  // player's state never lists a ghost, so "who is missing from `meeting.living`" is read
  // against this list, captured here since the lobby is the one phase everyone sees
  // everyone in.
  rosterIds = state.players.map((p) => p.id);
  setText(ui.lobbyCount, `${state.players.length}/10`);
  const isHost = state.host === welcome.id;
  // The host changed to this player (hand-over or the old host left): say so once.
  if (isHost && lastHost !== null && lastHost !== welcome.id) showToast("You are the host now. The class register is yours.");
  lastHost = state.host;

  // Redraw the list only when players or host change (states arrive 20 times a second).
  const key = JSON.stringify([state.host, state.colors, state.players.map((p) => [p.id, p.name])]);
  if (key !== lobbyKey) {
    lobbyKey = key;
    ui.lobbyPlayers.replaceChildren(
      ...state.players.map((p) => {
        // One line of the class roster (spec 015): the character, the name, the host mark
        // and, for the host, the hand-over button on every other player's line.
        const item = document.createElement("li");
        item.className = "lobby-chip";
        item.append(characterChip(playerColor(state, p.id), 32, playerHat(state, p.id)));
        const name = document.createElement("span");
        name.className = "lobby-chip-name";
        name.append(p.name); // appended as text: never read as HTML
        if (p.id === state.host) name.append(hostSymbol(), tag("host", "host"));
        if (p.id === welcome.id) name.append(tag("you", "you"));
        item.append(name);
        if (isHost && p.id !== welcome.id) {
          const handOver = document.createElement("button");
          handOver.type = "button";
          handOver.className = "make-host";
          handOver.textContent = "Make host";
          handOver.setAttribute("aria-label", `Make ${p.name} the host`);
          // The server checks host, phase and target; a rejection comes back as a toast.
          handOver.addEventListener("click", () => {
            Sound.play("click");
            send({ type: "make_host", target: p.id });
          });
          item.append(handOver);
        }
        return item;
      }),
    );
  }
  renderLobbySettings(state, isHost);
  const enough = state.players.length >= MIN_PLAYERS;
  ui.startButton.hidden = !isHost;
  ui.startButton.disabled = !enough;
  setText(ui.startButton, enough ? "Start game" : `Need ${MIN_PLAYERS - state.players.length} more players`);
  let hint = "";
  if (!isHost) hint = enough ? "Waiting for the host to start" : `Need at least ${MIN_PLAYERS} players`;
  setText(ui.startHint, hint);
}

// Spec 019: the examiner setting. Only the host can press the buttons; the server checks
// again (host, lobby, value) and answers a rejection with a toast.
function renderLobbySettings(state, isHost) {
  const chosen = state.settings ? state.settings.expellers : null;
  for (const button of ui.lobbySettings.querySelectorAll("button")) {
    const value = button.dataset.expellers === "auto" ? null : Number(button.dataset.expellers);
    const active = value === chosen;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
    button.disabled = !isHost;
    button.title = isHost ? "" : "Only the host can change this";
  }
}

ui.lobbySettings.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-expellers]");
  if (!button || button.disabled) return;
  Sound.play("click");
  const raw = button.dataset.expellers;
  send({ type: "settings", expellers: raw === "auto" ? null : Number(raw) });
  button.blur();
});

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

// The role reveal (spec 015): a letter from the campus with the role's motto and a stamp.
// Every text is set as text; the look per role is in style.css (data-role).
function showRoleScreen(roleName, role) {
  // One dramatic chord, played before the role is even looked at, so it is byte-for-byte
  // the same whichever role follows (spec 016): nobody can tell a role apart by sound.
  Sound.play("roleReveal");
  ui.roleTitle.textContent = role.title;
  if (roleName === "examiner") {
    ui.roleKicker.textContent = "Examination Board · strictly confidential";
    ui.roleMotto.textContent = "Fail them all";
    const fellows = role.fellows ? `Fellow examiner: ${role.fellows}.` : "You are the only examiner.";
    ui.roleDetail.textContent = `Blend in, hand out failed exams and do not get caught. ${fellows}`;
    ui.roleStamp.textContent = "Undercover";
  } else {
    ui.roleKicker.textContent = "Office of Admissions";
    ui.roleMotto.textContent = "Survive the semester";
    ui.roleDetail.textContent = "Finish your to-do list, stay enrolled and find out who the examiners are.";
    ui.roleStamp.textContent = "Enrolled";
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

// A timed cooldown (expel, vent, lights off): the ring sweeps back to full as
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
  Sound.play("click");
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
  else if (insideVent(state)) reason = "Leave the vent first";
  else if (cooldown > 0) reason = `Ready in ${cooldown} s`;
  else if (!target) reason = "Nobody in range";
  else reason = `Expel ${target.name}`; // the full reason, e.g. on hover; the label stays "Expel"
  if (insideVent(state)) ui.expelButton.disabled = true;
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
  pendingExpel = true; // checkExpelSound() plays the rip once the server confirms it
}

// The examiner's own half of the expel sound (spec 016): waits for the server to actually
// start the cooldown (the only way it can go from 0 to not-0 while still playing), instead
// of assuming the click succeeded. handleMessage's "error" branch clears pendingExpel on a
// rejection, so a target that stepped out of range in the meantime plays no sound at all.
function checkExpelSound(state) {
  if (!pendingExpel || state.phase !== "playing") return;
  if (state.expel_cooldown > 0) {
    pendingExpel = false;
    Sound.play("expel");
    Sound.play("expelVoice"); // spec 020: "Expelled!"
  }
}

function renderEnd(state) {
  // Redraw only when something on the end screen changes.
  const key = JSON.stringify([
    state.winner,
    state.roles,
    state.ghosts,
    state.colors,
    state.security_witnessed,
    state.players.map((p) => [p.id, p.name]),
  ]);
  if (key !== endKey) {
    endKey = key;
    // Spec 027: one added short note when the expel that ended the game was itself seen.
    ui.endSecurityNote.hidden = !state.security_witnessed;
    // The task win is the only way a round ends with every task done (spec 004).
    const progress = state.task_progress;
    const byTasks = state.winner === "students" && progress.total > 0 && progress.done === progress.total;
    let title = state.winner === "students" ? "Students win!" : "Examiners win!";
    if (byTasks) title = "All tasks done: students win";
    ui.endTitle.textContent = title;
    ui.endScreen.dataset.winner = state.winner;
    // The story around the clear title (spec 015): a diploma for the students' win, an
    // exmatriculation letter for the examiners' win. The look is in style.css.
    if (state.winner === "students") {
      ui.endKicker.textContent = "Nova Campus · Diploma";
      ui.endText.textContent = byTasks
        ? "This certifies that every form is stamped and every errand is done. The class survived the semester."
        : "This certifies that the class found every undercover examiner and sent them surfing.";
      ui.endStamp.textContent = "Passed";
    } else {
      ui.endKicker.textContent = "Nova Campus · Exmatriculation notice";
      ui.endText.textContent = "We regret to inform you that the examiners failed them all. Please return your student card at the gate.";
      ui.endStamp.textContent = "Expelled";
    }
    const ghosts = new Set(state.ghosts || []);
    ui.endRoles.replaceChildren(
      ...state.players.map((p) => {
        const role = state.roles[p.id];
        const item = document.createElement("li");
        const name = document.createElement("span");
        name.textContent = p.name; // set as text: never read as HTML
        markName(name, state, p.id); // spec 028: red for the examiners' team, green for the own student name
        item.append(characterChip(playerColor(state, p.id), 24, playerHat(state, p.id)), name);
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
  Sound.play("click");
  tryExpel();
  ui.expelButton.blur();
});

ui.restartButton.addEventListener("click", () => {
  Sound.play("click");
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
  const inVent = insideVent(state);
  ui.reportButton.disabled = !target || inVent;
  let reportReason = "";
  if (!alive) reportReason = "Ghosts cannot report";
  else if (inVent) reportReason = "Leave the vent first";
  else if (!target) reportReason = "No failed exam within reach";
  setActionReason(ui.reportButton, reportReason, "Report");

  const near = alive && nearMeetingTable(state);
  const used = Boolean(state.meeting_used);
  ui.meetingButton.disabled = !alive || used || !near || inVent;
  let meetingReason = "";
  if (!alive) meetingReason = "Ghosts cannot call a meeting";
  else if (inVent) meetingReason = "Leave the vent first";
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
  Sound.play("click");
  tryReport();
  ui.reportButton.blur();
});

// Key M and the button (spec 015). The server checks everything again; this only explains
// the two common reasons without a round trip.
function tryMeeting() {
  if (!latestState || !isLivingAndPlaying(latestState)) return;
  if (latestState.meeting_used) {
    showToast("You have already called a meeting");
    return;
  }
  if (!nearMeetingTable(latestState)) {
    showToast("Go to the meeting table first");
    return;
  }
  send({ type: "meeting" });
}

ui.meetingButton.addEventListener("click", () => {
  Sound.play("click");
  tryMeeting();
  ui.meetingButton.blur();
});

function renderMeeting(state) {
  const meeting = state.meeting;
  // A soft tick for every vote that lands, including ones cast between two redraws of this
  // screen: `meeting.voted` carries ids only, never a target, so this never learns who a
  // vote was for (spec 016). The own vote already played "voteSelf" at the moment it was
  // cast (castVote), so it is skipped here to avoid a second sound for the same vote.
  for (const id of meeting.voted) {
    if (knownVoted.has(id)) continue;
    knownVoted.add(id);
    if (id !== welcome.id) Sound.play("voteOther");
  }
  // The last 5 seconds of voting tick, for everyone (spec 017); not while the result shows.
  const secondsLeft = meeting.seconds_left;
  if (!meeting.result && secondsLeft !== lastCountdown && secondsLeft >= 1 && secondsLeft <= 5) {
    Sound.play("countdownTick");
  }
  lastCountdown = secondsLeft;
  setText(ui.meetingTimer, `${meeting.seconds_left} s`);
  const result = meeting.result;
  // Redraw only when something on the screen changes; the timer is updated above, so a
  // redraw does not replace the cards under the mouse every second.
  const key = JSON.stringify([{ ...meeting, seconds_left: null }, state.alive]);
  if (key === meetingKey) return;
  meetingKey = key;
  pendingVote = null; // a real change from the server always clears a half-made pick

  const caller = nameOf(meeting.called_by); // added as text: never read as HTML
  if (meeting.reason === "report") {
    ui.meetingReason.textContent = `${caller} found a failed exam on the floor.`;
  } else if (meeting.reason === "security") {
    // Spec 027: named exactly as called_by's name is read above, appended as text only.
    ui.meetingReason.textContent = `Campus Security caught ${nameOf(meeting.caught)} handing out a failing exam!`;
  } else {
    ui.meetingReason.textContent = `${caller} pressed the emergency button.`;
  }
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
function buildPlayerCard(state, playerId, { isGhost, hasVoted, canVote, caughtBySecurity }) {
  const card = document.createElement("div");
  card.className = "meeting-player-card" + (isGhost ? " ghost" : "");
  card.append(characterChip(playerColor(state, playerId), 40, playerHat(state, playerId)));
  const name = document.createElement("span");
  name.className = "player-name";
  name.append(nameOf(playerId)); // appended as text: never read as HTML
  markName(name, state, playerId); // spec 028: red for the examiners' team, green for the own student name
  if (playerId === welcome.id) name.append(tag("you", "you"));
  card.append(name);
  if (caughtBySecurity) {
    const stamp = document.createElement("span");
    stamp.className = "caught-stamp";
    stamp.textContent = "Caught by security";
    card.append(stamp);
  }
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
    Sound.play("click");
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
    Sound.play("click");
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
      caughtBySecurity: playerId === meeting.caught,
    }),
  );
  for (const playerId of ghostIds) {
    cards.push(
      buildPlayerCard(state, playerId, {
        isGhost: true,
        hasVoted: false,
        canVote: false,
        caughtBySecurity: playerId === meeting.caught,
      }),
    );
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
  setText(ui.meetingTitle, "Who is an examiner?");
  votingArgs = { state, meeting };
  buildVotingGrid();
}

// One small dot per vote (spec 014). Spec 019: once the vote is counted the server sends
// `ballots` (voter -> target), so each dot is drawn in the voter's colour; while voting it
// never does. `voters` is the list of voter ids for this card.
function voteDots(state, voters) {
  const wrap = document.createElement("span");
  wrap.className = "vote-dots";
  for (const voterId of voters) {
    const dot = document.createElement("span");
    dot.className = "vote-dot";
    const color = playerColor(state, voterId);
    if (color !== undefined) dot.style.background = Render.colorCss(color);
    dot.title = `${nameOf(voterId)} voted`;
    wrap.append(dot);
  }
  return wrap;
}

function votersFor(state, target) {
  return Object.entries(state.ballots || {})
    .filter(([, choice]) => choice === target)
    .map(([voterId]) => voterId);
}

function renderResult(state, result) {
  setText(ui.meetingTitle, "The faculty has decided");
  const cards = Object.entries(result.votes).map(([playerId, count]) => {
    const card = document.createElement("div");
    card.className = "meeting-player-card";
    card.append(characterChip(playerColor(state, playerId), 40, playerHat(state, playerId)));
    const name = document.createElement("span");
    name.className = "player-name";
    name.append(nameOf(playerId)); // appended as text: never read as HTML
    markName(name, state, playerId); // spec 028
    if (playerId === welcome.id) name.append(tag("you", "you"));
    if (playerId === result.surfing) name.append(tag("sent surfing", "surfing"));
    card.append(name);
    const votesLabel = document.createElement("span");
    votesLabel.className = "count";
    votesLabel.textContent = count === 1 ? "1 vote" : `${count} votes`;
    card.append(votesLabel, voteDots(state, votersFor(state, playerId)));
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
  skipCard.append(skipLabel, skipCount, voteDots(state, votersFor(state, "skip")));
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
  Sound.play("voteSelf");
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
  Sound.play("click");
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
let lastTaskSteps = new Map(); // multi-step task id -> its last-seen current station (spec 016)

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
  // Not during a meeting (spec 015): the notebook would cover the players standing
  // around the table on a phone; the shared bar above stays.
  const tasks = state.tasks || [];
  // A shorter chime for one finished station of a multi-step task (spec 016, spec 012 part
  // 4): the station the player is on moved forward, but the whole task is not done yet
  // (that case plays "taskDone" from showJoke instead, once the joke popup opens for it).
  for (const task of tasks) {
    if (!task.steps) continue;
    const previousStep = lastTaskSteps.get(task.id);
    if (previousStep !== undefined && task.step > previousStep && !task.done) Sound.play("taskStep");
    lastTaskSteps.set(task.id, task.step);
  }
  ui.taskList.hidden = !(state.phase === "playing" && tasks.length > 0);
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
    ui.taskButton.disabled = !player || Boolean(state.doing) || !target || insideVent(state);
    let reason = "";
    if (inRound && !player) reason = "Ghosts cannot do tasks";
    else if (insideVent(state)) reason = "Leave the vent first";
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
  Sound.play("taskDone"); // the whole task is done; only its own owner ever gets here
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
  Sound.play("click");
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
  tray: "Tap in the order of the Nova line.", // spec 021
  surf: "Stand up when the wave is under your board.", // spec 021
  print_file: "Print exactly the file the group chat asks for.", // spec 024
  cert_file: "Print exactly the file the office asks for.", // spec 024
  chat: "Answer the Helpdesk in Portuguese.", // spec 024
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
  // Spec 021: the surf wave's phase changes every tick; leave it out of the key so the
  // panel (and its button) is not rebuilt 20 times a second, and only move the wave.
  const { phase, ...stable } = doing.challenge;
  const key = JSON.stringify([doing.task, doing.challenge.kind === "surf" ? stable : doing.challenge]);
  if (key !== minigameKey) {
    minigameKey = key;
    renderChallenge(doing.task, doing.challenge);
  }
  if (doing.challenge.kind === "surf") moveWave(doing.challenge);
  const note = state.task_note || "";
  if (note !== minigameNoteShown) {
    minigameNoteShown = note;
    setText(ui.minigameNote, note);
    ui.minigameNote.hidden = !note;
    // A wrong-but-valid answer (spec 012) is the only way a note appears while `doing` is
    // still set: a time-out or a cancel clear `doing` in the very same snapshot, so they
    // never reach this branch. One shared buzz for every mini-game (spec 016).
    if (note) Sound.play("error");
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
  else if (challenge.kind === "tray") renderTray(taskId, challenge);
  else if (challenge.kind === "surf") renderSurf(taskId, challenge);
  else if (challenge.kind === "print_file" || challenge.kind === "cert_file") renderFilePick(taskId, challenge);
  else if (challenge.kind === "chat") renderChat(taskId, challenge);
}

// print_file and cert_file (spec 024) — a message says which file to print; four almost
// identical names to pick from. The file list is shown in a monospace font, so the tiny
// differences are visible.
function renderFilePick(taskId, challenge) {
  const message = document.createElement("p");
  message.className = "minigame-bubble";
  const who = challenge.kind === "cert_file" ? "Student Services" : "Group chat";
  message.textContent = `${who}: "Print ${challenge.request} !!"`;
  const round = document.createElement("p");
  round.className = "minigame-hits";
  round.textContent = `File ${challenge.round}/${challenge.rounds}`;
  const options = document.createElement("div");
  options.className = "minigame-options file-options";
  challenge.options.forEach((name, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `\u{1F4C4} ${name}`;
    button.addEventListener("click", () => {
      Sound.play("click");
      sendTaskInput(taskId, index);
    });
    options.append(button);
  });
  ui.minigameContent.append(message, round, options);
}

// chat (spec 024) — the Helpdesk says one line in Portuguese; pick the Portuguese reply that
// means what you want to say. Which one is right stays on the server.
function renderChat(taskId, challenge) {
  const desk = document.createElement("p");
  desk.className = "minigame-bubble";
  desk.textContent = `Helpdesk: "${challenge.line}"`;
  const want = document.createElement("p");
  want.className = "minigame-hits";
  want.textContent = `You want to say: ${challenge.want}  (${challenge.step + 1}/${challenge.steps})`;
  const options = document.createElement("div");
  options.className = "minigame-options";
  challenge.options.forEach((reply, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = reply;
    button.addEventListener("click", () => {
      Sound.play("typingClick");
      sendTaskInput(taskId, index);
    });
    options.append(button);
  });
  ui.minigameContent.append(desk, want, options);
}

// tray (spec 021) — the Nova cafeteria line: the order is printed, the buttons are shuffled.
const TRAY_ICONS = { "Main course": "\u{1F35D}", Soup: "\u{1F963}", Drink: "\u{1F964}", Dessert: "\u{1F36E}", Pay: "\u{1F4B6}" };

function renderTray(taskId, challenge) {
  const line = document.createElement("p");
  line.className = "minigame-hits";
  line.textContent = challenge.order.map((item, i) => (i < challenge.next ? `\u2713 ${item}` : item)).join("  \u2192  ");
  const options = document.createElement("div");
  options.className = "minigame-options";
  challenge.items.forEach((item, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${TRAY_ICONS[item] || ""} ${item}`;
    button.addEventListener("click", () => {
      Sound.play("click");
      sendTaskInput(taskId, index);
    });
    options.append(button);
  });
  ui.minigameContent.append(line, options);
}

// surf (spec 021) — a wave rolls under the board every 2 s; stand up on the crest. The
// server decides by its own tick; this only draws the wave from the latest `phase`.
let surfWave = null;

function renderSurf(taskId, challenge) {
  const rides = document.createElement("p");
  rides.className = "minigame-hits";
  rides.textContent = `Waves ridden: ${challenge.rides}/${challenge.goal}`;
  const sea = document.createElement("div");
  sea.className = "surf-sea";
  const crest = document.createElement("div");
  crest.className = "surf-crest";
  const board = document.createElement("div");
  board.className = "surf-board";
  board.textContent = "\u{1F3C4}";
  const wave = document.createElement("div");
  wave.className = "surf-wave";
  wave.textContent = "\u{1F30A}";
  sea.append(crest, wave, board);
  surfWave = { wave, crest, board };
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Stand up!";
  button.addEventListener("click", () => {
    Sound.play("click");
    sendTaskInput(taskId, true);
  });
  ui.minigameContent.append(rides, sea, button);
  moveWave(challenge);
}

// The wave travels from right to left once per cycle; the board sits where the crest
// window is, so "wave under the board" is exactly the moment the server accepts.
function moveWave(challenge) {
  if (!surfWave) return;
  const [low, high] = challenge.crest;
  const mid = (low + high) / 2;
  const at = (phase) => 100 - (phase / challenge.period) * 100; // percent from the left
  surfWave.wave.style.left = `${at(challenge.phase)}%`;
  surfWave.board.style.left = `${at(mid)}%`;
  surfWave.crest.style.left = `${at(high)}%`;
  surfWave.crest.style.width = `${((high - low) / challenge.period) * 100}%`;
  const riding = challenge.phase >= low && challenge.phase < high;
  surfWave.crest.classList.toggle("now", riding);
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
  button.addEventListener("click", () => {
    // The challenge already shows both numbers, so the right moment is not a secret
    // (spec 012): the ding plays right on the tap instead of waiting for the server.
    if (challenge.counter === challenge.number) Sound.play("ticketDing");
    sendTaskInput(taskId, true);
  });
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
    // The right translation is secret (spec 012): one flat typing click on every tap,
    // right or wrong; a wrong one also gets the shared error buzz once the server answers.
    button.addEventListener("click", () => {
      Sound.play("typingClick");
      sendTaskInput(taskId, index);
    });
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
    // Which cells are jammed is secret (spec 012): every tap just rattles the printer; a
    // real jam cleared moves the task on (taskDone/taskStep), a miss gets the error buzz.
    button.addEventListener("click", () => {
      Sound.play("paperRattle");
      sendTaskInput(taskId, i);
    });
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
    const value = input.value.padStart(5, "0");
    // The shown number is not a secret (spec 012): the accept beep plays on the tap itself.
    if (value === challenge.number) Sound.play("cardAccept");
    sendTaskInput(taskId, value);
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
    // Nothing in a cable challenge is secret (spec 012): the matching shape is the whole
    // game, so the plug click plays right on a real match, same as the "plugged" animation.
    if (challenge.cables[index] === challenge.port) {
      playAnimation(projectorSvg, "plugged");
      Sound.play("cableClick");
    } else {
      playAnimation(cableEl, "shake");
    }
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
      // The seagull's cell is shown, not secret (spec 012): a hit's squawk plays on the tap.
      if (i === challenge.cell) {
        flinchTart(tart);
        Sound.play("seagullHit");
      }
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
  Sound.play("click");
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
    ui.sabotageButton.disabled = !alive || dark || cooldown > 0 || insideVent(state);
    let reason = "";
    if (!alive) reason = "Ghosts cannot sabotage";
    else if (insideVent(state)) reason = "Leave the vent first";
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
  Sound.play("click");
  send({ type: "fix" });
  ui.fixButton.blur();
});

ui.sabotageButton.addEventListener("click", () => {
  Sound.play("click");
  trySabotage();
  ui.sabotageButton.blur();
});

// --- Vents (spec 015; they replace the staff doors of spec 008) -------------------------
// The server decides who is inside which vent and hides them from everyone else. This only
// shows the own state and sends "vent_enter", "vent_move" and "vent_leave"; the buttons are
// a convenience, the server checks role, place and cooldown again.

let ventKey = ""; // what the vent cards currently show, to redraw only on changes

function insideVent(state) {
  return Boolean(state && state.phase === "playing" && state.vent);
}

// The vent under the latest server position of a living examiner, or null.
// REPEATS SERVER RULE: Game._vent_under() in server/game.py (the centre is on the tile).
function ventUnder(state) {
  if (!isLivingExaminer(state)) return null;
  const me = state.players.find((p) => p.id === welcome.id);
  if (!me) return null;
  const t = welcome.map.tile_size;
  const col = Math.floor(me.x / t);
  const row = Math.floor(me.y / t);
  return (welcome.map.vents || []).find((vent) => vent.x === col && vent.y === row) || null;
}

// The vent this examiner is inside (the server's `vent` id), or null.
function currentVent(state) {
  if (!insideVent(state)) return null;
  return (welcome.map.vents || []).find((vent) => vent.id === state.vent) || null;
}

// The direction from one vent to another in map pixels (y grows downwards).
function ventDirection(from, to) {
  return { x: to.x - from.x, y: to.y - from.y };
}

// A small arrow, rotated in world space to point from the vent `here` toward `vent`.
function ventArrow(here, vent) {
  const { x, y } = ventDirection(here, vent);
  const angle = (Math.atan2(y, x) * 180) / Math.PI;
  const svg = svgEl("svg", { viewBox: "0 0 24 24", width: 18, height: 18, class: "door-arrow", "aria-hidden": "true" });
  const g = svgEl("g", { transform: `rotate(${angle} 12 12)` });
  g.append(
    svgEl("path", {
      d: "M4 12h13M12 6l6 6-6 6",
      fill: "none",
      stroke: "currentColor",
      "stroke-width": 2.4,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
    }),
  );
  svg.append(g);
  return svg;
}

function updateVents(state) {
  // The fixed VENT slot: examiners only, for the whole round (spec 014).
  ui.doorItem.hidden = state.role !== "examiner";
  if (ui.doorItem.hidden) {
    ventKey = "";
    return;
  }
  const alive = state.phase === "playing" && state.alive;
  const inside = currentVent(state);
  const here = inside || (alive ? ventUnder(state) : null);
  const cooldown = alive && !inside ? state.vent_cooldown : 0;
  ui.doorActionButton.disabled = !alive || !here || cooldown > 0;
  let reason = "";
  if (!alive) reason = "Ghosts cannot use vents";
  else if (!here) reason = "Not at a vent";
  else if (cooldown > 0) reason = `Ready in ${cooldown} s`;
  setActionReason(ui.doorActionButton, reason, inside ? "Leave the vent" : "Climb into the vent");
  setText(ui.doorActionLabel, inside ? "Leave vent" : "Vent");
  ui.doorActionButton.classList.toggle("inside", Boolean(inside));
  setCooldownRing(ui.doorActionButton, cooldown, VENT_COOLDOWN);

  // While inside: one arrow card per other vent, pointing toward it (spec 015).
  const key = inside ? inside.id : "";
  if (key === ventKey) return;
  ventKey = key;
  const targets = inside ? welcome.map.vents.filter((vent) => vent !== inside) : [];
  ui.doorButtons.replaceChildren(
    ...targets.map((vent) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "door-card";
      button.append(ventArrow(inside, vent));
      button.append(vent.name); // appended as text: never read as HTML
      button.addEventListener("click", () => {
        Sound.play("click");
        send({ type: "vent_move", to: vent.id });
        button.blur();
      });
      return button;
    }),
  );
}

// Key V and the round button: climb in on a vent, climb out when inside.
function tryVent() {
  if (!latestState || !isLivingExaminer(latestState)) return;
  if (insideVent(latestState)) {
    send({ type: "vent_leave" });
    return;
  }
  if (!ventUnder(latestState)) return;
  if (latestState.vent_cooldown > 0) {
    showToast(`Vent cooldown: ${latestState.vent_cooldown} s left`);
    return;
  }
  send({ type: "vent_enter" });
}

// An arrow key (or WASD) while inside: move to the vent that lies most in that direction.
// (dx, dy) is the pressed direction, each -1, 0 or 1; two keys together give a diagonal.
const VENT_KEY_ANGLE = 60; // degrees: a vent further off the pressed direction is not chosen
function tryVentDirection(dx, dy) {
  const here = currentVent(latestState);
  if (!here || (dx === 0 && dy === 0)) return;
  const pressed = Math.atan2(dy, dx);
  let best = null;
  let bestOff = (VENT_KEY_ANGLE * Math.PI) / 180;
  for (const vent of welcome.map.vents) {
    if (vent === here) continue;
    const { x, y } = ventDirection(here, vent);
    let off = Math.abs(Math.atan2(y, x) - pressed);
    if (off > Math.PI) off = 2 * Math.PI - off;
    if (off <= bestOff) {
      best = vent;
      bestOff = off;
    }
  }
  if (best) send({ type: "vent_move", to: best.id });
}

ui.doorActionButton.addEventListener("click", () => {
  Sound.play("click");
  tryVent();
  ui.doorActionButton.blur();
});

// --- Join form ------------------------------------------------------------------

ui.joinForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  Sound.play("click");
  ui.joinError.textContent = "";
  ui.joinButton.disabled = true;
  try {
    if (!socket) await connect();
    // The server validates the nickname and answers with "welcome" or "error".
    send({ type: "join", name: ui.nickname.value, hat: look.hat, color: look.color });
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

// How close a position (map pixels) is to the sea, for the waves (spec 017): 1 within one
// tile of a `sea` decor rectangle (a tile next to the water), falling to 0 at
// BEACH_RANGE_TILES. Only from the map everyone already has and the own position.
function beachCloseness(pos) {
  const t = welcome.map.tile_size;
  let nearest = Infinity; // in tiles
  for (const sea of welcome.map.decor || []) {
    if (sea.kind !== "sea") continue;
    const left = sea.x * t;
    const top = sea.y * t;
    const right = (sea.x + (sea.w || 1)) * t;
    const bottom = (sea.y + (sea.h || 1)) * t;
    const dx = Math.max(left - pos.x, 0, pos.x - right);
    const dy = Math.max(top - pos.y, 0, pos.y - bottom);
    nearest = Math.min(nearest, Math.hypot(dx, dy) / t);
  }
  return Math.min(1, Math.max(0, (BEACH_RANGE_TILES - nearest) / (BEACH_RANGE_TILES - 1)));
}

class CampusScene extends Phaser.Scene {
  constructor() {
    super("campus");
    this.sprites = new Map(); // id -> character from Render.makeCharacter()
    this.exams = new Map(); // failed exam id -> sheet from Render.makeExam()
    this.taskMarkers = new Map(); // own open task id -> glow from Render.makeTaskGlow()
    this.edgeArrows = new Map(); // own open task id -> arrow from Render.makeEdgeArrow()
    this.lastSent = { dx: 0, dy: 0 };
    // The own character, predicted in whole server ticks (see updateOwn).
    this.predicted = null; // position after the newest predicted tick
    this.previous = null; // position one tick earlier: the character is drawn between the two
    this.trail = []; // the last TRAIL_TICKS predicted positions, oldest first
    this.tickTime = 0; // seconds of frame time not yet used up by a tick
    this.drawOffset = { x: 0, y: 0 }; // how far the picture still is from the prediction
    this.minigameWasOpen = false; // the mini-game panel's open/closed state one tick ago
    this.vents = new Map(); // vent id -> hatch from Render.makeVent()
    this.ventPress = { dx: 0, dy: 0, timer: null }; // arrow keys pressed while inside a vent
    this.footstepTicks = 0; // ticks walked since the last footstep sound (spec 016)
    this.guard = null; // { sprite, cone } from Render.makeGuard(), spec 027, or null
  }

  create() {
    // The map is drawn from the server's data; the darkness covers what the own character
    // has no line of sight to. The vision radius and the tiles that block sight come from
    // the server ("welcome"), so the lit area matches what the server sends.
    const { width, height } = Render.drawMap(this, welcome.map, welcome.sight_grid);
    if (welcome.map.meeting_point) Render.makeMeetingPoint(this, welcome.map, welcome.meeting_table_radius);
    Render.makeGym(this, welcome.map); // spec 025: people working out under a skylight
    for (const vent of welcome.map.vents || []) this.vents.set(vent.id, Render.makeVent(this, welcome.map, vent));
    // Every task place of the map as an object (spec 015); own open ones get a glow below.
    for (const station of Render.taskStations(welcome.map)) Render.makeTaskPlace(this, welcome.map, station);
    this.taskRing = Render.makeTaskRing(this);
    this.darkness = Render.makeDarkness(this, welcome.map, welcome.sight_grid, welcome.vision_radius);
    this.switchMark = welcome.map.light_switch ? Render.makeSwitch(this, welcome.map) : null;

    const camera = this.cameras.main;
    camera.setBounds(0, 0, width, height);
    camera.setBackgroundColor(Render.BACKDROP);
    const fitCamera = () => camera.setZoom(Render.cameraZoom(width, height, welcome.vision_radius));
    fitCamera();
    this.scale.on("resize", fitCamera);

    this.keys = this.input.keyboard.addKeys("W,A,S,D,UP,DOWN,LEFT,RIGHT,E,R,F,V,Q,M");
    // On the key event itself, so even a very short tap counts (tryExpel checks the role).
    this.keys.E.on("down", () => tryExpel());
    this.keys.R.on("down", () => tryReport());
    this.keys.M.on("down", () => tryMeeting());
    this.keys.F.on("down", () => tryUse());
    this.keys.Q.on("down", () => trySabotage());
    this.keys.V.on("down", () => tryVent());
    // Inside a vent the walking keys choose the next vent instead (spec 015).
    const k = this.keys;
    for (const [key, dx, dy] of [[k.A, -1, 0], [k.LEFT, -1, 0], [k.D, 1, 0], [k.RIGHT, 1, 0], [k.W, 0, -1], [k.UP, 0, -1], [k.S, 0, 1], [k.DOWN, 0, 1]]) {
      key.on("down", () => this.ventKeyDown(dx, dy));
    }

    // When the tab loses focus, stop walking (otherwise the server keeps moving us).
    const stop = () => this.sendDirection(0, 0);
    window.addEventListener("blur", stop);
    document.addEventListener("visibilitychange", () => document.hidden && stop());
  }

  // A walking key went down while inside a vent: collect the keys of the next few
  // milliseconds (two together are a diagonal), then move to the vent in that direction.
  ventKeyDown(dx, dy) {
    if (!insideVent(latestState)) return;
    const press = this.ventPress;
    if (dx !== 0) press.dx = dx;
    if (dy !== 0) press.dy = dy;
    if (press.timer !== null) return;
    press.timer = setTimeout(() => {
      tryVentDirection(press.dx, press.dy);
      this.ventPress = { dx: 0, dy: 0, timer: null };
    }, VENT_KEY_WINDOW_MS);
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
    this.syncGuard(latestState.guard);
    this.updateGuard(time);
    // In a meeting everyone looks at the meeting table (spec 011).
    const table = lastPhase === "meeting" ? meetingTable() : null;
    for (const [id, sprite] of this.sprites) {
      const lookAt = table ? { x: table.x - sprite.x, y: table.y - sprite.y } : null;
      Render.animateCharacter(sprite, { ...sprite.walk, ghost: newest.ghosts.has(id), lookAt }, time);
      // Spec 028: red for an examiner's own name and the fellow examiner's, green for a
      // student's own name; every other name stays white.
      Render.setNameTone(sprite, nameTone(latestState, id));
    }
    this.frameMeeting(table, this.sprites.get(welcome.id));

    // Vents (spec 015): a hatch the server lists in `open_vents` shows open; the own
    // character is not drawn while inside, only its eyes in the vent it sits in.
    const ownVent = insideVent(latestState) ? latestState.vent : null;
    const openVents = lastPhase === "playing" ? latestState.open_vents || [] : [];
    for (const [id, hatch] of this.vents) Render.updateVent(hatch, { open: openVents.includes(id), occupied: id === ownVent }, time);
    const me = this.sprites.get(welcome.id);
    if (me) me.setVisible(!ownVent);

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

    // Tasks: a glow on the own open task places and the ring while one runs. The ring
    // moves smoothly from the time the task was first seen; the seconds are the server's.
    this.syncTaskMarkers(latestState.tasks || [], own, time);
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

  // One glow per own open task place (spec 015); a finished task (and a new round) loses
  // it. It is faint while the own character stands at it, so it does not cover the face.
  // Repositioned every frame: a multi-step task's glow must follow its current station once
  // an earlier step is done (spec 012, part 4), the only place this task entry's x/y mean.
  syncTaskMarkers(tasks, own, time) {
    const open = new Map(tasks.filter((task) => !task.done).map((task) => [task.id, task]));
    for (const [id, task] of open) {
      if (!this.taskMarkers.has(id)) this.taskMarkers.set(id, Render.makeTaskGlow(this, task));
      const marker = this.taskMarkers.get(id);
      marker.setPosition(task.x, task.y);
      const near = Boolean(own) && Math.hypot(task.x - own.x, task.y - own.y) <= welcome.task_range;
      Render.updateTaskGlow(marker, time, near);
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
        hat: playerHat(latestState, id),
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
    if (lastPhase === "ended" || lastPhase === "meeting" || minigameOpen || insideVent(latestState)) {
      // The server rejects movement now (or, for the panel, this browser stops sending it).
      // Inside a vent the walking keys choose the next vent instead (ventKeyDown).
      // Sending and predicting nothing keeps the own character where the server put it.
      this.lastSent = { dx: 0, dy: 0 };
    } else {
      ({ dx, dy } = this.readKeys());
      this.sendDirection(dx, dy);
    }
    this.previous = { ...this.predicted };
    if (dx !== 0 || dy !== 0) {
      walk(this.predicted, dx, dy);
      // Own footsteps only (spec 016): other players are drawn from the server's
      // positions in updateOthers(), never from here. A steady cadence instead of one per
      // tick, so a whole round of walking stays quiet instead of buzzing.
      this.footstepTicks++;
      if (this.footstepTicks % FOOTSTEP_TICKS === 0) Sound.play("footstep");
    } else {
      this.footstepTicks = 0;
    }
    // Sea waves (spec 017), from the own predicted position only, never another player's.
    Music.setBeach(beachCloseness(this.predicted));
    // The campus map's marker (spec 018): the own predicted position in the own colour,
    // only while the map is open and the round is on; never anyone else's.
    if (!ui.mapPanel.hidden) {
      // Spec 026: also in the lobby, to try the map before the round.
      if (lastPhase === "playing" || lastPhase === "lobby") CampusMap.setYou(this.predicted, Render.colorCss(latestState.colors[welcome.id]));
      else CampusMap.setYou(null);
    }
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
      // A player the server moved (meeting, new round) is not drawn gliding across the map.
      if (Math.hypot(b.x - a.x, b.y - a.y) > SNAP_DISTANCE_TILES * welcome.map.tile_size) a = b;
      sprite.setPosition(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f);
      // Walking direction for the animation: where they moved between the two states.
      sprite.walk = { dx: direction(b.x - a.x), dy: direction(b.y - a.y) };
    }
  }

  // Spec 027: created once state.guard first appears, destroyed once it is absent (a map
  // with no guard_route, or he is simply out of this player's own sight right now).
  syncGuard(guard) {
    if (guard && !this.guard) {
      this.guard = Render.makeGuard(this);
    } else if (!guard && this.guard) {
      this.guard.sprite.destroy();
      this.guard.cone.destroy();
      this.guard = null;
    }
  }

  // Interpolated between snapshots the same way updateOthers() already draws other players,
  // including snapping instead of gliding on a jump bigger than a tick could cover (a meeting
  // moving everyone, or the guard first coming into sight somewhere far from where he last
  // was out of it). The cone is rebuilt every frame from the server's own sight-blocking
  // edges (this.darkness.edges), the same data the player's own lit area already uses.
  updateGuard(time) {
    if (!this.guard) return;
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
    const b = newer.guard || latestState.guard;
    if (!b) return;
    let a = older.guard || b;
    if (Math.hypot(b.x - a.x, b.y - a.y) > SNAP_DISTANCE_TILES * welcome.map.tile_size) a = b;
    const span = newer.time - older.time;
    const f = span > 0 ? Phaser.Math.Clamp((renderTime - older.time) / span, 0, 1) : 1;
    const x = a.x + (b.x - a.x) * f;
    const y = a.y + (b.y - a.y) * f;
    this.guard.sprite.setPosition(x, y);
    Render.animateGuard(this.guard.sprite, b.paused, time);
    Render.drawGuardCone(this.guard.cone, this.darkness.edges, x, y, b.facing, welcome.guard_cone_degrees, welcome.guard_vision_radius);
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
