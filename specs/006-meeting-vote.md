# Spec 006 — Meetings and votes: report, bell, sent surfing

## Why
So far students can only watch: examiners expel until they win, and nobody can act on what they saw. Meetings turn suspicion into a decision. A failed exam is found or the bell is rung, everyone gathers in the Auditorium, discusses and votes someone out ("sent surfing"). This completes the core loop and gives students their second win condition. Covers BRD EX07, R5, the vote win in R6, R7 (two meeting calls, or an expel and a meeting start, in the same tick) and acceptance A4. Builds on spec 002 (phases, host, `snapshot_for`), spec 003 (expel, ghosts, failed exams, cooldowns, win check, restart) and spec 005 (colours, vision radius).

## What
- **New phase `meeting`**, entered from `playing` and left back to `playing` (or to `ended` by the win check). The meeting rules live in `server/game.py` like the others; time is counted in ticks, so tests advance it with `step()`.
- **Report:** a player sends `{"type": "report", "exam": "<failed exam id>"}`. Accepted only if:
  - the phase is `playing`;
  - the sender is alive (student or examiner: an examiner may report their own exam);
  - the exam exists and lies at most `REPORT_RANGE` (48 px, about 1.5 tiles, like the expel range) from the sender's centre.

  An unknown exam and an exam out of reach get the same reason ("No failed exam within reach"). That way a browser cannot find out about failed exams it cannot see by trying ids.
- **Bell:** a player sends `{"type": "bell"}`. Accepted only if the phase is `playing`, the sender is alive and has not rung the bell yet in this round. It can be rung anywhere on the map. Each player has one bell per round, and a new round gives it back. A rejected bell is not used up.
- **One meeting at a time (R7):** an accepted report or bell switches the phase to `meeting` at once. A second report or bell processed before the next tick is rejected ("A meeting is already running") and changes nothing. The first one the server processes wins, and so does a meeting start over an expel that comes after it in the same tick.
- **When a meeting starts:**
  - every player, ghosts too, is put on the centre of their own floor tile in the Auditorium (the area named "Auditorium" in the map). Players go in join order onto every second floor tile of every second row, in reading order (row by row, left to right), so no two stand on neighbouring tiles. If the room is too small for that, the rest go on the remaining floor tiles. If the map has fewer floor tiles there than players (the small test maps of earlier specs have no Auditorium), the remaining players stay where they are. Everyone's direction is set to 0;
  - the voting timer starts: `MEETING_SECONDS = 60`;
  - the server remembers who called the meeting and why (`"report"` or `"bell"`).
- **Paused:** for the whole meeting (voting and result), movement input and expels are rejected ("Meeting in progress"), and nobody moves. Join, start and restart stay rejected as before. `step()` still counts ticks, closes the voting when it is due and ends the meeting after the result.
- **Vote:** a player sends `{"type": "vote", "target": "<player id>"}` or `{"type": "vote", "target": "skip"}`. Accepted only if:
  - the phase is `meeting` and the voting is still open;
  - the sender is alive and has not voted yet in this meeting (a vote cannot be changed);
  - the target is `"skip"` or a living player (voting for yourself is allowed).

  The sender is checked before the target, as with expel. Ghosts cannot vote.
