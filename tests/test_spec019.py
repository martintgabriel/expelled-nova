"""Tests for spec 019 (playtest fixes, part 2: sound). Like the tests of specs 016 and
017 they read the static files, since the sound only exists in the browser."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def effects_block():
    return re.search(r"const EFFECTS = \{(.*?)\n  \};", read("sound.js"), re.S).group(1)


# --- 1. Volume slider ----------------------------------------------------------------------


def test_the_page_has_a_volume_slider_from_0_to_100():
    page = read("index.html")
    tag = re.search(r'<input[^>]*id="volume-slider"[^>]*>', page).group(0)
    assert 'type="range"' in tag
    assert 'min="0"' in tag and 'max="100"' in tag
    assert "aria-label" in tag


def test_the_slider_sits_outside_every_overlay_like_the_mute_button():
    page = read("index.html")
    assert page.index('id="volume-slider"') > page.index('id="mute-button"')


def test_sound_js_has_volume_functions_and_still_one_master_constant():
    sound = read("sound.js")
    assert len(re.findall(r"MASTER_VOLUME\s*=", sound)) == 1
    assert re.search(r"function setVolume\(", sound)
    assert "getVolume" in sound and "setVolume" in sound
    assert re.search(r"MASTER_VOLUME\s*\*\s*volume", sound)


def test_the_volume_is_remembered_with_storage_errors_caught():
    sound = read("sound.js")
    assert "expelled-nova-volume" in sound
    assert sound.count("try {") >= 4  # load and save, for mute and for volume


def test_main_js_wires_the_slider():
    script = read("main.js")
    assert 'getElementById("volume-slider")' in script
    assert "Sound.setVolume(" in script


def test_style_css_styles_the_slider():
    assert ".volume-slider" in read("style.css")


# --- 2. Expel voice ------------------------------------------------------------------------


def test_the_expel_voice_is_generated_by_the_browser():
    sound = read("sound.js")
    assert "speechSynthesis" in sound
    assert "Expelled!" in sound
    assert re.search(r"\bexpelVoice\s*:", effects_block())


def test_the_voice_respects_mute():
    sound = read("sound.js")
    body = sound[sound.index("function say("):]
    body = body[: body.index("\n  }\n")]
    assert "muted" in body


def test_the_voice_plays_exactly_where_the_paper_rip_plays():
    script = read("main.js")
    assert script.count('Sound.play("expel")') == script.count('Sound.play("expelVoice")') == 2


# --- 3. End sound by winning side ----------------------------------------------------------


def test_there_is_an_end_sound_for_each_side():
    block = effects_block()
    assert re.search(r"\bstudentsWin\s*:", block)
    assert re.search(r"\bexaminersWin\s*:", block)
    assert "winJingle" not in read("sound.js") and "loseJingle" not in read("sound.js")


def test_the_end_sound_depends_on_the_winner_not_on_the_own_role():
    script = read("main.js")
    match = re.search(r'state\.phase === "ended" && previousPhase !== "ended"\) \{(.{0,300})', script, re.S)
    after = match.group(1)
    assert 'Sound.play("studentsWin")' in after and 'Sound.play("examinersWin")' in after
    assert "winner" in after
    assert "state.role" not in after
