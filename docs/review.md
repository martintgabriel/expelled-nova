# Review of Expelled! (spec 038, part 1)

An audit of `main` as of 23 Nov 2026, after spec 037 was merged. Nothing in the code was changed. There are four audits: requirements, security and privacy, tests, and leanness. Each one is followed by the contradictions between the specs and the code.

**Severity:**
- **must-fix**: breaks a requirement or a graded point, or is a reproduced bug.
- **should**: weakens a graded point.
- **nice**: polish.

**How the findings were checked:**
- Every must-fix item was re-read in the code. The ones marked *(reproduced)* were also run in memory.
- Items marked *(code path only)* are still to be confirmed by a failing test in part 3 or part 4 before anything is fixed.
- Evidence is `file:function` or `file:line` (line numbers as of this audit).

## Test run

`uv run pytest` (run with `-p no:cacheprovider` so that no files are written):

```
1428 passed, 1 warning in 55.30s
```

The one warning is `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`. It comes from a dev dependency and does not affect the game.

## Must-fix summary

| ID | Finding | Fixed in |
|---|---|---|
| M1 | The handbook says "three errands" and "wait 20 seconds" (`web/index.html:443, 450`). The code deals 5/6/7 tasks (`tasks_per_player`, spec 037) and `EXPEL_COOLDOWN = 30` (spec 019). | part 2, with a guard test |
| M2 | The browser still has `const EXPEL_COOLDOWN = 20` (`web/main.js:24`, labelled "REPEATS SERVER RULE"). `setCooldownRing` uses `min(1, left/20)` (`main.js:982–991`), so the expel button's ring stays full for the first 10 of the 30 s. Every examiner sees this in every round. | part 2 or 3 (decision needed) |
| M3 | Phantom player *(reproduced)*. In `server/main.py:152–184`, `game.join()` adds the player before `await ws.send_json(welcome)`, and the socket is registered in `connections` only after that send. If the client is already gone, the send raises `WebSocketDisconnect`. `finally` (line 249) then sees `connections.get(player_id) is not ws` and never calls `game.disconnect`. The player stays: not away, holding a slot and a nickname, possibly the host. Ten join-then-close connections fill the game, and only a restart helps. | part 4 |
| M4 | Unhandled `OverflowError` *(reproduced)*. A stop message with a huge integer in `at` (`{"x": 999…9}`, 458 bytes) makes `math.isfinite()` raise `OverflowError` in `Game.set_input` (`game.py:1555`). That is not a `GameError`, so it escapes the handler. The sender is disconnected (in the lobby: removed) and the server logs a traceback. This breaks "validate every message" in AGENTS.md. | part 4 |
| M5 | One slow reader stalls everyone *(code path only)*. `game_loop` (`main.py:75–79`) awaits `ws.send_text` for each player in turn with no timeout. Once a client stops reading (a phone on bad mobile data, or on purpose), uvicorn pauses writing at about 64 KiB, which is about 2 s of state at 20 Hz. The tick then waits for that one client, so every player freezes. | part 4 (test first) |
| M6 | The walkthrough documents are missing: README "How it works", `docs/ARCHITECTURE.md`, `specs/README.md`, `docs/manual-test-checklist.md` and `docs/walkthrough.md`. | parts 2, 3, 6 |
| M7 | No end-to-end WebSocket test plays a whole round with several clients (join → start → task → report → meeting with chat and vote → ejection → end → restart). `report`, `end_round`, `vote_host`, `task_cancel` and `restart` are never sent over the WebSocket in any test. | part 3 |
| M8 | These rejections have no test at all:<br>• `task_input`: Unknown player, Game is over, not started, non-text task id<br>• `cancel_task`: all five phase/type checks<br>• `kick`, `quit`, `chat`: "Unknown player"<br>• disconnect during a meeting | part 3 |

---

## Audit 1 — Requirements

### Course rubric and the AGENTS.md grading points

| # | Item | Verdict | Evidence | Severity / fix |
|---|---|---|---|---|
| R-1 | It works | partly | One in-memory game (`main.py:42`). Every rejected action returns `{"type":"error","reason":…}` (`main.py:242`). M2–M5 are real bugs. The deployed app could not be checked from here. | must-fix M2–M5 |
| R-2 | Design (UI/UX) | partly | Round action buttons that stay in place; a greyed-out button gives its reason as `title`/`aria-label` (spec 014). Phone layout from spec 037. But the handbook numbers are wrong (M1) and the cooldown ring is wrong (M2). | must-fix M1, M2 |
| R-3 | Scope and ambition | met | 37 specs. Roadmap items built: F1 guard (027), F2 phone and QR (007), F3 mini-games (012/021/024/031), F4 sabotage (008/023), F5 chat (029), F10 sound (016/017/020/028), and part of F8 (host setting, 019). | — |
| R-4 | Verification | partly | 1428 tests pass. Rejections are mostly tested together with "nothing changed" (`tests/test_game.py::test_rejected_expel_changes_nothing`, `tests/test_meeting.py::test_rejected_action_changes_nothing`). Gaps M7 and M8; see audit 3. | must-fix M7, M8 |
| R-5 | Walkthrough | partly | The rules are separated from the network (`server/game.py` has no network code). The documents are missing (M6), and three files are far over 1,000 lines (audit 4). | must-fix M6 |
| AG-1 | Works, including invalid input | partly | `parse_message` (`game.py:291`) checks text, 512 B, JSON, object, a known type, and join first/once. The rate limit is 30 msg/s (`RateLimiter`, `main.py:149`). Exception: M4. | must-fix M4 |
| AG-2 | Results and errors clearly shown | met | Errors in a round show as a toast (`showToast`, `#toast role="status"`). Before joining they show in `#join-error role="alert"` (`showJoinError`). Chat errors also show under the input (spec 036). Small text error: R10. | nice R10 |
| AG-3 | Substantial, consistent scope | met | As R-3. Leftovers from replaced specs: L3, L4, L14–L16. | nice |
| AG-4 | Tests cover accepted, rejected and edge cases | partly | Same tick (`test_meeting.py::test_report_then_expel_in_the_same_tick_rejects_the_expel`), tie (`::test_without_a_clear_majority_nobody_is_sent_surfing`), 11th player (`test_websocket.py::test_eleventh_client_is_rejected_then_a_new_one_joins_after_a_player_leaves`). Gaps: M7, M8, audit 3. | must-fix M7, M8 |
| AG-5 | Security | partly | Host-only checks (`start`, `settings`, `make_host`, `kick`, `restart`), lobby-only checks (`vote_host`, `make_host`, `settings`), secret roles (`snapshot_for`), no `innerHTML` anywhere, pinned dependencies, no secrets. Missing: Origin check, security headers, transport size limit (S8–S12). Robustness: M3–M5. | must-fix M3–M5; should S1–S12 |
| AG-6 | Walkthrough-ready code and docs | partly | The README has only how to run the app, the team and links, and still says "(working title)". | must-fix M6; should R2 |

