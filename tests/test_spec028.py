"""Tests for spec 028: sound settings, taken colours, examiners recognise each other.

The server part (which colours are taken, for the colour picker on the join screen) is
tested directly. The browser part is checked like specs 016, 017 and 020: by reading the
static files in web/, since it only exists in the browser.
"""

import json
import random
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.game import Game, GameError, load_map
from server.main import app

WEB = Path(__file__).resolve().parent.parent / "web"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def new_game():
    return Game(load_map(), rng=random.Random(0))


def playing(count=7):
    """A started round. With 7 players the automatic rule gives 2 examiners (spec 019)."""
    game = new_game()
    players = [game.join(f"Player {i}") for i in range(count)]
    game.start(players[0].id)
    examiners = [p for p in players if p.role == "examiner"]
    students = [p for p in players if p.role == "student"]
    return game, examiners, students


def receive_until(ws, predicate, limit=200):
    for _ in range(limit):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message did not arrive")


def function_body(script, name):
    """The body of the top-level `function name(...) { ... }` in a script."""
    match = re.search(rf"^function {name}\([^)]*\)\s*\{{\n(.*?)^\}}", script, re.S | re.M)
    assert match, f"no top-level function {name}()"
    return match.group(1)


# --- 3. Taken colours: the rule ---------------------------------------------------------------


def test_an_empty_game_has_no_taken_colours():
    assert new_game().taken_colors() == {}


def test_taken_colours_name_the_player_who_has_each_colour():
    game = new_game()
    game.join("Ada", color=5)
    game.join("Bo")  # "any": the lowest free colour, 0
    assert game.taken_colors() == {5: "Ada", 0: "Bo"}


def test_a_colour_is_free_again_when_its_player_leaves():
    game = new_game()
    ada = game.join("Ada", color=5)
    game.join("Bo", color=2)
    game.leave(ada.id)
    assert game.taken_colors() == {2: "Bo"}
    assert game.join("Cy", color=5).color == 5  # and it can be picked again


def test_a_rejected_join_takes_no_colour():
    game = new_game()
    game.join("Ada", color=5)
    with pytest.raises(GameError, match="Colour is already taken"):
        game.join("Bo", color=5)
    assert game.taken_colors() == {5: "Ada"}


def test_picking_a_taken_colour_is_still_rejected_and_changes_nothing():
    """The picker only shows what is taken; the server rule of spec 022 stays the judge."""
    game = new_game()
    game.join("Ada", color=5)
    before = json.dumps(game.snapshot())
    with pytest.raises(GameError, match="Colour is already taken"):
        game.join("Bo", color=5)
    assert len(game.players) == 1
    assert json.dumps(game.snapshot()) == before


def test_taken_colours_stay_the_same_during_a_round():
    """Ghosts keep their colour (it is kept until the player leaves), so the list tells
    nobody who is still alive."""
    game, examiners, students = playing()
    before = game.taken_colors()
    students[0].alive = False
    assert game.taken_colors() == before
    assert len(before) == 7


# --- 3. Taken colours: the page asks the server before joining -------------------------------


def test_the_taken_colours_endpoint_starts_empty():
    with TestClient(app) as client:
        response = client.get("/taken-colors")
        assert response.status_code == 200
        assert response.json() == {"taken": {}}


def test_the_taken_colours_endpoint_follows_joining_and_leaving():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as a:
            a.send_json({"type": "join", "name": "Ada", "color": 6})
            receive_until(a, lambda m: m["type"] == "welcome")
            with client.websocket_connect("/ws") as b:
                b.send_json({"type": "join", "name": "Bo", "color": 3})
                receive_until(b, lambda m: m["type"] == "welcome")
                assert client.get("/taken-colors").json() == {"taken": {"6": "Ada", "3": "Bo"}}
            # Bo's connection closed: wait until Ada no longer receives Bo, then ask again.
            receive_until(a, lambda m: m["type"] == "state" and len(m["players"]) == 1)
            assert client.get("/taken-colors").json() == {"taken": {"6": "Ada"}}


def test_a_taken_colour_is_still_rejected_over_the_websocket():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
            a.send_json({"type": "join", "name": "Ada", "color": 6})
            receive_until(a, lambda m: m["type"] == "welcome")
            b.send_json({"type": "join", "name": "Bo", "color": 6})
            assert receive_until(b, lambda m: m["type"] == "error")["reason"] == "Colour is already taken"
            assert client.get("/taken-colors").json() == {"taken": {"6": "Ada"}}


