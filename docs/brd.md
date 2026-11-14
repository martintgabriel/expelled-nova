# Expelled! (working title) — Business requirements

Team project · Introduction to Programming 2026/27 · Nova SBE · Version 1.0 · 14 November 2026
Team: Martin Gabriel, Cornelius Paprottka, Manuel Ritter, Leonard Kowall

## The opportunity
Nova students share one campus, too many deadlines and the fear of a failed exam. We build a live multiplayer social-deduction game set on a stylised Nova campus: students complete everyday admin tasks while undercover examiners try to get them expelled. A round takes 2–3 minutes, so a group, including our demo audience, can join from their own devices and play together.

## First release
One campus map with about six recognisable areas, 4–10 players per game, live movement, secret roles, tasks, expelling, meetings with votes and two win conditions. One game runs at a time. Name, characters and graphics are our own.

## The user journey
The host opens the game and shares the link. Players join with a nickname; the host starts, and each player secretly learns their role. Students walk the campus doing tasks; examiners blend in and hand out failing exams. When a failed exam is found or the bell is rung, everyone meets, discusses and votes someone out ("sent surfing"). The round ends when one side wins; the host can start a new round.

## Required capabilities
- **EX01 Join** — Join via the shared link with a valid nickname. The first player is the host and starts the game once at least 4 players are in.
- **EX02 Live movement** — Players move with the keyboard. Everyone sees nearby players move smoothly; walls block movement; vision is limited to a radius.
- **EX03 Secret roles** — The server assigns 1 examiner (4–6 players) or 2 (7–10). Each player sees only their own role; examiners also see each other.
- **EX04 Tasks** — Each student gets 3 tasks at fixed places (e.g. submit the Bachelor certificate at Student Services, get help at the Portuguese-only Helpdesk, print at the Library). A shared bar shows overall progress.
- **EX05 Expel** — An examiner next to a student hands out a failing exam (6/20). The student is expelled, becomes a ghost and the exam stays on the floor.
- **EX06 Staff doors** — Examiners travel between staff doors and choose the destination.
- **EX07 Meeting and vote** — A living player who finds an exam reports it, or rings the bell (once per player per game). Everyone meets in the Auditorium, discusses (timer) and votes or skips.
- **EX08 End and replay** — The winner is shown with all roles revealed; the host can start a new round with the same players.

## Business rules
- **R1** The server decides every move and action; the browser only sends inputs. A rejected action changes nothing and shows the reason.
- **R2** A player never receives another player's role (examiners only see fellow examiners).
- **R3** Expelling requires a living examiner, a living student within range, an elapsed cooldown (e.g. 20 s) and no running meeting.
- **R4** A task counts once per student and only at its place. Ghosts can finish their tasks but cannot report, ring or vote.
- **R5** Each living player has one vote per meeting. The most-voted player is sent surfing (becomes a ghost); a tie or a "skip" majority sends no one.
- **R6** Students win when all tasks are done or all examiners are voted out. Examiners win when living examiners are at least as many as living students.
- **R7** If two actions conflict (two reports, an expel while a meeting starts), the first one the server processes wins; the other is rejected.
- **R8** Nicknames have 1–16 characters (letters, digits, spaces) and are unique per game; a game holds at most 10 players.

## What the product must remember
During a game the server keeps players, positions, roles, tasks, cooldowns, votes and the game phase in memory. A server restart ends running games (accepted limit). The first release stores nothing permanently; accounts and match history come with F6.

## Acceptance criteria
- **A1 Live** — On the deployed URL, two devices (one on mobile data) see each other move smoothly; walking into a wall does not move the player.
- **A2 Rejected expel** — An examiner out of range or on cooldown tries to expel: nothing changes, a reason is shown.
- **A3 Secret roles** — As a student, nothing the browser receives reveals another player's role.
- **A4 Vote** — After a report, a majority sends the chosen player surfing; a tie sends no one.
- **A5 Win** — Finishing all tasks ends the game with a student win; expelling until examiners equal students ends it with an examiner win.
- **A6 Invalid join** — An empty, too long or duplicate nickname and an 11th player are rejected with a message.

## Scope boundaries
Not in the first release: accounts, chat, sabotage, special roles, the Segway security guard, phone controls, sound, 3D, several parallel games. No names, characters or graphics from existing games; no Google Maps or Street View images in the repository (reference only); no real people (staff, professors) by name or photo.

## Roadmap after the first release (one spec and one pull request each)
F1 Segway security guard: patrols a fixed route; an examiner who expels inside his view cone is caught · F2 Phone controls and QR-code join (needed for the demo) · F3 More Nova tasks as mini-games · F4 Sabotage (eduroam outage hides the map, fire alarm) · F5 Text chat in meetings · F6 Accounts, stats and leaderboard (Supabase) · F7 Special roles · F8 Host settings and room codes for parallel games · F9 Projector view for spectators · F10 Sound and polish
