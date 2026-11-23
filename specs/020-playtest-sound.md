# Spec 020 — Playtest fixes, part 2: sound

## Why
The playtest on 23 Nov asked for three sound changes: a volume control instead of only
on/off, a funny voice when a student is expelled, and an end sound that tells at once which
side won (a gloomy one when the examiners win, a happy "wheeey" when the students win).
Builds on specs 016 (sound effects) and 017 (music and more sounds).

## What
1. **Volume slider** next to the mute button, on every screen (`<input type="range"
   id="volume-slider">`, 0–100). It scales the one master gain, so it changes effects and
   music together. `MASTER_VOLUME` stays the one constant: the gain is
   `MASTER_VOLUME * volume`. The volume is remembered per browser (localStorage, wrapped in
   try/catch like the mute choice). Moving the slider while muted unmutes; 0 counts as muted.
   `Sound` gets `getVolume()` and `setVolume(value)` (0–1, clamped).
2. **"Expelled!" voice** for the two players who already hear the paper rip (spec 016): the
   expelling examiner and the expelled student. A deep, slow voice from the browser's own
   speech synthesis (`speechSynthesis`, no audio file), plus a low generated drop
   (`expelVoice` effect). It respects mute and volume; without speech synthesis only the
   drop plays.
3. **End sound by winning side**, the same for every player: `examinersWin` (three low,
   gloomy notes, "dun dun dun") when the examiners win, `studentsWin` (a rising "wheeey"
   slide and a bright chord) when the students win. They replace `winJingle` and
   `loseJingle`, which depended on the player's own role.

## Out of scope
Recorded voices, per-sound volume, separate music volume.

## Done when
- New tests in `tests/test_spec020.py` check the slider, the volume functions, the voice and
  the new end sounds in the files.
- This spec changes the two tests in `tests/test_spec017.py` that named `winJingle` and
  `loseJingle`: they now expect `studentsWin` and `examinersWin`, compared against `winner`.
- All tests pass; locally the slider changes the volume of music and effects, an expel says
  "Expelled!" and each side's win plays its own sound.