def test_the_taken_colours_endpoint_is_never_cached():
    with TestClient(app) as client:
        assert client.get("/taken-colors").headers["cache-control"] == "no-store"


def test_the_taken_colours_endpoint_ignores_any_input():
    with TestClient(app) as client:
        response = client.get("/taken-colors?taken=9&name=Mallory")
        assert response.json() == {"taken": {}}


def test_the_taken_colours_endpoint_tells_names_and_colours_only(fresh_game):
    """Anyone can ask (also without joining), so the answer must hold nothing secret: no
    player id, no role, no position, not who is a ghost. Also in a running round."""
    players = [fresh_game.join(f"Player {i}") for i in range(7)]
    fresh_game.start(players[0].id)
    next(p for p in players if p.role == "student").alive = False
    with TestClient(app) as client:
        answer = client.get("/taken-colors").json()
    assert answer == {"taken": {str(p.color): p.name for p in players}}
    text = json.dumps(answer)
    for secret in ("examiner", "student", "role", "alive", "ghost"):
        assert secret not in text, secret
    assert not any(p.id in answer["taken"].values() for p in players)


# --- 4. Examiners see each other; students get nothing new -----------------------------------


def test_a_student_snapshot_has_no_fellow_examiner_information():
    """BRD R2: the red names are drawn from `fellow_examiners`, which only examiners get."""
    game, examiners, students = playing()
    examiner_ids = {p.id for p in examiners}
    assert len(examiner_ids) == 2
    for student in students:
        snapshot = game.snapshot_for(student.id)
        assert snapshot["role"] == "student"
        assert "fellow_examiners" not in snapshot
        assert "roles" not in snapshot
        assert "examiner" not in json.dumps(snapshot)
        # No list in the snapshot is exactly the examiners (which would give them away).
        for key, value in snapshot.items():
            if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
                assert set(value) != examiner_ids, key


def test_a_ghost_student_snapshot_has_no_fellow_examiner_information_either():
    game, examiners, students = playing()
    students[0].alive = False
    snapshot = game.snapshot_for(students[0].id)
    assert "fellow_examiners" not in snapshot
    assert "roles" not in snapshot
    assert "examiner" not in json.dumps(snapshot)


def test_a_student_gets_nothing_about_examiners_in_a_meeting():
    game, examiners, students = playing()
    caller = students[0]
    col, row = game.campus["meeting_point"]
    tile = game.campus["tile_size"]
    caller.x, caller.y = (col + 0.5) * tile, (row + 0.5) * tile
    game.call_meeting(caller.id)
    assert game.phase == "meeting"
    for student in students:
        snapshot = game.snapshot_for(student.id)
        assert "fellow_examiners" not in snapshot
        assert "examiner" not in json.dumps(snapshot)


def test_each_examiner_gets_exactly_the_other_examiner():
    game, examiners, students = playing()
    first, second = examiners
    assert game.snapshot_for(first.id)["fellow_examiners"] == [second.id]
    assert game.snapshot_for(second.id)["fellow_examiners"] == [first.id]


def test_examiners_still_know_each_other_at_the_end_and_students_get_the_public_roles_only():
    """The end screen: roles are public for everyone there (spec 003); the fellow list still
    goes to examiners only."""
    game, examiners, students = playing()
    for student in students:
        student.alive = False
    game.step()  # the win check
    if game.phase != "ended":
        game.leave(students[0].id)  # a leave runs the win check too
    assert game.phase == "ended"
    assert game.snapshot_for(examiners[0].id)["fellow_examiners"] == [examiners[1].id]
    student_view = game.snapshot_for(students[1].id)
    assert "fellow_examiners" not in student_view
    assert set(student_view["roles"].values()) == {"student", "examiner"}


# --- 1. One "Sound settings" button and one panel ----------------------------------------------


def sound_panel():
    page = read("index.html")
    start = page.index('id="sound-panel"')
    return page[page.rindex("<div", 0, start) : page.index("<script")]


def test_the_speaker_button_opens_the_sound_settings():
    page = read("index.html")
    tag = re.search(r'<button id="mute-button"[^>]*>', page).group(0)
    assert 'aria-label="Sound settings"' in tag
    assert 'aria-expanded="false"' in tag
    assert 'aria-controls="sound-panel"' in tag
    assert "help-button" in tag  # the same round button, in the same place on every screen


