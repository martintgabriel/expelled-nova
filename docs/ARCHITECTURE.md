# Architecture

This page is for the walkthrough. It shows how a key press becomes a picture on every
screen, what each file does, how the server keeps roles secret, the limits, and how the
project could grow.

## The idea in one sentence
**The server decides everything; the browser only sends what the player wants and draws
what the server sends back.** All rules are plain Python in `server/game.py`, with no
network code, so they can be tested directly.

## From a key press to the screen

```
 Browser (web/main.js)            Server (server/main.py)               Rules (server/game.py)
 ─────────────────────            ───────────────────────               ──────────────────────
 key W / joystick
   │ readKeys()
   │ sendDirection(): only when the direction changes
   ▼
 {"type":"input","dx":0,"dy":-1} ──► websocket_endpoint()
                                       RateLimiter.allow()  (30/s)
                                       parse_message()      (512 B, JSON, type, phase)
                                       game.set_input() ──────────────────► store dx, dy
                                                                            (checks first,
                                                                             changes after)
                                     game_loop(), 20 times per second:
                                       game.step() ───────────────────────► move everyone one step
                                                                            (walls, sliding),
                                                                            guard, tasks, lights,
                                                                            emergency, meeting timer
                                       for each connection:
                                         game.snapshot_for(player_id) ───► only what this
                                                                            player may know
 {"type":"state", ...} ◄──────────── ws.send_text(json)
   │ snapshots (about 1 s of history)
   │ own character: predicted locally with the same step and wall rule,
   │                corrected from the server position
   │ other players: drawn 100 ms in the past, interpolated
   ▼
 render.js draws with Phaser (map, characters, darkness); main.js updates the HTML (HUD,
 buttons, panels)
```

Every other action works the same way: the button or key sends a small JSON message
(`{"type":"expel","target":"p3"}`), `server/main.py` hands it to one method of `Game`, and
the next snapshot shows the result. A rejected action raises `GameError`; the server answers
`{"type":"error","reason":"Too far away"}` and the browser shows the reason in a toast.

## Files

| File | Responsibility |
|---|---|
| `server/main.py` | The network layer: the WebSocket `/ws` (receive, check, dispatch to `Game`), the 20 Hz `game_loop`, the welcome message, kick/leave/rejoin of connections, the routes `/healthz`, `/qr.svg`, `/taken-colors`, and the static files from `web/`. |
| `server/game.py` | All rules: `Game` (join, host, start and roles, movement, expel, vents, report, meetings and votes, chat, tasks, sabotage and fixing, win, end), message checks (`parse_message`, `validate_nickname`, `RateLimiter`) and what each player may see (`snapshot_for`). |
| `server/minigames.py` | The task mini-games: building a challenge, checking an answer, and the view a player may see. |
| `server/guard.py` | The Segway guard's route graph and movement maths. |
| `server/campus.json` | Fixed content: the 46 × 43 tile grid, areas, labels, spawn points, meeting table, light switch, sabotage places, 4 vents, 11 tasks, decor and the guard's route. |
| `web/index.html` | The page: ID card, lobby, role card, action buttons, meeting, handbook, panels. Loads the scripts in order. |
| `web/main.js` | The client: connection, prediction and interpolation, the Phaser scene, the HTML interface (lobby, buttons, meeting, chat, mini-game panel, vents, sabotage). |
| `web/render.js` | How things look: map, characters, failed exams, darkness, guard, arrows. Everything is drawn from shapes; there are no image files. |
| `web/controls.js` | The touch joystick. |
| `web/campusmap.js` | The campus map overlay (key C). |
| `web/hats.js` | The ten hats, drawn on the map and in the HTML. |
| `web/sound.js`, `web/music.js` | Generated sound effects, music and waves (Web Audio, no audio files). |
| `web/style.css` | All styling, including the phone layout. |
| `web/vendor/phaser.min.js` | Phaser 3.90.0, a pinned copy (no npm, no build step). |
| `tests/` | pytest: rules directly on `Game`, and end to end over the WebSocket with FastAPI's `TestClient`. `conftest.py` gives every test a fresh game. |

## Messages

**Browser → server** (every one is checked: at most 512 bytes, JSON object, known type,
allowed in the current phase, at most 30 per second):

| Area | Types |
|---|---|
| Joining and leaving | `join`, `leave` |
| Lobby and host | `start`, `settings`, `make_host`, `vote_host`, `kick`, `end_round`, `restart` |
| Moving | `input` |
| Examiners | `expel`, `vent_enter`, `vent_move`, `vent_leave`, `sabotage` |
| Everyone in a round | `task`, `task_input`, `task_cancel`, `fix`, `report`, `meeting` |
| Meetings | `vote`, `chat` |

**Server → browser:** `welcome` (once: own id, the map, speed, ranges, cooldowns and the
rejoin token), `state` (20 times
per second, per player), `error` (with a reason), `kicked`, `left`.

## How the server keeps roles secret
- `snapshot_for(player_id)` builds each player's own message. Only the player's own role is
  in it; examiners also get `fellow_examiners`. Other roles are sent only once the round has
  ENDED.
- A living player in a round only receives players, failed exams and the guard within their
  own line of sight (6 tiles, 1.5 for students while the lights are out).
- Ghosts are hidden from the living. Votes are hidden until they are counted. Who is inside a
  vent (except to the examiner inside), other players' tasks and cooldowns, and the guard's
  route are never sent.
- Rejected actions are checked in an order that tells a student nothing: an expel is checked
  for the sender's role before the target.

## Protection at the edges (spec 038)
- `server/main.py` refuses a WebSocket from another site's page (`Origin` must be this
  server's own address), allows at most 30 open connections, and checks the rejoin token
  when someone comes back as an away player.
- Every send in the game loop has a 1 s timeout: a browser that stops reading is treated as
  disconnected, so it can never freeze the game for the others.
- Every HTTP answer carries security headers and a Content-Security-Policy; the page has no
  inline code. The start command sets `--ws-max-size 4096`.
- In `game.py`, a stop's correction (`_settle`) is paid from a small movement budget, so no
  browser can move faster than walking.

## Data and what survives a restart
| What | Where | After a server restart |
|---|---|---|
| Map, areas, tasks, vents, sabotage places, guard route | `server/campus.json`, loaded at start | loaded again |
| Players, roles, positions, tasks, cooldowns, votes, chat, phase | `Game` in server memory | gone: the running game ends |
| Own nickname, look, sound settings, rejoin token per nickname | the browser's local storage | kept in that browser; a token is only valid in the running server |

Nothing is stored permanently: no database, no accounts, no cookies.

## Limits
- One game at a time; a server restart ends it (the free Render server also sleeps after 15
  minutes without visitors).
- A player who lost the connection comes back only from the same browser, which holds the
  rejoin token; a server restart makes every token useless (the game is gone anyway).
- Anyone in the game can end a round; the host is trusted (a kick can decide a round).
- More limits and the security findings are in [review.md](review.md).

## How it could change
- **Accounts and statistics (BRD roadmap F6, Supabase):** a small storage layer called at
  the end of a round (`Game._end`) would save results; the rules in `game.py` stay as they are.
- **Parallel games with room codes (F8):** `server/main.py` would keep a dict of `Game`
  objects by room code instead of one `game`, and each connection would belong to one room.
  `Game` itself needs no change, because it already holds everything about one game.
- **A new rule:** a new method or check in `game.py`, a test in `tests/` that shows it
  failing first, then one line in the dispatch in `server/main.py` and a button in `main.js`.
