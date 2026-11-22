# Spec 013: Every match starts in the Main Entrance

This spec describes what was built. See "Changes during implementation".

## Why
In the lobby players walk around the whole campus while they wait. When the host started the match, `start()` dealt roles and tasks but left everyone where they stood, so a round began with players spread over the map. A match should start like a real one: everyone together in the Main Entrance, so nobody has an advantage and the first minutes feel the same for all. Builds on spec 002 (lobby, start) and spec 009 (campus map and spawn points).

## What
- **Spawn at start (server):** when `start()` succeeds, every player is placed on a spawn point from `campus.json` `"spawns"`. All spawn points lie in the Main Entrance. Players are placed in join order, each on a different spawn point (10 spawn points for at most 10 players).
- **No walking on:** each player's movement input is cleared (`dx = dy = 0`), so a key held in the lobby does not keep them walking.
- **One helper:** `_place_on_spawns()` in `server/game.py` does this for both `start()` and `_reset_round()` (new round), instead of two copies of the same code.
- **Rejected start:** a start that is rejected (not the host, too few players, game already running) changes no positions.
- **Browser:** no change needed. The own character already jumps to the server position when it is more than 2 tiles away (`SNAP_DISTANCE_TILES` in `web/main.js`), so it does not glide across the map.

## Out of scope
- New or moved spawn points, other start areas, random spawn order.
- Anything else about the lobby, roles, tasks or movement.

## Done when
- Tests in `tests/test_spec013.py`:
  - after start every player stands on the centre of a spawn tile, all on different tiles, each tile in the area "Main Entrance";
  - this holds with 4 and with 10 players;
  - `dx` and `dy` are 0 for everyone after start;
  - a rejected start does not move anyone;
  - after a finished round, restart, walking in the lobby and a new start, everyone is in the Main Entrance again.
- `uv run pytest` passes on main (880 passed).
- Manual check: players spread out in the lobby; after start all of them stand in the Main Entrance at once.

## Changes during implementation
- The code and tests for this spec were merged together with PR #17 (fix for the server side of the projector cable mini-game) by mistake. This spec documents the change afterwards; no code is changed by it.
