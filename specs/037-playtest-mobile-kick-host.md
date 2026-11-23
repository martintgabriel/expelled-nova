# Spec 037 — Playtest fixes: more tasks, kick, take over host, phone layout

## Why
Playtest of 23 Nov (evening, 4 and then 7 players, several on phones):
- Rounds with 4 players were over in about 2 minutes: everyone had only 3 tasks.
- A player who had left stayed in the lobby, and nobody could remove them.
- When the host is away from the keyboard, nobody can start or change anything.
- Players could not get back in: "Nickname is already taken" (their old connection on the
  phone was still open).
- There was no way to leave a game except closing the tab.
- Nobody found the light switch: first-time players need to be shown where to go for
  lights, fire alarm and Wi-Fi.
- Ghosts saw no chat field and thought the chat was broken.
- The handbook says "fail them all", but the game is about expelling.
- On a phone: tapping the joystick several times selects the whole page; the to-do list and
  the class roster cover the character; "You have been expelled" covers the buttons.
Builds on spec 015 (host), 019 (task count), 023 (sabotages), 029 (chat) and 036.

## What

### A. More tasks
`tasks_per_player`: 5 tasks for 4–5 players, 6 for 6–7, 7 for 8–10 (still at most the
number of task places on the map).

### B. The host can remove a player (`kick`)
`{"type": "kick", "target": id}`: only the host, never themselves, at any time (lobby,
round, meeting, end screen). The player leaves the game exactly as if they had left
(`leave`, which decides the game if needed), their connection is told
`{"type": "kicked"}` and closed. In the lobby each line of the class roster has a
"Remove" button for the host, next to "Make host".

### C. Electing a new host in the lobby (`vote_host`)
`{"type": "vote_host", "target": id | null}`: in the lobby every player can vote for who
should be host (also for themselves; `null` takes the vote back; never for the current
host). As soon as more than half of the players in the game vote for the same player, that
player becomes host and all votes are cleared. Votes of players who left and votes for them
do not count; starting a round clears them. The class roster shows "Vote host 2/3" on every
other player's line (not on the host's screen: the host has "Make host"). Ending a round
stays open to everyone (spec 036).

### D. Enrolling again with the same nickname, also in the lobby
In the lobby, enrolling with the nickname of a player who is already in (any capitals)
makes you that player again, like during a round (spec 036): the older connection of that
player is closed. The new connection is registered before the old one is closed, so the
old one's ending never removes the player.

### E. Leave the game (`leave`)
`{"type": "leave"}`: the player leaves the game (`leave`), the connection gets
`{"type": "left"}`, and the page goes back to the ID card. Button "Leave the game" at the
bottom of the handbook, for everyone, with two taps.

### F. Showing where to go in an emergency
While the lights are out, the fire alarm runs or the Wi-Fi is down, everyone sees a big red
arrow: at the screen's edge pointing towards the place if it is off screen, otherwise
bobbing above it (light switch, assembly point, router).

### G. Chat for ghosts
A ghost in a meeting sees "Ghosts cannot chat. You can still read along." instead of an
empty space where the chat field was.

### H. Wording
The handbook and the role card say "expel them all" instead of "fail them all".

### I. Phone layout (touch screens only; the desktop layout does not change)
1. Nothing in the game can be selected or long-pressed (no text selection, no callout);
   text fields stay normal.
2. The to-do list and the class roster can be folded by tapping their title (also on the
   desktop). On a touch screen they start folded; the title shows the count
   ("Semester to-do 1/5", "Class roster 4/10"). The start and invite buttons stay visible.
3. On a touch screen "You have been expelled" shows at the top, never over the buttons.

## Out of scope
Closing the gap in the glass wall west of the meeting table (row 21, column 26): one of
the ten places in the meeting circle is there. The walking sound; new task kinds; a separate mobile app.

## Done when
- `tests/test_spec037.py` covers A–I.
- Test changes made by this spec: the task count of spec 019 (`test_spec019.py`; in
  `test_tasks.py` a fixture keeps the original 3 tasks, so its numbers still check the task
  rules); the same nickname in the lobby is the same player again (`test_websocket.py`,
  `test_game.py`, `test_look.py`).
- All tests pass.
