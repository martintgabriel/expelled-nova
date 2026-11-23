# Spec 019 — Playtest fixes, part 1: game rules

## Why
A playtest on 23 Nov showed four problems with the rules: the examiner can expel again too
soon, rounds with many players end too fast because everyone has only three tasks, the host
cannot choose how many examiners there are, and after a vote nobody can see who voted for
whom. Builds on specs 002 (roles), 003 (expel), 004/012 (tasks) and 006 (votes).

## What
1. **Longer expel cooldown:** `EXPEL_COOLDOWN` goes from 20 to 30 seconds (closer to the
   genre's usual default). It still starts at the beginning of a round and after every meeting.
2. **More tasks with more players:** `tasks_per_player(player_count)` deals 3 tasks for 4–5
   players, 4 for 6–7 and 5 for 8–10, never more than the map has. `TASKS_PER_STUDENT`
   (3) stays as the base. Examiners get the same number of fake tasks.
3. **Host setting: number of examiners.** A new message `{"type": "settings", "expellers": X}`
   with X = `null` (automatic, as before: 1 for 4–6 players, 2 for 7–10), `1` or `2`.
   - Only the host, only in the lobby; any other value is rejected with a reason and changes
     nothing.
   - Every snapshot carries `"settings": {"expellers": X}` so every player sees the choice.
     The key is "expellers", not "examiners": the existing role-leak tests check that no
     snapshot before the end contains the word "examiner".
   - Starting with 2 examiners needs at least 6 players, otherwise the start is rejected
     ("2 examiners need at least 6 players").
   - The setting stays for the next round; it goes back to automatic when everyone has left.
4. **Who voted for whom:** once a vote is counted, every player's snapshot carries
   `"ballots": {voter_id: target_id or "skip"}` for the votes actually cast, until the meeting
   ends. During the vote it is never sent, so voting stays secret until the result.
   The result screen colours each vote dot in the voter's colour.

Client: the lobby shows the examiner setting (the host can change it, everyone else sees it);
the result screen uses `ballots`.

## Out of scope
More task kinds (a later spec), other host settings (cooldown, speed), anonymous votes.

## Done when
- New tests in `tests/test_spec019.py` cover accepted and rejected settings, the 2-examiner
  start rule, the task counts per player count, the cooldown and the ballots (also that
  they are hidden while voting).
- This spec changes three existing tests in `tests/test_tasks.py` that expected 3 tasks
  (or a total of 15) with 7 and 10 players: they now expect `tasks_per_player(count)`.
- All tests pass; locally a game with 4 and with 8 browser tabs plays without errors.
