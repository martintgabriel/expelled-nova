# AGENTS.md — Expelled!

Shared rulebook for every coding agent in this repository (Claude Code, Codex, …). Read it completely before each task.

## Project
A live 2D multiplayer social-deduction game on a stylised Nova SBE campus.
- Product requirements: `docs/brd.md`
- One change = one spec in `specs/` (Why · What · Out of scope · Done when)

## Stack (fixed; do not switch or add frameworks without the team's decision)
- Server: Python 3.12, FastAPI + Uvicorn with WebSockets, managed with uv.
- Client: one static web page in `web/` (HTML + JavaScript + Phaser as a pinned copy in `web/vendor/`). No build step, no npm.
- Hosting: Render (free web service). Permanent data (later, roadmap F6): Supabase.

## Commands
- Run the app: `uv run uvicorn server.main:app --reload`, then open http://localhost:8000
- Run the tests: `uv run pytest`

## Architecture rules
- The server decides everything: positions, roles, expelling, tasks, votes, wins. The client only sends inputs and draws what the server sends.
- Game rules live in `server/game.py` as plain Python without network code, so they can be tested directly.
- The server sends each player only what that player may know. Never send another player's role to a client (examiners may see fellow examiners).
- Validate every message from a client (type, values, allowed in the current game phase). A rejected action changes nothing and returns a short reason.
- Running games live in server memory. This is an accepted limit: a server restart ends running games.

## Rules
- Do not run git commands. Git is handled in GitHub Desktop.
- Write the tests for a change before the implementation and show that they fail first.
- Never edit files in `tests/` unless the task says so.
- Before finishing a task, run the tests and paste the output.
- Only touch what the task needs. At the end, list every file you created or changed.
- Never create or edit `.env` files or other files with secrets. Read secrets only from environment variables; keep `.env` in `.gitignore`.
- Add a dependency only if the task needs it, pin it and say why.
- Use only original names, characters and graphics: no assets, names or logos from existing games, no images from Google Maps or Street View, no real people's names or photos.
- All text in the game, code and docs is in English.

## What the course grades (check your work against it)
1. It works: all workflows run on the deployed app without errors, including invalid input.
2. UI/UX: workflows are direct; results and errors are clearly shown.
3. Scope: substantial features, implemented consistently.
4. Verification: tests cover accepted and rejected actions and edge cases; all pass on main.
5. Security: access control and input validation enforced; dependencies minimal and pinned; no credentials in the repository.
6. Walkthrough: every team member can explain how it is built, why, its limits and how it could change. Keep the code simple enough to explain.
