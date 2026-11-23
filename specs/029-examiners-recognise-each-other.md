# Spec 029 — Examiners recognise each other everywhere

## Why
With 7–10 players there can be two examiners. They already learn each other's names at the
role reveal and in the role badge (spec 003), but on the map and in a meeting nothing marks
the team-mate, so in a busy round an examiner can lose track of who is on their side. In the
original genre the impostors' names are red for each other. Team feedback, 23 Nov.

## What
Only for a player whose own role is examiner, from what the server already sends that player
(`role` and `fellow_examiners`, spec 003); nothing changes on the server and nothing new
reaches a student:
1. **On the map** the names of the examiner team (the own name and every fellow examiner's)
   are drawn in red (`EXAMINER_NAME_COLOR`). Everyone else keeps the usual colours. The
   colour is checked every frame, so it switches as soon as the round starts and back in
   the lobby.
2. **In a meeting** (voting cards and the result) a fellow examiner's card carries a red
   "examiner" tag, and the own card too.
3. A student sees exactly what they saw before: the helper returns an empty set for anyone
   whose own role is not examiner.

## Out of scope
Showing roles to ghosts or after the end (already done by spec 003: everyone sees all roles
at the end).

## Done when
- `tests/test_spec029.py` checks the server still sends `fellow_examiners` only to
  examiners, and that the client colours and tags only from `role` and
  `fellow_examiners`.
- All tests pass; locally, with 7 tabs and 2 examiners, both see each other's names in red
  and the tag in a meeting, and the students see nothing new.