### BRD capabilities, rules and acceptance criteria

| ID | Verdict | Evidence (code · test) | Note |
|---|---|---|---|
| EX01 Join | met (changed by 015/036/037) | `Game.join`, `validate_nickname`; the first player is host (`game.py:447`); start needs ≥4 · `test_game.py::test_new_game_is_in_lobby_and_first_player_is_host`, `::test_start_with_three_players_is_rejected` | 015 make_host, 036 late join as a ghost, 037 kick and host vote |
| EX02 Live movement | met (changed by 008/010/011/036) | `Game.step`, `_walk`, `_move_axis`, `_in_sight` · `test_websocket.py::test_client_b_sees_client_a_move`, `test_game.py::test_moving_into_wall_is_rejected_and_position_unchanged` | Stop messages with `at` weaken it (S7) |
| EX03 Secret roles | met (changed by 019) | `examiner_count`, `snapshot_for` · `test_websocket.py::test_host_starts_and_each_client_gets_only_its_own_role` | The host can force 1 or 2 examiners |
| EX04 Tasks | met (changed by 012/019/037) | `tasks_per_player` 5/6/7 (`game.py:343`), mini-games, fake tasks for examiners · `test_spec037.py::test_a_more_tasks_per_player` | The BRD still says 3 (R3) |
| EX05 Expel | met | `Game.expel` (`game.py:717`) · `test_game.py::test_examiner_expels_student_in_range_after_cooldown` | — |
| EX06 Staff doors | met (replaced by 015: vents) | `enter_vent`, `move_vent`, `leave_vent` · `tests/test_spec015.py` | The client still says "door" (L14) |
| EX07 Meeting and vote | met (changed by 008/011/029) | `report`, `call_meeting` (once per round, `meeting_used` reset in `_reset_round`), `vote`, `MEETING_SECONDS = 60` · `test_meeting.py::test_majority_sends_a_player_surfing` | The BRD says bell, Auditorium and "once per game"; the code has a meeting table and once per round |
| EX08 End and replay | met (changed by 036) | `_end`; roles and the winner only in ENDED; `end_round` by anyone · `test_game.py::test_all_roles_and_the_winner_are_shown_at_the_end` | The client no longer sends `restart` (L16) |
| R1 Server decides; a rejection shows its reason | partly | All actions are checked on the server; errors reach the toast | S7: stop messages with `at` move a player without a limit |
| R2 No role leaves the server | partly | `snapshot_for` · `test_game.py::test_no_snapshot_shows_other_roles_before_the_end`, `test_spec028.py::test_a_student_snapshot_has_no_fellow_examiner_information` | S3, S4 and S5 leak roles indirectly; 027's `caught` and 035's `fire_missing` name players by design |
| R3 Expel conditions | met (changed by 019: 30 s) | `Game.expel` · `test_game.py::test_rejected_expel_changes_nothing` | — |
| R4 Task once, at its place; ghosts | met | `task`, `_finish_step` · `test_tasks.py::test_reliability_a_finished_task_counts_once`, `test_meeting.py::test_a_student_sent_surfing_is_a_ghost_who_can_no_longer_report_ring_or_vote` | — |
| R5 One vote; tie or skip sends no one | met | `_close_voting` · `test_meeting.py::test_without_a_clear_majority_nobody_is_sent_surfing` | Players who are away still count as living (R9) |
| R6 Win conditions | met (extended by 023: fire alarm) | `_check_win`, `_all_tasks_done` · `test_game.py::test_examiners_win_when_they_equal_the_living_students` | — |
| R7 First processed wins | met | `_check_meeting_caller`, `expel` · `test_game.py::test_two_expels_of_the_same_student_in_one_tick_first_wins` | — |
| R8 Nickname rules, ≤10 players | met | `validate_nickname`, `MAX_PLAYERS` · `test_game.py::test_invalid_nicknames_are_rejected`, `::test_eleventh_player_is_rejected` | Any Unicode letter is allowed (S14) |
| A1 Live on two devices | not checked here | Covered by tests only; needs the manual checklist on the deployed app | — |
| A2 Rejected expel | met | `test_game.py::test_rejected_expel_changes_nothing`, `test_websocket.py` ("Too far away") | — |
| A3 Secret roles | met | `test_websocket.py::test_host_starts_and_each_client_gets_only_its_own_role` | see R2 |
| A4 Vote | met | `test_meeting.py::test_four_votes_over_websocket_send_the_student_surfing` | — |
| A5 Win | met | `test_tasks.py::test_the_last_open_task_ends_the_game_with_a_student_win`, `test_game.py::test_examiners_win_when_they_equal_the_living_students` | — |
| A6 Invalid join | met | `test_game.py::test_invalid_nicknames_are_rejected`, `test_websocket.py::test_duplicate_nickname_over_websocket_is_rejected`, `::test_eleventh_client_*` | Reasons are not checked exactly (audit 3) |

### Other requirement findings

