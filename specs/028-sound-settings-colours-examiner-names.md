# Spec 028 — Sound settings, taken colours, examiners recognise each other

This spec describes what was built. Where the result differs from the first version of the spec, "Changes during implementation" says how and why.

## Why
Playtest feedback:
- the sound controls are unclear and the music switch sits in the "How to play" panel, although it is a setting;
- taken colours still look selectable;
- with many players, examiners cannot reliably spot their teammate.

In Among Us, impostors see each other's names in red everywhere. Builds on specs 015, 017, 020 and 022.

## What

### 1. One "Sound settings" button and one small panel
- **The button:** the round speaker button next to "?" (top right), in the same place on the join screen, in the lobby and in the game. It replaces the mute button of spec 016 and keeps its element id (`mute-button`). Its label is "Sound settings"; `aria-expanded` says whether the panel is open.
- **The panel** (`#sound-panel` in `web/index.html`): a small paper card under the button, not a full-screen overlay, so the game and the join card stay visible and the game does not pause. It closes with the button, its ×, Esc or a click or tap anywhere else. Opening the handbook or the campus map closes it. It bundles every sound control:
  - **Background music** on/off (`#music-switch`, `Music.toggle()`, spec 017);
  - **Volume** (`#volume-slider`, spec 020): one slider for music and effects together, with a quiet speaker at its left end and a loud speaker at its right end;
  - **Sound effects** on/off (`#effects-switch`, `Sound.setEffectsOn()`), new: see below.
- **Music and effects are separated in the code now** (`web/sound.js`). Before, "mute" set the master gain to 0 and silenced everything. Now the effects switch only stops `Sound.play()` and the "Expelled!" voice; the master gain is always `MASTER_VOLUME * volume`, so the music plays on. `Sound` exposes `effectsOn()` and `setEffectsOn(value)` instead of `isMuted()`, `setMuted()` and `toggleMute()`.
- **The music switch moved out of "How to play".** The handbook has one new line instead: "The speaker button (top right) opens the sound settings."
- **Remembered per browser as before,** under the same three `localStorage` keys: `expelled-nova-music` (music), `expelled-nova-volume` (volume) and `expelled-nova-muted` (now: "1" = sound effects off).

### 2. Muted icon
Whenever the music is off or the volume is 0, the speaker shows a red diagonal strike-through: on the button and on the speaker icon in the panel's title (`.sound-strike`, shown by `updateSoundSettings()` in `web/main.js`). The button's label then says why: "Sound settings (music is off)" or "Sound settings (volume is 0)". Switching only the sound effects off does not strike the icon: the spec ties it to the music and the volume.

### 3. Taken colours
- **Rule (`server/game.py`):** `Game.taken_colors()` returns `{colour number: nickname}` for every player in the game.
- **Endpoint (`server/main.py`):** `GET /taken-colors` answers `{"taken": {"<colour>": "<nickname>"}}` with `Cache-Control: no-store`. It takes no input and changes nothing. Someone on the join screen has not joined yet, so they receive no snapshots; this is how the page learns the taken colours before joining.
- **Picker (`web/main.js`, `renderLook()`):** a colour another player has is crossed out with a diagonal line, washed out, disabled (not clickable) and has "Taken by <name>" as title and `aria-label`. The name is only ever set as an attribute's text.
- **Live:** while the join screen shows, the page asks every 1.5 seconds (`refreshTakenColors()`), and at once when a join was rejected or the tab comes back from the background. Asking stops once joined. A colour is free again as soon as its player has left.
- **If the own pick gets taken,** the picker goes back to "Any". This is not saved, so the remembered favourite colour is offered again next time.
- **The server rule stays:** joining with a taken colour is still rejected with "Colour is already taken" (spec 022). The picker only shows it earlier.

### 4. Name colours: red for the examiners' team, green for the own student name
One rule decides the colour of every name, `nameTone(state, playerId)` in `web/main.js`:

| Who looks | Own name | Fellow examiner | Everyone else |
|---|---|---|---|
| Examiner | red | red | normal |
| Student | green | (not known) | normal |
| Lobby (no role yet) | normal | – | normal |

"Normal" is white on the map (the own name yellow, as before, while there is no role) and ink on the paper cards.

- **Where:** above the characters on the map (`Render.setNameTone()` in `web/render.js`; `render.js` only gets a tone per character), on the meeting and voting cards, on the cards of the vote result, and in the class list of the end screen (`markName()`; classes `.name-examiner` and `.name-student` in `web/style.css`).
- **Only from the own snapshot.** The own name follows the own `role`. Another player's name turns red only if that player is in `fellow_examiners`, which the server sends to examiners only, as before. A student's page therefore never colours anyone else's name, also not on the end screen, where the roles are public as tags: nobody learns from a name who else is a student. **No server code for this part changed** (BRD R2).
- A fellow examiner's red name also has the title "Fellow examiner". A ghost's own name keeps its colour on the meeting cards.

## Out of scope
New sounds or music, new colours, any change to roles or rules.

