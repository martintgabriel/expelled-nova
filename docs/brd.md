# Expelled! — Business requirements

Team project · Introduction to Programming 2026/27 · Nova SBE · **Version 2.0 · 23 November 2026**
Team: Martin Gabriel, Cornelius Paprottka, Manuel Ritter, Leonard Kowall

Version 2.0 describes the game as it is built today (specs 001–037). Every number below
is checked against `server/game.py` and `server/campus.json`. The IDs of version 1.0
(EX01–EX08, R1–R8, A1–A6) are kept so older specs still match; new items have new IDs.
Version 1.0 (14 November 2026) is in the git history; the table at the end lists what
changed.

## The opportunity
Nova students share one campus, too many deadlines and the fear of a failed exam. We build a
live multiplayer social-deduction game set on a stylised Nova campus: students complete
everyday admin tasks while undercover examiners try to get them expelled. A round takes a few
minutes, so a group, including our demo audience, can join from their own laptops and phones
and play together.

## The product today
One campus map (46 × 43 tiles: seven areas plus beach, plaza, gym, lecture halls and
courtyards), 4–10 players in one shared game, live movement, secret roles, mini-game tasks,
expelling, vents, three sabotages, a Segway security guard, meetings with chat and votes, two
win conditions, phone controls with QR-code join, sound and music. One game runs at a time.
Name, characters and graphics are our own; everything is drawn from simple shapes and
generated sounds, with no image or audio files.

## The user journey
The host opens the game and shares the link or the QR code. Players fill in an ID card
(nickname, hat, colour) and join the lobby; the host chooses the number of examiners and
starts. Each player secretly learns their role. Students walk the campus solving their
errands; examiners blend in, hand out failed exams, use the vents and set off sabotages. When
a failed exam is found, the meeting button at the table is pressed or the security guard sees
an expel, everyone meets at the table, chats, and votes someone out ("sent surfing"). The
round ends when one side wins; all roles are revealed, and anyone can take the group back to
the lobby for the next round.

## Capabilities

| ID | Capability | What it does today |
|---|---|---|
| **EX01** | Join | Join via the shared link or QR code with a valid nickname, a hat (10) and a colour (10, taken colours shown). The first player is the host; the host starts once at least 4 players are in. |
| **EX02** | Live movement | Keyboard (WASD or arrows) or touch joystick. The server moves everyone 20 times per second at 160 px/s; the browser predicts the own character with the same rule. Walls block living players and they slide round corners. A living player sees 6 tiles with line of sight; ghosts pass walls and see everything. |
| **EX03** | Secret roles | The server deals 1 examiner for 4–6 players and 2 for 7–10, or what the host chose (1 or 2; 2 needs at least 6 players). Each player sees only their own role; examiners also see each other's names. |
| **EX04** | Tasks | Each player gets 5 tasks with 4–5 players, 6 with 6–7 and 7 with 8–10, at fixed places on campus (11 tasks, one with two steps; 12 mini-game kinds, e.g. print at the Library, the Helpdesk in Portuguese, a tray at the Cafeteria, a wave at Carcavelos). Examiners get the same number of fake tasks that never count. A shared bar shows the students' overall progress. |
| **EX05** | Expel | An examiner next to a student hands out a failed exam (6/20). The student is expelled, becomes a ghost and the exam stays on the floor; both see an "EXPELLED!" stamp. |
| **EX06** | Vents (were staff doors) | Examiners climb into one of 4 floor vents, travel unseen to another vent and climb out there. Others only see a hatch move. |
| **EX07** | Meeting and vote | A living player reports a failed exam within reach, or presses the meeting button at the meeting table (once per player per round). Everyone meets at the table, discusses and votes for a player or skips. |
| **EX08** | End and next round | The winner is shown with all roles revealed. Any player takes everyone back to the lobby; the host starts the next round with the same players. |
| **EX09** | Host and lobby | The host chooses the number of examiners, hands the host role to another player, and removes ("kicks") a player at any time. In the lobby the players can elect a new host by majority. |
| **EX10** | Sabotage | Examiners pick an emergency on the campus map: lights out, fire alarm or Wi-Fi down. Every player sees a red arrow to the place where it is solved. |
| **EX11** | Campus Security | A security guard on a Segway patrols the campus on a random route. An examiner he sees expel a student is caught: a security meeting starts and names them. |
| **EX12** | Meeting chat | Living players write short messages during the vote; ghosts read along. |
| **EX13** | Phone play | Touch joystick and round action buttons, QR-code join, a phone layout with foldable to-do list and roster. |
| **EX14** | Campus map | A map of the whole campus (key C or the map button) with the own position and open tasks, to say where one was. |
| **EX15** | Sound and music | Generated sound effects, background music and beach waves, with a sound panel (effects, music, volume). |
| **EX16** | Leave and come back | "Leave the game" at any time. A player whose connection drops during a round stays in it (marked away) and can come back with the same nickname. A new player can join a running round as a ghost. |

