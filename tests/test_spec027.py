"""Tests for spec 027: the sound settings panel. Like specs 016, 017 and 020, they read the
static files, since sound only exists in the browser."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def panel_html():
    page = read("index.html")
    return re.search(r'<div id="sound-panel".*?\n  </div>\n', page, re.S).group(0)


def test_the_panel_bundles_sound_volume_and_music():
    panel = panel_html()
    for control in ('id="sound-switch"', 'id="volume-slider"', 'id="music-switch"'):
        assert control in panel, control
    assert "hidden" in panel.split(">")[0]  # closed at first


def test_the_music_switch_left_the_handbook():
    page = read("index.html")
    help_panel = re.search(r'id="help-panel".*?</section>', page, re.S)
    assert page.count('id="music-switch"') == 1
    assert "help-music" not in page


def test_the_speaker_button_opens_the_panel():
    script = read("main.js")
    handler = re.search(r'ui\.muteButton\.addEventListener\("click", \(\) => \{(.*?)\n\}\);', script, re.S).group(1)
    assert "setSoundPanelOpen(" in handler
    assert "toggleMute" not in handler


def test_the_panel_closes_with_esc_and_a_click_outside():
    script = read("main.js")
    assert re.search(r'event\.key === "Escape" && !ui\.soundPanel\.hidden', script)
    assert "ui.soundPanel.contains(event.target)" in script


def test_the_icon_has_three_states():
    page = read("index.html")
    for part in ('id="mute-icon-on"', 'id="mute-icon-off"', 'id="music-off-badge"'):
        assert part in page, part
    body = script_function(read("main.js"), "updateMuteIcon")
    assert "Music.isOn()" in body and "Sound.isMuted()" in body


def script_function(script, name):
    start = script.index(f"function {name}(")
    return script[start : script.index("\n}\n", start)]


def test_the_sound_switch_mutes():
    script = read("main.js")
    handler = re.search(r'ui\.soundSwitch\.addEventListener\("click", \(\) => \{(.*?)\n\}\);', script, re.S).group(1)
    assert "Sound.toggleMute()" in handler or "Sound.setMuted(" in handler