## Done when
- **Server tests first** (`tests/test_spec028.py`, 40 tests: 37 in the first version, 3 more for the name colours). Before the implementation 30 failed and 7 passed. The 7 are guards that were already true and must stay true: a student's snapshot has no fellow-examiner information (living, ghost, in a meeting), examiners get exactly each other, the end screen's public roles, picking a taken colour is rejected and changes nothing, and the three storage keys.
  - **taken colours, rule (6):** empty game; who has which colour; free again after a leave; a rejected join takes no colour; still rejected; unchanged during a round (ghosts keep their colour).
  - **taken colours, endpoint (6):** starts empty; follows joining and leaving over the real WebSocket; a taken colour is still rejected over the WebSocket; never cached; ignores query parameters; holds names and colours only (no id, role, or who is a ghost), also in a running round.
  - **examiners (5):** the guards above.
  - **browser files (23):** the button, the panel and its three controls, the icons at both ends of the slider, no music switch in the handbook, Esc, the split in `sound.js`, the strike-through and its condition, the picker asking the server, the taken swatch, and the name colours: the rule (own name from the own role, other names only from the fellow list, never from `roles`), the three card builders, the map, the two tone colours and the stylesheet. The name-colour tests were rewritten for the red-and-green rule and 8 of them failed before that change.
- `uv run pytest` passes: 1204 tests (1164 before, plus 40).
- **No existing test was changed.** `test_the_music_switch_sits_inside_the_help_overlay_with_an_aria_label` in `tests/test_spec017.py` still passes, but only because it reads the page from the handbook to the end, where the sound panel now is. Its name is out of date; the new test `test_how_to_play_no_longer_contains_the_music_switch` checks the real rule.
- **Checked in a running game** (7 tabs of the built-in browser on one laptop, 2 examiners):
  - the sound panel opens from the one button, switches the music and the effects, and the slider changes the volume setting; all three survive a reload;
  - the strike-through appears with the music off and with the volume at 0, on the button and in the panel, and goes away again;
  - "How to play" no longer contains the music switch;
  - taken colours are crossed out for someone on the join screen with "Taken by Ada/Bo/Cy", a colour is free again after its player left, and a forced join with a taken colour is rejected with "Colour is already taken";
  - each examiner sees the own name and the other examiner's name in red on the map, on the voting cards and on the end screen (the result cards were checked in the first version, with the fellow's name only);
  - a student sees the own name in green in the same places, also as a ghost, and every other name in the normal colour, the two examiners' included; its snapshot has no `fellow_examiners`;
  - the panel fits a 375 px wide phone screen; no errors in the browser console.
- **Still to check by hand:** the sound by ear (music stays on with the effects off, and the other way round), a real phone, and the deployed app.

## Changes during implementation
- **Spec number 028.** It was written as 027; a colleague's spec took that number, so the spec, its test file and every comment were renumbered.
- **Red and green instead of only a red fellow name.** The first version coloured only the fellow examiner's name. After a look at it, the own name got a colour too: red for an examiner, green for a student, so the own side is visible at any moment.
- **A small HTTP endpoint instead of a new WebSocket message.** A page on the join screen has no snapshots. Sending the taken colours over the WebSocket would have meant opening the socket on page load and a new message before "join"; several existing tests read the first message after joining and would have broken. A read-only `GET /taken-colors`, asked every 1.5 s, is a few lines on each side.
- **Sound effects got their own switch.** The spec asked for it "if the code separates them". It did not: there was one mute for everything. With the mute button turned into the settings button, one master mute next to a music switch and a volume slider would have been three overlapping controls again. Now each control does one thing: music, effects, volume.
- **The spec 020 rule "moving the slider while muted unmutes" is gone** with the master mute. Volume 0 is simply silence.
- **The strike is red with a paper-coloured edge,** so it stays readable on top of the speaker's sound waves at 20 px.
- **Setting the strike with `toggleAttribute("hidden")`.** The old mute icon was switched with the `hidden` property, which SVG elements do not have, so its crossed-out state never showed.

## Limits
- **Up to 1.5 seconds late.** The picker asks instead of being told. Two people can still pick the same free colour within that time; the second one gets "Colour is already taken", and the picker then shows it. A background tab does not ask until it shows again.
- **Anyone who opens the page can read the nicknames and colours of the players in the game,** also during a round and without joining. It is what the lobby shows; no ids, roles, positions or ghosts.
- **A browser that was muted before this change** now has its sound effects off and its music on (if its music switch was on), because the old mute key became the effects switch.
- **The effects switch does not strike the icon.** With the music on and the effects off the speaker looks unmuted, as the spec defines it.
- **An effect that is already playing rings out** (at most about 1.5 s) when the effects are switched off.
- **The own name's colour tells the own role to anyone looking at the screen:** red for an examiner, green for a student (and a second red name is the teammate). That is the price of the feature, as in the original game; the role badge already says the role in words.
- **In the lobby the own name is yellow, not green or red:** there is no role before the round starts.
- **The colours on the map are fixed** (`NAME_TONE_COLORS` in `web/render.js`), brighter than the stylesheet's stamp red and green, because the map's names stand on a dark outline.
- **The button's id is still `mute-button`,** because the tests of specs 016, 018 and 020 look for it.
- **No automatic browser tests,** as in specs 015–020: the tests read the files in `web/`.

## Files created or changed
- `server/game.py`: `Game.taken_colors()`.
- `server/main.py`: `GET /taken-colors`.
- `web/sound.js`: effects switch separated from the master gain; `effectsOn()`, `setEffectsOn()`.
- `web/music.js`: one comment (the volume slider, not the mute button, reaches the music).
- `web/index.html`: the speaker button with the strike, the sound panel, no music switch in the handbook, one handbook line.
- `web/style.css`: the sound panel, the strike, the taken swatch, the red and the green name; the handbook's music row and the fixed slider position are gone.
- `web/render.js`: `NAME_TONE_COLORS`, `setNameTone()`.
- `web/main.js`: the sound settings section (replaces mute, volume and music switch), the taken colours in the picker, `isFellowExaminer()`, `nameTone()` and `markName()` and their four uses.
- `tests/test_spec028.py`: new.
- `specs/028-sound-settings-colours-examiner-names.md`: this spec.
