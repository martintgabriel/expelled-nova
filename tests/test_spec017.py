"""Tests for spec 017: background music and more sound effects.

Like spec 016, everything lives in the browser (web/music.js and web/sound.js, hooked from
web/main.js); the server is untouched. What music or a sound actually sounds like cannot be
checked by pytest, so these tests guard what can be checked from outside a browser: the new
file is served and loaded in the right order, it reaches for no audio file and no second
AudioContext, the music switch exists, every new mood and effect is wired up, and each hook
sits behind the guard that keeps it from revealing anything (spec 017, "What a sound or the
music must not reveal"). Playing the game by hand (the spec's manual checklist) covers the
rest.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from server.main import app

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

MOODS = ["lobby", "playing", "dark", "off"]
NEW_EFFECTS = [
    "reportAlarm",
    "countdownTick",
    "ventHatch",
    "lightsOut",
    "lightsOn",
    "studentsWin",  # spec 020: replaces winJingle
    "examinersWin",  # spec 020: replaces loseJingle
]
# Sounds the spec decided against: each would play on one role's phone only.
REMOVED_EFFECTS = ["ventIn", "ventOut", "ventMove", "fixTick"]


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def function_containing(script, needle):
    """The body of the top-level `function name(...) { ... }` in main.js that contains needle."""
    for match in re.finditer(r"^function \w+\([^)]*\)\s*\{\n(.*?)^\}", script, re.S | re.M):
        if needle in match.group(1):
            return match.group(1)
    raise AssertionError(f"no top-level function contains {needle}")


def text_before(script, needle, length):
    """The `length` characters in front of the first occurrence of needle."""
    at = script.index(needle)
    return script[max(0, at - length) : at]


# --- The file exists, is served, and is loaded between sound.js and main.js -------------


def test_music_js_is_served_by_the_app():
    client = TestClient(app)
    response = client.get("/music.js")
    assert response.status_code == 200
    assert "Music" in response.text


def test_index_html_loads_sound_then_music_then_main():
    page = read("index.html")
    assert 'src="music.js"' in page
    assert page.index('src="sound.js"') < page.index('src="music.js"') < page.index('src="main.js"')


# --- music.js: generated only, no context of its own, one volume knob -------------------


def test_music_js_uses_no_audio_files_or_urls():
    music = read("music.js")
    for ext in (".mp3", ".wav", ".ogg", ".m4a", ".flac"):
        assert ext not in music
    assert "http://" not in music and "https://" not in music


def test_music_js_creates_no_audio_context_and_uses_sound_on_unlock():
    music = read("music.js")
    assert not re.search(r"new\s+\w*AudioC\w*\s*\(", music)
    assert "webkitAudioContext" not in music
    assert "Sound.onUnlock(" in music


def test_music_js_has_exactly_one_music_volume_constant():
    music = read("music.js")
    assert len(re.findall(r"MUSIC_VOLUME\s*=", music)) == 1


def test_music_switch_is_stored_under_its_own_key_with_try_catch():
    music = read("music.js")
    assert music.count("localStorage") >= 2  # read the stored choice, and save a new one
    assert "catch" in music
    assert '"expelled-nova-music"' in music
    assert "expelled-nova-muted" not in music  # the mute key belongs to sound.js


def test_music_pauses_while_the_tab_is_hidden():
    assert "visibilitychange" in read("music.js")


def test_music_uses_one_lookahead_scheduler_against_the_audio_clock():
    music = read("music.js")
    assert "setInterval" in music
    assert "currentTime" in music


# --- sound.js: still the one place that creates the context; now with onUnlock ----------


def test_sound_js_still_creates_the_context_in_exactly_one_place():
    sound = read("sound.js")
    assert len(re.findall(r"new\s+\w*AudioC\w*\s*\(", sound)) == 1


def test_sound_js_exposes_on_unlock():
    sound = read("sound.js")
    assert re.search(r"return\s*\{[^}]*onUnlock", sound, re.S)


def test_each_new_effect_is_defined_in_sound_js():
    sound = read("sound.js")
    effects = re.search(r"const EFFECTS = \{(.*?)\n  \};", sound, re.S).group(1)
    for name in NEW_EFFECTS:
        assert re.search(rf"\b{name}\s*:", effects), f"{name} missing from EFFECTS"


# --- The music switch: inside the help overlay ------------------------------------------


def test_the_music_switch_exists_with_an_aria_label():
    # Spec 027 moved the switch from the help overlay into the sound settings panel
    # (tests/test_spec027.py); what stays from spec 017: one switch with an aria-label.
    page = read("index.html")
    switch = re.search(r'<(?:button|input)[^>]*id="music[^"]*"[^>]*>', page)
    assert switch, "no music switch"
    assert "aria-label" in switch.group(0)


# --- main.js: moods and the beach waves ---------------------------------------------------


def test_main_js_sets_every_mood_and_the_beach():
    script = read("main.js")
    for mood in MOODS:
        assert f'Music.setMood("{mood}")' in script, f'missing Music.setMood("{mood}")'
    assert "Music.setBeach(" in script


def test_the_mood_depends_on_neither_role_nor_alive():
    """Music the same for every role and for ghosts: an examiner theme or a ghost theme would
    tell the people sitting next to that phone who or what that player is."""
    script = read("main.js")
    body = function_containing(script, "Music.setMood(")
    # Every mood is picked in that one function, nowhere else.
    assert body.count("Music.setMood(") == script.count("Music.setMood(")
    assert "role" not in body
    assert "alive" not in body


# --- main.js: every new effect is played, each behind its guard --------------------------


def test_main_js_plays_every_new_effect():
    script = read("main.js")
    for name in NEW_EFFECTS:
        assert f'Sound.play("{name}")' in script, f'missing Sound.play("{name}")'


def test_report_alarm_only_plays_for_a_report():
    script = read("main.js")
    before = text_before(script, 'Sound.play("reportAlarm")', 200)
    assert re.search(r'reason\s*===\s*"report"', before)


def test_the_vent_hatch_comes_from_open_vents_never_from_the_own_vent():
    """Every player in sight of the hatch hears it, the examiner included; state.vent is
    sent to examiners only, so a sound from it would play on an examiner's phone only."""
    script = read("main.js")
    assert script.count('Sound.play("ventHatch")') == 1
    body = function_containing(script, 'Sound.play("ventHatch")')
    assert "open_vents" in body
    assert "state.vent" not in body


