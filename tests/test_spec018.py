"""Tests for spec 018: the campus map (key C).

Everything in this spec lives in the browser (web/campusmap.js, opened from web/main.js);
the server is untouched. As with specs 015-017, what the map looks like cannot be checked
by pytest, so these tests guard what can be checked from outside a browser: the new file is
served and loaded in the right order, the button and the overlay exist, the key C toggles
the map with the same guards as H (and M still calls a meeting), and above all that the map
module reads only the static campus data it draws and main.js only ever hands it the own
position and colour. Playing the game by hand (the spec's manual checklist) covers the rest.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from server.main import app

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

# The only parts of welcome.map the map module may read (spec 018, "Reads only what it draws").
ALLOWED_MAP_KEYS = {"tile_size", "grid", "decor", "areas", "labels", "meeting_point", "light_switch"}
# What the map must never read: other players, roles, hidden things, and the parts of
# welcome.map it does not draw. Everyone's task stations (welcome.map's "tasks") stay
# forbidden through ALLOWED_MAP_KEYS; the player's own open tasks reach the map only through
# CampusMap.setTasks() from main.js (spec 018, "Own tasks on the map").
FORBIDDEN_NAMES = [
    "players",
    "ghosts",
    "vents",
    "open_vents",
    "spawns",
    "role",
    "fellow_examiners",
    "failed_exams",
]
SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def read(name):
    return (WEB / name).read_text(encoding="utf-8")


def code_without_text(source):
    """The JavaScript source with comments and the text of string literals blanked out.

    Template literals keep their ${...} expressions, since those are code. What is left are
    the identifiers and property accesses the file really uses; string literals are
    returned separately so that obj["name"] can be checked too.
    """
    code, strings = [], []
    i, n = 0, len(source)
    while i < n:
        c = source[i]
        if source.startswith("//", i):
            end = source.find("\n", i)
            i = n if end == -1 else end
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif c in "\"'":
            j, text = i + 1, []
            while j < n and source[j] != c:
                if source[j] == "\\":
                    j += 1
                text.append(source[j] if j < n else "")
                j += 1
            strings.append("".join(text))
            code.append('""')
            i = j + 1
        elif c == "`":
            j, text = i + 1, []
            while j < n and source[j] != "`":
                if source.startswith("${", j):
                    end = source.find("}", j)
                    code.append(" " + source[j + 2 : end] + " ")
                    j = end + 1
                    continue
                if source[j] == "\\":
                    j += 1
                text.append(source[j] if j < n else "")
                j += 1
            strings.append("".join(text))
            code.append('""')
            i = j + 1
        else:
            code.append(c)
            i += 1
    return "".join(code), strings


def names_read(source, names):
    """Which of `names` the source uses as an identifier or a property (x.name, x["name"],
    { name }), ignoring comments and plain text in strings such as `pointer-events` or the
    value of an attribute like role="img"."""
    code, _ = code_without_text(source)
    found = set()
    for name in names:
        if re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", code):
            found.add(name)
        if re.search(rf"\[\s*([\"'`]){re.escape(name)}\1\s*\]", source):
            found.add(name)
    return found


def function_body(script, name):
    """The body of the top-level `function name(...) { ... }` in main.js."""
    match = re.search(rf"^function {name}\([^)]*\)\s*\{{\n(.*?)^\}}", script, re.S | re.M)
    assert match, f"no top-level function {name}() in main.js"
    return match.group(1)


def keydown_listener(script):
    """The document keydown listener that handles H (spec 015) and now C."""
    match = re.search(
        r'document\.addEventListener\("keydown", \(event\) => \{\n(.*?)\n\}\);', script, re.S
    )
    assert match, "no document keydown listener"
    return match.group(1)


def css_px(style, selector, prop):
    """The px number in `prop: calc(<n>px ...)` of the first rule for selector."""
    rule = re.search(rf"(?m)^{re.escape(selector)}\s*\{{([^}}]*)\}}", style)
    assert rule, f"no rule for {selector}"
    value = re.search(rf"(?<![\w-]){prop}:\s*calc\((?:100vw\s*-\s*)?(\d+)px", rule.group(1))
    assert value, f"{selector} has no {prop}: calc(...px"
    return int(value.group(1))


# --- The helper that guards the map module, checked on its own -----------------------------


def test_the_identifier_guard_matches_whole_names_only():
    """The guard below must catch real reads and nothing else (spec 018, "Done when")."""
    caught = [
        "const v = map.vents;",
        'const t = map["vents"];',
        "const { spawns } = map;",
        "for (const p of state.players) {}",
        "if (me.role === 1) {}",
        "draw(`${map.failed_exams}`);",
        "const { fellow_examiners } = message;",
    ]
    for line in caught:
        assert names_read(line, FORBIDDEN_NAMES), line
    harmless = [
        'svg.setAttribute("role", "img");',
        'el.style.setProperty("pointer-events", "none");',
        "// never draws vents, tasks or players",
        "const events = 1; const roles2 = 2; const myplayers = 3;",
        'label.textContent = "Ghosts of exams past";',
    ]
    for line in harmless:
        assert not names_read(line, FORBIDDEN_NAMES), line


# --- The file exists, is served, and is loaded between music.js and main.js ----------------


def test_campusmap_js_is_served_by_the_app():
    client = TestClient(app)
    response = client.get("/campusmap.js")
    assert response.status_code == 200
    assert "CampusMap" in response.text


def test_index_html_loads_sound_music_campusmap_then_main():
    page = read("index.html")
    assert 'src="campusmap.js"' in page
    order = [page.index(f'src="{name}"') for name in ("sound.js", "music.js", "campusmap.js", "main.js")]
    assert order == sorted(order)


# --- index.html: the button, the overlay and the handbook line ----------------------------


def test_the_map_button_is_a_round_button_left_of_mute_with_an_aria_label():
    page = read("index.html")
    tag = re.search(r'<button id="map-button"[^>]*>', page)
    assert tag, "no map button"
    tag = tag.group(0)
    assert "help-button" in tag  # the same round shape as "?" and mute
    assert 'aria-label="Campus map"' in tag
    assert 'aria-expanded="false"' in tag
    assert re.search(r"\bhidden\b", tag)  # nothing to show before the welcome message
    body = re.search(r'<button id="map-button".*?</button>', page, re.S).group(0)
    assert "<svg" in body and "<img" not in body  # an inline icon, no image
    # Next to the other two round buttons in the page.
    assert page.index('id="map-button"') < page.index('id="mute-button"') < page.index('id="help-button"')


def test_the_map_panel_is_an_overlay_after_the_help_panel_with_a_close_button():
    page = read("index.html")
    assert 'id="map-panel"' in page
    start = page.index('id="map-panel"')
    assert page.index('id="help-panel"') < start < page.index("<script")
    panel_tag = page[page.rindex("<div", 0, start) : page.index(">", start)]
    assert "overlay" in panel_tag and re.search(r"\bhidden\b", panel_tag)
    panel = page[start : page.index("<script")]
    close = re.search(r'<button id="map-close"[^>]*>', panel)
    assert close and "aria-label" in close.group(0)
    assert "Campus map" in panel
    assert 'id="map-where"' in panel  # the "You are in" line
    assert 'id="map-slot"' in panel  # where main.js puts the built SVG


def test_the_handbook_lists_the_c_key_for_the_map():
    page = read("index.html")
    start = page.index('id="help-panel"')
    end = page.find('id="map-panel"')
    handbook = page[start : end if end != -1 else page.index("<script")]
    line = re.search(r'<li class="hint-keyboard">[^\n]*<kbd class="key">C</kbd>[^\n]*</li>', handbook)
    assert line, "no handbook line with the C key"
    assert "map" in line.group(0).lower()


# --- style.css: three round buttons, nothing runs under them --------------------------------


def test_style_css_places_the_map_button_left_of_mute_and_moves_panels_and_hud_over():
    style = read("style.css")
    mute = css_px(style, ".mute-button", "right")
    map_button = css_px(style, ".map-button", "right")
    assert map_button >= mute + 40 + 4  # a 40 px button and a gap to the left of mute
    # The lobby roster / role badge panels start left of the map button.
    assert css_px(style, ".panel", "right") >= map_button + 40 + 4
    # The HUD starts at 12 px from the left and must end before the map button.
    assert css_px(style, "#hud", "max-width") >= 12 + map_button + 40 + 4


# --- main.js: opening, closing, the key C and the meeting key M -----------------------------


def test_c_toggles_the_map_behind_the_same_guards_as_h():
    listener = keydown_listener(read("main.js"))
    guard = "if (typing || event.ctrlKey || event.metaKey || event.altKey || event.repeat) return;"
    assert guard in listener
    c_key = re.search(r'if \(event\.key === "c" \|\| event\.key === "C"\) setMapOpen\(ui\.mapPanel\.hidden\)', listener)
    assert c_key, "C does not toggle the map"
    assert listener.index(guard) < c_key.start()
    assert 'event.key === "h" || event.key === "H"' in listener  # H unchanged


def test_escape_closes_the_map():
    listener = keydown_listener(read("main.js"))
    assert re.search(r'event\.key === "Escape"[^\n]*!ui\.mapPanel\.hidden', listener)
    assert "setMapOpen(false)" in listener


def test_m_still_calls_a_meeting_and_c_is_not_a_phaser_key():
    script = read("main.js")
    assert 'this.keys.M.on("down", () => tryMeeting());' in script
    keys = re.search(r'addKeys\("([^"]*)"\)', script).group(1).split(",")
    assert "M" in keys and "C" not in keys


def test_the_map_and_help_close_each_other():
    script = read("main.js")
    open_map = function_body(script, "setMapOpen")
    open_help = function_body(script, "setHelpOpen")
    assert re.search(r"setHelpOpen\(false\)|helpPanel\.hidden = true", open_map)
    assert re.search(r"setMapOpen\(false\)|mapPanel\.hidden = true", open_help)
    assert 'mapButton.setAttribute("aria-expanded"' in open_map


def test_the_map_button_cross_and_background_open_and_close_it_with_a_click_sound():
    script = read("main.js")
    button = re.search(r'ui\.mapButton\.addEventListener\("click", \(\) => \{(.*?)\n\}\);', script, re.S)
    assert button and 'Sound.play("click")' in button.group(1) and "setMapOpen(" in button.group(1)
    close = re.search(r'ui\.mapClose\.addEventListener\("click", \(\) => \{(.*?)\n\}\);', script, re.S)
    assert close and 'Sound.play("click")' in close.group(1) and "setMapOpen(false)" in close.group(1)
    assert re.search(r"event\.target === ui\.mapPanel\) setMapOpen\(false\)", script)


# --- main.js: built once from welcome.map, fed only the own position ------------------------


def test_the_map_is_built_once_from_welcome_map():
    script = read("main.js")
    assert script.count("CampusMap.build(") == 1
    assert "CampusMap.build(welcome.map)" in script
    welcome_branch = re.search(r'message\.type === "welcome"\) \{(.*?)\n  \}', script, re.S).group(1)
    assert "CampusMap.build(welcome.map)" in welcome_branch or "buildCampusMap()" in welcome_branch
    assert "CampusMap.build(" not in function_body(script, "setMapOpen")  # opening never rebuilds


def test_set_you_only_gets_the_own_position_and_colour_or_null():
    script = read("main.js")
    calls = re.findall(r"CampusMap\.setYou\((.*?)\);", script)
    assert calls, "CampusMap.setYou is never called"
    for args in calls:
        assert args == "null" or re.fullmatch(
            r"this\.predicted, Render\.colorCss\(latestState\.colors\[welcome\.id\]\)", args
        ), args
    # Fed from the own prediction, and only while playing (spec 018, "You are here").
    predict = re.search(r"\n  predictTick\(\) \{\n(.*?)\n  \}\n", script, re.S).group(1)
    assert "CampusMap.setYou(this.predicted" in predict
    assert "CampusMap.setYou(null)" in predict
    assert 'lastPhase === "playing"' in predict


def test_the_you_are_in_line_comes_from_the_own_area():
    script = read("main.js")
    assert "You are in: " in script
    at = script.index("You are in: ")
    assert re.search(r"\.area\b", script[at - 300 : at + 300])
    assert "ui.mapWhere" in script


# --- campusmap.js: draws only the static campus, never anything about a player -------------


def test_campusmap_js_exposes_build_and_set_you():
    source = read("campusmap.js")
    assert re.search(r"\bconst CampusMap\s*=", source)
    assert re.search(r"return\s*\{[^}]*\bbuild\b[^}]*\bsetYou\b|return\s*\{[^}]*\bsetYou\b[^}]*\bbuild\b", source, re.S)
    assert re.search(r"function build\(map\)", source)


def test_campusmap_js_is_plain_svg_with_text_set_as_text():
    source = read("campusmap.js")
    assert "innerHTML" not in source
    assert "textContent" in source
    assert "createElementNS" in source and "viewBox" in source
    # The SVG is announced as one picture (kept on purpose, spec 018).
    assert re.search(r'setAttribute\(\s*"role"\s*,\s*"img"\s*\)', source)
    # No images and no URL other than the SVG namespace itself.
    assert "<image" not in source and "Image(" not in source
    for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        assert ext not in source
    assert set(re.findall(r"https?://[^\s\"'`]*", source)) <= {SVG_NAMESPACE}


def test_campusmap_js_never_reads_players_roles_or_hidden_things():
    source = read("campusmap.js")
    assert names_read(source, FORBIDDEN_NAMES) == set()


def test_campusmap_js_reads_only_the_parts_of_the_map_it_draws():
    source = read("campusmap.js")
    code, _ = code_without_text(source)
    used = set(re.findall(r"(?<![\w$.])map\.(\w+)", code))
    used |= set(re.findall(r"(?<![\w$.])map\[\s*[\"'`](\w+)[\"'`]\s*\]", source))
    assert used, "build(map) reads nothing from the map"
    assert used <= ALLOWED_MAP_KEYS, used - ALLOWED_MAP_KEYS
    # No walking over every key of the map either.
    assert not re.search(r"Object\.(keys|values|entries)\(\s*map\s*\)", code)
    assert not re.search(r"\bin\s+map\b", code)
    # It receives the map and the own position only: no game state, no connection.
    assert names_read(source, ["latestState", "snapshots", "welcome", "socket", "state"]) == set()


# --- The server stays untouched -------------------------------------------------------------


def test_the_server_gained_no_map_overlay_code():
    for path in ("server/game.py", "server/main.py"):
        source = (ROOT / path).read_text(encoding="utf-8").lower()
        for word in ("campusmap", "map-panel", "map_panel", "setyou", "map-button"):
            assert word not in source, (path, word)


# --- Own tasks on the map (spec 018, extended): only the player's own open tasks -------------


def test_campusmap_js_exposes_set_tasks_and_draws_numbered_markers():
    source = read("campusmap.js")
    assert re.search(r"return\s*\{[^}]*\bsetTasks\b", source, re.S)
    assert re.search(r"function setTasks\(", source)
    code, _ = code_without_text(source)
    body = re.search(r"function setTasks\([^)]*\)\s*\{(.*?)\n  \}", code, re.S).group(1)
    assert "textContent" in body or "text(" in body  # the number is set as text


def test_campusmap_js_never_reads_the_task_stations_of_the_map():
    """welcome.map lists every task's stations, everyone's; the map must not draw those."""
    code, strings = code_without_text(read("campusmap.js"))
    assert not re.search(r"(?<![\w$.])map\.tasks\b", code)
    assert not re.search(r"(?<![\w$.])map\[\s*[\"'`]tasks[\"'`]\s*\]", read("campusmap.js"))
    assert "taskStations" not in code


def test_the_map_panel_has_a_list_for_the_own_tasks():
    page = read("index.html")
    panel = page[page.index('id="map-panel"') : page.index("<script")]
    assert re.search(r'<ol id="map-tasks"[^>]*>', panel)


def test_main_js_hands_the_map_only_the_own_open_tasks_while_playing():
    script = read("main.js")
    body = function_body(script, "updateMapTasks")
    assert "state.tasks" in body  # the own snapshot: never anyone else's tasks
    assert ".done" in body  # finished tasks are left out
    assert 'state.phase === "playing"' in body or 'state.phase !== "playing"' in body
    assert "CampusMap.setTasks(" in body
    for name in ("welcome.map", "players", "roles", "fellow_examiners", "taskStations", "innerHTML"):
        assert name not in body, name
    assert "textContent" in body or "setText(" in body  # the list is filled as text
    # Every call of setTasks is in that one function.
    assert script.count("CampusMap.setTasks(") == body.count("CampusMap.setTasks(")


def test_the_task_list_is_refreshed_when_the_map_opens_and_on_new_snapshots():
    script = read("main.js")
    assert "updateMapTasks(latestState)" in function_body(script, "setMapOpen")
    assert re.search(r"if \(!ui\.mapPanel\.hidden\) \{?[^\n]*updateMapTasks\(message\)", script) or re.search(
        r"if \(!ui\.mapPanel\.hidden\) \{\n(?:[^\n]*\n){0,3}[^\n]*updateMapTasks\(message\)", script
    )


# --- The grey base map (spec 018, extended) ---------------------------------------------------


def hex_is_grey(value, tolerance=16):
    r, g, b = (int(value[i : i + 2], 16) for i in (1, 3, 5))
    return max(r, g, b) - min(r, g, b) <= tolerance


def test_the_base_map_is_grey_and_does_not_use_the_area_colours():
    source = read("campusmap.js")
    for name in ("WALL", "FLOOR", "SEA", "SAND", "AREA_FILL", "AREA_EDGE"):
        match = re.search(rf'const {name} = "(#[0-9a-fA-F]{{6}})"', source)
        assert match, f"no colour constant {name}"
        assert hex_is_grey(match.group(1)), (name, match.group(1))
    assert "area.color" not in source


# --- Names centred in their rooms (spec 018, extended) ----------------------------------------
# Every label in server/campus.json names a room: a rectangle of tiles the map centres the
# name in. The room never mixes floor and wall tiles, so a name never crosses a wall.


def campus():
    import json

    return json.loads((ROOT / "server" / "campus.json").read_text(encoding="utf-8"))


def room_tiles(room):
    return [(col, row) for row in range(room["y"], room["y"] + room["h"]) for col in range(room["x"], room["x"] + room["w"])]


def test_the_lecture_halls_and_the_student_hall_have_their_full_names():
    texts = [label["text"] for label in campus()["labels"]]
    assert "Lecture hall B" in texts and "Lecture hall D" in texts and "CTT Student Hall" in texts
    assert "Lecture hall" not in texts and "Student Hall" not in texts
    assert len(texts) == len(set(texts)), "two labels share a name"


def test_every_label_has_a_room_inside_the_grid_that_crosses_no_wall():
    data = campus()
    grid = data["grid"]
    for label in data["labels"]:
        room = label.get("room")
        assert room, f"{label['text']} has no room"
        assert all(type(room[key]) is int for key in ("x", "y", "w", "h")), label["text"]
        assert room["w"] >= 1 and room["h"] >= 1, label["text"]
        assert 0 <= room["x"] and room["x"] + room["w"] <= len(grid[0]), label["text"]
        assert 0 <= room["y"] and room["y"] + room["h"] <= len(grid), label["text"]
        kinds = {grid[row][col] for col, row in room_tiles(room)}
        assert len(kinds) == 1, f"the room of {label['text']} mixes floor and wall"


def test_no_two_label_rooms_overlap():
    rooms = [(label["text"], set(room_tiles(label["room"]))) for label in campus()["labels"]]
    for i, (text_a, tiles_a) in enumerate(rooms):
        for text_b, tiles_b in rooms[i + 1 :]:
            assert not tiles_a & tiles_b, (text_a, text_b)


def test_the_meeting_point_and_the_light_switch_are_labels_only_on_the_map():
    data = campus()
    only_map = {label["text"]: label for label in data["labels"] if label.get("only_on_map")}
    assert set(only_map) == {"Meeting point", "Light switch"}
    col, row = data["meeting_point"]
    room = only_map["Meeting point"]["room"]
    # Right under the table, in the open space around it.
    assert room["x"] <= col < room["x"] + room["w"] and room["y"] == row + 1
    # The game world draws the table and the switch itself: it skips these labels.
    assert re.search(r"only_on_map", read("render.js"))


def test_campusmap_js_centres_names_in_their_rooms_with_one_font_size():
    source = read("campusmap.js")
    code, _ = code_without_text(source)
    assert re.search(r"\.room\b", code)
    assert "rotate(-90" in source  # a tall, narrow room gets its name along it
    fonts = set(re.findall(r"const (\w+_FONT) =", code))
    assert fonts == {"NAME_FONT", "TASK_FONT"}, fonts
    # The texts of the two places come from the map data now, not from the code.
    assert "Meeting point" not in source and "Light switch" not in source
