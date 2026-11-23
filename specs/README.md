# Specs

One spec per change: Why · What · Out of scope · Done when. Old specs are not edited or
deleted: they are the project's history. Where a later spec changed a rule, the later spec
wins; the status column says which one. The current rules are summarised in
[docs/brd.md](../docs/brd.md) (version 2.0).

| No. | Title | What it changed | Status |
|---|---|---|---|
| [001](001-realtime-movement.md) | Live movement on the campus map | Project skeleton, map as data, join, server movement at 20 Hz, browser prediction, Render deploy | partly replaced by 008 (prediction), 009 (map), 011 (sliding), 036 (smooth stopping) |
| [002](002-lobby-host-roles.md) | Lobby, host and secret roles | Game phases, host, start with at least 4, 1 or 2 examiners, a snapshot per player | partly replaced by 015 (hand over host), 019 (examiner setting), 036 (late join), 037 (kick, host vote) |
| [003](003-expel-ghosts-end.md) | Expel, ghosts, game end and new round | Expel with a cooldown (20 s), ghosts, win check, the host restarts | partly replaced by 008 (ghosts pass walls), 019 (30 s), 036 (anyone ends a round) |
| [004](004-tasks.md) | Nova tasks and the students' task win | Task places, 3 tasks each, progress bar, task win | partly replaced by 012 (mini-games, fake tasks), 019 and 037 (number of tasks) |
| [005](005-look.md) | Look | Colours, current area, `render.js`, vision radius | partly replaced by 010 (line of sight), 022 (hats), 028 (colour picker) |
| [006](006-meeting-vote.md) | Meetings and votes | Report, bell, 60 s vote, sent surfing | partly replaced by 008, 011 (meeting table), 019 (ballots), 029 (chat) |
| [007](007-phone-controls-qr-join.md) | Phone controls and QR-code join | Touch joystick, `/qr.svg`, invite panel | partly replaced by 037 (phone layout) |
| [008](008-fixes-and-mechanics.md) | Fixes and remaining mechanics | Nine parts: matching prediction, no self-vote, ghosts pass walls, the bell at one place, task reliability, staff doors, vision behind walls, lights sabotage, pictograms | partly replaced by 010, 011, 015 (vents), 023, 033 |
| [009](009-nova-campus-map.md) | The Nova campus map | The real campus layout, areas, decor | partly replaced by 011, 015, 034–036 |
| [010](010-line-of-sight-vision.md) | Line-of-sight vision | Darkness with straight shadows from walls | done |
| [011](011-free-movement-meeting-point-walls.md) | Free movement, meeting point and clear walls | Sliding round corners, the meeting table, glass vs walls | done |
| [012](012-task-minigames.md) | Task mini-games and fake tasks | Mini-game framework (`server/minigames.py`), fake tasks for examiners, two-step tasks | partly replaced by 021, 024, 031, 035 (campus mini-games), 019 and 037 (number of tasks) |
| [013](013-start-in-main-entrance.md) | Every match starts in the Main Entrance | Spawn points | done |
| [014](014-ui-redesign.md) | UI redesign | Round action buttons with cooldown rings, meeting screen, lobby | partly replaced by 015, 023, 033 |
| [015](015-story-ui-vents-beach.md) | Story UI, how to play, vents, beach | The handbook, hand over host, vents instead of staff doors, a bigger beach | partly replaced by 028, 037 |
| [016](016-sound-effects.md) | Sound effects | Generated sound effects (`web/sound.js`) | partly replaced by 020, 028 |
| [017](017-music-and-more-sounds.md) | Background music and more sound effects | Generated music and waves (`web/music.js`) | partly replaced by 028 |
| [018](018-campus-map.md) | Campus map (key C) | The campus map overlay (`web/campusmap.js`) | partly replaced by 023, 026 |
| [019](019-playtest-fixes.md) | Playtest fixes, part 1: game rules | Expel cooldown 30 s, 3/4/5 tasks by round size, examiner setting, ballots | partly replaced by 037 (5/6/7 tasks) |
| [020](020-playtest-sound.md) | Playtest fixes, part 2: sound | Volume slider, an "Expelled!" voice, an end sound by winning side | partly replaced by 028 |
| [021](021-cafeteria-and-beach-tasks.md) | Cafeteria tray and Beach surfing | Two new mini-games | done |
| [022](022-hats-and-colours.md) | Hats and a colour of your own | Hat and colour on the ID card | partly replaced by 028 (taken colours) |
| [023](023-sabotage-menu-fire-alarm.md) | Sabotage menu: lights, fire alarm, Wi-Fi down | Three emergencies, one at a time, shared cooldown | partly replaced by 033, 035, 037 (red arrow) |
| [024](024-better-print-and-helpdesk-tasks.md) | Better print and helpdesk tasks | New print and Portuguese helpdesk mini-games | done |
| [025](025-gym-skylight.md) | People in the gym | Decoration: a skylight into the gym with animated figures | done |
| [026](026-colourful-campus-map.md) | A colourful campus map | Colours on the campus map, a hint that it exists | done |
| [027](027-segway-security-guard.md) | Campus Security: the Segway guard | The guard (`server/guard.py`); a seen expel starts a security meeting | partly replaced by 034 (speed), 035 (vision) |
| [028](028-sound-settings-colours-examiner-names.md) | Sound settings, taken colours, examiner names | Sound panel, `/taken-colors`, examiners recognise each other | done |
| [029](029-meeting-chat.md) | Chat in the meeting | Meeting chat (80 characters, 1.5 s, last 30 kept) | partly replaced by 036, 037 (note for ghosts) |
| 030 | — | Never on `main`. Leonard's specs for sound settings, taken colours and examiners recognising each other duplicated Martin's spec 028 (PR #26), so he dropped them (commit 7773d0e, "Drop duplicate 028–030 (Martin's #26 wins)") and numbered his next specs 031–033. The number 030 stayed unused. | — |
| [031](031-shoo-the-seagulls.md) | Shoo the seagulls off your pastel de nata | The `nata` mini-game | done |
| [032](032-expelled-stamp.md) | "EXPELLED!" on screen | A stamp for the examiner and the student involved | done |
| [033](033-examiners-can-fix-the-lights.md) | Examiners can turn the lights back on | Every living player can fix | done |
| [034](034-campus-edge-and-calmer-guard.md) | Campus edge and a calmer guard | The campus surroundings, a slower guard | partly replaced by 035 |
| [035](035-bugfixes-after-playtest.md) | Playtest of 23 Nov: bugfixes | Fire alarm counts everyone and names who did not come, guard vision, new west-side games, campus names | partly replaced by 036 |
| [036](036-never-stuck-and-campus-polish.md) | Never stuck, smooth stopping, campus polish | Away and rejoin, late join as a ghost, the host moves on, anyone ends a round, smooth stopping | partly replaced by 037 (a nickname in use is never taken over) |
| [037](037-playtest-mobile-kick-host.md) | Playtest fixes: tasks, kick, host, phone | 5/6/7 tasks, kick, host vote, leave, emergency arrow, phone layout | done |
| [038](038-review-tests-security-lean.md) | Review, tests, security, leaner code | Audit (`docs/review.md`), docs, tests, security, refactoring | in progress |
