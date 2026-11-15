# Expelled! (working title)

Live 2D multiplayer social-deduction game on the Nova SBE campus.

## Live app

https://expelled-nova.onrender.com

Note: the app runs on a free server that sleeps after 15 minutes without visitors. The first visit after that takes about a minute while it wakes up.

## Team

| Name | Student number | GitHub |
|---|---|---|
| Martin Gabriel | 78518 | martintgabriel |
| Cornelius Paprottka | 78283 | cpaprottka |
| Leonard Kowall | 78697 | leonardk-hue |
| Manuel Ritter | 78936 | manuelritter78936 |

## Run locally

Requires [uv](https://docs.astral.sh/uv/).

Install the dependencies:

```bash
uv sync
```

Run the app, then open http://localhost:8000:

```bash
uv run uvicorn server.main:app --reload
```

Run the tests:

```bash
uv run pytest
```

## Docs

- [Business requirements (BRD)](docs/brd.md)
- [Specs](specs/): one spec per change
