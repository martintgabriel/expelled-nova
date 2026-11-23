# Spec 021 — Two new tasks: Cafeteria tray and Beach surfing

## Why
With spec 019, 8–10 players each get 5 tasks, but the campus had only 6 tasks, so everyone
did almost the same ones. The playtest asked for a task in the Cafeteria and one on the
beach. Builds on spec 012 (mini-games) and spec 015 (the beach).

## What
Two new mini-game kinds in `server/minigames.py`, each with a time limit, a time-out note,
validation, answer checking and a public view, and two new tasks in `server/campus.json`:

1. **`tray`: "Fill your tray at the Cafeteria"** (Food Court, tile 41, 12). Like the real
   Nova cafeteria line: tap Main course → Soup → Drink → Dessert → Pay, in this order. The
   five buttons are shuffled. A wrong tap starts the line again with a new shuffle and the
   note "Wrong order. Back of the queue." Value: the index of the tapped button (0–4).
   Time limit 30 s; time-out note "The cafeteria closed."
2. **`surf`: "Catch a wave at Carcavelos"** (Beach, tile 3, 19). A wave rolls in every 2 s;
   press "Stand up!" while the crest is under the board (a half-second window). Ride 3
   waves in a row to finish; a press at the wrong moment is a wipeout ("Wipeout! Paddle
   back out.") and the count starts again. Like the ticket game the value is always `true`
   and the server's own tick decides. Time limit 25 s; time-out note "The waves are gone.
   Flat sea."

Nothing is secret in either game (the tray order is printed on the panel, the wave is
visible), so the public view shows the whole challenge; for `surf` it carries the wave's
current phase so the client can draw it. The client draws both in the existing mini-game panel.

## Out of scope
Replacing the paper-jam and seagull games, a longer helpdesk conversation (later specs).

## Done when
- New tests in `tests/test_spec021.py` cover building, accepted and rejected answers,
  invalid values, the time-outs and both tasks on the campus.
- This spec changes existing tests that listed or counted the campus tasks: `SPEC_TASKS`
  and 6 → 8 tasks (`tests/test_tasks.py`), the station list and place count
  (`tests/test_spec015.py`), the seed of two WebSocket tests that relied on how 6 tasks
  were dealt (seed 1 → 4, same roles and first task), and the station-area check, since the
  beach is sand and not an area (spec 015).
- All tests pass; locally both tasks can be played to the end.

## Changes after the merge
- Bug fix (23 Nov): the surf panel's sea had no width of its own and shrank to 0 px inside
  the centred mini-game panel, so the wave could not be seen. It now takes the panel's
  full width (`tests/test_spec021.py::test_the_surf_sea_takes_the_panel_width`).