- **Voting closes** at the first tick at which every living player has voted or the timer has run out. Anyone who has not voted by then counts as a skip.
- **Result (R5):** a player is sent surfing only with more votes than every other player and more votes than skips. A tie between players, or skips at least as many as the top player's votes, sends nobody. The player sent surfing becomes a ghost at once (`alive = False`, like an expelled player but without a failed exam). Nothing in the result reveals that player's role.
- **Result time:** the phase stays `meeting` for `RESULT_SECONDS = 5` more. Everyone sees the result at the same moment and nobody moves behind the result screen.
- **Meeting end:** then all failed exams are removed and every examiner's expel cooldown restarts (a full 20 s from now). The phase returns to `playing`, and players walk on from the Auditorium. Then the win check from spec 003 runs. Students win when no living examiner is left (all examiners voted out), and examiners win when living examiners are at least as many as living students. The check runs after the result time, so everyone sees the result before the end screen.
- **Leaving during a meeting:** the leaver's own vote is removed. Votes cast for them are taken back, so those players can vote again. The win check runs as it does while playing, and if the game ends, the meeting is over. If everyone still living has voted, the voting closes at the next tick.
- **New round and empty game:** restart and the last player leaving also clear the meeting and give everyone their bell back.
- **What each player receives (`snapshot_for`):**
  - every snapshot has `bell_used`: whether this player has rung the bell in this round (their own bell only);
  - in `meeting`, a `meeting` object:
    - `reason` (`"report"` or `"bell"`) and `called_by` (the caller's id);
    - `living`: the ids of the living players in join order, meaning who can vote and be voted for;
    - `voted`: the ids of the living players who have already voted, never whom they voted for;
    - `my_vote`: this player's own vote (a player id, `"skip"` or `null`);
    - `seconds_left`: while voting, the voting time left; during the result, the time until play resumes (whole seconds, rounded up);
    - `result`: `null` while voting, then `{"votes": {id: count}, "skips": n, "surfing": id or null}`. `votes` has an entry for every player who was living when the voting closed, 0 included;
  - **vision:** the radius from spec 005 applies only in `playing`. In a meeting, a living player receives all living players and all failed exams at any distance. Ghosts stay hidden from the living (spec 003), and a ghost still receives everyone and every failed exam. Player entries stay exactly `{id, name, x, y}`;
  - **roles** do not change: before `ended`, nobody receives another player's role (examiners still see fellow examiners).
- **`server/main.py`:** `report`, `bell` and `vote` become allowed message types (so they are rejected before joining) and are passed to the game. `welcome` also carries `report_range`.
- **Browser** (HTML panels in `index.html`, `style.css` and `main.js`, like the lobby and the end screen; names are always added as text, never as HTML):
  - **Report button** (and key R): shown to a living player while playing, only when a failed exam is within `report_range` of the latest server position. It reports the nearest one;
  - **Bell button:** shown to living players while playing. After use it stays visible but disabled as "Bell used". It has no key, so it cannot be rung by accident;
  - **meeting screen** (for everyone, ghosts too): who called it and why (e.g. "Ana found a failed exam" or "Ana rang the bell"), the timer, and the living players with colour dot and name. A "voted" mark appears next to everyone who has voted. There is a Vote button per player and one Skip button. After voting the buttons are disabled and the screen shows "You voted for Ben" or "You skipped". A ghost sees the screen without buttons and with "Ghosts cannot vote";
  - **result screen** (5 s, for everyone): votes per player and the skips, then "Ana was sent surfing" or "Nobody was sent surfing". Afterwards the player sent surfing sees "You have been sent surfing" instead of "You have been expelled". The end screen marks ghosts as "ghost" instead of "expelled", because a ghost may also have been voted out;
  - during a meeting the browser sends no movement and predicts none. The role screen shows only when the game starts, not when play resumes after a meeting. Rejected actions show their reason as a toast, as before.

## Out of scope
- Chat or any text in meetings (roadmap F5): players discuss out loud.
- Revealing the role of the player sent surfing.
- Changing a vote.
- A bell cooldown or a fixed bell place: the bell rings from anywhere, also right after a meeting.
- Host settings for the timers (F8) and sound (F10).
- Tasks and the students' task win (spec 004): whichever of 004 and 006 is merged second makes sure that no task can be done during a meeting.
- Staff doors, phone controls (spec 007) and map changes. `server/campus.json` stays as it is; its Auditorium is 11 × 8 floor tiles.
- Existing rules (movement, roles, expel, vision while playing, colours, restart) change only where stated above.

## Done when
- Tests in a new file `tests/test_meeting.py`, written first and red before the implementation.
  - Accepted:
    - a living student next to a failed exam reports it → phase `meeting`, `reason` "report", `called_by` the student, 60 s on the timer; a living examiner can report as well;
    - a living player rings the bell → phase `meeting`, `reason` "bell"; their `bell_used` is true, nobody else's is;
    - at the start of a meeting every player, ghosts included, stands on the centre of their own floor tile in the Auditorium with direction 0. On the campus map with 10 players that means 10 different tiles, each in "Auditorium" (`area_at`), none `blocked()`, no two neighbouring;
    - a vote for a living player and a skip are accepted; the voter appears in everyone's `voted` and in their own `my_vote`;
    - a majority (e.g. 3 votes for one player, 1 for another, 1 skip) → that player is a ghost, no new failed exam lies on the floor, `result` shows the counts and `surfing` (A4);
    - after `RESULT_SECONDS`: phase `playing`, no failed exams, every examiner's cooldown is a full 20 s again, players can move again;
    - student win by vote: the only examiner is voted out → `ended`, winner students, after the result time. With 7 players, voting out one of two examiners lets the game go on, and voting out the second ends it with a student win;
    - examiner win after a vote: voting out a student so that living examiners equal living students → `ended`, winner examiners;
    - after a new round every player can ring the bell again.
  - Rejected (each leaves phase, players (position, direction, alive, bell), votes, timer and failed exams unchanged):
    - report by a ghost; with the exam one pixel beyond `REPORT_RANGE`; with an unknown exam id; with an exam id that is not a string or missing; in `lobby`, in `meeting` and in `ended`; of an exam removed by the previous meeting; an unknown exam and an exam out of reach give the same reason;
    - bell rung a second time by the same player (after the first meeting); by a ghost; in `lobby`, in `meeting` and in `ended`;
    - vote in `lobby`, in `playing` and in `ended`; by a ghost; a second vote by the same player (same or another target); for a ghost; for an unknown id; with a target that is a number, `null`, a list or missing; after the voting has closed (during the result);
    - during a meeting: movement input (the position is unchanged after `step()`), an expel by an examiner in range with the cooldown over, join, start and restart;
    - `report`, `bell` and `vote` before joining are rejected by `parse_message`.
  - Edge cases:
    - in the same tick: report then bell → one meeting (reason "report"), the bell is rejected and not used up; bell then report; two players reporting the same exam; two players ringing the bell;
    - in the same tick: report then expel → the expel is rejected; expel then a report of the new exam → accepted; an expel that ends the game, then a report → "Game is over";
    - a report from exactly `REPORT_RANGE` away is accepted;
    - the timer: a vote one tick before 60 s is accepted; after exactly 60 s the voting has closed and a vote is rejected; those who did not vote count as skips;
    - nobody votes → nobody is sent surfing and the game goes on;
    - a 2–2 tie between two players → nobody; one player's votes equal to the skips → nobody; more skips than any player's votes → nobody; one vote for a player while everyone else lets the timer run out → nobody (the non-voters count as skips);
    - a vote for oneself counts;
    - the voting closes at the next tick once every living player has voted, without waiting for ghosts or the timer;
    - leaving during the vote: the leaver's vote and the votes for them are removed, and those voters can vote again; when everyone remaining has voted, the voting closes; the only examiner leaving ends the game with a student win;
    - a player sent surfing cannot report, ring, vote in the next meeting or expel; a student sent surfing leaves no failed exam;
    - vision in a meeting: a living player receives all living players and all failed exams at any distance but no ghosts; a ghost receives everyone; after the meeting the radius applies again;
    - privacy: while voting, no snapshot contains whom another player voted for; the result contains only counts and `surfing`; a student's snapshot during and after a meeting contains no other player's role;
    - an examiner whose cooldown was over before the meeting is rejected one tick before 20 s after the meeting end and accepted at exactly 20 s;
    - restart and the last player leaving clear the meeting and the bell use;
    - the campus map has an area "Auditorium" with at least `MAX_PLAYERS` floor tiles.
- WebSocket tests (same file), with 4 clients:
  - one rings the bell → every client receives `meeting` with reason "bell";
  - all four vote for the same student → every client receives the result with that count and `surfing`, and the student's own state shows `alive: false`;
  - a second vote over the socket gets an error with a reason, and the connection stays usable.
- `uv run pytest` passes; the output is pasted. Existing tests still pass unchanged.
- Manual check with 4 browser windows locally, then one report-and-vote round on the deployed URL:
  - the Report button appears only for a living player next to a failed exam. Reporting opens the meeting screen in all windows, everyone stands in the Auditorium, and the arrow keys move nobody;
  - the timer counts down in all windows at the same pace. A "voted" mark appears in every window when someone votes, and nobody sees for whom;
  - a majority shows the result screen for 5 s with the counts in all windows. The window voted out shows "You have been sent surfing" and the ghost view. Afterwards the failed exams are gone, the darkness is back and the examiner's Expel button counts down from 20;
  - a 2–2 tie shows "Nobody was sent surfing";
  - the Bell button works once, then shows "Bell used". A ghost window has no Report, Bell or vote buttons;
  - letting the timer run out ends the voting after 60 s;
  - voting out the only examiner leads to "Students win!" after the result screen;
  - a second vote sent from the browser console (`send({type: "vote", target: "skip"})`) shows "You have already voted" as a toast.
