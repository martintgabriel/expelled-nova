# Spec 024 — Better print and helpdesk tasks

## Why
The playtest on 23 Nov found two of the campus mini-games boring: "Print your assignment"
and the paper-jam step of the certificate are random clicking, and asking the Helpdesk is a
single translation. Builds on spec 012 (mini-games) and 021 (two new tasks). Spec 023 is
left free for another team member's change.

## What
Three new mini-game kinds in `server/minigames.py` replace the old ones on the campus. The
old kinds (`paper_jam`, `translate`) stay in the engine, since test maps still use them.

1. **`print_file`: "Print your assignment"** (Library). The group chat says which file to
   print ("Print final_REAL_use_this.docx!!"); the printer lists four almost identical file
   names. Pick the right one, 3 times in a row. A wrong pick starts again at round 1 with
   the note "Wrong file. You printed 40 pages of it." Value: 0–3. 30 s, time-out note
   "The printer went to sleep."
2. **`cert_file`: "Print a copy of your certificate"** (Library, step 1 of the certificate).
   Same game with certificate files, 2 rounds. Time-out note "The printer went to sleep."
3. **`chat`: "Ask the Helpdesk for help"** (Main Entrance). A three-line conversation in
   European Portuguese: the Helpdesk says something, the panel says in English what you
   want to answer, and you pick the right Portuguese reply out of three. A wrong reply
   starts the conversation again ("Não percebi. Outra vez, por favor."). Value: 0–2. 45 s,
   time-out note "The Helpdesk closed for lunch."

Nothing is secret apart from which option is right; the public view never says which one.

## Out of scope
The seagull game (kept as it is), new voice lines, more conversations.

## Done when
- New tests in `tests/test_spec024.py` cover building, right and wrong answers, invalid
  values, time-out notes, that the view hides the answer and the campus places.
- This spec changes `SPEC_TASKS` in `tests/test_tasks.py` (new kinds for "certificate"
  step 1, "helpdesk" and "print").
- All tests pass; locally all three tasks can be played to the end.
