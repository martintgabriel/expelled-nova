# Spec 002 — Lobby, host and secret roles

## Why
Before expelling, tasks or meetings can be built, the game needs a start and secret roles. Secret roles are also our main security story: a browser must never learn another player's role (BRD R2, acceptance A3).

## What
- **Game phases** in `server/game.py`: `lobby` (before the start; players join and walk around as now) and `playing`. Later specs add `meeting` and `ended`.
- **Host:** the player who has been in the game longest. If the host leaves, the next-longest player becomes host. Every player can see who the host is.
- **Start:** the host sends `{"type": "start"}`. It is accepted only from the host, only in `lobby` and only with at least 4 players (`MIN_PLAYERS = 4`). Otherwise it is rejected with a short reason and nothing changes.
- **Roles at the start:** 1 examiner with 4–6 players, 2 with 7–10; everyone else is a student. Chosen at random. `Game` accepts an optional random generator so tests can fix the outcome.
- **Joining while `playing`** is rejected ("Game already running").
- **One snapshot per player:** replace the shared snapshot with `snapshot_for(player_id)`. It contains the phase, the host id, the player's own role and, for an examiner, the ids of the fellow examiners. No snapshot ever contains another player's role. `server/main.py` sends each player their own snapshot every tick.
- **Browser:** a lobby panel lists the players and marks the host. The host sees a "Start game" button; below 4 players it is disabled with "Need at least 4 players". At the start, a role screen shows for 3 seconds ("You are a Student" / "You are an Undercover Examiner", plus the fellow examiners), then the role stays visible in a corner.

## Out of scope
Expelling, tasks, meetings, voting, winning, a new round, staff doors. Map and graphics change in parallel in spec 005: in `web/`, only touch what the lobby and role screens need.

## Done when
- Tests for `server/game.py`, written first and red before the implementation:
  - the host starts with 4 players → phase `playing`, exactly 1 examiner; with 7 and with 10 players → 2 examiners;
  - start is rejected from a non-host, with 3 players, and a second time while `playing`; each rejection leaves phase and roles unchanged;
  - joining while `playing` is rejected;
  - the host role passes on when the host leaves, in the lobby and while playing;
  - a student's snapshot contains no role of any other player; an examiner's snapshot (7+ players) lists the fellow examiner and no student roles.
- One WebSocket test with 4 clients: the host starts; every client receives its own role and nobody else's.
- `uv run pytest` passes; the output is pasted. Existing tests still pass unchanged.
- Manual check with 4 browser windows locally: only the host sees the start button; each window shows its own role.