def test_no_sound_exists_for_one_role_only():
    script = read("main.js")
    sound = read("sound.js")
    for name in REMOVED_EFFECTS:
        assert name not in script, name
        assert name not in sound, name


def test_lights_sounds_only_play_while_the_round_goes_on():
    """A meeting turns the lights back on: that must play only the meeting sounds."""
    script = read("main.js")
    for name in ("lightsOut", "lightsOn"):
        before = text_before(script, f'Sound.play("{name}")', 400)
        assert 'previousPhase === "playing"' in before, name


def test_the_jingles_sit_in_the_ended_phase_change_and_compare_against_winner():
    script = read("main.js")
    match = re.search(
        r'(state\.phase === "ended".{0,80}!== "ended"|!== "ended".{0,80}state\.phase === "ended")(.{0,500})',
        script,
        re.S,
    )
    assert match, "no phase change into ended"
    after = match.group(2)
    assert "winner" in after
    assert 'Sound.play("studentsWin")' in after  # spec 020: by winning side
    assert 'Sound.play("examinersWin")' in after


def test_the_countdown_only_ticks_while_the_vote_is_open():
    script = read("main.js")
    before = text_before(script, 'Sound.play("countdownTick")', 300)
    assert "result" in before
    assert "seconds_left" in before


# --- The server stays untouched ------------------------------------------------------------


def test_the_server_gained_no_sound_or_music_code():
    for path in ("server/game.py", "server/main.py"):
        source = (ROOT / path).read_text(encoding="utf-8").lower()
        assert "sound" not in source, path
        assert "music" not in source, path
