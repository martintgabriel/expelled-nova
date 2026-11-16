# Spec 007: Phone controls, QR-code join and test follow-ups from spec 001

## Why
In the demo the examiners should play along on their own phones. Today the game only works with a keyboard, and a guest has to type the URL by hand. A phone needs touch controls, and joining should take one scan of a QR code shown on the host's screen. This is roadmap item F2 ("needed for the demo") and supports BRD EX01, EX02 and acceptance A1 (one device on mobile data).

The review of spec 001 (PR #1) also listed missing tests. They are added here, so the test suite matches what the course grades under "Verification".

## What

### 1. QR-code join
- **Invite URL:** the URL the QR code points to. The server takes it from the environment variable `RENDER_EXTERNAL_URL` (set automatically by Render for every web service, e.g. `https://expelled-nova.onrender.com`). If it is not set (local run), it uses the base URL of the request (e.g. `http://192.168.1.20:8000/` when a phone on the same Wi-Fi opens the laptop's address). The URL always ends with exactly one `/`. A small helper `invite_url(env_url, base_url)` in `server/main.py` decides this, so it can be tested directly.
- **Endpoint `GET /qr.svg`:** returns the invite URL as a QR code in SVG (`image/svg+xml`), black on white, with the standard quiet zone of 4 modules, so phone cameras read it reliably. It takes no input: query parameters are ignored, so nobody can make the game show a QR code for another site. Other methods (e.g. POST) are rejected by FastAPI with 405. Matched before the static files, like `/ws` and `/healthz`.
- **Dependency:** `segno==1.6.6` (pinned) builds the QR code. Why: a QR encoder is too complex to write ourselves, and segno is pure Python with no dependencies of its own. It is added with `uv add segno==1.6.6`, so `pyproject.toml` and `uv.lock` change. The server decides what the QR code contains; the browser only shows the image.
- **Browser:** in the lobby panel, every player sees an "Invite players" button. It opens a large overlay with the QR code (`<img src="/qr.svg">`, at least 240 × 240 px and never wider than the screen), the URL as text below it, the line "Scan to join · max 10 players" and a "Close" button. On a laptop connected to a projector the whole room can scan it. The button and the overlay exist only in phase `lobby`; when the host starts the game, an open overlay closes.
- **Joining by QR uses the existing rules:** the QR code opens the normal join screen. A full game ("Game is full (10 players)") and a running game ("Game already running") are rejected with the existing messages. Nothing about joining changes on the server.

### 2. Phone controls
- **Touch joystick:** on devices whose main pointer is a finger (`matchMedia("(pointer: coarse)")`), a round joystick is shown at the bottom left (about 120 px wide, half-transparent, drawn with HTML/CSS, no images). The player drags the knob with the thumb:
  - the drag direction is snapped to the nearest of 8 directions (45° each) and turned into the same `{"type": "input", "dx", "dy"}` message the keyboard sends. The server and the message format do not change;
  - inside a dead zone (less than 25 % of the radius from the centre) the direction is `(0, 0)`;
  - lifting the finger, a cancelled touch (e.g. an incoming call), the tab losing focus or the screen locking sends `(0, 0)`, so nobody keeps walking;
  - a new direction is sent only when it changes, and at most once every 50 ms (one server tick). The newest direction is always sent at the end of such a pause. So even fast thumb wiggling stays far below the rate limit of 30 messages per second.
- **Keyboard still works:** on a laptop nothing changes and no joystick is shown. If a device has both, a held joystick wins over the keys.
- **Multi-touch:** the joystick and the buttons use pointer events and track each finger separately, so a player can hold the joystick and tap "Expel" at the same time.
- **Action buttons:** "Expel" moves into a fixed action bar at the bottom right (`<div id="actions">`). On touch devices each button is at least 56 px high, and key hints like "(E)" are hidden. Specs 004 and 006 put their buttons ("Use", "Report", "Ring the bell") into the same bar.
- **No page scrolling or zooming during play:** a drag or pinch on the game area or the joystick does not scroll, zoom or select text (CSS `touch-action: none`, `user-select: none`, `overscroll-behavior: none` on the game). Buttons use `touch-action: manipulation`, so a double tap does not zoom. Text inputs keep a font size of at least 16 px, so iOS does not zoom in when typing the nickname.
- **Small screens:** works in portrait and landscape from 360 px width. Lobby panel, role badge, toasts and banners never cover the joystick or the action bar. Content stays clear of the notch and home bar (`viewport-fit=cover` plus `env(safe-area-inset-*)`).
- **Hints:** on touch devices the join screen and the HUD say "Drag the joystick to move" instead of "WASD / arrow keys to move".
- **Code location:** the joystick lives in a new file `web/controls.js` (loaded before `main.js`). It offers one function that returns the current joystick direction (or `null` when not held). `main.js` only combines it with the keys in `readKeys()` and calls the throttled send. This keeps the overlap with spec 005 (`web/render.js`) and spec 006 small.

### 3. Test follow-ups from the review of spec 001
- **Map connectivity (flood fill):** a test proves that every spawn point and at least one floor tile of every area can be reached from the first spawn point. It walks the floor tiles (4 neighbours) and checks each tile centre with `Game.blocked()`, so it also holds for the real campus map later. A second test runs the same check on a small handmade map with a walled-off room and expects it to fail, so we know the check really detects a closed area.
- **WebSocket: 11th client:** ten clients join, the 11th gets an error with "Game is full"; after one player leaves, a new client can join.
- **WebSocket: invalid input leaves the position unchanged:** a joined client sends invalid inputs (`dx: 2`, `dx: "1"`, `dx: true`, missing `dy`). Each gets an error, and the player's position in the following states stays the same. A valid input afterwards still moves the player.
- **Each WebSocket test uses its own game:** a new `tests/conftest.py` gives every WebSocket test a fresh `Game` and an empty connection list (replacing `server.main.game` and `server.main.connections`). The existing expel test in `tests/test_websocket.py` is changed to use this game instead of the module-level `game` import. This is the only change to an existing test.

## Out of scope
- The buttons and screens of other specs: tasks ("Use", spec 004), report, bell and vote buttons (spec 006). Spec 007 only provides the action bar and the touch rules they follow.
- Look, characters, area display and vision radius (spec 005, `web/render.js`); the real campus map.
- Room codes and parallel games (F8), a projector/spectator view (F9), sound and vibration, installing as an app (PWA), a native app.
- Any change to game rules, message formats or the rate limit.
- `README.md` and `docs/decisions.md` (the rate-limit note from the 001 review is Martin's follow-up).

## Done when
- Tests, written first and red before the implementation:
  - **Invite URL and QR code:**
    - `invite_url`: with `https://expelled-nova.onrender.com` → `https://expelled-nova.onrender.com/`; a trailing `/` is not doubled; without an env value → the request base URL; an empty env value counts as not set;
    - `GET /qr.svg` → 200, content type `image/svg+xml`, and the body equals segno's SVG for the expected invite URL (same settings), both with `RENDER_EXTERNAL_URL` set (via `monkeypatch`) and without (`http://testserver/`);
    - rejected and edge cases: `GET /qr.svg?url=https://evil.example` still encodes the game's invite URL; `POST /qr.svg` → 405;
    - the page loads `controls.js`, and `GET /controls.js` → 200.
  - **Joining by QR while a game runs (WebSocket):** with 4 clients in `playing`, a 5th client's join gets "Game already running", and the other clients' states still list 4 players.
  - **Review follow-ups:** the flood-fill tests (campus map reachable; handmade map with a closed room detected), the 11th-client test, the invalid-input test and the fresh-game fixture as described above.
- `uv run pytest` passes; the output is pasted. All existing tests still pass; only the expel test in `tests/test_websocket.py` is changed, to use the fresh game.
- `segno==1.6.6` is pinned in `pyproject.toml` and `uv.lock`; no other new dependency.
- Manual check:
  - **Laptop:** keyboard movement as before, no joystick visible; "Invite players" shows a QR code and the URL in the lobby only.
  - **Phones, before the pull request** (one iPhone with Safari, one Android with Chrome, on the same Wi-Fi as the laptop running `uv run uvicorn server.main:app --host 0.0.0.0`):
    - scanning the QR code from the laptop screen opens the join screen, and joining works;
    - the joystick moves the player in all 8 directions; lifting the thumb stops at once;
    - locking the screen stops the player;
    - while dragging or pinching, the page does not scroll or zoom;
    - portrait and landscape both work;
    - an examiner can hold the joystick and tap "Expel" at the same time.
  - **Full game:** with 10 players in the lobby, an 11th phone that scans the code sees "Game is full (10 players)".
  - **After the merge, on the Render URL:** the same phone checks once more, with at least one phone on mobile data.
