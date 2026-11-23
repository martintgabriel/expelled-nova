"""Tests for spec 025: the gym skylight. Like the sound tests, they read the static files,
since the drawing only exists in the browser."""

import re
from pathlib import Path

from server.game import load_map

WEB = Path(__file__).resolve().parent.parent / "web"


def render_js():
    return (WEB / "render.js").read_text(encoding="utf-8")


def gym_function():
    text = render_js()
    start = text.index("function makeGym(")
    return text[start : text.index("// --- Characters", start)]


def test_render_js_exports_make_gym():
    assert re.search(r"return \{[^}]*\bmakeGym,", render_js(), re.S)


def test_the_gym_is_found_through_its_label_and_roof():
    body = gym_function()
    assert '"Gym"' in body and '"roof"' in body
    campus = load_map()
    label = next(l for l in campus["labels"] if l["text"] == "Gym")
    roofs = [
        d for d in campus["decor"]
        if d["kind"] == "roof" and d["x"] <= label["x"] <= d["x"] + d["w"] and d["y"] <= label["y"] <= d["y"] + d["h"]
    ]
    assert len(roofs) == 1


def test_the_figures_move_with_endless_tweens():
    body = gym_function()
    assert body.count("scene.tweens.add(") >= 3
    assert "repeat: -1" in body


def test_the_gym_talks_to_nobody():
    body = gym_function()
    assert "send(" not in body and "socket" not in body


def test_main_js_draws_the_gym_once():
    assert (WEB / "main.js").read_text(encoding="utf-8").count("Render.makeGym(") == 1
