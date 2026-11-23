# Spec 022 — Hats and a colour of your own

## Why
The playtest asked for a bit of personality before joining: everyone is the same figure
with the same graduation cap and a colour handed out by the server. Picking a hat and a
colour on the ID card makes players easy to tell apart and is simply fun. Builds on specs
002 (joining, colours) and 014/015 (the character and the ID card).

## What
1. **Join with a look:** `{"type": "join", "name": ..., "hat": H, "color": C}`.
   - `hat`: a whole number 0–9 (`HAT_COUNT` = 10); missing means 0, the graduation cap.
   - `color`: a whole number 0–9 or `null`/missing for "any free colour" (as before). A
     colour someone in the game already has is rejected ("Colour is already taken").
   - Anything else (wrong type, out of range, booleans) is rejected with a reason and the
     player does not join.
2. **Everyone sees the hats:** every snapshot carries `"hats": {player_id: H}` for the same
   players as `"colors"`.
3. **Ten original hats**, drawn from one shared definition in `web/hats.js` both on the
   map (Phaser) and in the small SVG figures (lobby, meeting, end screen): graduation cap,
   beanie, top hat, cowboy hat, crown, party hat, chef's hat, baseball cap, beret and a
   laurel wreath.
4. **ID card:** arrows to flip through the hats with a live preview of the figure, and a
   row of colour swatches with "Any" first.

## Out of scope
Changing the look after joining, extra accessories or symbols on the body.

## Done when
- New tests in `tests/test_spec022.py` cover joining with and without a look, every
  rejected value, a taken colour, the hats in snapshots and the WebSocket join.
- This spec replaces the spec 005 test that said a client cannot pick its own colour
  (`tests/test_look.py`): it now checks that a picked colour is used and stays unique.
- All tests pass; locally four tabs with different hats and colours show them on the map,
  in the lobby and in a meeting.