| ID | Finding (evidence) | Severity | Fix |
|---|---|---|---|
| R1 | `README.md:1`, `AGENTS.md:1` and `docs/brd.md:1` say "(working title)". The page title is "Expelled!". | should | Part 2 |
| R2 | The Render build and start command is in no file. Production flags such as `--ws-max-size` and ping cannot be checked. | should | Add a README "Deploy" section with the exact start command |
| R3 | The BRD is out of date:<br>• EX04 says 3 tasks<br>• EX06 still describes staff doors<br>• EX07 says bell, Auditorium and once per game<br>• R3 says "e.g. 20 s"<br>• the scope list excludes chat, sabotage, sound and phone controls, which now exist | should | Part 2: a "Changes since v1.0" section |
| R4 | `PR-008-description.md` is in the repo root. Only spec 038 mentions it. | nice | Part 2: move it to `docs/` |
| R5 | `.DS_Store` is not in `.gitignore` (it is not tracked). | nice | Add it to `.gitignore` |
| R6 | Phaser 3.90.0 is a pinned copy, but its version and licence are recorded nowhere. | nice | Name it in README "How it works"; add `web/vendor/PHASER-LICENSE` |
| R9 | Players who are away (spec 036) still count as living. A meeting with one away player always runs the full 60 s (`_step_meeting`: `all(p.id in votes for p in living)`), and away players count in `_check_win`. No test covers this. | should | Decide whether this is a limit or a change; test it in part 3 |
| R10 | `web/index.html:372` says "Your place in the round is kept", but it also shows in the lobby, where a disconnect removes the player (`game.py:487`). | nice | Reword it |

---

## Audit 2 — Security and privacy

### Shared gate for every WebSocket message
Every message passes these checks in order (`server/main.py:websocket_endpoint`):
1. `RateLimiter.allow` allows 30 per second **per connection**.
2. `parse_message` checks that the message is text, at most 512 B UTF-8 (measured after the whole frame has arrived), valid JSON, a JSON object, and a known `type`.
3. The type must be `join` before joining, and is never `join` again after joining.

After that:
- Every game method first checks `player_id in players` ("Unknown player").
- Every `GameError` goes back as `{"type":"error","reason":…}`.
- Extra keys are ignored.

### Messages

| type | Sender | Phases | Target / value checks | Checks before changes? | Evidence |
|---|---|---|---|---|---|
| `join` | a socket that has not joined | LOBBY; PLAYING/ENDED rejoin or late ghost; MEETING rejoin only | Nickname: text, NFC, 1–16 chars, letters/digits/spaces, unique ignoring case. `hat`: int 0–9 (bool rejected). `color`: None or a free int 0–9. During a round an **away** nickname takes that player over with no secret (S3) | yes in `game.py`; **no in `main.py`** (M3) | `join:424`, `_rejoin:450`, `main.py:152–188` |
| `input` | any joined player | LOBBY, PLAYING | dx/dy: int −1..1. Inside a vent only stop. `at` only with a stop, must be finite | **no for a huge int** (M4); repeat without limit (S7) | `set_input:1535`, `_settle:1562` |
| `start` | host | LOBBY | ≥4 players; 2 examiners need ≥6 | yes | `start:634` |
| `restart` | host | ENDED | – | yes | `restart:1087` |
| `make_host` | host | LOBBY | target: text, not self, exists | yes | `make_host:596` |
| `settings` | host | LOBBY | `expellers` is None, 1 or 2 (bool rejected) | yes | `set_settings:615` |
| `kick` | host | any phase | target: text, not self, exists. Anyone can be kicked, including away players and ghosts | yes, then `leave()` | `kick:575`, `main.py:189–196` |
| `vote_host` | any player | LOBBY | None, or an existing id that is not the host; voting for yourself is allowed (spec 037); majority = votes×2 > players | yes | `vote_host:552` |
| `leave` | any player | any | – | yes (`quit` raises before the connection is dropped) | `quit:590`, `main.py:199–203` |
| `end_round` | **any player, including late ghosts** | PLAYING, MEETING, ENDED | – | yes | `end_round:501` (S6) |
| `expel` | living examiner, not in a vent | PLAYING | target: text, exists, a living student, ≤48 px, cooldown over. The sender's role is checked before the target, so a student learns nothing | yes | `expel:717` |
| `report` | living player, not in a vent | PLAYING | exam: text. Unknown and out of reach give the same reason | yes | `report:879`, `_check_meeting_caller:914` |
| `meeting` | living player, not in a vent | PLAYING, not during the fire alarm | once per round, at the table | yes | `call_meeting:894` |
| `vote` | living player | MEETING while voting is open | `"skip"` or a living player who is not yourself; one vote | yes | `vote:980` |
| `chat` | living player | MEETING while voting is open | text, trimmed, 1–80 chars, no chars <32 or 127, 1.5 s apart, the last 30 kept | yes | `chat:1378` |
| `sabotage` | living examiner, not in a vent | PLAYING | `kind` is lights, fire or wifi; the place exists; no emergency running; shared cooldown | yes | `sabotage:1326` |
| `fix` | any living player, not in a vent | PLAYING | lights off or Wi-Fi down; not already fixing or doing a task; in range | yes (the reason during the fire alarm is misleading: S24) | `fix:1472` |
| `vent_enter` / `vent_move` / `vent_leave` | living examiner | PLAYING | standing on a vent; cooldown; `to` is a known vent and not the current one | yes | `_check_vent_user:848` |
| `task` | student (ghosts too) or living examiner | PLAYING | text id among the sender's own tasks; unknown and someone else's give the same reason; in range; no Wi-Fi outage | yes | `task:1131` |
| `task_input` | the player doing that task | PLAYING | `doing == task`; a mini-game exists; in range; the value is checked by `minigames.validate_value` | yes | `task_input:1179`, `minigames.py:225` |
| `task_cancel` | the player doing that task | PLAYING | `doing == task` | yes | `cancel_task:1220` |

**`kick`, `leave` and `vote_host` in detail** (checked):
- **A kicked connection can do nothing.**
  - `main.py:192` removes it from `connections`, sends `{"type":"kicked"}` and closes it.
  - Its handler still holds the old id, but `leave()` removed the player, so every action gets "Unknown player".
  - A second `join` on that socket gets "You have already joined".
  - It receives no state, and its `finally` skips `disconnect`.
  - Ids are never reused: `next_id` only goes up.