## Business rules

| ID | Rule |
|---|---|
| **R1** | The server decides every move and action; the browser only sends inputs. A rejected action changes nothing and shows the reason. |
| **R2** | A player never receives another player's role before the end (examiners only see fellow examiners). Roles are revealed to everyone when the round ends. |
| **R3** | Expelling requires a living examiner outside a vent, a living student within 48 px (1.5 tiles), an elapsed cooldown of 30 s and no running meeting. The cooldown also runs from the start of the round and from the end of every meeting. |
| **R4** | A task counts once per student and only at its place (within 48 px). Ghost students can finish their tasks; ghosts cannot report, call a meeting, vote or chat. No task can start during a Wi-Fi outage. |
| **R5** | Each living player has one vote per meeting; nobody votes for themselves. Voting lasts 60 s or until every living player has voted; whoever did not vote counts as a skip. The player with the most votes is sent surfing (becomes a ghost) only with more votes than any other player and more than the skips; a tie or a skip majority sends no one. The result shows for 5 s, with who voted for whom. Failed exams are cleared after every meeting. |
| **R6** | Students win when all students' tasks are done or no living examiner is left. Examiners win when living examiners are at least as many as living students, or when the fire alarm runs out. |
| **R7** | If two actions conflict (two reports, an expel while a meeting starts), the first one the server processes wins; the other is rejected. |
| **R8** | Nicknames have 1–16 characters (letters, digits, spaces) and are unique per game, ignoring case; a game holds at most 10 players. A nickname of a connected player is never taken over. |
| **R9** | One emergency runs at a time. The sabotage cooldown (30 s) is shared by all examiners and runs from the start of the round, from the end of each emergency and from the end of every meeting. A meeting ends every emergency and turns the lights on. Lights out: living students see only 1.5 tiles until any living player stays at the light switch in Student Services for 3 s. Fire alarm: every living student must reach the assembly point on the EDP Plaza within 40 s. Wi-Fi down: running tasks break off and none can start until a living player restarts the router in the Library (3 s). |
| **R10** | The meeting button works only at the meeting table (within 48 px of its edge), once per player per round, not during the fire alarm. Reports still work during the fire alarm. |
| **R11** | The guard moves at 1.2 × the players' speed and sees 6 tiles in a 100° cone. If he sees the examiner or the student at the moment of an expel, a security meeting starts naming that examiner. |
| **R12** | Only the host starts a round, changes the settings (lobby only) and kicks players (any time, never themselves). The host hands over in the lobby only. A lobby host vote wins when more than half of the players in the game vote for the same player. If the host leaves, the player who has been in the game longest becomes host. |
| **R13** | In the lobby a lost connection removes the player. During a round the player stays (standing still, marked away) and may come back with the same nickname; if nobody is connected any more, an empty lobby opens. A new nickname during a round joins as a ghost without tasks (not during a meeting, not when the game is full). Any player in the game can end a running or finished round. |
| **R14** | Chat: living players only, while the vote is open; 1–80 characters, no line breaks or control characters, one message per player every 1.5 s; a meeting keeps the last 30 messages. |
| **R15** | Every message from a browser is checked: at most 512 bytes, valid JSON, a known type, allowed in the current phase, at most 30 messages per second per connection. |

