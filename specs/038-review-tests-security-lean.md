# Spec 038 — Review, tests, security and a leaner, explainable codebase

## Why
The game is feature-complete for the presentation. What is left is making sure it is
graded well on everything else now that spec 037 (playtest fixes and phone layout) is merged. The course grades the team presentation on "it works · design · scope and
ambition · verification · walkthrough": a live demo at the deployed URL and a code
walkthrough in which every member is asked about code they did not write
(evaluation page). AGENTS.md adds the stricter list the team works against, including
security (access control, input validation, minimal pinned dependencies, no credentials).
The exam asks six kinds of questions about one's own app: explain a workflow, explain the
state and stored data (including what is loaded after a restart), predict an outcome,
locate a bug, show how a rule was verified, and reason about a change (exam question
template).

After 36 specs written by four people and several agents, the code has grown
(`web/main.js` ~3,600 lines, `server/game.py` ~1,900, `web/render.js` ~1,850), the specs
partly replace each other, and the README still says "working title". This spec checks
everything once from top to bottom, closes gaps in tests and security, makes the code
leaner **without changing behaviour**, and leaves the team with documents that make the
walkthrough and the exam easier. Builds on specs 001–037 (037 added `kick`, `vote_host` and `leave`).

## What
Six parts, done in order, each one a separate commit (like spec 008), in two pull requests:
parts 1–4 first, then parts 5–6 on top of the merged result, so a problem in the refactoring
never holds back the tests, docs and security work. While part 5 runs, nobody else changes
`server/` or `web/`.

### Part 1 — Audit (read only): `docs/review.md`
No change to any file except creating `docs/review.md`. Four audits, each finding with
evidence (file and function), severity (must-fix / should / nice) and a one-line fix:
1. **Requirements:** every point of the course rubric (it works, design, scope and
   ambition, verification, walkthrough), the six grading points in AGENTS.md and every
   acceptance criterion in `docs/brd.md`: met / partly / not met, with evidence.
2. **Security and privacy:** every WebSocket message type (`join`, `kick`, `vote_host`,
   `leave`, `start`, `chat`, `settings`, `make_host`, `expel`, `report`, `meeting`,
   `sabotage`, `fix`, `vent_*`, `task*`, `vote`, `restart`, `end_round`); for `kick`,
   `vote_host` and `make_host` in particular: who may send them, in which phase, against
   whom, and that a kicked or departed player's connection can do nothing afterwards and every HTTP route (`/`, `/healthz`,
   `/qr.svg`, `/taken-colors`, static files): validation of type, values, length and game
   phase; host-only actions; rate limiting; maximum message size; the WebSocket `Origin`;
   security headers; every place player text (nicknames, chat) reaches the page; what each
   snapshot sends to whom (no role or hidden information may leak: chat, ghosts, guard,
   vents, sabotages, tasks); dependencies pinned; no secrets; which personal data is kept,
   for how long, and whether anything is logged.
3. **Tests:** the full `uv run pytest` summary; every workflow and rejected action without a
   test; untested edge cases (disconnect mid-meeting, host leaves, last examiner voted out,
   tie or empty vote, maximum players, invalid JSON, a message in the wrong phase, two
   actions in the same tick, the host kicked or leaving mid-round).
4. **Leanness:** the `thermo-nuclear-code-quality-review` skill in report mode only, on
   `server/` and `web/`: dead code, duplicated logic, leftovers of replaced specs, unclear
   names, long condition chains (for example the message dispatch in `server/main.py`),
   files far over 1,000 lines. Each finding ranked by benefit for explaining the code
   versus risk of breaking something.
Plus: contradictions between specs and code, and specs later specs replaced.

### Part 2 — Docs and the in-game handbook (no code change)
- Move `PR-008-description.md` into `docs/` and fix every link to it.
- Final name **"Expelled!"** (the `<title>` in `web/index.html`): remove "(working title)"
  in `README.md`, `AGENTS.md` and `docs/brd.md`.