def test_the_sound_panel_bundles_every_sound_control():
    panel = sound_panel()
    assert re.search(r"\bhidden\b", panel[: panel.index(">")])  # closed until the button opens it
    music = re.search(r'<button[^>]*id="music-switch"[^>]*>', panel)
    effects = re.search(r'<button[^>]*id="effects-switch"[^>]*>', panel)
    slider = re.search(r'<input[^>]*id="volume-slider"[^>]*>', panel)
    assert music and effects and slider
    for switch in (music, effects):
        assert 'role="switch"' in switch.group(0) and "aria-label" in switch.group(0)
    assert "Background music" in panel and "Sound effects" in panel and "Volume" in panel
    close = re.search(r'<button[^>]*id="sound-close"[^>]*>', panel)
    assert close and "aria-label" in close.group(0)


def test_the_panel_is_not_a_full_screen_overlay():
    """A small panel under the button: it must not cover the game or the join card."""
    panel = sound_panel()
    assert "overlay" not in panel[: panel.index(">")]
    assert ".sound-panel" in read("style.css")


def test_the_slider_has_a_speaker_icon_at_both_ends():
    panel = sound_panel()
    slider_at = panel.index('id="volume-slider"')
    row_start = panel.rindex('class="sound-volume"', 0, slider_at)
    row = panel[row_start : panel.index("</div>", slider_at)]
    assert "<svg" in row[: row.index("<input")], "no icon left of the slider"
    assert "<svg" in row[row.index("<input") :], "no icon right of the slider"
    assert "<img" not in panel  # inline SVG only, no image files


def test_how_to_play_no_longer_contains_the_music_switch():
    page = read("index.html")
    handbook = page[page.index('id="help-panel"') : page.index('id="map-panel"')]
    assert "music" not in handbook.lower()
    assert 'role="switch"' not in handbook
    assert page.count('id="music-switch"') == 1


def test_main_js_wires_the_panel_and_its_controls():
    script = read("main.js")
    for element in ("sound-panel", "sound-close", "music-switch", "effects-switch", "volume-slider"):
        assert f'getElementById("{element}")' in script, element
    assert "Music.toggle()" in script or "Music.setOn(" in script
    assert "Sound.setEffectsOn(" in script
    assert "Sound.setVolume(" in script
    body = function_body(script, "setSoundOpen")
    assert "aria-expanded" in body


def test_escape_closes_the_sound_panel():
    script = read("main.js")
    listener = re.search(r'document\.addEventListener\("keydown", \(event\) => \{\n(.*?)\n\}\);', script, re.S).group(1)
    assert re.search(r'"Escape".{0,80}soundPanel', listener, re.S)


def test_sound_js_separates_the_effects_from_the_volume():
    """The effects switch silences effects only; the slider is the one volume for music and
    effects, so the master gain no longer follows the effects switch."""
    sound = read("sound.js")
    assert re.search(r"return\s*\{[^}]*setEffectsOn", sound, re.S)
    assert re.search(r"return\s*\{[^}]*effectsOn", sound, re.S)
    gain = re.search(r"function gainValue\(\)\s*\{(.*?)\n  \}", sound, re.S).group(1)
    assert "muted" not in gain
    assert re.search(r"function play\([^)]*\)\s*\{[^}]*muted", sound)


def test_the_settings_stay_remembered_under_the_same_keys():
    sound = read("sound.js")
    assert '"expelled-nova-muted"' in sound and '"expelled-nova-volume"' in sound
    assert '"expelled-nova-music"' in read("music.js")


# --- 2. The muted icon: a diagonal strike-through ----------------------------------------------


def test_the_strike_through_is_on_the_button_and_in_the_panel():
    page = read("index.html")
    button = re.search(r'<button id="mute-button".*?</button>', page, re.S).group(0)
    assert 'class="sound-strike"' in button
    assert 'class="sound-strike"' in sound_panel()
    # Hidden until main.js finds the music off or the volume at 0.
    for tag in re.findall(r'<[^>]*class="sound-strike"[^>]*>', page):
        assert re.search(r"\bhidden\b", tag), tag


def test_the_strike_through_follows_music_off_or_volume_zero():
    script = read("main.js")
    body = function_body(script, "updateSoundSettings")
    assert "sound-strike" in body or "soundStrikes" in body
    assert "Music.isOn()" in body
    assert "Sound.getVolume() === 0" in body
    # SVG elements have no `hidden` property: the attribute itself must be toggled.
    assert "toggleAttribute(" in body


