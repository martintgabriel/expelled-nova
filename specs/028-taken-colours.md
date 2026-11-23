# Spec 028 — Taken colours show on the ID card

## Why
Since spec 022 players pick a colour on the ID card, but they only learn that it is taken
when "Enrol" is rejected. Team feedback, 23 Nov: colours other players already have should
be crossed out in the picker.

## What
- **`GET /colors`** answers `{"taken": [numbers]}`: the colour numbers of the players in
  the game right now, sorted. Nothing else: no names, no ids, no roles, so it tells a
  stranger nothing they could not see in the lobby. It takes no input (query parameters
  are ignored).
- **On the ID card** the client asks for it when the page opens and every 2 seconds while
  the ID card is shown. Taken swatches are crossed out and cannot be picked. If the
  player's own pick gets taken meanwhile, the pick goes back to "Any" with a short note.
- The server still checks the colour on "join" (spec 022): the list is a convenience, not
  the rule. A failed request simply leaves every swatch pickable.

## Out of scope
Pushing the list without asking (a WebSocket before joining).

## Done when
- `tests/test_spec028.py` covers the endpoint (empty, after joins, after a leave, query
  parameters ignored, nothing but numbers) and the client wiring.
- All tests pass.