- **After `leave`**, `player_id = None`, so the same socket may join again under a new id.
- **Kick is not a ban.** The kicked browser can enrol again at once: in the lobby as a new player, during a round as a late ghost.
- **Kick during a meeting:** while voting is open, `leave()` removes the kicked player's vote and the votes for them, and then `_check_win` may end the round. The host can therefore decide a round by kicking (the host is trusted: a limit).
- **`vote_host` for an away player or a ghost cannot happen:** in the lobby nobody is away or a ghost (`end_round` drops away players; `_reset_round` revives everyone).

### HTTP routes

| Route | Methods | Input | Answers | Notes |
|---|---|---|---|---|
| `/` and static files (`FreshStaticFiles(web/, html=True)`) | GET, HEAD | path | `web/` files, `Cache-Control: no-cache` | Path traversal is blocked (Starlette `lookup_path`). `web/` holds only client files and `vendor/phaser.min.js`. `server/campus.json` is not served. |
| `/healthz` | GET | – | `{"status":"ok"}` | — |
| `/qr.svg` | GET | ignores the query | QR code of `RENDER_EXTERNAL_URL`, or the request's base URL | tested: `test_qr_svg_ignores_a_url_query_parameter` |
| `/taken-colors` | GET | – | `{"taken": {colour: nickname}}`, `no-store` | lists **every** nickname to anyone, without joining (S2) |
| `/ws` | WebSocket | JSON frames | welcome, state, error, kicked, left | no Origin check (S8) |
| `/docs`, `/redoc`, `/openapi.json`, `/docs/oauth2-redirect` | GET, HEAD | – | FastAPI's automatic API pages; Swagger and ReDoc load scripts from a CDN | on by default; not needed (S11) |

None of these responses has a security header (no CSP, `X-Content-Type-Options` or `frame-ancestors`).

### Findings

| ID | Finding (evidence) | Severity | One-line fix |
|---|---|---|---|
| M3 | Phantom player after a failed welcome send (see the summary). | must-fix | In `finally`, also call `game.disconnect` when the socket never got registered (`connections.get(player_id, ws) is ws`), or catch the failed send and disconnect |
| M4 | A huge int in `at` raises `OverflowError` (see the summary). | must-fix | Check `type(v) in (int, float)` and a range (for example `abs(v) < 1e6`) before `math.isfinite` |
| M5 | A slow reader stalls the game loop (see the summary). | must-fix | `asyncio.wait_for(ws.send_text(...), timeout)` in `game_loop`; on timeout drop the connection and call `game.disconnect` |
| S1 | **Players can be taken over by nickname.** `_rejoin` (`game.py:450`) needs only the nickname of an away player. The impersonator gets that player's role, fellow examiners, tasks and vote. This was a deliberate decision in spec 036 ("there is no password"). | should | A random `rejoin_token` in the welcome, kept in sessionStorage and required by `_rejoin`; or at least S2 |
| S2 | `/taken-colors` publishes every nickname to anyone, in every phase (`game.py:706`). That is exactly the list S1 needs. | should | Return only the taken colours; the join screen shows "taken" without a name |
| S3 | **Ghost vision from a second tab.** Any new nickname can join a running round as a late ghost (spec 036), and ghosts see everyone, every ghost and every failed exam. A living player with a second tab can watch the examiners. | should | Late joiners get no state until ENDED, or no late join; otherwise list it under Limits |
| S4 | **Leaving reveals a role.** `_task_progress` (`game.py:1296`) adds up only the players still in the game. When a student leaves or is kicked, the total drops; when an examiner leaves, it stays. The host can probe this on purpose. | should | Keep a departed student's tasks in the total, or list it under Limits |
| S5 | **Anyone can end the round** (`end_round:501`, spec 036), including a stranger who joins as a late ghost. This makes the host check on `restart` pointless. | should | Spec 038 forbids changing 037 behaviour: list it under Limits |
| S7 | **Faster than allowed with stop messages.** Each stop with `at` may move a player up to `SETTLE_DISTANCE` (16 px) through `_settle` (`game.py:1562`), even if they were not walking. With 30 messages a second, that is about 480 px/s against `SPEED` 160. Walls still block. This goes against "the server decides positions". | should | Accept `at` only on the first stop after walking |
| S8 | No `Origin` check on `/ws` (`main.py:140`): any website can make its visitors' browsers join or fill the lobby. There are no cookies, so no session can be stolen. | should | Before `accept`, compare the Origin host with the `Host` header and close with code 1008 on a mismatch; allow a missing Origin |
| S9 | No security headers. | should | Middleware with `X-Content-Type-Options: nosniff`, the CSP below and `frame-ancestors 'none'`; first move the inline `onclick` (`index.html:374`) into `main.js` |
| S10 | The transport size limit is uvicorn's default `ws_max_size` of 16 MiB. The 512 B check runs only after the whole frame has arrived. | should | `--ws-max-size 4096` in the start command (Render dashboard, README, `.claude/launch.json`) |
| S11 | `/docs`, `/redoc` and `/openapi.json` are public and load scripts from a CDN. | should | `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` |
| S12 | The number of connections is unlimited: the rate limit is per connection, sockets that never join stay open, and there is no limit per IP. | should | A global cap on open sockets; close a socket that has not joined within 60 s |
| S13 | `main.py:157–188` "replaces an old connection of the same player". Since spec 037 D only away players can rejoin, and they have already been removed from `connections`, so `old` is always `None`. The branch is dead and its comment misleads. | nice | Part 5: remove the branch or fix the comment |
| S14 | Look-alike nicknames: `isalpha()` accepts every script ("Аnn" in Cyrillic next to "Ann"). | nice | Latin letters only, or a confusables check |
| S15 | Chat allows Unicode format characters (bidi overrides, zero-width). They are shown as plain text, so this can only spoof. | nice | Reject categories Cf, Cs and Co |
| S16 | Failed-exam ids `e{n}` are never reset, so gaps show how many expels happened out of sight. In a meeting everyone receives all failed exams. | nice | Limit, or ids per round |
| S17 | `localStorage["expelled-nickname"]` is never cleared, which matters on a shared PC. | nice | Clear it on "Leave the game" |
| S18 | Sending an error to a socket that was just closed raises `WebSocketDisconnected`, and uvicorn logs a traceback. | nice | Catch it around the error send |
| S24 | `fix` during the fire alarm answers "The lights are on". | nice | A clearer reason |

