# Spec 031 — Shoo the seagulls off your pastel de nata

## Why
Playtest, 23 Nov: "Eat your pastel de nata in the sun" (tap the seagull in a 3×3 grid five
times) is boring. Wanted: you hold your pastel and seagulls keep swooping in from all
sides; you fend them off with the mouse (or a finger). Builds on spec 012 (mini-games).

## What
A new mini-game kind `nata` in `server/minigames.py` replaces `seagull` on the campus. The
old kind stays in the engine, since test maps still use it.

- **The flight plan:** 8 seagulls; seagull *i* takes off `NATA_FIRST + i * NATA_GAP` ticks
  after the start, from one of 8 directions (random), and needs `NATA_FLY - i * 2` ticks to
  reach the pastel, so they get faster. All of it is decided when the challenge is made.
- **Shoo:** the value is the seagull's number (0–7). It counts only while that seagull is
  in the air (taken off, not yet arrived, not shooed yet); any other tap changes nothing.
- **Done:** 6 seagulls shooed.
- **Fail:** a seagull that reaches the pastel takes a bite; at 2 bites the pastel is gone,
  the challenge ends with "A seagull took your pastel." and the task can be started again.
  This is checked every tick (`minigames.failure`), like the time limit.
- Time limit 15 s (the last seagull lands after about 11 s); time-out note "Too slow. The
  seagulls won.".
- **What the player sees:** the whole flight plan, which seagulls are shooed, the bites and
  how many ticks have passed. Nothing is secret: the client only animates it.

## Out of scope
More seagulls with more players, other birds.

## Done when
- `tests/test_spec031.py` covers the plan, shooing in and out of the air, the win, the
  2-bite fail through the game loop, invalid values, the view and the campus task.
- This spec changes `SPEC_TASKS` in `tests/test_tasks.py` ("nata": seagull → nata).
- All tests pass; locally the seagulls fly in and can be shooed.
