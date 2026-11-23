"""Tests for spec 032: the "EXPELLED!" stamp for the examiner and the expelled student."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def test_the_page_has_the_stamp_hidden():
    page = read("index.html")
    tag = re.search(r'<div id="expelled-stamp"[^>]*>', page).group(0)
    assert "hidden" in tag
    assert "EXPELLED!" in page
    assert "#expelled-stamp" in read("style.css")


def test_the_stamp_shows_exactly_where_the_expel_sound_plays():
    script = read("main.js")
    assert script.count("showExpelledStamp(") == 3  # the function and its two calls
    for match in re.finditer(r'Sound\.play\("expel"\);', script):
        after = script[match.end() : match.end() + 250]
        assert "showExpelledStamp(" in after


def test_each_side_gets_its_own_line():
    script = read("main.js")
    assert 'showExpelledStamp("You expelled a student.")' in script
    assert 'showExpelledStamp("An examiner caught you. You are a ghost now.")' in script
