# Spec 027 — One sound settings panel

## Why
Team feedback on 23 Nov: the volume slider on its own does not say what it does, the
background music switch hides in the "?" handbook although it is a setting, and turning the
music off leaves the speaker icon unchanged. Builds on specs 016 (mute), 017 (music) and
020 (volume slider).

## What
- The speaker button (`#mute-button`, same place) now opens a small **Sound** panel
  (`#sound-panel`) instead of muting at once. The panel bundles:
  - **Sound** On/Off (`#sound-switch`): the old mute, still remembered per browser.
  - **Volume** (`#volume-slider`, moved here from under the buttons).
  - **Background music** On/Off (`#music-switch`, moved here from the handbook).
- The panel closes with the speaker button again, with Esc or a click anywhere outside it.
- **The icon tells the state:** a speaker with sound waves when everything is on; the
  speaker crossed out when there is no sound at all (Sound off or volume 0); the speaker with
  a small crossed-out note when only the music is off.
- Nothing about how sounds or music are made changes.

## Out of scope
Separate volumes for music and effects.

## Done when
- `tests/test_spec027.py` checks the panel and its three controls, that the music switch
  left the handbook, the three icon states and how the panel closes.
- This spec replaces the spec 017 test that required the music switch inside the help
  overlay (`tests/test_spec017.py`) with one that only requires the switch and its label.
- All tests pass; locally the panel opens, each control works and the icon follows.