# --- 3. Taken colours in the picker --------------------------------------------------------------


def test_the_picker_asks_the_server_which_colours_are_taken():
    script = read("main.js")
    body = re.search(r"^async function refreshTakenColors\(\)\s*\{\n(.*?)^\}", script, re.S | re.M).group(1)
    assert 'fetch("/taken-colors"' in body
    assert "catch" in body  # an unreachable server must not break the join screen
    # Live: asked again and again while the join screen shows, and stopped once joined.
    assert re.search(r"setInterval\(refreshTakenColors,", script)
    assert "clearInterval(" in script


def test_a_taken_swatch_is_unavailable_and_says_who_has_it():
    script = read("main.js")
    body = function_body(script, "renderLook")
    assert "Taken by " in body
    assert ".disabled = " in body  # not clickable
    assert '"taken"' in body  # the crossed-out, dimmed look (style.css)
    assert "aria-label" in body and ".title = " in body
    assert "textContent" in body or "setAttribute(" in body  # the name is set as text, never HTML
    assert "innerHTML" not in body


def test_style_css_crosses_out_and_dims_a_taken_swatch():
    style = read("style.css")
    assert ".swatch.taken" in style
    rules = " ".join(re.findall(r"\.swatch\.taken[^{]*\{[^}]*\}", style))
    assert "opacity" in rules
    assert "not-allowed" in rules
    assert "linear-gradient" in rules  # the diagonal line


# --- 4. Name colours: red for the examiners' team, green for the own student name --------------


def test_the_red_name_comes_from_fellow_examiners_only():
    script = read("main.js")
    body = function_body(script, "isFellowExaminer")
    assert "fellow_examiners" in body
    assert "roles" not in body and "role" not in body.replace("fellow_examiners", "")


def test_the_own_name_follows_the_own_role_and_other_names_only_the_fellow_list():
    """Examiner: the own name and the teammate's are red. Student: only the own name is
    green. Every other name keeps its normal colour, so nobody learns who else is a student:
    for another player the colour may only come from `fellow_examiners`, never from the
    public `roles` of the end screen or anything else."""
    body = function_body(read("main.js"), "nameTone")
    own, others = body.split("isFellowExaminer(")[0], body[body.index("isFellowExaminer(") :]
    assert "playerId === welcome.id" in own  # the own name is decided first ...
    assert "state.role" in own  # ... from the own role only
    assert "roles" not in body
    assert "state.role" not in others  # another player's name never follows a role
    assert '"examiner"' in others


@pytest.mark.parametrize("function", ["buildPlayerCard", "renderResult", "renderEnd"])
def test_meeting_voting_and_result_names_are_marked(function):
    body = function_body(read("main.js"), function)
    assert "markName(" in body


def test_a_marked_name_gets_its_class_from_the_tone_as_text_only():
    body = function_body(read("main.js"), "markName")
    assert "nameTone(" in body
    assert "classList.add(" in body
    assert "innerHTML" not in body


def test_the_map_names_are_coloured_from_the_same_rule():
    script = read("main.js")
    assert "Render.setNameTone(" in script
    assert re.search(r"Render\.setNameTone\([^;]*nameTone\(", script)
    render = read("render.js")
    assert re.search(r"return \{[^}]*\bsetNameTone,", render, re.S)
    # render.js only gets a tone per character: it never reads the state itself.
    assert "fellow_examiners" not in render


def test_render_js_has_a_red_and_a_green_name_and_keeps_the_normal_ones():
    render = read("render.js")
    tones = re.search(r"const NAME_TONE_COLORS = \{(.*?)\};", render, re.S).group(1)
    assert re.search(r"examiner:\s*\"#[0-9a-f]{6}\"", tones)
    assert re.search(r"student:\s*\"#[0-9a-f]{6}\"", tones)
    # Without a tone (the lobby, every other player) the name keeps the colour it was made
    # with: yellow for the own name, white for everyone else.
    assert "OWN_NAME_COLOR" in render and '"#ffffff"' in render


def test_style_css_has_the_red_and_the_green_name():
    style = read("style.css")
    red = re.search(r"\.name-examiner[^{]*\{([^}]*)\}", style)
    green = re.search(r"\.name-student[^{]*\{([^}]*)\}", style)
    assert red and "--stamp-red" in red.group(1)
    assert green and "--stamp-green" in green.group(1)
