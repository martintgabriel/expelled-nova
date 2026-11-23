# Spec 039 — Drop the unfinished parts of spec 038

## Why
Spec 038 planned six parts. Parts 1–4 (audit, docs and handbook, tests, security) are merged. Parts 5 (leaner code) and 6 (docs/walkthrough.md) were not started before the submission deadline, and refactoring right before it would put the tested game at risk. The repository should not promise documents that will not exist.

## What
- `specs/038-review-tests-security-lean.md`: parts 5 and 6 are removed. "What" says four parts in one pull request. "Done when" no longer mentions `docs/walkthrough.md` or line counts. "Limits" gets one line saying both parts were dropped before the deadline.
- `README.md`: the link to `docs/walkthrough.md` is removed.

## Out of scope
Any change to code, tests, the game or other docs.

## Done when
- Neither file mentions `docs/walkthrough.md` as an existing or coming document, apart from the one "Limits" line in spec 038.
- No test is needed: text only. The full `uv run pytest` passes unchanged.
