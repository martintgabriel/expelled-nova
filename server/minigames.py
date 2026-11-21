"""Mini-game challenges for Nova tasks (spec 012). Plain Python, no network code, so it
can be tested directly, like server/game.py.

Each kind has a time limit, a function that builds a fresh challenge with the game's rng,
a function that validates and applies a player's answer, and a function that builds the
player-visible view of a challenge (hiding whatever must stay secret, e.g. which socket is
free). server/game.py owns the player's state (which task, which step) and calls into this
module only for what happens inside one station's challenge.
"""

TIME_LIMITS = {
    "ticket": 45,
    "translate": 30,
    "card": 30,
    "paper_jam": 30,
    "socket": 30,
    "seagull": 8,
}

TIMEOUT_NOTES = {
    "ticket": "The queue moved on without you.",
    "translate": "The queue moved on.",
    "card": "The gate locks again.",
    "paper_jam": "Someone else cleared it.",
    "socket": "All sockets taken. Try again later.",
    "seagull": "A seagull took it.",
}

KINDS = set(TIME_LIMITS)

# European Portuguese sentences and their English translations (helpdesk mini-game).
SENTENCES = [
    ("Preciso de ajuda.", "I need help."),
    ("Onde fica a biblioteca?", "Where is the library?"),
    ("Perdi o meu cartão de estudante.", "I lost my student card."),
    ("A senha do wifi não funciona.", "The Wi-Fi password doesn't work."),
    ("Quando abre a secretaria?", "When does the office open?"),
]

INVALID_VALUE = "Invalid value for this task"


def make_challenge(kind, rng, tick, tick_rate):
    """A fresh challenge of `kind`, with its time limit starting now."""
    if kind == "ticket":
        challenge = {"kind": kind, "start_tick": tick, "number": rng.randint(3, 6)}
    elif kind == "translate":
        challenge = {"kind": kind, **_new_sentence(rng)}
    elif kind == "card":
        challenge = {"kind": kind, "number": _new_card_number(rng)}
    elif kind == "paper_jam":
        challenge = {"kind": kind, "jams": rng.sample(range(9), 3), "cleared": []}
    elif kind == "socket":
        challenge = {"kind": kind, "free": rng.randrange(12), "tried": []}
    elif kind == "seagull":
        challenge = {"kind": kind, "cell": rng.randrange(9), "hits": 0}
    else:
        raise ValueError(f"Unknown mini-game kind: {kind}")
    challenge["deadline_tick"] = tick + TIME_LIMITS[kind] * tick_rate
    return challenge


def _new_sentence(rng):
    index = rng.randrange(len(SENTENCES))
    sentence, correct = SENTENCES[index]
    others = [english for i, (_, english) in enumerate(SENTENCES) if i != index]
    wrong = rng.sample(others, 2)
    options = rng.sample([correct] + wrong, 3)
    return {"sentence": sentence, "options": options, "correct": correct}


def _new_card_number(rng):
    return f"{rng.randrange(100000):05d}"


def validate_value(kind, value):
    """Raise ValueError if `value` has the wrong type, range or length for `kind`."""
    if kind == "ticket":
        ok = type(value) is bool and value is True
    elif kind == "translate":
        ok = type(value) is int and value in (0, 1, 2)
    elif kind == "card":
        ok = isinstance(value, str) and len(value) == 5 and value.isascii() and value.isdigit()
    elif kind in ("paper_jam", "seagull"):
        ok = type(value) is int and 0 <= value <= 8
    elif kind == "socket":
        ok = type(value) is int and 0 <= value <= 11
    else:
        ok = False
    if not ok:
        raise ValueError(INVALID_VALUE)


def apply_answer(challenge, value, rng, tick, tick_rate):
    """Check an already-validated `value` against `challenge`.

    May mutate `challenge` in place (a wrong answer usually rerolls it). Returns
    (done, note): `done` means the station is finished; `note` is a short message for the
    player, or None when nothing needs saying (a silent miss, or a correct answer).
    """
    kind = challenge["kind"]
    if kind == "ticket":
        return _apply_ticket(challenge, rng, tick, tick_rate)
    if kind == "translate":
        return _apply_translate(challenge, value, rng)
    if kind == "card":
        return _apply_card(challenge, value, rng)
    if kind == "paper_jam":
        return _apply_paper_jam(challenge, value)
    if kind == "socket":
        return _apply_socket(challenge, value)
    if kind == "seagull":
        return _apply_seagull(challenge, value, rng)
    raise ValueError(f"Unknown mini-game kind: {kind}")


def _apply_ticket(challenge, rng, tick, tick_rate):
    # The value itself (always True) carries no information: the counter, recomputed
    # from the current tick, decides whether "that's me!" came at the right moment.
    counter = (tick - challenge["start_tick"]) // tick_rate
    if counter == challenge["number"]:
        return True, None
    note = "Not your turn. Take a new ticket." if counter < challenge["number"] else "You missed your number."
    challenge["start_tick"] = tick
    challenge["number"] = rng.randint(3, 6)
    return False, note


def _apply_translate(challenge, value, rng):
    if challenge["options"][value] == challenge["correct"]:
        return True, None
    challenge.update(_new_sentence(rng))
    return False, "Não percebi."


def _apply_card(challenge, value, rng):
    if value == challenge["number"]:
        return True, None
    challenge["number"] = _new_card_number(rng)
    return False, "Beep. Red."


def _apply_paper_jam(challenge, value):
    if value in challenge["jams"] and value not in challenge["cleared"]:
        challenge["cleared"].append(value)
        if len(challenge["cleared"]) == len(challenge["jams"]):
            return True, None
        return False, None
    return False, "Nothing there."


def _apply_socket(challenge, value):
    if value == challenge["free"]:
        return True, None
    if value not in challenge["tried"]:
        challenge["tried"].append(value)
    return False, "Taken."


def _apply_seagull(challenge, value, rng):
    if value != challenge["cell"]:
        return False, None  # a plain miss: no note, no state change
    challenge["hits"] += 1
    if challenge["hits"] >= 5:
        return True, None
    others = [cell for cell in range(9) if cell != challenge["cell"]]
    challenge["cell"] = rng.choice(others)
    return False, None


def public_view(challenge, tick, tick_rate):
    """The subset of `challenge` the owning player may see, with its secrets removed."""
    kind = challenge["kind"]
    if kind == "ticket":
        counter = (tick - challenge["start_tick"]) // tick_rate
        return {"kind": kind, "number": challenge["number"], "counter": counter}
    if kind == "translate":
        return {"kind": kind, "sentence": challenge["sentence"], "options": list(challenge["options"])}
    if kind == "card":
        return {"kind": kind, "number": challenge["number"]}
    if kind == "paper_jam":
        return {"kind": kind, "cleared": list(challenge["cleared"])}
    if kind == "socket":
        return {"kind": kind, "taken": list(challenge["tried"])}
    if kind == "seagull":
        return {"kind": kind, "cell": challenge["cell"], "hits": challenge["hits"]}
    raise ValueError(f"Unknown mini-game kind: {kind}")
