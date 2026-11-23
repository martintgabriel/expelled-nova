# Spec 023 — Sabotage menu: lights, fire alarm, Wi-Fi down

## Why
Playtest and team brainstorm, 23 Nov: the examiners have exactly one sabotage (lights off,
spec 008), so every sabotage looks the same and students always know where to run. In the
original genre, sabotage opens the map and the impostor picks one of several emergencies.
Wanted: the lights (Student Services) as before, a fire alarm where everyone has to meet
outside on the EDP Plaza, and a third emergency. Builds on spec 008 (lights), 018/026
(campus map) and 033 (everyone can fix the lights).

Spec 023 was left free for another change that ended up as spec 027; this fills the gap.

## What

### 1. Choosing a sabotage on the map
- The examiner's sabotage key (Q) and button no longer turn the lights off at once. They open
  the campus map in **sabotage mode**: the normal map plus one marker per emergency,
  each with its name and an icon. Tapping a marker sends
  `{"type": "sabotage", "kind": "lights" | "fire" | "wifi"}` and closes the map.
- A message without `kind` still means `"lights"`, so the old message keeps working.
- **One shared cooldown** for all three (`SABOTAGE_COOLDOWN`, 30 s, as before), starting at
  the start of the round, after every meeting and when an emergency ends.
- **Only one emergency at a time.** While one runs, every other sabotage is rejected with
  "An emergency is already running".
- The markers' places come from `campus.json` (`"sabotages"`: kind, tile, name), so the map
  stays data, like vents and tasks.

### 2. Lights (as before)
Unchanged from spec 008 and 033: the light switch in Student Services, any living player
fixes it in 3 s.

### 3. Fire alarm (new, critical)
- **What happens:** an alarm sound for everyone, a red flashing border and a banner
  "FIRE ALARM — evacuate to the EDP Plaza! 0:40". Everyone sees the countdown.
- **How to end it:** every **living student** must have stepped onto the assembly point
  (a marked area on the EDP Plaza) at least once during the alarm. A student is checked in
  the moment they enter it; leaving again does not undo it. The banner shows
  "Evacuated: 3/5".
- **If time runs out** (`FIRE_SECONDS` = 40) before every living student is checked in, the
  **examiners win** ("The building burned down. Exams cancelled forever.").
- Examiners do not need to go (they would lose nothing by staying away), but nothing stops
  them from walking along to blend in.
- **Meetings:** the emergency button cannot be used during the alarm ("Not during the fire
  alarm"), but a report still can. A meeting ends every emergency (as it already did for
  the lights).
- Expelling during the alarm works as usual.

### 4. Wi-Fi down (new, not critical)
- **What happens:** "eduroam is down" for everyone. While it lasts, nobody can start or
  finish a step of a task ("No Wi-Fi. Try again later."); a task already running is
  cancelled with that note.
- **How to end it:** any living player stands at the router in the Library and holds
  "Restart router" for 3 s (the same mechanic as the light switch, spec 008/033).
- No time limit: it simply blocks the students' task win until someone fixes it (or a
  meeting ends it). Router and switch share one "fix" message: the server fixes whatever
  is broken.

### 5. What players receive
- Every snapshot while playing: `"emergency": null` or
  `{"kind": "fire" | "lights" | "wifi", "seconds_left": n or null,
    "evacuated": x, "students": y}` (the last two only for the fire alarm).
  `lights_on` stays as it is for older code.
- Examiners additionally receive the shared cooldown (`sabotage_cooldown`, as before).
- Nothing here reveals a role: the evacuated count counts students, but the number of
  examiners is set in the lobby (spec 019) and public anyway.

## Changes during implementation
- **Messages kept:** for the lights, the old rejection texts of spec 008 stay word for word
  ("The lights are already off", "Lights cooldown: n s left"), so spec 008's tests pass
  unchanged; the new kinds say "Sabotage cooldown: n s left".
- **Map data:** `campus.json` got `"sabotages"`: the lights at the light switch, the fire
  alarm at tile (38, 33) with the assembly point x 36–40, y 32–35 on the EDP Plaza, and the
  router at tile (33, 19) in the Library. A map without this list (the test maps) only
  offers the lights, as before.
- **On the map in the game:** the assembly point is painted on the plaza and the router
  stands in the Library all the time, so players learn where they are before they need them.
  During the fire alarm the assembly point blinks on everyone's campus map; during the
  outage, the router.
- **Sounds:** a new `fireAlarm` bell at the start of the alarm; the Wi-Fi outage reuses the
  power-down sound of the lights.
- **No existing test had to change.**

## Out of scope
More than three emergencies, doors that lock, a second fixer needed at the same time
(like the reactor in the original), voice lines.

## Done when
- `tests/test_spec023.py` covers, test first: choosing each kind (accepted and rejected:
  wrong role, ghost, cooldown, already running, unknown kind, in a meeting, lobby); the old
  message without `kind`; fire alarm check-in, success, time-out win for the examiners,
  the blocked emergency button and a report ending it; Wi-Fi blocking task starts and
  inputs and cancelling a running task, the router fix and walking away from it; the
  snapshot fields for every role; the campus data.
- Existing spec 008 tests keep passing unchanged where possible; any that change are
  listed here.
- Played in the browser with 5 tabs: each sabotage chosen from the map, the fire alarm
  won and lost once, Wi-Fi fixed once.
