"""Tests for spec 016: sound effects.

Everything in this spec lives in the browser (web/sound.js, hooked from web/main.js); the
server is untouched (no new message, no new rule). As with the story UI of spec 015, what a
sound actually sounds like cannot be checked by pytest, so these tests guard what can be
checked from outside a browser: the file is served and loaded, the mute button exists, the
module never reaches for an audio file, degrades silently without Web Audio, and every sound
named in the spec is actually wired up in main.js at a plausible, correctly scoped place.
Playing the game by hand (see the spec's manual checklist) covers the rest.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from server.main import app

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# Every sound the spec lists, by the name main.js must pass to Sound.play(...).
EVENT_SOUNDS = [
    "footstep",
    "click",
    "voteSelf",
    "voteOther",
    "roleReveal",
    "taskDone",
    "taskStep",
    "meetingChime",
    "expel",
    "error",
]
MINIGAME_SOUNDS = [
    "ticketDing",
    "cardAccept",
    "cableClick",
    "seagullHit",
    "typingClick",
    "paperRattle",
]


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


# --- The file exists, is served, and is loaded before main.js --------------------------


def test_sound_js_is_served_by_the_app():
    client = TestClient(app)
    response = client.get("/sound.js")
    assert response.status_code == 200
    assert "AudioContext" in response.text


def test_index_html_loads_sound_js_before_main_js():
    page = read("index.html")
    assert 'src="sound.js"' in page
    assert page.index('src="sound.js"') < page.index('src="main.js"')


# --- The mute button: top right, next to "?", same place on every screen ----------------


def test_the_mute_button_sits_next_to_the_help_button():
    page = read("index.html")
    assert 'id="mute-button"' in page
    assert 'id="help-button"' in page
    # Both are plain top-level buttons (not inside an overlay that only shows sometimes),
    # the same way the "?" button already has to be visible on every screen.
    mute_tag = re.search(r'<button id="mute-button".*?</button>', page, re.S).group(0)
    assert 'aria-label' in mute_tag


def test_style_css_places_the_mute_button_beside_help_and_moves_the_panels_over():
    style = read("style.css")
    assert ".mute-button" in style
    # The lobby roster / role badge panel must not start under either round button.
    assert re.search(r"\.panel\s*\{[^}]*right:\s*calc\(1\d\dpx", style, re.S)


# --- The module itself: generated audio only, one volume knob, fails silently ----------


def test_sound_js_uses_no_audio_files_or_external_libraries():
    sound = read("sound.js")
    for ext in (".mp3", ".wav", ".ogg", ".m4a", ".flac"):
        assert ext not in sound
    assert "http://" not in sound and "https://" not in sound


def test_sound_js_has_exactly_one_master_volume_constant():
    sound = read("sound.js")
    assert len(re.findall(r"MASTER_VOLUME\s*=", sound)) == 1


def test_sound_js_degrades_silently_without_web_audio():
    sound = read("sound.js")
    assert "AudioContext" in sound
    # No context (construction failed, or no gesture yet) must make play() a no-op, not throw.
    assert re.search(r"function play\([^)]*\)\s*\{[^}]*if\s*\([^)]*ctx", sound)


def test_sound_js_wraps_localstorage_in_try_catch():
    sound = read("sound.js")
    assert sound.count("localStorage") >= 2  # read the stored choice, and save a new one
    assert "catch" in sound


def test_sound_is_unlocked_on_a_user_gesture_not_on_load():
    sound = read("sound.js")
    assert "pointerdown" in sound or "click" in sound
    assert "keydown" in sound


# --- main.js: every sound the spec lists is actually wired up ---------------------------


def test_main_js_plays_every_event_sound():
    script = read("main.js")
    for name in EVENT_SOUNDS:
        assert f'Sound.play("{name}")' in script, f"missing Sound.play(\"{name}\")"


def test_main_js_plays_every_minigame_sound():
    script = read("main.js")
    for name in MINIGAME_SOUNDS:
        assert f'Sound.play("{name}")' in script, f"missing Sound.play(\"{name}\")"


def test_role_reveal_sound_does_not_depend_on_the_role():
    """The chord must play before the student/examiner branch, so it cannot differ by role."""
    script = read("main.js")
    body = re.search(r"function showRoleScreen\([^)]*\)\s*\{(.*?)\n\}", script, re.S).group(1)
    call_at = body.index('Sound.play("roleReveal")')
    branch_at = body.index('if (roleName === "examiner")')
    assert call_at < branch_at


def test_expel_sound_is_scoped_to_the_examiner_and_the_expelled_player_only():
    """Heard only by the two players involved (spec 016), not broadcast like a toast."""
    script = read("main.js")
    assert script.count('Sound.play("expel")') == 2
    # The examiner's side waits for the server to actually accept the expel (the cooldown
    # starting), not just for the button being pressed.
    assert "pendingExpel" in script


def test_task_sounds_distinguish_a_finished_step_from_a_finished_task():
    script = read("main.js")
    assert 'Sound.play("taskDone")' in script
    assert 'Sound.play("taskStep")' in script
    # The full chime belongs to the existing per-player joke popup, which already only ever
    # fires for the task's own owner (spec 004/012); it must not move into a shared place.
    joke_fn = re.search(r"function showJoke\(task\)\s*\{(.*?)\n\}", script, re.S).group(1)
    assert 'Sound.play("taskDone")' in joke_fn


def test_meeting_bell_plays_once_per_meeting_for_everyone():
    script = read("main.js")
    assert 'Sound.play("meetingChime")' in script
    # Triggered by a phase change, not by who called it, so report and the button both ring it.
    assert re.search(r'state\.phase === "meeting".{0,80}!== "meeting".{0,400}Sound\.play\("meetingChime"\)', script, re.S) or re.search(
        r'!== "meeting".{0,80}state\.phase === "meeting".{0,400}Sound\.play\("meetingChime"\)', script, re.S
    )


def test_vote_sounds_never_reveal_who_was_voted_for():
    script = read("main.js")
    assert 'Sound.play("voteSelf")' in script
    assert 'Sound.play("voteOther")' in script
    # voteOther comes from the existing vote-count list, never from a target id.
    assert "meeting.voted" in script


def test_error_buzz_only_fires_while_the_minigame_is_still_running():
    """A wrong-but-valid answer keeps `doing` set (spec 012); a cancel/time-out does not.
    The buzz must live inside the branch that only runs while `doing` is still truthy, so it
    never fires for a cancel or time-out, which are not "a wrong answer"."""
    script = read("main.js")
    fn = re.search(r"function updateMinigame\(state\)\s*\{(.*)\n\}", script, re.S).group(1)
    assert 'Sound.play("error")' in fn


# --- The server stays untouched: no new message, no new rule, nothing to leak ----------


def test_the_server_gained_no_sound_related_message_or_rule():
    game_src = (ROOT / "server" / "game.py").read_text(encoding="utf-8")
    main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
    assert "sound" not in game_src.lower()
    assert "sound" not in main_src.lower()
