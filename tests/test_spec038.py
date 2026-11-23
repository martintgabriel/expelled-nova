"""Tests for spec 038: the in-game handbook can never drift from the rules again.

The handbook in web/index.html is plain text for people, but every number in it is a rule
the server decides. These tests read the handbook and compare each number with the
constant or function in server/game.py it describes.
"""

import html
import re
from pathlib import Path

from server.game import (
    EXPEL_COOLDOWN,
    FIRE_SECONDS,
    FIX_SECONDS,
    MAX_PLAYERS,
    MIN_PLAYERS,
    tasks_per_player,
)

INDEX = Path(__file__).resolve().parent.parent / "web" / "index.html"

# The failed exam's grade (6/20) is part of the story (BRD EX05), not a rule.
STORY_GRADE = "6/20"

NUMBER_WORDS = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}


def handbook_text():
    """The handbook's visible text: from the help panel to its buttons, tags removed."""
    page = INDEX.read_text(encoding="utf-8")
    start = page.rindex("<", 0, page.index('id="help-panel"'))
    end = page.rindex("<", 0, page.index('id="end-round-button"'))
    text = re.sub(r"<[^>]+>", " ", page[start:end])
    return " ".join(html.unescape(text).split())


def sentence_with(word):
    """The handbook sentence that contains `word`, to show in a failing assertion."""
    return next((s for s in re.split(r"(?<=[.:])\s", handbook_text()) if word in s), "")


def task_bands():
    """[(tasks, fewest players, most players)] from tasks_per_player, e.g. (5, 4, 5)."""
    bands = []
    for players in range(MIN_PLAYERS, MAX_PLAYERS + 1):
        count = tasks_per_player(players)
        if bands and bands[-1][0] == count:
            bands[-1] = (count, bands[-1][1], players)
        else:
            bands.append((count, players, players))
    return bands


def test_the_handbook_names_the_smallest_task_count_in_words():
    fewest = tasks_per_player(MIN_PLAYERS)
    assert f"at least {NUMBER_WORDS[fewest]} errands" in handbook_text(), sentence_with("errands")


def test_the_handbook_gives_the_task_count_for_every_round_size():
    text = handbook_text()
    for count, fewest, most in task_bands():
        assert f"{count} with {fewest}–{most}" in text, sentence_with("errands")


def test_the_handbook_gives_the_expel_cooldown():
    assert f"wait {EXPEL_COOLDOWN} seconds" in handbook_text(), sentence_with("wait")


def test_the_handbook_gives_the_time_to_fix_the_lights():
    assert f"light switch in Student Services for {FIX_SECONDS} seconds" in handbook_text()


def test_the_handbook_gives_the_fire_alarm_time():
    assert f"within {FIRE_SECONDS} seconds" in handbook_text()


def test_the_handbook_gives_the_time_to_restart_the_router():
    # The router is fixed like the light switch (FIX_TICKS, game.py: fix and _step_emergency).
    assert f"router in the Library ({FIX_SECONDS} seconds)" in handbook_text()


def test_every_number_in_the_handbook_is_a_rule_from_the_server():
    """A number added to the handbook later must be added here too, with its constant."""
    allowed = {EXPEL_COOLDOWN, FIRE_SECONDS, FIX_SECONDS}
    for count, fewest, most in task_bands():
        allowed |= {count, fewest, most}
    text = handbook_text().replace(STORY_GRADE, "")
    found = {int(number) for number in re.findall(r"\d+", text)}
    assert found <= allowed, f"numbers without a rule: {sorted(found - allowed)}"
    words = {word for number, word in NUMBER_WORDS.items() if number not in allowed}
    stale = [word for word in words if re.search(rf"\b{word}\b", text, re.IGNORECASE)]
    assert not stale, f"number words without a rule: {stale}"
