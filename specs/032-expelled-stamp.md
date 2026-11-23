# Spec 032 — "EXPELLED!" on screen for the two people involved

## Why
Playtest, 23 Nov: when an examiner expels a student, nothing visible says so. It should
show "EXPELLED!" for the examiner who did it and the student who was expelled, and for
nobody else (everyone else must not learn about it).

## What
- A red stamp "EXPELLED!" appears in the middle of the screen for about 1.6 seconds, with a
  line under it: "You expelled a student." for the examiner, "An examiner caught you. You
  are a ghost now." for the student.
- It appears exactly where the paper-rip sound and the voice already play (spec 016/020):
  for the examiner when the server confirms the expel (the cooldown starts), for the student
  when their own `alive` turns false while playing. Both only use the own state, so no other
  player can ever see it.

## Out of scope
An animation of the expel on the map for others.

## Done when
- `tests/test_spec032.py` checks the stamp element, that it is shown right next to each of
  the two expel sounds and nowhere else.
- All tests pass.
