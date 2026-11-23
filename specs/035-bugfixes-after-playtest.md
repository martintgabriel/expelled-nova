# Spec 035 — Playtest of 23 Nov: bugfixes, campus names and new west-side games

## Why
Leonard played the merged game (specs 023–033) on 23 Nov (afternoon) and found bugs, wrong
or missing place names, a too open west side, and too few reasons to go west. Builds on specs
008/033 (lights), 009/015 (campus), 012 (mini-games), 017 (sea waves), 018/026 (campus map),
021 (tray, surf), 023 (sabotage menu), 027 (security guard) and 031 (seagull flight engine).

## What

### A. Bugfixes
1. **"Fix router", not "fix lights".** While the Wi-Fi is down the action's label (the USE
   slot, the controls bar and the button's title) says "Restart router"/"router", never
   "lights".
2. **The router lights up** on the map in the game while the Wi-Fi is down, exactly like the
   flashing bolt over the light switch while the lights are off.
3. **A real action instead of only waiting.** Pressing "use" (F) at the switch or the router
   opens a small panel first:
   - lights: drag the lever up to the top;
   - router: pull the plug out of the router, then push it back in.
   Only when the action is done does the browser send `fix`; the server's rules and the
   3 seconds of spec 008/033 stay exactly as they are (the server cannot see a drag; like
   every mini-game, the server stays the judge of the rest).
4. **Fire alarm: everyone goes to the assembly point.**
   - The banner counts every living player: "Evacuated 3/5".
   - The alarm is over as soon as every living student is in, as before: examiners who stay
     away do not make the examiners win.
   - But when the alarm ends, everyone sees who did not come, for 8 seconds:
     "Not at the assembly point: Cy". Staying away gives an examiner away; going there costs
     time. `state["fire_missing"]`: the ids, while it shows.
   - If the time runs out before every living student is in, the examiners win (unchanged).
5. **Security guard:** a bigger view (6 tiles instead of 4, a 100° cone instead of 70°) and
   a little slower (1.3× a player's speed instead of 1.6×), so players can see him coming.
   His random route stays.
6. **Sea waves in the lobby too:** the waves play in the lobby like in a round (still
   louder the closer to the beach), and quietly anywhere in the lobby.
7. **Cafeteria tray: a real tray.** The items are dragged onto a drawn tray (main course,
   soup, drink, dessert), then "Pay" is pressed. The order and the rules on the server are
   unchanged (spec 021); a tap on an item still works on phones as a fallback.

### B. Campus names, the NOVA sign and a more winding west side
1. **Names**
   - The area "Food Court" is called **"Cafeteria"** (that is what students call it). Inside
     it, the left counter is labelled **"Pokehaus"** and the right one **"The Cut"** (they
     replace the labels "Shop" and "Cafeteria").
   - The small green between Lecture hall D, Hall E and the beach gets the label
     **"Little Courtyard"** (tiles x 7–14, y 32–35).
2. **The campus map shows the green.** The grass of the courtyards is drawn on the campus map
   in green (like the sea and the sand already are), so the Upper Courtyard reaches down to
   the Lower Courtyard on the map as it does in the game, next to the CTT Student Hall.
3. **The NOVA sign:** big letters "NOVA" stand in the Main Entrance next to the welcome desk,
   drawn by `Render.makeNovaSign()` from the "Welcome desk" label (no new map data), under the
   players.
4. **A more winding west side:** the two short passages between the courtyards and the
   lecture halls are closed: Upper Courtyard ↔ Lecture hall B (tiles 9–10, row 13) and Lower
   Courtyard ↔ Lecture hall D (tiles 9–10, row 25). Both halls are still reachable from the
   beach and from Hall B / Hall D. The guard's route loses the two connections that drove
   through them (west-vent – upper-courtyard, lower-courtyard – west-south); his graph stays
   connected.

### C. Three new tasks on the west side, surfing moves up
1. **Surfing moves** to the top of the beach (tile 3, 10). The game itself is unchanged.
2. **`beer`: "Chug a beer at Carcavelos"** (Beach, bottom: tile 3, 33). Tap "Sip!" fast:
   8 sips empty a beer, 3 beers finish the task. A pause of more than 1.5 s lets the beer
   go warm: that beer starts again ("Too slow. It got warm."). Value: `true`; the server's
   own tick measures the pauses. 20 s; time-out note "Last call. The bar closed."
3. **`frisbee`: "Catch the frisbee in the Little Courtyard"** (tile 10, 34). Five frisbees fly
   in from all sides, one after another, faster each time (spec 031's flight plan with its
   own numbers). Tap one while it is in the air to catch it; 3 catches finish the task,
   3 drops ("You dropped too many.") end it. 15 s; time-out note "The others went to class."
4. **`seat`: "Find a free seat in Hall B"** (tile 16, 10). Twelve seats, all taken but one;
   the free one changes every 1.5 s (its order is fixed when the game starts). Tap the free
   seat 3 times (three lectures). A taken seat: "Taken. Awkward." and the count stays.
   Value: the seat (0–11); the server's tick decides which seat is free. 20 s; time-out note
   "The lecture started without you."
5. Hall B and the Little Courtyard are named places on the map, not areas: a station there
   names its place like the beach's (spec 021).

## Out of scope
Changing how long a fix takes; new sabotages; new areas for the halls; changing any existing
mini-game; more than three new tasks.

## Done when
- `tests/test_spec035.py` covers: the fire alarm counting and the missing list (server), the
  client wiring of the router label/mark, the lever/plug panel, the lobby waves, the tray and
  the guard constants; the names, the closed passages, the guard route, the green on the map
  and the NOVA sign; each new task kind (making, right and wrong answers, invalid values,
  time-out notes, the views) and the campus places.
- Test changes made by this spec:
  - `tests/test_spec023.py`: the fire alarm test expects `"total"` (living players) instead
    of `"students"`.
  - `tests/test_spec027.py`: the guard in `test_seen_by_guard_requires_range_angle_and_a_clear_line`
    moves from tile (5, 3) to (2, 3) (with the bigger view the old point lay inside a wall).
  - "Food Court" → "Cafeteria" in `test_campus.py`, `test_game.py`, `test_spec015.py`,
    `test_spec021.py`, `test_tasks.py`.
  - `tests/test_spec011.py`: the two closed passages leave the doorway list.
  - `tests/test_tasks.py`: `SPEC_TASKS` 8 → 11 tasks, surf's new place, and the station-area
    rule (a named place like the beach); `tests/test_spec015.py`: place counts;
    `tests/test_spec021.py`: surf's place.
- All tests pass.
