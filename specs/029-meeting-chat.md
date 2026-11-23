# Spec 029 — Chat in the meeting

## Why
Team brainstorm, 23 Nov: playing online, players cannot talk during a meeting unless they
sit in one room or a call. The original genre has a text chat while voting. Builds on
spec 006 (meetings and votes).

## What
- **Message:** `{"type": "chat", "text": "..."}`.
- **When:** only while a meeting's vote is open (not during the result, not while playing).
- **Who:** living players only. Ghosts cannot chat ("Ghosts cannot chat"), so they cannot
  help the living (as before, they cannot vote either).
- **Text rules (checked on the server, a rejection changes nothing):**
  - a string, 1–80 characters after trimming spaces;
  - no control characters (no line breaks, tabs, …);
  - at most one message per player every 1.5 s ("Slow down");
  - nothing is ever read as HTML: the client sets every message as plain text.
- **What everyone in the meeting receives:** `state["chat"]`, the list of the meeting's
  messages, oldest first, at most the last 30: `[{"from": player id, "text": "..."}]`.
  Only while the phase is "meeting"; a new meeting starts with an empty chat.
- **Client:** under the voting cards, a small chat box: the messages as "Name: text" in
  the sender's colour, an input (80 characters) and a "Send" button; Enter sends. While
  someone types, the game's own keys (W, A, S, D, E, …) do not react, so every letter can be
  typed. A ghost sees the chat but not the input.

## Out of scope
Chat while playing, ghosts chatting with each other, emojis as pictures, a filter for words.

## Done when
- `tests/test_spec029.py` covers, test first: accepted messages and the list everyone gets;
  every rejection (wrong phase, ghost, result shown, not a string, empty, too long, control
  characters, too fast); the 30-message cap; an empty chat in the next meeting; the
  WebSocket message; and the client wiring (plain text only, keys off while typing).
- All tests pass.