### Checked and fine
- **No HTML injection.** `web/*.js` has no `innerHTML`, `insertAdjacentHTML`, `outerHTML`, `eval` or `document.write`. Nicknames and chat reach the page only through `textContent`, `title`/`aria-label` set as attributes, and Phaser canvas text (`render.js:909`). Error reasons never echo user input.
- **Roles stay secret** (`snapshot_for`, `game.py:1802`):
  - Every player receives their own role, alive flag, tasks, `doing`, `task_note`, `fixing`, vision radius, the lights and emergency state, and the shared task progress.
  - Only examiners receive `fellow_examiners`, their cooldowns, their own vent and the sabotage cooldown.
  - Ghosts and everyone in ENDED receive `ghosts`. Roles are sent only in ENDED.
  - Never sent: other players' tasks, cooldowns, fixing or vent, the voters behind host votes, the guard route (removed from `campus`), or individual votes before the result.
  - Apart from S1, S3, S4 and S16, nothing reveals a role to a living student.
- **Dependencies:** `fastapi==0.163.0`, `uvicorn==0.54.0`, `websockets==17.4` (needed for uvicorn's WebSockets) and `segno==1.6.6` (QR code) are all pinned. The dev dependencies `httpx==0.28.1` and `pytest==9.2.0` are pinned too. `uv.lock` is present. None is unused.
- **Secrets:** none in the repository. `.env` is in `.gitignore`. The only environment variable read is `RENDER_EXTERNAL_URL`. `.claude/settings.local.json` is ignored by git.
- **Personal data:**
  - The server keeps the nickname, colour and hat in memory only, until leave, kick, `end_round` (for away players) or a restart. Chat lasts until the meeting ends, and host votes until the start.
  - Nothing is stored permanently: no cookies, no accounts.
  - The server code has no `print` or `logging`. The uvicorn and Render access logs record IP addresses and paths; nicknames are never in a URL.
  - The browser keeps the nickname, look and sound settings in localStorage. sessionStorage `expelled-kicked` is deleted after it is shown.

### Proposed Content-Security-Policy (for part 4)

```
default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'
```

- **Scripts:** `index.html:558–565` loads only same-origin scripts. The only inline handler is `index.html:374`, which has to move into `main.js` first. Phaser's `new Function` fallback is never reached in modern browsers, so `'unsafe-eval'` is not needed.
- **Styles:** no `<style>` blocks and no `style=` attributes. JS changes styles only through the CSSOM, which CSP allows.
- **Images:** `data:` is needed because Phaser's built-in default, missing and white textures are `data:image/png` URIs. `/qr.svg` is same-origin.
- **Connections:** `connect-src 'self'` covers `fetch("/taken-colors")` and the same-host `ws`/`wss` connection in current browsers. Older Safari needs `ws://host wss://host` added; test this on a phone.

---

## Audit 3 — Tests

The test run is at the top: 1428 passed. Below, **F** means a test proves "nothing changed" with the full state, **P** that it checks one or two fields, **N** that it checks only the error.

### Workflows and their tests

| Workflow | Accepted | Rejected | Gap |
|---|---|---|---|
| join, nickname, look | `test_game.py::test_join_places_player_on_spawn`, spec022, `test_websocket.py` | `test_game.py::test_invalid_nicknames_are_rejected` (no reason check), duplicate nickname, 11th player, spec037 D | the reasons for invalid nicknames are never checked |
| lobby settings | spec019 tests, including over the WebSocket | spec019 (three reasons not checked, N) | MEETING/ENDED phase not tested |
| make_host | spec015, over the WebSocket | `test_spec015.py::test_rejected_make_host_changes_nothing` (F) | — |
| vote_host | `test_spec037.py::test_c_*` | `test_c_host_votes_are_checked` (N) | never over the WebSocket; no proof that nothing changed |
| kick | spec037 B (lobby, round, last examiner); `test_e_kick_tells_the_removed_player` (WebSocket) | `test_b_only_the_host_kicks_and_never_themselves` (P: player count only) | "Unknown player"; non-host kick over the WebSocket; closing of the socket; kick in a meeting |
| leave | `test_spec037.py::test_e_leave_removes_the_player_and_says_so` | – | "Unknown player"; leave and join again on the same socket |
| start and roles | `test_game.py`, `test_websocket.py::test_host_starts_and_each_client_gets_only_its_own_role` | `test_game.py` (P), spec013 | start in ENDED |
| movement | `test_game.py`, spec011, spec036 | `test_game.py::test_invalid_input_*` (P), `test_movement_in_ended_is_rejected` (F) | `test_spec036.py::test_a_bad_at_is_rejected` checks no reason and no state; no huge-int case (M4) |
| tasks and mini-games | `test_tasks.py`, `test_minigames.py`, over the WebSocket | `test_rejected_task_changes_nothing` (F), mini-game rejections (F) | `task_input`/`task_cancel` in the wrong phase or with a non-text id (M8); `task_cancel` never over the WebSocket |
| expel | `test_game.py`, `test_websocket.py::test_examiner_expels_over_websocket_*` | `test_rejected_expel_changes_nothing` (F) | — |
| guard | spec027 | n/a | — |
| vents | spec015, over the WebSocket | spec015 tables (F) | — |
| report | `test_meeting.py` | `test_rejected_action_changes_nothing` (F) | never over the WebSocket |
| meeting button | spec011, over the WebSocket | spec011 (F), spec023 fire alarm (P) | — |
| chat | spec029, over the WebSocket | spec029 (four reasons not checked) | "Unknown player" |
| vote and ejection | `test_meeting.py`, `test_four_votes_over_websocket_*` | `test_rejected_action_changes_nothing` (F) | — |
| sabotage and fix | spec008, spec023, spec033, over the WebSocket (lights) | spec008 (F); spec023 (P/N) | fire and Wi-Fi never over the WebSocket; spec023 has no full-state proof |
| win conditions | `test_game.py`, `test_meeting.py`, `test_tasks.py`, spec023 | n/a | — |
| end_round | spec036 (non-host, late ghost) | `test_ending_needs_*` (N) | in MEETING; never over the WebSocket |
| restart | `test_game.py`, spec013, `test_meeting.py` | `test_rejected_restart_changes_nothing` (F) | never over the WebSocket |
| disconnect, away, rejoin | spec036, spec037 D, `test_websocket.py::test_disconnected_player_disappears_for_others` | spec036/037 (P) | disconnect in MEETING (M8); a real rejoin over the WebSocket |
| HTTP routes | `/qr.svg` ×4, `/healthz`, `/taken-colors` ×6, static files | POST `/qr.svg` → 405 | no tests for headers, Origin or `/docs` (to add in part 4) |

### Rejections without a test, or without a reason check
There are 168 `raise GameError` in `server/game.py`, plus the rate limit in `main.py:150`.

- **Never triggered by any test (12):**
  - `kick`, `quit`, `chat`: "Unknown player"
  - `task_input`: "Unknown player", "Game is over", "The game has not started yet", "Task must be a task id", "No Wi-Fi" (`game.py:1205`, which looks unreachable because a Wi-Fi outage cancels running tasks)
  - `cancel_task`: "Unknown player", "Game is over", "Meeting in progress", "The game has not started yet", "Task must be a task id"
- **Triggered, but the reason is never checked (15):**
  - nickname ×4
  - `parse_message`: "Messages must be text", "not valid JSON", "JSON object"
  - settings ×3
  - chat text ×4
  - `at` ×1
- **Rejected with no proof that nothing changed (N):**
  - `vote_host` ×5, `end_round` ×2
  - `_rejoin` during a meeting
  - chat "Voting is over" and "Ghosts cannot chat"
  - settings (unknown player, missing, during a round)
  - a ghost examiner's sabotage, fire alarm cooldown, a map without a fire alarm
  - fix far from the router
  - a bad `at`

### Edge cases named in the spec

| Edge case | Status | Where / test to add | Severity |
|---|---|---|---|
| Disconnect during a meeting | **not covered** | a test: the player stays alive and away, the votes stay, the host moves on, the meeting waits for the timer (R9) | must-fix (M8) |
| Host leaves: lobby / round | covered | `test_game.py::test_host_leaving_in_lobby_passes_host_on`, `::test_host_leaving_while_playing_passes_host_on` | — |
| Host leaves during a meeting | not covered | `leave(host)` while voting: the host passes on, votes are removed, the phase stays MEETING | should |
| Last examiner voted out | covered | `test_meeting.py::test_voting_out_the_only_examiner_lets_the_students_win_after_the_result` | — |
| Tie or empty vote | covered | `test_meeting.py::test_without_a_clear_majority_nobody_is_sent_surfing`, `::test_nobody_voting_sends_nobody_surfing_*` | — |
| Maximum players | covered | `test_game.py::test_eleventh_player_is_rejected`, `test_spec036.py::test_no_late_ghost_when_the_game_is_full_or_in_a_meeting` | — |
| Invalid JSON over the WebSocket | partly | `test_websocket.py::test_invalid_messages_*` checks only `type == "error"`: add exact reasons, a binary frame and >512 B | should |
| A message in the wrong phase | mostly | missing: `task_input`/`task_cancel` (M8), settings in MEETING/ENDED, start in ENDED, `end_round` in MEETING, kick in a meeting | must-fix (M8) / should |
| Two actions in the same tick | covered | `test_meeting.py::test_two_reports_of_the_same_exam_in_one_tick_first_wins`, `::test_report_then_expel_*`, `test_game.py::test_two_expels_*` | — |
| Host kicked / leaves during a round | covered in `game.py`; not over the WebSocket | a WebSocket test: the host sends `leave` and the others see the new host | should |
| A kicked connection sends more messages | not covered | a WebSocket test: after `kicked`, any further message gets "Unknown player" and changes nothing | should |
| Leave, then join again on the same socket | not covered | a WebSocket test | should |
| A whole round over the WebSocket | **not covered** | one test with 4–5 clients, a seeded `rng`, guard off | must-fix (M7) |
| A phantom player after a failed welcome | not covered | a test for M3 | must-fix (part 4) |

### Weak or fragile tests (tests may not be edited: new tests only)
- **Tests that do not check the reason** (`test_game.py::test_invalid_nicknames_are_rejected`, `::test_malformed_messages_are_rejected`, `test_spec029.py::test_invalid_text_is_rejected`, spec019, spec036 `at`) still pass if the wrong check fires. Fix: new parametrised tests with the exact reason.
- **Tests that build fake state:**
  - `test_spec036.py::test_no_late_ghost_*` builds a fake `Meeting(reason="meeting")`.
  - spec036 ENDED sets `game.phase = ENDED` by hand.
  - `test_spec033.py` sets `vent = "somewhere"`.
  - Several tests set `alive = False` directly.

  These can hide bugs in the real transitions.
- **WebSocket tests that change `fresh_game` from the test thread** while the loop runs `step()` have a small race risk. `conftest.fresh_game` uses unseeded randomness and leaves the guard on, so a WebSocket test may take a different path each run.
- **21 test files assert on source text** (for example `test_spec036.py:125` needs `game.end_round(player_id)` and `connections.get(player_id) is ws` in `server/main.py`; `test_spec011.py` bans "bell"; `test_spec016.py` bans "sound" in the server files and needs certain `Sound.play("…")` strings in `main.js`). They prove that a string exists, not that the code works, and they constrain part 4 and part 5. **Check these pins before every refactor.**
- `tests/test_game.py:744` has a stale comment, "exactly 20 seconds of ticks" (it is 30). Tests may not be edited, so it is only noted here.

---

## Audit 4 — Leanness

Run with the `thermo-nuclear-code-quality-review` skill in report mode only; nothing was applied. The list is ranked by benefit for explaining the code against the risk of breaking something. Every "unused" claim was checked with grep across `server/`, `web/` and `tests/`.

### Line counts

| File | Lines | File | Lines |
|---|---|---|---|
| server/game.py | **1901** | web/main.js | **3625** |
| server/minigames.py | 538 | web/render.js | **1850** |
| server/main.py | 271 | web/style.css | **1430** |
| server/guard.py | 202 | web/index.html | 567 |
| | | web/campusmap.js · sound.js · music.js · hats.js · controls.js | 284 · 280 · 259 · 146 · 117 |

The total is 11,470 lines (`web/vendor` not counted).

### Findings

| ID | Where | What | Benefit | Risk | Severity | Change |
|---|---|---|---|---|---|---|
| L1 | `web/main.js:24` | `EXPEL_COOLDOWN = 20`, which is M2. | high | low | must-fix | Set it to 30; also check `VENT_COOLDOWN` and `SABOTAGE_COOLDOWN` in the drift test |
| L2 | `web/index.html:443, 450` | Wrong handbook numbers, which is M1. | high | low | must-fix | Part 2 |
| L3 | `web/main.js:1735–1810, 2342` | **Misleading names and comments for the mini-games.**<br>• The comment speaks of "six kinds" and "'seagull' (nata)"; there are 15 kinds, and `seagull` is a different kind from `nata`.<br>• It mentions "placeholders" that no longer exist.<br>• `nataEaten`, `NATA_EATEN_MS` and `lastSeagullChallenge` serve only the retired `seagull` kind, which is now used on test maps only: they react to the note "A seagull took it." and never to nata's "A seagull took your pastel." | high | low | should | Rename to `seagullEaten`/`SEAGULL_EATEN_MS` and rewrite the comments |
| L4 | `server/game.py`, `web/index.html` | **Comments that contradict the current rules:**<br>• `game.py:103`: ENDED lasts "until the host restarts" (now anyone, with `end_round`)<br>• `index.html:493`: "the host can end a running round"<br>• `game.py:1506`: `_step_lights` says "a student" (every role since 033)<br>• `game.py:1820` docstring: "A student also gets their own fixing"<br>• `game.py:172`: "REPORT or BUTTON" (SECURITY is missing)<br>• `game.py:1–9`: the module docstring lists only some of the message types<br>• `chat()` (`game.py:1378`) sits under the "Lights sabotage" header | high | low | should | Fix the comments; move `chat()` to the meeting section |
| L5 | `game.py`: `expel`, `_check_vent_user`, `_check_meeting_caller`, `task`, `task_input`, `cancel_task`, `sabotage`, `fix` | The same four-step guard is copied 8 times: Unknown player → Game is over → meeting → not started. | high | low | should | One helper `_playing_player(player_id, meeting_reason=…)` with the same order and reasons (about −55 lines) |
| L6 | `server/main.py:139–251` | An if/elif chain with 22 branches; 19 are a one-line `game.<method>(player_id, message.get(...))`. | high | low–med | should | A dispatch table of lambdas that read the global `game` when called (`conftest` replaces it). `join`, `kick` and `leave` stay explicit. Keep the text `game.end_round(player_id)` and `connections.get(player_id) is ws` (pinned by `test_spec036.py:125`). Move the welcome message into `welcome_message(player)`. |
| L7 | `game.py` (11 places) | The trio `doing = None; challenge = None; task_note = …` is repeated. | med-high | low | should | Add `_stop_task(player, note=None)` |
| L8 | `game.py`: `_distance_to_task`, `_distance_to_router`, `_distance_to_switch`, `call_meeting` | Four copies of "distance to a tile centre"; `min(tasks_step…, len(steps) - 1)` three times. | med | low | should | Add `_distance_to_tile(player, col, row)` and `_station_index(player, task_id)` |
| L9 | `server/minigames.py:122–125` | `FLIGHTS` is an 8-tuple read by position (`[:5]`, `[5]`, `[6:8]`); `_nata_*` also serves `frisbee`. | high | low | should | Named keys; rename to `_flight_*` |
| L10 | `game.py`: `disconnect`, `end_round`, `leave` | "Empty game → open a clean lobby" appears 3 times. The new-host choice differs: `leave`/`end_round` take the first player even if they are **away**; `disconnect` takes the first player who is present. | med | low | should | `_open_empty_lobby()`; ask the team about the host difference first (that would be a behaviour change) |
| L11 | `game.py:snapshot_for` (83 lines) | One long function with four phase/role blocks. | med | low | should | Extract `_round_state_for(me)` and `_examiner_state_for(me)` |
| L12 | `web/main.js`: `updatePhase` (82 lines), `renderLobby` (84), `updateTasks` (85), `CampusScene.update` (72) | They mix UI and sound; `me`/`own` are looked up twice; the switch-range maths is duplicated. | med | low | should | `playPhaseSounds`, `lobbyLine`, one `own`, `nearTile` |
| L13 | `web/main.js` | The "nearest within range" loop 3×, the own-player lookup 8×, tile-centre maths 6×. | med | low | nice | `ownPlayer`, `nearestWithin`, `tileCentre` |
| L14 | `web/main.js`, `render.js`, `index.html` | "door" names (`doorActionButton`, …) for the vents of spec 015; `TASKS_PER_STUDENT` also counts examiners' fake tasks. | med | low | nice | Rename |
| L15 | `server/minigames.py`, `web/main.js` | The kinds `seagull`, `translate`, `paper_jam` and plain-wait stations are used only by test maps (`server/campus.json` uses 12 kinds, none of them). | med | **high** | should (team) | Do not delete (tests use them; `test_spec016` pins `Sound.play("paperRattle")`/`("seagullHit")`). Mark them "test maps only". |
| L16 | `game.py:1087`, `main.py:236` | The `restart` message is never sent by the page (the "New round" button sends `end_round`). | med | **high** | should | Keep it (≥8 tests use it); comment "tests/API only"; rename `ui.restartButton` → `newRoundButton` |
| L17 | `game.py:_step_lights` vs the Wi-Fi branch of `_step_emergency` | The same fixer loop twice, with two small differences. | med | med | nice | One helper, carefully |
| L18 | `game.py:sabotage` | "Ghosts cannot turn off the lights" also for fire and Wi-Fi. | low-med | low | nice | Other wording for fire and Wi-Fi only (the lights text is pinned) |
| L19 | `server/guard.py:157, 183` | The parameter `pause_ticks` holds seconds. | low-med | low | nice | Rename it to `pause_seconds` |
| L20 | `web/main.js` | `TOUCH_SCREEN` duplicates `Controls.isTouch`; `/10` hard-coded twice; two "was alive" trackers. | low-med | low | nice | Reuse; `MAX_PLAYERS` marked "REPEATS SERVER RULE" |
| L21 | `web/music.js`, `web/index.html` | `Music.setOn` exported but unused; ids `help-title`, `examiner-setting-label`, `controls`, `control-map` never referenced. **CSS: no dead selectors** (all 227 classes and 28 ids are used). | low | low | nice | Drop the export; use the two ids for `aria-labelledby` |
| L22 | `web/style.css:1257–1430` | Rules added per spec after the media queries; duplicate selectors `.id-photo`, `.vote-dot`, `.swatch`. | low-med | med | nice | Merge only after checking the cascade |
| L23 | `game.py:35–43` | `MESSAGE_TYPES` is built from 9 `\|=` lines and is a second list that must match the dispatch. | low | low | nice | One grouped set; a comment that the two must match |
| L24 | `web/render.js:drawMap` (462 lines, about 15 nested closures) | The longest function in the repo. | med | med | nice | Lift the inner `draw*` helpers to module level inside `render.js` (`drawGlassPane` must stay there) |

**File splits (files over 1,000 lines).** Recommendation: no file split in spec 038. Reorganise inside the files instead (L11, L12, L13, L24).
- `web/main.js` could be cut into `minigames.js` (lines 1731–2426) and `scene.js` (2957–3049 and 3110–3625). But source-text tests require strings to stay in `main.js` (`test_spec016`, `test_spec011.py:327`), so the risk is high.
- `server/game.py` has one low-risk cut: lines 181–274 (decor sets, `sight_grid`, `load_map`, `validate_campus`) into `server/campus.py`, imported back into `game.py`.

---

## Contradictions between specs and code, and replaced specs

**Contradictions that no later spec explains:**
- M1 (handbook) and M2 (client cooldown).
- S13: the dead "replace old connection" branch from spec 036, made dead by 037 D.
- L3: the seagull/nata leftovers from spec 031.
- L4: comments still describing host-only `restart`.
- R3: the BRD.

**Replaced specs.** One line per spec; this becomes `specs/README.md` in part 2.

| No. | Title | Status |
|---|---|---|
| 001 | Live movement | partly replaced by 008 (prediction), 009 (map), 011 (sliding), 036 (stop spot, away) |
| 002 | Lobby, host, roles | partly replaced by 015 (make_host), 019 (examiner setting), 036 (late join), 037 (kick, vote_host) |
| 003 | Expel, ghosts, end | partly replaced by 008 (ghosts pass walls), 019 (30 s), 036 (`end_round` by anyone) |
| 004 | Tasks | partly replaced by 012 (mini-games, fake tasks), 019 and 037 (number of tasks) |
| 005 | Look | partly replaced by 010 (line of sight), 022 (hats), 028 (colour picker) |
| 006 | Meeting and vote | partly replaced by 008, 011 (meeting table instead of Auditorium), 019, 029 (chat) |
| 007 | Phone controls, QR join | partly replaced by 036, 037 I (phone layout) |
| 008 | Fixes and mechanics | partly replaced by 010, 011, 015 (staff doors → vents), 023, 033 |
| 009 | Nova campus map | partly replaced by 011, 015, 034–036 |
| 010 | Line-of-sight vision | done |
| 011 | Free movement, meeting point | done |
| 012 | Mini-games | partly replaced by 021, 024, 031, 035 (campus kinds), 019 and 037 (number of tasks) |
| 013 | Start in the Main Entrance | done |
| 014 | UI redesign | partly replaced by 015, 023, 033 |
| 015 | Story UI, vents, beach | partly replaced by 028, 037 |
| 016 | Sound effects | partly replaced by 020, 028 |
| 017 | Music | partly replaced by 028 |
| 018 | Campus map | partly replaced by 023, 026 |
| 019 | Playtest rules | partly replaced by 037 (5/6/7 tasks) |
| 020 | Playtest sound | partly replaced by 028 |
| 021 | Cafeteria and beach tasks | done |
| 022 | Hats and colours | partly replaced by 028 |
| 023 | Sabotage menu | partly replaced by 033, 035, 037 F |
| 024 | Print and helpdesk tasks | done |
| 025 | Gym skylight | done |
| 026 | Colourful campus map | done |
| 027 | Segway guard | partly replaced by 034 (speed), 035 (vision, cone) |
| 028 | Sound settings, taken colours, examiner names | done |
| 029 | Meeting chat | partly replaced by 036 C, 037 G |
| 030 | — | never on `main`: duplicates of 028 that were dropped (Martin's #26 won); the next specs became 031–033 |
| 031 | Shoo the seagulls | done (leftovers: L3) |
| 032 | EXPELLED stamp | done |
| 033 | Examiners can fix the lights | done |
| 034 | Campus edge, calmer guard | partly replaced by 035 |
| 035 | Bugfixes after playtest | partly replaced by 036 D |
| 036 | Never stuck, campus polish | partly replaced by 037 D (a nickname in use cannot be taken over) |
| 037 | Playtest: tasks, kick, host vote, phone | done (handbook left behind: M1) |
| 038 | Review, tests, security, lean | in progress (this document) |

## Proposed limits

To go into the "Limits" section of spec 038 unless the team decides to change them:
- **S1:** takeover by nickname.
- **S3:** ghost view from a second tab.
- **S4:** a role revealed by leaving.
- **S5:** anyone can end a round.
- **R9:** away players count as living.
- **The host is trusted:** a kick can decide a round, and a kick is not a ban.
- **S16:** failed-exam ids.
- **Server restart:** a restart ends a running game (accepted limit in AGENTS.md).