- `docs/brd.md` becomes **version 2.0** and describes the game as it is today:
  capabilities, business rules, acceptance criteria and scope boundaries, every number
  checked against the code. The existing IDs (EX01–EX08, R1–R8, A1–A6) are kept so older
  specs still match; new capabilities get new IDs. The roadmap shows for each item whether it
  is delivered and by which spec, or still open. At the end a short table "Changes from
  v1.0" (change, reason, spec). Version 1.0 stays in the git history; no separate copy.
- `README.md` is rewritten, short and scannable (details belong in `docs/ARCHITECTURE.md`):
  - name and one-line pitch;
  - live URL with the sleep note;
  - how a round works, in a few lines;
  - main features;
  - team;
  - run locally;
  - tests;
  - "How it works": where the rules live (`server/game.py`, `server/guard.py`,
    `server/minigames.py`), what `server/main.py` does, how `web/` is organised;
  - data and privacy, i.e. **what survives a restart**: fixed content in
    `server/campus.json` is loaded at start; players, roles, tasks, votes and the game phase
    live only in server memory, so a restart ends a running game; nothing is stored
    permanently (no accounts, no cookies, nicknames only for one session);
  - security measures as one short list;
  - limits;
  - the project structure as a short folder tree;
  - links to `docs/ARCHITECTURE.md`, `docs/brd.md`, `specs/README.md`,
    `docs/manual-test-checklist.md` and `docs/walkthrough.md`.
- `docs/ARCHITECTURE.md`: one page for the walkthrough: the data flow from a key press to
  the screen (input → WebSocket → 20 Hz tick in `game.py` → `snapshot_for()` per player
  → drawing), what each file is responsible for, the message types, how the server keeps
  roles secret, limits, and how the project could change (BRD roadmap F6 Supabase, F8
  parallel games). Plain language; every statement checked against the code.
- **The in-game handbook matches the rules** (`web/index.html`, the handbook and the role
  card): this is the only change in `web/` in part 2, and it is text only. Part 2 changes
  no code; its only new test is the handbook guard test (below), written first and shown
  failing before the text is fixed.
  - Tasks: "three errands" is wrong since spec 037. It says instead that the to-do list
    names at least five errands, more in bigger rounds (5 for 4–5 players, 6 for 6–7,
    7 for 8–10, from `tasks_per_player()`).
  - Expelling: "wait 20 seconds" is wrong since spec 019; `EXPEL_COOLDOWN` is 30.
  - Every other number and rule in the handbook and on the role card (fix time, fire alarm,
    router, meetings, vents, cooldowns) is checked against the constants in
    `server/game.py` and corrected where it differs.
- `specs/README.md`: an index of all specs, one line each (number, title, what it changed,
  status: done / partly replaced by NNN), and why 030 is missing. Old specs are not edited
  or deleted: they are the project's history.

### Part 3 — Tests
From the must-fix and should items of audit 3. Only new tests are added; existing tests
are not edited, deleted or skipped.
- At least one end-to-end WebSocket test with several clients: join, start, a task, a
  report, a meeting with chat and a vote, an ejection, the end of the round, a restart.
- Every rejected action with its reason and the proof that nothing changed.
- If a new test for existing behaviour fails, it is a real bug: stop and report it with
  the cause before fixing anything .
- A test that reads the handbook in `web/index.html` and checks that every number in it
  equals its constant or function in `server/game.py` (task counts, expel cooldown, fix
  time, fire alarm, router), so the text can never drift from the rules again. It is
  written at the start of part 2, before the handbook text is fixed, so it can be shown
  failing first (AGENTS.md).
- `docs/manual-test-checklist.md`: every workflow to click through on the deployed app
  with 4+ browser tabs, including invalid input (empty, too long and duplicate names,
  actions in the wrong phase, a second tab trying host actions).

### Part 4 — Security hardening
Only the must-fix and should items of audit 2 that the audit confirmed. Likely candidates:
- reject a WebSocket whose `Origin` is not the page's own host (so it keeps working on
  `localhost` and on Render, and through the QR code);
