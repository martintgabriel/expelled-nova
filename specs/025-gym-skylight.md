# Spec 025 — People in the gym

## Why
In the playtest the gym was just a grey roof with "Gym" written on it. Nobody needs to go
in, but you should see that it is a gym. Builds on spec 009 (the campus map) and 015.

## What
- `Render.makeGym(scene, map)` in `web/render.js` draws a skylight into the gym's roof: a
  rubber floor, two treadmills with runners bobbing, a bench press with a bar going up and
  down and a figure lifting hand weights, all with Phaser tweens.
- The gym is found as the roof decor under the "Gym" label, so `campus.json` stays as it is.
  Without such a label or roof nothing is drawn.
- Pure decoration: the gym stays a solid block, nothing is sent to or from the server, and
  the figures are drawn below players, failed exams and vents.
- The figures are original shapes (a round body and two eyes), like the players.

## Out of scope
Walking into the gym, a gym task.

## Done when
- `tests/test_spec025.py` checks that render.js has `makeGym`, finds the gym through the
  label, animates with tweens, and that main.js calls it once.
- All tests pass; locally the gym shows people working out.
