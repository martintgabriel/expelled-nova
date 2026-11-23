# Spec 026 — A colourful campus map, and saying it exists

## Why
Playtest feedback on the campus map of spec 018: nobody knew it was there (only the
handbook mentions C), the grey base map looks dull, and in the lobby you cannot see
yourself on it. Builds on spec 018 (campus map) and spec 008 (controls pictograms).

## What
1. **Tell players about it:** the ID card says "Walk with WASD or the arrow keys, open the
   campus map with C.", and the controls bar shows a `C map` keycap next to "move"
   (keyboard only, like the other keycaps).
2. **Colour:** the base map uses colours like the game world: a warm floor, dark walls,
   a blue sea, yellow sand, and every area in its own colour from `campus.json`
   (`area.color`, see-through, with an outline in the same colour). The own marker and the
   own task markers stay as they are and still stand out (white ring, green circles).
3. **Dark when it is dark:** while the lights are off for a living student (the same
   moment the game world goes dark), the map gets the class `dark` and is shown dimmed.
   `CampusMap.setDark(on)` switches it; nothing else changes.
4. **You are here, also in the lobby:** the own marker now also shows in the lobby, so
   players can try the map before the round. Still only the own position and colour,
   never anyone else's.

The own open tasks were already on the map (numbered markers and the list below it,
spec 018); that stays.

## Out of scope
Other players on the map, a mini-map in the corner.

## Done when
- `tests/test_spec026.py` checks the hints, the colour constants, `setDark` and that the
  marker shows in the lobby.
- This spec replaces the spec 018 test that required a grey map
  (`test_the_base_map_is_grey_and_does_not_use_the_area_colours` in
  `tests/test_spec018.py`) with one that requires the colours above.
- All tests pass.