## What the product must remember
The fixed content (the map, areas, tasks, vents, sabotage places and the guard's route) is
loaded from `server/campus.json` when the server starts. During a game the server keeps
players, positions, roles, tasks, cooldowns, votes, chat and the game phase in memory only.
A server restart ends a running game (accepted limit). Nothing is stored permanently: no
accounts, no cookies, no match history. The browser remembers only the own nickname, look
and sound settings (local storage).

## Acceptance criteria

| ID | Criterion |
|---|---|
| **A1** Live | On the deployed URL, two devices (one on mobile data) see each other move smoothly; walking into a wall does not move the player. |
| **A2** Rejected expel | An examiner out of range or on cooldown tries to expel: nothing changes, a reason is shown. |
| **A3** Secret roles | As a student, nothing the browser receives during a round reveals another player's role. |
| **A4** Vote | After a report, a majority sends the chosen player surfing; a tie sends no one. |
| **A5** Win | Finishing all tasks ends the round with a student win; expelling until examiners equal students ends it with an examiner win. |
| **A6** Invalid join | An empty, too long or duplicate nickname and an 11th player are rejected with a message. |
| **A7** Sabotage | The lights go out for students until someone fixes them at the switch; a fire alarm that not every living student answers within 40 s ends the round with an examiner win. |
| **A8** Host | Only the host can start, change the settings and kick; a kicked player's page is told and goes back to the ID card; a lobby majority elects a new host. |
| **A9** Come back | A player whose connection drops during a round comes back with the same nickname into the same role; a nickname of a connected player is rejected. |
| **A10** Handbook | Every number in the in-game handbook matches the rules (guarded by `tests/test_spec038.py`). |

## Scope boundaries
Not in the product: accounts, statistics or a leaderboard; special roles; several parallel
games or room codes; a projector view for spectators; permanent storage of any kind; 3D. No
names, characters or graphics from existing games; no Google Maps or Street View images in the
repository (reference only); no real people (staff, professors) by name or photo.

## Roadmap

| Item | Status |
|---|---|
| F1 Segway security guard | delivered (spec 027; tuned in 034, 035) |
| F2 Phone controls and QR-code join | delivered (spec 007; phone layout 037) |
| F3 More Nova tasks as mini-games | delivered (specs 012, 021, 024, 031) |
| F4 Sabotage (eduroam outage, fire alarm) | delivered (lights 008, menu with fire alarm and Wi-Fi 023; examiners fix 033) |
| F5 Text chat in meetings | delivered (spec 029) |
| F6 Accounts, stats and leaderboard (Supabase) | open |
| F7 Special roles | open |
| F8 Host settings and room codes for parallel games | partly: host settings delivered (019); room codes and parallel games open |
| F9 Projector view for spectators | open |
| F10 Sound and polish | delivered (specs 016, 017, 020, 028, 032) |

## Changes from v1.0

| Change | Reason | Spec |
|---|---|---|
| Tasks are mini-games; examiners get fake tasks | a task was only "stand next to it": nothing to do, and an idle examiner was easy to spot | 012 |
| Tasks per player 3 → 3/4/5 → 5/6/7 by round size | rounds ended too fast in the playtests of 23 Nov | 019, 037 |
| Expel cooldown 20 s → 30 s | the examiner could expel again too soon (playtest) | 019 |
| Staff doors → 4 vents | staff doors worked differently from the vents players know from the genre | 008, 015 |
| Bell anywhere → meeting button at the meeting table, once per round; meetings at the table instead of the Auditorium | the bell was a placeholder; one central meeting point | 008, 011 |
| Ghosts pass walls; vision follows line of sight | ghosts got stuck; vision looked wrong | 008, 010 |
| Host can hand over, be voted in and kick; the host role moves on when the host leaves | the game was stuck when the host left or was away; a player who left stayed in the lobby | 015, 036, 037 |
| Anyone can end a round; a lost connection keeps the player in the round; late join as a ghost | the host lost the connection and nobody could continue (playtest) | 036, 037 |
| No vote for yourself; ballots shown after counting | a bug; nobody could see who voted for whom | 008, 019 |
| Sabotage, guard, chat, phone controls, sound and music added | roadmap items F1–F5 and F10 | 007, 008, 016, 017, 023, 027, 029 |
| EX09–EX16, R9–R15 and A7–A10 added | describe what the later specs built | 007–038 |
