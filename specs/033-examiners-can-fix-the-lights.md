# Spec 033 — Examiners can turn the lights back on too

## Why
Playtest, 23 Nov: only students could fix the lights, so a player standing at the switch
doing nothing was an examiner for sure. In the original genre everyone can fix a sabotage,
which lets an examiner blend in. Builds on spec 008 (lights).

## What
- `fix` is allowed for every living player, student or examiner, under the same rules as
  before (at the switch, lights off, not busy with a task, `FIX_SECONDS`, stay in reach).
  An examiner inside a vent is rejected with the usual "Leave the vent first".
- Every player's snapshot now carries `fixing` while playing (null or the seconds left), so
  its presence no longer tells a student from an examiner.
- The client shows the fix button and the F key to examiners too.
- Ghosts still cannot fix.

## Out of scope
Examiners being able to sabotage while fixing (unchanged: they can, it is their switch).

## Done when
- `tests/test_spec033.py` covers an examiner fixing, the vent rule and `fixing` for both
  roles.
- This spec changes two spec 008 tests in `tests/test_spec008.py`: the examiner rejection
  ("Only students can fix the lights") is removed, and an examiner's snapshot now has
  `fixing`.
- All tests pass.