- a maximum size for one client message;
- security headers on every response: `X-Content-Type-Options: nosniff`, a
  `Content-Security-Policy` that allows only the page's own scripts, styles, images and
  WebSocket, and `frame-ancestors 'none'`. Note: `web/index.html` has one inline
  `onclick="location.reload()"` (the "Reload and rejoin" button), which a strict policy
  blocks: replace it with a listener in `main.js` first;
- length and character limits for nicknames and chat, if any are missing.
Also the confirmed must-fix code bugs from `docs/review.md`:
- M2: the browser's expel cooldown ring uses its own `EXPEL_COOLDOWN = 20` (`web/main.js`)
  while the server uses 30. One source of truth: the server sends the cooldowns (expel,
  vent, sabotage) in the welcome message and the browser uses those.
- M3 (phantom player after a failed welcome), M4 (`OverflowError` on a huge `at`), M5 (one
  slow reader stalls the game loop).
No change to game rules. Tests first for each item.

### Part 5 — Leaner code (after parts 1–4 are merged)
From the leanness audit, re-run against the then-current `main`. Only findings that are
behaviour-preserving, low risk and make the code easier to explain: dead code, duplicated
logic, leftovers of replaced specs, unclear names, long functions that split cleanly, a
dispatch table instead of a long condition chain. No new features, no change to any
message format, no file split unless it is a clean cut the whole team can follow.
- One finding per step, the full `uv run pytest` after each step, stop at the first red
  test.
- Tests in `tests/` are not edited, deleted or skipped. If a test only fails because it
  checks a text or structure that was removed, stop and ask.
- Report line counts per file before and after.

### Part 6 — Walkthrough and exam preparation: `docs/walkthrough.md`
For each of the six exam question types, one worked example from this game, with real
values and cause and effect, checked against the code:
1. a workflow (for example: an examiner expels a student),
2. state and stored data (fixed content vs. game progress, where each lives, what a
   restart loads),
3. predicting an outcome (an action that is accepted and one that is rejected, and what
   stays unchanged),
4. locating a bug (a symptom, where to look, how to reproduce it),
5. a verification (one test: start state, action, expected result, what mistake it
   catches, what it does not prove),
6. a change (a new requirement, what it affects, what must keep working, which test to
   add).
Plus a list of 15 likely professor questions with short answers, spread over server,
network, browser, tests and security, so every member can answer about code they did not
write.

## Out of scope
Changing what spec 037 built (task count, kick, host vote, nicknames, leave, emergency
arrow, ghost chat note, wording, phone layout) beyond fixing a bug part 3 proves; the
walking sound (a separate decision). New features. Permanent storage (BRD roadmap F6). Any change to game rules,
balance or look.

## Done when
- `docs/review.md` exists; every must-fix item is either fixed in parts 2–5 or listed under
  "Limits" with a reason.
- `README.md`, `AGENTS.md` and `docs/brd.md` no longer say "working title";
  `PR-008-description.md` is in `docs/`.
- `docs/brd.md` is version 2.0: it matches the code (every number checked), keeps the old
  IDs, shows each roadmap item as delivered (with its spec) or open, and ends with
  "Changes from v1.0".
- `README.md` is rewritten with every section listed in part 2 and links to all five
  documents;
  `docs/ARCHITECTURE.md`, `specs/README.md`, `docs/manual-test-checklist.md` and
  `docs/walkthrough.md` exist and match the code.
- The handbook says "at least five" errands and 30 seconds after an expel, every number
  in it matches the code, and a test guards this.
- New tests from part 3 and part 4 were shown failing first where they test new behaviour;
  the full `uv run pytest` passes after every part (output pasted here); no existing test
  was edited, deleted or skipped.
- The game loads and plays on the deployed app with the new headers (laptop and phone via
  QR code), and the whole manual checklist passes there with 4+ tabs.
- Line counts before and after part 5 are listed.

## Changes during implementation
(Filled in after implementation.)

## Limits
(Filled in after implementation.)

## Files created or changed
(Filled in after implementation.)
