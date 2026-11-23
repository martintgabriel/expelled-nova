# Expelled!

A live 2D multiplayer social-deduction game on the Nova SBE campus: students finish their
errands while undercover examiners try to get them expelled.

## Live app

https://expelled-nova.onrender.com

Note: the app runs on a free server that sleeps after 15 minutes without visitors. The first
visit after that takes about a minute while it wakes up.

## How a round works

1. The host opens the link and shares it (or the QR code in the lobby). 4–10 players fill
   in an ID card: nickname, hat and colour.
2. The host starts. Everyone secretly learns their role: student or undercover examiner
   (1 examiner with 4–6 players, 2 with 7–10).
3. Students walk the campus and solve 5–7 mini-game errands. Examiners blend in, hand out
   failed exams (6/20), use the vents and set off sabotages.
4. A found exam, the meeting button or the security guard calls a meeting: everyone chats
   and votes, and the player with the most votes is sent surfing.
5. Students win when all tasks are done or every examiner is voted out. Examiners win when
   they are as many as the students, or when the fire alarm runs out.

## Main features

- Live movement for 4–10 players, with line-of-sight vision and walls
- Secret roles, decided and kept on the server
- 11 campus tasks with 12 mini-game kinds, and fake tasks for examiners
- Expelling, ghosts, 4 vents and a Segway security guard
- Sabotage: lights out, fire alarm, Wi-Fi down
- Meetings with chat, votes and ballots
- Host tools: settings, hand over, kick, host vote; leave and come back after a lost connection
- Phone play: touch joystick and QR-code join; campus map; generated sound and music

## Team

| Name | Student number | GitHub |
|---|---|---|
| Martin Gabriel | 78518 | martintgabriel |
| Cornelius Paprottka | 78283 | cpaprottka |
| Leonard Kowall | 78697 | leonardk-hue |
| Manuel Ritter | 78936 | manuelritter78936 |

## Run locally

Requires [uv](https://docs.astral.sh/uv/). Install the dependencies:

```bash
uv sync
```

Run the app, then open http://localhost:8000:

```bash
uv run uvicorn server.main:app --reload
```

## Tests

```bash
uv run pytest
```

The tests are in `tests/`: the rules are tested directly on `Game`, and whole workflows over
the real WebSocket with FastAPI's `TestClient`. There is one file per spec (`test_specNNN.py`).

## How it works

- **The server decides everything.** The browser only sends inputs ("walk up", "expel p3")
  and draws what the server sends back.
- **`server/game.py`** holds all rules as plain Python without network code: joining, roles,
  movement, expelling, vents, meetings and votes, chat, tasks, sabotage, winning. It also
  builds each player's own view (`snapshot_for`).
- **`server/minigames.py`** holds the task mini-games and **`server/guard.py`** the
  security guard's route and movement.
- **`server/main.py`** is the network layer. It receives WebSocket messages, checks them,
  hands each to one `Game` method, and sends every player their own state 20 times per
  second. It also serves the page, the QR code and the health check.
- **`web/`** is one static page with no build step: `index.html`, `main.js` (connection
  and interface), `render.js` (drawing with Phaser), a few small helpers (`controls.js`,
  `campusmap.js`, `hats.js`, `sound.js`, `music.js`) and `style.css`.

More in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Data and privacy

- **Loaded at start:** the fixed content (map, tasks, vents, sabotage places, guard route)
  comes from `server/campus.json`.
- **In memory only:** players, roles, positions, tasks, votes, chat and the game phase live
  only in the server's memory. A server restart ends a running game.
- **Nothing permanent:** no database, no accounts, no cookies. A nickname exists only for
  one session. The browser remembers the own nickname, look and sound settings locally.

## Security measures

- The server decides every position and action; roles are sent only to their owner
  (examiners see fellow examiners) until the round ends.
- Every message is checked: at most 512 bytes, valid JSON, a known type, allowed in the
  current phase and for this player (host-only actions included).
- A rejected action changes nothing and returns a short reason.
- Rate limit: 30 messages per second per connection.
- Nicknames are 1–16 letters, digits or spaces; chat messages are 1–80 characters with no
  control characters. Both are always shown as text, never as HTML.
- The QR code ignores any input. Dependencies are pinned (`pyproject.toml`, `uv.lock`,
  `web/vendor`). No secrets are in the repository.

## Limits

- One game at a time; a server restart ends it.
- A player who lost the connection comes back with the nickname alone (no password).
- Anyone in the game can end a round, and the host is trusted (a kick can decide a round).
- The open findings of the review are in [docs/review.md](docs/review.md).

## Project structure

```
expelled-nova/
├── server/
│   ├── main.py          network: WebSocket, 20 Hz loop, routes
│   ├── game.py          all game rules
│   ├── minigames.py     task mini-games
│   ├── guard.py         security guard
│   └── campus.json      the campus map and its content
├── web/
│   ├── index.html       the page
│   ├── main.js          client: connection and interface
│   ├── render.js        drawing (Phaser)
│   ├── controls.js, campusmap.js, hats.js, sound.js, music.js
│   ├── style.css
│   └── vendor/          Phaser 3.90.0 (pinned copy)
├── tests/               pytest, one file per spec
├── specs/               one spec per change
└── docs/                BRD, architecture, review
```

## Docs

- [Architecture](docs/ARCHITECTURE.md): how it is built, for the walkthrough
- [Business requirements (BRD)](docs/brd.md)
- [Specs](specs/README.md): one spec per change, with an index
- [Manual test checklist](docs/manual-test-checklist.md) (follows in spec 038, part 3)
- [Walkthrough and exam preparation](docs/walkthrough.md) (follows in spec 038, part 6)
- [Review](docs/review.md): the audit from spec 038
