# Spec 017 — Background music and more sound effects

## Why
Spec 016 gave the game sixteen generated sound effects. It left out background music,
ambience, and sounds for everything around them: reports, the meeting countdown, vents, the
lights and the end of a round (see 016's "Out of scope"). A round still has long silent
stretches between effects. The most dramatic moments (lights going out, a failed exam being
reported, winning or losing) have no sound of their own.

This spec adds a quiet, generated soundtrack that changes with the phase, sea waves near
Carcavelos Beach, and seven more effects. As in 016, everything is generated in the browser
with Web Audio: no audio file, no URL, no library, so there is no licence to check and nothing
to download. Builds on specs 001–016. Every event used below already reaches the browser in
its own snapshot, so the server is untouched.

## What

### `web/music.js`: a generated soundtrack, nothing recorded
A new, self-contained module, loaded after `sound.js` and before `main.js`. It exposes one
object, `Music`, with `setMood(name)`, `setBeach(closeness)`, `isOn()`, `setOn(value)` and
`toggle()`. `main.js` is the only file that calls it. `Music` knows nothing about the game:
`main.js` decides the mood from the state, and `music.js` only plays it.

- **No second `AudioContext`.** `sound.js` gets one small addition,
  `Sound.onUnlock(callback)`. It calls `callback(ctx, master)` once the shared context
  exists, or right away if it already does. `music.js` connects its own `GainNode` into that
  same master gain, so the existing mute button silences music and effects together without
  any extra code. `sound.js` stays the one place that creates the context on the first
  gesture. Before the first gesture, `setMood()` only remembers the mood; it starts playing
  once the context exists. Without Web Audio, `Music` stays silent and never throws.
- **One music volume constant:** `MUSIC_VOLUME` in `web/music.js`. It is relative to the
  master gain and clearly below the effects (start around 0.25 of the master and tune by
  ear). It is the only place the music's loudness is set.
- **Moods.** Each mood is a slow progression of 3–4 soft chords: sine/triangle tones through
  a lowpass filter, each chord several seconds long, with a slow attack and release. On top
  come a few sparse, random notes from one pentatonic scale. No melody repeats noticeably.
  - `lobby`: calm and a bit brighter (major chords), while waiting for the host;
  - `playing`: quieter and more open (minor chords), the bed of every round, for students,
    examiners and ghosts alike;
  - `dark`: while the lights are out; lower, with a darker filter and slower notes;
  - `off`: silence, faded out over about one second.
- **Which mood when** (all in `main.js`, from the latest state):
  - lobby → `lobby`;
  - playing with `lights_on` true → `playing`;
  - playing with `lights_on` false → `dark`;
  - meeting → `off` (the gong and the silence carry the tension);
  - ended → `off` (the win/lose jingle below plays instead).

  The mood depends only on `phase` and `lights_on`, which every player receives alike. So it
  is the same for every role and tells nobody anything about anyone.
- **Smooth changes:** switching moods crossfades over about 1.5 s with `setTargetAtTime`.
  There are no hard cuts and no clicks.
- **A lookahead scheduler, not one timer per note:** one `setInterval` (about every 200 ms)
  schedules the notes of the next second against `ctx.currentTime`. Timing stays steady even
  when the main thread is busy.
- **Pauses while the tab is hidden:** on `visibilitychange` to hidden, the music fades out and
  the scheduler stops. When the tab is visible again, it resumes in the current mood.
- **Sea waves near the beach:** a soft, slowly swelling noise layer (lowpass-filtered noise
  with a slow volume wave). Its loudness follows `Music.setBeach(closeness)`, a number from 0
  to 1.
  - `main.js` computes it in `CampusScene.predictTick()` from the own predicted position: 1
    on a tile next to the sea, falling to 0 at about 6 tiles from the nearest `sea` decor tile
    in `welcome.map`.
  - It is only on in the moods `playing` and `dark`.
  - It comes only from the own position, never from another player's.
- **Music switch, remembered per browser:**
  - a "Music" on/off switch inside the help ("?") overlay, with an `aria-label` and a
    visible on/off state;
  - on by default;
  - `setOn()` stores the choice in `localStorage` under its own key
    (`expelled-nova-music`), with both the read and the write wrapped in `try`/`catch`,
    exactly like the mute key in `sound.js`;
  - turning the music off also turns the waves off;
  - the mute button keeps silencing everything.

### Seven more effects in `web/sound.js`
Built from the existing `tone()` and `noise()` primitives and added to `EFFECTS`, each a few
lines long. All are played from `main.js` only.

1. **`reportAlarm`:** a short, urgent two-tone alarm. It plays together with the existing
   `meetingChime` on the one tick the phase becomes `"meeting"` and `meeting.reason` is
   `"report"`, for every player at once. A meeting from the button plays only the gong, as
   today.
2. **`countdownTick`:** a soft tick once per second for the last 5 seconds of voting, when
   `meeting.seconds_left` changes to 5, 4, 3, 2 or 1 while `meeting.result` is still null.
   It does not play during the result display.
3. **`ventHatch`:** one metal hatch clank. It plays when a vent id is new in `open_vents`
   compared with the previous snapshot.
   - `open_vents` is filtered by sight on the server, so every player who can see the hatch
     hears it. The examiner's own vent is in their own `open_vents`, so the examiner hears
     exactly what a bystander hears.
   - Only climbing in or out opens a hatch. Moving between vents makes no sound.
   - The sound never comes from `state.vent`.
4. **`lightsOut`, `lightsOn`:** a power-down slide and a power-up click. They play when
   `lights_on` flips from true to false and back, for every player at once (everyone receives
   `lights_on` and sees the result anyway). Both play only while the phase stays `"playing"`:
   the lights coming back on because a meeting started plays only the meeting sounds.
5. **`winJingle`, `loseJingle`:** a short rising and a short falling phrase, played once on
   the tick the phase becomes `"ended"`. `winJingle` plays if the own role's team
   (`student` → `"students"`, `examiner` → `"examiners"`) equals `state.winner`, otherwise
   `loseJingle`. Ghosts get their team's result too. Roles are public at the end of a round,
   so nothing is revealed early.

Names must avoid the word b-e-l-l anywhere in the files `tests/test_spec011.py` guards (spec
016 already ran into this).

## Constraints from the code
What the snapshots and the existing tests already fix. Every hook above has to fit them.

### Snapshot fields
- **`winner` and `role` are spelled differently.** `state.winner` is `"students"` or
  `"examiners"` (`server/game.py`, `STUDENTS_WIN`/`EXAMINERS_WIN`), while `state.role` is
  `"student"` or `"examiner"`. A win/lose check compares `winner` with `role + "s"`, never
  `winner === role`.
- **Some fields are only sometimes there.** `lights_on`, `tasks` and `doing` are missing in
  the lobby. `fixing` is only sent to students and `vent` only to examiners, so for the other
  role they are `undefined`, not `null`. `winner` and `roles` only come in `"ended"`, and
  `meeting` only in `"meeting"`.

### Lights
- **A meeting turns the lights back on.** The server sets `lights_on = True` when a meeting
  starts, and `updateLights()` only counts it as dark while the phase is `"playing"`. So
  `lightsOn` (and `lightsOut`) play only when both the previous and the current phase are
  `"playing"`. Otherwise `lightsOn` would sound at every meeting called in the dark, on top
  of the gong.
- **There is no sound for fixing itself.** When the first student's fix completes, the server
  clears `fixing` for every student at the switch, in the same snapshot in which `lights_on`
  turns true. `lightsOn` marks that moment for every player alike.

### Vents
- **Only climbing in or out opens a hatch.** `vent_enter` and `vent_leave` put the vent id
  into `open_vents` for 0.5 s (`VENT_OPEN_TICKS`); `vent_move` opens nothing. `ventHatch`
  fires when an id is new in `open_vents` compared with the previous snapshot.
- **No per-snapshot hook exists yet.** `main.js` only reads `open_vents` inside
  `CampusScene.update()` (drawing). The hatch sound needs its own check, called from
  `updatePhase()`, with a set of the ids already heard that is cleared on a phase change.

### Meeting and end
- **Report vs. button.** A report meeting is told apart by `meeting.reason === "report"`.
  `test_meeting_bell_plays_once_per_meeting_for_everyone` (spec 016) needs
  `Sound.play("meetingChime")` within 400 characters after the meeting-start check. So
  `reportAlarm` is added next to the chime, never instead of it.
- **The end jingle goes on the phase change.** `renderEnd()` redraws whenever its key
  changes, so a jingle there could replay. It belongs in `updatePhase()` on
  `state.phase === "ended" && previousPhase !== "ended"`. A game can end straight from a
  meeting (the last examiner voted out), not only from `"playing"`.

### Audio unlock
- **Music asked for before the first gesture must not be lost.** `Sound.play()` does nothing
  until the first tap or key press creates the `AudioContext`. `Music.setMood()` remembers
  the requested mood, and the `Sound.onUnlock()` callback starts it.

### Existing tests this spec must not break
- `tests/test_spec016.py`:
  - `Sound.play("expel")` appears exactly twice, so no new sound reuses that name;
  - `sound.js` has exactly one `MASTER_VOLUME =`; the music volume is `MUSIC_VOLUME` in
    `music.js`;
  - `play()` keeps its early return when there is no `ctx`;
  - no `http://`, `https://`, `.mp3`, `.wav`, `.ogg`, `.m4a` or `.flac` anywhere in
    `sound.js`, comments included;
  - the word `sound` does not appear in `server/game.py` or `server/main.py`, comments
    included: music and sounds stay client-only;
  - `.panel` keeps `right: calc(1xxpx …)` (the music switch lives in the help overlay, so no
    third round button is needed).
- `tests/test_spec011.py`: the word "b-e-l-l" is banned in `server/game.py`,
  `server/main.py`, `server/campus.json`, `web/index.html`, `web/main.js`, `web/render.js`
  and `web/style.css`. Only `web/sound.js` may use it.

## What a sound or the music must not reveal
Players usually sit in one room, so whatever one phone plays, the people next to it hear. A
sound or a piece of music that only one role, or only ghosts, can hear tells everyone nearby
that player's role or state.

- **Music follows public state only:** `phase` and `lights_on`. It never depends on `role`,
  `alive`, `expel_cooldown`, `vent`, `doing` or the players in sight. An "examiner theme"
  would reveal the role. Music that changes for a ghost would reveal an expel before anyone
  has found the failed exam.
- **No new sound that only one role's phone plays:**
  - vents use the one `ventHatch` sound, played for every player in sight of the hatch
    through `open_vents`;
  - moving between vents (`vent_move`) makes no sound;
  - `lightsOut` plays for everyone when `lights_on` changes, not when the examiner presses Q;
  - fixing the lights has no sound of its own; `lightsOn` plays for everyone.
- **Known existing leaks (spec 016):** the expel rip and the click on the lights-off button
  are only heard on the examiner's phone. They stay as they are and are listed under Limits.
- **The dark changes who sees what.** With the lights off, examiners see further than
  students. A hatch sound driven by sight-filtered data then plays on an examiner's phone
  while the students next to them hear nothing. This gap is listed under Limits.
- **Sounds come from sight-filtered data only** (`open_vents`), never from map distance
  alone. Otherwise a vent behind a wall would become audible.
- **Safe to play:**
  - the win/lose jingles, since every role is public once the game has ended;
  - the moods, which come from `phase` and `lights_on` only;
  - `reportAlarm` and `countdownTick`, from the meeting every player receives;
  - the beach waves, from the own predicted position only.

## Out of scope
- other players' footsteps;
- a sound for moving between vents;
- a sound for fixing the lights;
- a separate volume slider;
- different music per campus area (except the beach waves);
- recorded or downloaded audio of any kind;
- vibration;
- any server change;
- changing or removing any sound from spec 016.

## Done when
- **Tests first (AGENTS.md):** `tests/test_spec017.py`, written and shown to fail before the
  implementation, in the style of `tests/test_spec016.py`. It checks what can be checked
  outside a browser:
  - `GET /music.js` is served; `index.html` loads `sound.js`, then `music.js`, then
    `main.js`;
  - `music.js`:
    - contains no audio file extension (`.mp3`, `.wav`, `.ogg`, `.m4a`, `.flac`) and no
      `http://`/`https://`;
    - creates no `AudioContext` of its own and uses `Sound.onUnlock`;
    - has exactly one `MUSIC_VOLUME` constant;
    - wraps `localStorage` in `try`/`catch` under a key different from the mute key;
    - listens to `visibilitychange`;
    - uses `setInterval` with `currentTime` for scheduling;
  - `sound.js` still creates the context in exactly one place and exposes `onUnlock`;
  - the music switch exists inside the help overlay with an `aria-label`;
  - `main.js` calls `Music.setMood` with each of `lobby`, `playing`, `dark` and `off`, and
    calls `Music.setBeach`; the function that picks the mood reads neither the role nor
    `alive`;
  - each of the seven new effect names is defined in `sound.js` and played from `main.js`;
  - placement and guards in `main.js`:
    - `reportAlarm` sits in a branch that checks `reason` for `"report"`;
    - `ventHatch` is played from `open_vents`, never from `state.vent`;
    - no `ventIn`, `ventOut`, `ventMove` or `fixTick` sound exists;
    - `lightsOut`/`lightsOn` are guarded by the previous phase being `"playing"`;
    - the jingles sit in the `"ended"` phase change and compare against `winner`;
    - `countdownTick` is guarded by the vote still being open;
  - `server/game.py` and `server/main.py` gained no sound- or music-related code;
  - all of `tests/test_spec016.py` and `tests/test_spec011.py` still pass unchanged.
- `uv run pytest` passes in full: 993 tests (971 before, plus 22 new). Before the
  implementation, 19 of the 22 new tests failed. The 3 that passed are guards that were
  already true: `sound.js` creates the context once, no examiner-only sound name exists, and
  the server has no sound or music code.

  ```
  tests/test_websocket.py ....................                             [100%]
  ======================== 993 passed, 1 warning in 5.50s ========================
  ```
  (The one warning is Starlette's `httpx` deprecation notice from the test client, unrelated
  to this spec.)
- **A manual check list on the deployed app** (two browser tabs, one at phone width with
  touch emulation):
  - lobby music starts after the first tap/key and is clearly quieter than a click;
  - starting a round crossfades to the playing mood, with no click or gap;
  - turning the lights off switches every tab to the dark mood and plays `lightsOut`;
    fixing them plays `lightsOn` on every tab; a meeting called in the dark plays no
    `lightsOn`;
  - the button meeting plays only the gong, and a report plays the alarm plus the gong, on
    every tab; the music fades out for the meeting, and the last 5 voting seconds tick;
  - walking onto the beach brings up the waves smoothly; walking away fades them out;
  - climbing into or out of a vent plays the hatch on every tab that can see it, the
    examiner's own included; moving between vents is silent everywhere;
  - at the end, the winning team's tabs hear the rising jingle and the others the falling
    one;
  - the music switch turns music and waves off and on and survives a reload; the mute button
    still silences everything;
  - switching to another tab pauses the music, and coming back resumes it;
  - after 10 minutes of play the music still does not feel repetitive or tiring.

## Changes during implementation
- **Seven effects, not ten.** The first draft had `ventIn`, `ventOut` and `ventMove`, played
  from the own `state.vent`, plus `fixTick`, played on the fixing student's phone. Each would
  have played on one role's phone only, so the people sitting next to that player would hear
  their role. They became one shared `ventHatch` from `open_vents`, and fixing got no sound of
  its own (see "What a sound or the music must not reveal").
- **The mood is picked in its own small function, `updateMusic(state)`,** not inside
  `updatePhase()`. `updatePhase()` reads `state.alive` for the ghost banner, and keeping the
  mood in a function that reads only `phase` and `lights_on` makes "same music for every
  role and for ghosts" checkable by a test.
- **The lights sounds live in `updatePhase()`, not `updateLights()`,** because they need
  `previousPhase`, which only `updatePhase()` has.
- **`timbre`, not `wave`, for a mood's oscillator type in `music.js`.** `mood.wave` contains
  the text `.wav`, which the "no audio files" test rightly rejects.
- **One hatch sound per snapshot,** even if two hatches open in the same tick: two clanks at
  the same instant would only sound louder, not different.
- **The waves always run once audio is unlocked,** at volume 0 away from the beach, instead
  of being started and stopped. Fewer moving parts, and a fade in or out is just one volume
  change.
- **The music switch is a `<button role="switch">`** with `aria-checked` and the visible text
  "On"/"Off". When off, it is drawn on plain paper instead of the yellow highlighter.

## Limits
- **Two examiner-only sounds remain from spec 016:** the expel rip and the click on the
  lights-off button. People sitting next to the examiner can hear them. Changing spec 016's
  sounds was out of scope here.
- **The dark changes who hears a hatch.** With the lights off, examiners (and ghosts) see
  further than students, and `open_vents` follows sight. So an examiner's phone can clank for
  a hatch that the students next to them neither see nor hear.
- **Ghosts hear every hatch on the map.** A ghost receives all of `open_vents`, not only the
  ones nearby, so a ghost's phone can clank when nobody near it sees a vent. That is a weak
  hint to neighbours that the player is out; spec 016's expel rip already gives the same
  away more loudly.
- **The beach closeness is a straight line** to the nearest `sea` rectangle and ignores
  walls. It only uses the map every player has and the own position, so it reveals nothing.
- **Music keeps being scheduled while muted.** Mute sets the master gain to 0 (spec 016), so
  nothing is heard, but the scheduler still creates a few silent notes per chord.
- **Hiding the tab fades out what is already scheduled** (up to 1 s ahead) instead of
  cutting it. Coming back starts the mood again from its first chord.
- **The 4-player checks were not run by hand.** These are the lights, report, countdown, vent,
  jingle and 10-minute items of the manual checklist; a round needs four players. Checked in a
  local browser:
  - the lobby music starts after the join tap;
  - the music switch turns notes off, its state survives a reload, and its On/Off text and
    `aria-checked` change;
  - `checkVentSounds()`, `updateMusic()` and `beachCloseness()` give the expected results for
    made-up states: one clank per newly opened hatch and none in a meeting; moods
    lobby/playing/dark/off/off; closeness 1 at the water, 0.5 three tiles away and 0 further
    inland;
  - no console or server errors.

  The other checklist items still need a two-tab game on the deployed app.
- **No automated browser tests,** same as specs 015 and 016: `tests/test_spec017.py` reads
  the files in `web/` to guard what must stay in place.

## Files created or changed
- `web/music.js`: new. The whole music module (`Music.setMood`/`setBeach`/`isOn`/`setOn`/
  `toggle`), generated audio only, sharing `sound.js`'s context.
- `web/sound.js`: `Sound.onUnlock()` (and its waiting list, called from `unlock()`), plus
  the seven new effects in `EFFECTS`. No existing effect, `MASTER_VOLUME` or the mute logic
  changed.
- `web/main.js`:
  - `BEACH_RANGE_TILES` and `ui.musicSwitch`;
  - the music switch's setup (`updateMusicSwitch`, its click listener);
  - the trackers `wasLightsOn`, `lastCountdown` and `heardOpenVents`;
  - in `updatePhase()`: `reportAlarm`, the jingles, the lights sounds and the calls to
    `updateMusic()` and `checkVentSounds()`;
  - the new functions `updateMusic()`, `checkVentSounds()` and `beachCloseness()`;
  - `countdownTick` in `renderMeeting()` and `Music.setBeach()` in
    `CampusScene.predictTick()`.
- `web/index.html`: `<script src="music.js">` between `sound.js` and `main.js`; the music
  switch inside the help overlay.
- `web/style.css`: `.help-music`, `.help-music-label`, `.music-switch`.
- `tests/test_spec017.py`: new, the tests described above.
- `specs/017-music-and-more-sounds.md`: this spec.
