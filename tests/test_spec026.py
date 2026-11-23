"""Tests for spec 026: a colourful campus map that players know about. Like the other map
tests (spec 018), they read the static files."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def colour(source, name):
    match = re.search(rf'const {name} = "(#[0-9a-fA-F]{{6}})"', source)
    assert match, name
    value = match.group(1)
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))


def test_the_id_card_and_the_controls_bar_mention_the_map_key():
    page = read("index.html")
    assert "open the campus map with C" in page
    controls = re.search(r'<span id="controls".*?\n    </span>\n', page, re.S).group(0)
    assert re.search(r'<kbd class="key">C</kbd>\s*map', controls)


def test_the_base_map_has_colours():
    source = read("campusmap.js")
    r, g, b = colour(source, "SEA")
    assert b > r + 40  # blue
    r, g, b = colour(source, "SAND")
    assert r > b + 40  # yellow-ish
    assert "area.color" in source  # every area in its own colour


def test_the_map_can_be_dimmed_when_the_lights_are_off():
    source = read("campusmap.js")
    assert re.search(r"function setDark\(", source)
    assert re.search(r"return \{[^}]*setDark[^}]*\}", source)
    script = read("main.js")
    call = re.search(r"CampusMap\.setDark\((.*?)\);", script, re.S).group(1)
    assert "lights_on === false" in call and '"student"' in call and "alive" in call
    assert ".campus-map.dark" in read("style.css")


def test_the_own_marker_also_shows_in_the_lobby():
    script = read("main.js")
    predict = re.search(r"\n  predictTick\(\) \{\n(.*?)\n  \}\n", script, re.S).group(1)
    assert re.search(r'lastPhase === "playing" \|\| lastPhase === "lobby"', predict)
