# Manual test checklist

Click through this on the **deployed app** (https://expelled-nova.onrender.com) before the
demo and after every deploy. The automated tests (`uv run pytest`) cover the rules; this
list covers what only a real browser shows: drawing, layout, phones, sound and the deployed
server.

## Setup
- Open the app once and wait until it has woken up (up to a minute on the free server).
- Open **4 browser windows** side by side (A, B, C, D), plus **one phone** that joins via the
  QR code. Use separate windows, not background tabs: browsers slow down hidden tabs.
- Mark each line ✅ or write down what happened (window, steps, what you saw).
- **Sending a raw message:** some checks need a message that the page never sends. Open the
  browser's developer console in that window and type `send({...})`. The answer appears as a
  short message (toast) at the bottom of the game.

## 1. Join (BRD EX01, A6)
- [ ] A: empty nickname → "Nickname must not be empty"; nothing else happens.
- [ ] A: a 17th character cannot be typed (the field stops at 16).
- [ ] A: `Ann!` → "Nickname may only contain letters, digits and spaces".
- [ ] A joins as "Ana" with a hat and a colour. The lobby shows Ana as host.
- [ ] B: `ana` (same name, other case) → "Nickname is already taken".
- [ ] B: Ana's colour is shown as taken on the ID card; B joins as "Ben" with another colour.
- [ ] C and D join ("Cleo", "Dan"). The phone joins by scanning the QR code from "Invite players".
- [ ] Each window shows everyone in the class roster with the right hat and colour.

## 2. Lobby and host (EX09)
- [ ] B (not host) has no start button. In B's console `send({type: "start"})` → "Only the host can start the game".
- [ ] B: `send({type: "settings", expellers: 1})` → "Only the host can change the settings".
- [ ] B: `send({type: "kick", target: "p1"})` → "Only the host can remove players".
- [ ] A: sets "Undercover Examiners" to 2 with 5 players (4 windows + phone) → start is rejected with "2 examiners need at least 6 players"; back to automatic.
- [ ] A: "Make host" on B's line → B is host; B hands it back.
- [ ] B, C, D press "Vote host" on Cleo's line: the count rises; at 3 of 5 votes Cleo becomes host, and the votes are cleared.
- [ ] Cleo (host): "Remove" on the phone's line, tap twice → the phone goes back to the ID card with a note. The phone joins again.
- [ ] Moving in the lobby works for everyone (WASD, arrow keys, joystick on the phone).

## 3. A round (EX02–EX05, EX07, A1–A5)
- [ ] The host starts. Each window sees its own role card; with 5 players there is 1 examiner.
- [ ] A student never sees anyone's role. An examiner sees the fellow examiner's name if there are 2.
- [ ] Walking into a wall: the character stops at the wall and slides round corners.
- [ ] The phone and a laptop on another network see each other move smoothly.
- [ ] The to-do list shows 5 errands (4–5 players). Doing one: walk to the glowing object, press Use (F), solve it → it is ticked and the shared bar grows.
- [ ] Wrong mini-game answers show a note; walking away cancels the task.
- [ ] Examiner tries to expel at once → greyed button with the cooldown (30 s at the start).
- [ ] Examiner too far away → "Too far away". Nothing changes.
- [ ] Examiner expels a student next to them: "EXPELLED!" stamp for both; the student becomes a ghost, walks through walls and sees everyone; the exam lies on the floor.
- [ ] The examiner's expel button now counts down 30 s again.
- [ ] Vents: the examiner climbs in (V), moves with the arrows, climbs out; others only see a hatch move.

## 4. Meeting, chat and vote (EX07, EX12, A4)
- [ ] A living student next to the exam reports it (R): everyone is placed round the table.
- [ ] The ghost cannot report, vote or chat ("Ghosts cannot chat. You can still read along.").
- [ ] Chat: an empty message is not sent; a long message stops at 80 characters; two messages within 1.5 s → "Slow down".
- [ ] Voting for yourself is not possible. A tie (or a skip majority) sends nobody.
- [ ] A majority sends the chosen player surfing; after the result everyone sees who voted for whom.
- [ ] The meeting button at the table works once per player per round; a second press → "You have already called a meeting". Far from the table → "Too far from the meeting table".
- [ ] During a meeting, closing one window: the player stays in the meeting, marked away.

## 5. Sabotage and the guard (EX10, EX11, A7)
- [ ] Examiner sabotage → campus map with three emergencies. The red arrow shows everyone where to go.
- [ ] Lights out: students see very little; anyone at the switch in Student Services for 3 s turns them on.
- [ ] Wi-Fi down: running tasks break off, new ones → "No Wi-Fi. Try again later."; the router in the Library (3 s) fixes it.
- [ ] Fire alarm: every living student reaches the EDP Plaza within 40 s, or the examiners win.
- [ ] Right after an emergency the sabotage button is greyed with its cooldown; in a console `send({type: "sabotage", kind: "fire"})` → "Sabotage cooldown: … s left" (or "An emergency is already running" while one runs).
- [ ] An expel in the guard's view cone starts a security meeting naming the examiner.

## 6. End, next round, leaving (EX08, EX16, A9)
- [ ] When a side wins, everyone sees the winner and every role.
- [ ] "New round" (any player) takes everyone back to the lobby; the host starts again.
- [ ] During a round a non-host ends it from the handbook ("End this round for everyone", tap twice).
- [ ] During a round, reload one window and enrol with the same nickname → back in the same role.
- [ ] During a round, close one window, open the app again in the same browser and enrol with the same nickname → back in the same role.
- [ ] The same nickname from another browser or device (no rejoin token there) → "Nickname is already taken".
- [ ] A new nickname during a round joins as a ghost.
- [ ] With a connected player's nickname → "Nickname is already taken".
- [ ] "Leave the game" (tap twice) → back to the ID card; the others see the player gone.

## 7. Invalid messages (R15)
- [ ] In a console: `socket.send("not json")` → "Message is not valid JSON".
- [ ] `send({type: "fly"})` → "Unknown message type".
- [ ] `send({type: "input", dx: 5, dy: 0})` → "dx and dy must each be -1, 0 or 1"; the character does not move.
- [ ] `send({type: "expel", target: "p1"})` from a student → "Only examiners can expel".
- [ ] `send({type: "vote", target: "p1"})` outside a meeting → "No meeting is running".
- [ ] After every error the game goes on normally in that window.

## 8. Page, phone and sound (EX13–EX15)
- [ ] The handbook (?) says "at least five errands" and "30 seconds".
- [ ] Phone: nothing gets selected by tapping the joystick; the to-do list and roster fold by tapping their titles; "You have been expelled" never covers the buttons.
- [ ] Campus map (C or the map button) shows the own position and open tasks.
- [ ] Sound panel: effects, music and volume work; muting stays after a reload.
- [ ] No errors in the developer console of any window during the whole session.
