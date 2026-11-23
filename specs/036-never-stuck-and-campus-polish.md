# Spec 036 — Never stuck, smooth stopping, and campus polish

## Why
Playtest of 23 Nov (evening), Martin, Manuel and Leonard:
- Martin (the host) lost his connection while switching networks. Nobody could end the round
  or start a new one, and nobody could get back in ("Game already running"). The only way
  out was restarting the server. This must never happen again.
- Stopping sometimes pulls the character back a little.
- Some chat messages could not be sent, and nobody saw why.
- Most tasks are plain white clipboards on the floor, some lie on a name, and a few places
  look wrong (Lecture hall D's wall, the Upper Courtyard on the campus map, the NOVA sign,
  Poke House and The Cut).
Builds on spec 015 (host), 008 (prediction), 029 (chat), 009/015 (campus) and 035.

## What

### A. Nobody is ever stuck
1. **Coming back into a running round.** If a player's connection is lost during a round,
   the player stays in it, marked away (standing still). Enrolling again with the same
   nickname (any capitals) makes you that player again: same role, tasks, ghost or not.
   An older connection of that player is closed. The browser remembers the last nickname,
   so after "Connection lost" it is just reload and "Enrol". There is no password: friends
   play this game together, so the nickname is trusted.
2. **Joining late as a ghost.** Someone with a new nickname joins a running round as a
   ghost: a student without tasks, so they change no win. From there they watch and can end
   the round like everyone else. Not while a meeting runs ("A meeting is running. Try again
   in a moment."), and not when 10 players are in ("Game is full").
3. **The host can go.** If the host's connection is lost, the first player still connected
   becomes host at once. If nobody is connected any more, an empty lobby opens.
4. **Anyone in the game can end the round** (`end_round`): every player (a late ghost too), at any time during a round or
   on the end screen, takes everyone back to the lobby. Away players leave then. In the
   game it is the button "End this round for everyone" in the handbook (?) and "New round"
   on the end screen for everyone (not only the host); both need two taps.
5. `state["away"]`: the ids of the players who are away.

### B. Stopping does not jump back
When a player stops, the browser sends where it drew them standing:
`{"type": "input", "dx": 0, "dy": 0, "at": {"x", "y"}}`. The server takes that spot if it
is at most two steps away and reachable by the walking rules (no wall in between);
otherwise its own spot stays. `at` with a walking direction, or not two finite numbers,
is rejected.

### C. Chat
A message the server rejects (e.g. "Slow down", "Voting is over") is explained right
under the chat input, and the input keeps the focus after sending. The rules stay: only
living players write, and only while the vote is open.

### D. Campus polish
1. **Every task is an object, never a clipboard:** printers, ticket machine, helpdesk
   sign, projector, card gate, nata plate, a stack of trays, a surfboard, a beer stand, a
   frisbee and a free chair. (The mini-games were renamed after the list of objects was
   made, which turned most tasks into clipboards.)
2. **Names never lie on a task:** the Hall B seat moves to tile (24, 10); the "Little
   Courtyard" name moves to the top of the courtyard; the "MAIN ENTRANCE" name moves off
   the gate (`name_at` of an area).
3. **Lecture hall D:** the hedge on the wall where the passage was closed is continuous.
4. **Campus map:** the Upper Courtyard includes the green west of the CTT Student Hall
   (an `extra` rectangle of the area, also for "You are in:"); only the strip below is the
   Lower Courtyard.
5. **NOVA sign:** white block letters with a grey side, like the real sign, at the map's
   `nova_sign` spot, covering no tree, task or name.
6. **Poke House and The Cut** (not "Pokehaus"): two food counters side by side, bowls at
   Poke House, pizza and pasta at The Cut, instead of a shop.

## Out of scope
Several games at once (lobbies); the mobile map size; network lag itself (the lag seen was
one player's connection; the security guard moves smoothly elsewhere).

## Done when
- `tests/test_spec036.py` covers A–D.
- Test changes made by this spec: joining a running round is no longer rejected but a
  late ghost (`test_game.py`, `test_look.py`, `test_meeting.py`: only during a meeting,
  `test_websocket.py`); the new counter kinds in `FLOOR_KINDS`
  (`tests/test_campus.py`); "Poke House" and the seat at (24, 10) in
  `tests/test_spec035.py` and `tests/test_tasks.py`.
- All tests pass.
