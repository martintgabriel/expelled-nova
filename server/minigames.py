"""Mini-game challenges for Nova tasks (spec 012). Plain Python, no network code, so it
can be tested directly, like server/game.py.

Each kind has a time limit, a function that builds a fresh challenge with the game's rng,
a function that validates and applies a player's answer, and a function that builds the
player-visible view of a challenge (hiding whatever must stay secret, e.g. which cell has a
paper jam before it is found). server/game.py owns the player's state (which task, which
step) and calls into this module only for what happens inside one station's challenge.
"""

TIME_LIMITS = {
    "ticket": 45,
    "translate": 30,
    "card": 30,
    "paper_jam": 30,
    "cable": 25,
    "seagull": 8,
    "tray": 30,  # spec 021
    "surf": 25,  # spec 021
    "print_file": 30,  # spec 024
    "cert_file": 30,  # spec 024
    "chat": 45,  # spec 024
}

TIMEOUT_NOTES = {
    "ticket": "The queue moved on without you.",
    "translate": "The queue moved on.",
    "card": "The gate locks again.",
    "paper_jam": "Someone else cleared it.",
    "cable": "Out of time.",
    "seagull": "A seagull took it.",
    "tray": "The cafeteria closed.",
    "surf": "The waves are gone. Flat sea.",
    "print_file": "The printer went to sleep.",
    "cert_file": "The printer went to sleep.",
    "chat": "The Helpdesk closed for lunch.",
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

# The five projector/cable port types of the "cable" mini-game (socket, Auditorium).
PORT_TYPES = ["HDMI", "USB-C", "VGA", "DisplayPort", "Mini DisplayPort"]

# Spec 021: the Nova cafeteria line, in order (tray mini-game, Food Court).
TRAY_ORDER = ["Main course", "Soup", "Drink", "Dessert", "Pay"]
# Spec 021: the surf mini-game (beach). A wave rolls by every SURF_PERIOD ticks; standing
# up while its crest is under the board (ticks SURF_CREST of the cycle) rides it.
SURF_PERIOD = 40  # ticks per wave (2 s at 20 ticks per second)
SURF_CREST = (15, 25)  # the riding window inside one cycle, half-open: half a second
SURF_GOAL = 3  # waves to ride

# Spec 024: "pick the right file" for the printer. Each group is four almost identical file
# names; one of them is the file the group chat (or the office) asks for.
FILE_GROUPS = {
    "print_file": [
        ["Assignment_FINAL_v3.pdf", "Assignment_FINAL_v3 (1).pdf", "Assignment_FINAL_v2.pdf", "Assignment_FINAL_v3_old.pdf"],
        ["final_REAL_use_this.docx", "final_REAL_use_this_NOT.docx", "final_REAL.docx", "final_real_use_this.docx"],
        ["group_report_ok_now.pdf", "group_report_ok_now(2).pdf", "group_report_ok.pdf", "group_report_not_ok.pdf"],
        ["slides_last_minute_v7.pptx", "slides_last_minute_v8.pptx", "slides_last_minute_v7.ppt", "slides_lastminute_v7.pptx"],
        ["essay_2999_words.pdf", "essay_3001_words.pdf", "essay_2999_words(1).pdf", "essay_299_words.pdf"],
    ],
    "cert_file": [
        ["Bachelor_certificate_SIGNED.pdf", "Bachelor_certificate_UNSIGNED.pdf", "Bachelor_certificate_SIGNED.jpg", "Bachelour_certificate_SIGNED.pdf"],
        ["certificate_scan_sharp.pdf", "certificate_scan_blurry.pdf", "certificate_photo_from_bed.jpg", "certificate_scan_sharp_cropped.pdf"],
        ["diploma_translated_EN.pdf", "diploma_translated_DE.pdf", "diploma_google_translated_EN.pdf", "diploma_EN_translated.pdf"],
    ],
}
FILE_ROUNDS = {"print_file": 3, "cert_file": 2}
WRONG_FILE = "Wrong file. You printed 40 pages of it."

# Spec 024: three short conversations with the Helpdesk, in European Portuguese. "desk" is
# what the Helpdesk says, "want" what the player wants to answer (in English), "reply" the
# right Portuguese answer. Wrong options are right answers from other lines.
CONVERSATIONS = [
    [
        {"desk": "Olá! Em que posso ajudar?", "want": "I lost my student card.", "reply": "Perdi o meu cartão de estudante."},
        {"desk": "Qual é o seu número de aluno?", "want": "I don't remember.", "reply": "Não me lembro."},
        {"desk": "Então tem de preencher este formulário.", "want": "Thank you, have a nice day!", "reply": "Obrigado, bom dia!"},
    ],
    [
        {"desk": "Bom dia! Diga.", "want": "The Wi-Fi doesn't work.", "reply": "O wifi não funciona."},
        {"desk": "Já tentou desligar e ligar outra vez?", "want": "Yes, three times.", "reply": "Sim, três vezes."},
        {"desk": "Então volte amanhã.", "want": "Okay, see you tomorrow.", "reply": "Está bem, até amanhã."},
    ],
    [
        {"desk": "Olá! Precisa de alguma coisa?", "want": "Where is the auditorium?", "reply": "Onde fica o auditório?"},
        {"desk": "É ali, ao fundo do corredor.", "want": "And the cafeteria?", "reply": "E a cafetaria?"},
        {"desk": "Também ao fundo. Tudo é ao fundo.", "want": "Thank you very much!", "reply": "Muito obrigado!"},
    ],
]
WRONG_REPLY = "Não percebi. Outra vez, por favor."

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
    elif kind == "cable":
        challenge = {"kind": kind, "round": 1, "wrong": 0, **_new_cable_round(rng)}
    elif kind == "seagull":
        challenge = {"kind": kind, "cell": rng.randrange(9), "hits": 0}
    elif kind == "tray":
        challenge = {"kind": kind, "items": rng.sample(TRAY_ORDER, len(TRAY_ORDER)), "next": 0}
    elif kind == "surf":
        challenge = {"kind": kind, "start_tick": tick, "rides": 0}
    elif kind in FILE_GROUPS:
        challenge = {"kind": kind, "round": 1, "rounds": FILE_ROUNDS[kind], **_new_file_round(kind, rng)}
    elif kind == "chat":
        challenge = {"kind": kind, "conversation": rng.randrange(len(CONVERSATIONS)), "step": 0}
        challenge.update(_chat_line(challenge, rng))
    else:
        raise ValueError(f"Unknown mini-game kind: {kind}")
    challenge["deadline_tick"] = tick + TIME_LIMITS[kind] * tick_rate
    return challenge


def _new_file_round(kind, rng):
    group = rng.choice(FILE_GROUPS[kind])
    return {"request": rng.choice(group), "options": rng.sample(group, len(group))}


def _chat_line(challenge, rng):
    """The current line of the conversation: what the desk says, what the player wants to
    say, and three Portuguese replies (the right one and two right replies of other lines)."""
    conversation = CONVERSATIONS[challenge["conversation"]]
    line = conversation[challenge["step"]]
    others = [l["reply"] for c in CONVERSATIONS for l in c if l["reply"] != line["reply"]]
    options = rng.sample([line["reply"]] + rng.sample(others, 2), 3)
    return {
        "steps": len(conversation),
        "line": line["desk"],
        "want": line["want"],
        "options": options,
        "correct": line["reply"],
    }


def _new_sentence(rng):
    index = rng.randrange(len(SENTENCES))
    sentence, correct = SENTENCES[index]
    others = [english for i, (_, english) in enumerate(SENTENCES) if i != index]
    wrong = rng.sample(others, 2)
    options = rng.sample([correct] + wrong, 3)
    return {"sentence": sentence, "options": options, "correct": correct}


def _new_card_number(rng):
    return f"{rng.randrange(100000):05d}"


def _new_cable_round(rng):
    port = rng.choice(PORT_TYPES)
    others = [kind for kind in PORT_TYPES if kind != port]
    wrong_three = rng.sample(others, 3)
    return {"port": port, "cables": rng.sample([port] + wrong_three, 4)}


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
    elif kind == "tray":
        ok = type(value) is int and 0 <= value < len(TRAY_ORDER)
    elif kind == "surf":
        ok = type(value) is bool and value is True
    elif kind in FILE_GROUPS:
        ok = type(value) is int and 0 <= value <= 3
    elif kind == "chat":
        ok = type(value) is int and value in (0, 1, 2)
    elif kind == "cable":
        ok = (
            type(value) is dict
            and set(value) == {"cable"}
            and type(value["cable"]) is int
            and 0 <= value["cable"] <= 3
        )
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
    if kind == "cable":
        return _apply_cable(challenge, value, rng)
    if kind == "seagull":
        return _apply_seagull(challenge, value, rng)
    if kind == "tray":
        return _apply_tray(challenge, value, rng)
    if kind == "surf":
        return _apply_surf(challenge, tick)
    if kind in FILE_GROUPS:
        return _apply_file(challenge, value, rng)
    if kind == "chat":
        return _apply_chat(challenge, value, rng)
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


def _apply_cable(challenge, value, rng):
    index = value["cable"]
    if challenge["cables"][index] == challenge["port"]:
        challenge["round"] += 1
        if challenge["round"] > 3:
            return True, None
        challenge.update(_new_cable_round(rng))
        return False, None
    challenge["wrong"] += 1
    if challenge["wrong"] >= 2:
        challenge["round"] = 1
        challenge["wrong"] = 0
        challenge.update(_new_cable_round(rng))
        return False, "Two wrong cables. Start again."
    return False, "No signal."


def _apply_seagull(challenge, value, rng):
    if value != challenge["cell"]:
        return False, None  # a plain miss: no note, no state change
    challenge["hits"] += 1
    if challenge["hits"] >= 5:
        return True, None
    others = [cell for cell in range(9) if cell != challenge["cell"]]
    challenge["cell"] = rng.choice(others)
    return False, None


def _apply_tray(challenge, value, rng):
    if challenge["items"][value] == TRAY_ORDER[challenge["next"]]:
        challenge["next"] += 1
        return challenge["next"] == len(TRAY_ORDER), None
    challenge["next"] = 0
    challenge["items"] = rng.sample(TRAY_ORDER, len(TRAY_ORDER))
    return False, "Wrong order. Back of the queue."


def _apply_file(challenge, value, rng):
    kind = challenge["kind"]
    if challenge["options"][value] == challenge["request"]:
        if challenge["round"] >= challenge["rounds"]:
            return True, None
        challenge["round"] += 1
        challenge.update(_new_file_round(kind, rng))
        return False, None
    challenge["round"] = 1
    challenge.update(_new_file_round(kind, rng))
    return False, WRONG_FILE


def _apply_chat(challenge, value, rng):
    if challenge["options"][value] == challenge["correct"]:
        if challenge["step"] + 1 >= challenge["steps"]:
            return True, None
        challenge["step"] += 1
        challenge.update(_chat_line(challenge, rng))
        return False, None
    challenge["step"] = 0
    challenge.update(_chat_line(challenge, rng))
    return False, WRONG_REPLY


def _surf_phase(challenge, tick):
    return (tick - challenge["start_tick"]) % SURF_PERIOD


def _apply_surf(challenge, tick):
    # Like the ticket game, the value (always True) carries no information: the server's
    # own tick decides whether the player stood up on the crest.
    low, high = SURF_CREST
    if low <= _surf_phase(challenge, tick) < high:
        challenge["rides"] += 1
        return challenge["rides"] >= SURF_GOAL, None
    challenge["rides"] = 0
    return False, "Wipeout! Paddle back out."


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
    if kind == "cable":
        return {
            "kind": kind,
            "round": challenge["round"],
            "port": challenge["port"],
            "cables": list(challenge["cables"]),
            "wrong": challenge["wrong"],
        }
    if kind == "seagull":
        return {"kind": kind, "cell": challenge["cell"], "hits": challenge["hits"]}
    if kind == "tray":
        return {"kind": kind, "items": list(challenge["items"]), "next": challenge["next"], "order": list(TRAY_ORDER)}
    if kind in FILE_GROUPS:
        return {
            "kind": kind,
            "request": challenge["request"],
            "options": list(challenge["options"]),
            "round": challenge["round"],
            "rounds": challenge["rounds"],
        }
    if kind == "chat":
        # Never "correct": which reply is right stays secret.
        return {
            "kind": kind,
            "line": challenge["line"],
            "want": challenge["want"],
            "options": list(challenge["options"]),
            "step": challenge["step"],
            "steps": challenge["steps"],
        }
    if kind == "surf":
        return {
            "kind": kind,
            "phase": _surf_phase(challenge, tick),
            "period": SURF_PERIOD,
            "crest": list(SURF_CREST),
            "rides": challenge["rides"],
            "goal": SURF_GOAL,
        }
    raise ValueError(f"Unknown mini-game kind: {kind}")
