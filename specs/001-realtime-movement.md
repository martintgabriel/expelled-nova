# Spec 001 — Live movement on the campus map (foundation)

## Why
The whole game depends on several players moving live on one map. We prove this first, on the deployed URL, before any game rules are built. Team decision point: Monday 16 November, evening.

## What
- Project skeleton as described in AGENTS.md: `server/` (FastAPI), `web/` (static page with a pinned Phaser copy), `tests/`, `pyproject.toml` with pinned dependencies.
- A first campus map, top-down, drawn with our own simple shapes: about six areas connected by corridors (Main Entrance, Library, Food Court, Auditorium, Student Services, Courtyard), with walls. The map is stored as data (e.g. a JSON grid), not hard-coded in the drawing code.
- Join: open the URL, enter a nickname (1–16 characters: letters, digits, spaces; unique in the game) and join the one shared game. At most 10 players.
- Movement: WASD or arrow keys. The client sends only its input direction. The server moves players at a fixed speed, blocks walls and broadcasts positions about 20 times per second. The own character feels immediate (the client may predict, the server position wins); other players move smoothly between updates.
- Leaving: a player who closes the tab disappears for the others within 2 seconds.
- Deployment: prepared for a free web service on Render; the agent lists every setting to enter on render.com.

## Out of scope
Roles, tasks, expelling, meetings, voting, host, room codes, accounts, database, phone controls, sound, final graphics. `README.md` (Martin updates it in a separate pull request).

## Done when
- Tests for `server/game.py`, written first and red before the implementation:
  - movement at a fixed speed; diagonal movement is not faster;
  - moving into a wall is rejected and leaves the position unchanged;
  - an invalid input message is rejected without any state change;
  - nickname validation: empty, too long, invalid characters, duplicate;
  - an 11th player is rejected;
  - a disconnect removes the player.
- One WebSocket test with two clients: client A moves, client B receives A's new position.
- `uv run pytest` passes; the output is pasted.
- Manual check: two browser windows locally, then two devices on the deployed URL (one on mobile data) see each other move smoothly.
