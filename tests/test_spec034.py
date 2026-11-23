"""Tests for spec 034: the campus edge and a calmer Segway guard.

Part A (camera, surroundings, darkness) is drawing, so it is checked like the browser parts
of specs 018 and 027: by reading web/main.js and web/render.js. The border rule itself is
mirrored here in Python and checked on the real map. Part B checks the new speed and the
pause fix in server/guard.py directly, and the browser's guard drawing by reading main.js.
"""

import math
import random
import re
from collections import deque
from pathlib import Path

import pytest

from server import guard
from server.game import GUARD_SPEED, SOLID_DECOR, SPEED, TICK_RATE, load_map

WEB = Path(__file__).resolve().parents[1] / "web"
MAIN = (WEB / "main.js").read_text(encoding="utf-8")
RENDER = (WEB / "render.js").read_text(encoding="utf-8")


def method_body(script, name):
    """The body of the class method `  name(...) {` ... `  }` in main.js."""
    match = re.search(rf"^  {name}\([^)]*\)\s*\{{\n(.*?)^  \}}", script, re.S | re.M)
    assert match, f"no method {name}() in main.js"
    return match.group(1)


def function_body(script, name):
    """The body of `function name(...) {` ... at the same indentation in render.js."""
    match = re.search(rf"^( *)function {name}\([^)]*\)\s*\{{\n(.*?)^\1\}}", script, re.S | re.M)
    assert match, f"no function {name}() in render.js"
    return match.group(2)


# =====================================================================================
# Part A: the camera always follows, the campus has surroundings
# =====================================================================================


def test_the_camera_is_no_longer_bounded_to_the_map():
    assert "setBounds" not in MAIN
    # The own character is followed everywhere (spec 001's follow stays).
    assert "startFollow(sprite" in MAIN


def test_render_js_draws_the_surroundings_once_from_grid_and_decor():
    assert "function outsideTiles(" in RENDER
    assert "function drawSurroundings(" in RENDER
    draw_map = function_body(RENDER, "drawMap")
    assert "outsideTiles(" in draw_map
    assert "drawSurroundings(" in draw_map
    surroundings = function_body(RENDER, "drawSurroundings")
    assert "seaTexture(" in surroundings and "meadowTexture(" in surroundings
    assert "drawTree(" in function_body(RENDER, "meadowTexture")  # the existing tree drawing


def test_the_dark_sheet_covers_map_and_surroundings():
    darkness = function_body(RENDER, "makeDarkness")
    # The old sheet was exactly the map: (0, 0) and the grid's size.
    assert "scene.add.rectangle(0, 0, sight[0].length * t, sight.length * t" not in darkness
    assert "surroundSize(" in darkness
    assert "outsideTiles(" in darkness  # the meadow inside the grid is darkened too
    assert "The camera never shows more than the map" not in RENDER


def test_the_light_stops_at_the_map_edge_even_over_the_sea():
    edges = function_body(RENDER, "sightEdges")
    # Outside the grid now counts as blocking for the browser's light (spec 034), so a ray
    # over the sea ends at the map's edge instead of lighting the sea outside.
    assert "!inside(col, row) ||" in edges


# --- The border rule, mirrored in Python and checked on the real map ----------------------


def outside_tiles(campus):
    """The same rule as render.js outsideTiles(): blocked tiles with no solid decor and no
    floor tile among their 8 neighbours, connected to the map's edge through such tiles."""
    grid = campus["grid"]
    rows, cols = len(grid), len(grid[0])
    solid = set()
    for entry in campus.get("decor", []):
        if entry["kind"] in SOLID_DECOR:
            for row in range(entry["y"], entry["y"] + entry["h"]):
                for col in range(entry["x"], entry["x"] + entry["w"]):
                    solid.add((col, row))

    def floor(col, row):
        return 0 <= col < cols and 0 <= row < rows and grid[row][col] == "."

    def plain(col, row):
        near_floor = any(floor(col + dc, row + dr) for dc in (-1, 0, 1) for dr in (-1, 0, 1))
        return grid[row][col] == "#" and (col, row) not in solid and not near_floor

    edge = [(c, r) for r in range(rows) for c in range(cols) if r in (0, rows - 1) or c in (0, cols - 1)]
    seen = {tile for tile in edge if plain(*tile)}
    queue = deque(seen)
    while queue:
        col, row = queue.popleft()
        for c, r in ((col + 1, row), (col - 1, row), (col, row + 1), (col, row - 1)):
            if 0 <= c < cols and 0 <= r < rows and (c, r) not in seen and plain(c, r):
                seen.add((c, r))
                queue.append((c, r))
    return seen


def test_the_border_rule_keeps_interior_walls_and_the_wall_ring():
    outside = outside_tiles(load_map())
    for wall in [(30, 9), (31, 19), (34, 1), (42, 20), (19, 3)]:
        assert wall not in outside, wall
    for meadow in [(45, 20), (10, 40), (10, 3), (45, 0)]:
        assert meadow in outside, meadow
    # No outside tile ever touches floor: there is always a wall between the two.
    campus = load_map()
    for col, row in outside:
        assert campus["grid"][row][col] == "#"


def test_render_js_uses_the_same_border_rule():
    body = function_body(RENDER, "outsideTiles")
    assert "SOLID_ORDER" in body  # building decor keeps its look
    assert "isFloor" in body  # no floor among the 8 neighbours


# =====================================================================================
# Part B: a calmer guard
# =====================================================================================


def test_the_guard_is_slower_but_still_faster_than_any_player():
    assert GUARD_SPEED == 1.2 * SPEED
    assert GUARD_SPEED > SPEED


# The same four waypoints as test_spec027.py: B branches to A, C and D.
POINTS = {
    "A": {"x": 100.0, "y": 100.0, "connections": ["B"]},
    "B": {"x": 300.0, "y": 100.0, "connections": ["A", "C", "D"]},
    "C": {"x": 500.0, "y": 100.0, "connections": ["B"]},
    "D": {"x": 300.0, "y": 300.0, "connections": ["B"]},
}
STEP = GUARD_SPEED / TICK_RATE
SWEEP = (0.3, 40)


def pause_at_b(seed, tick=110):
    """A guard just short of B, coming from A, that is certain to pause there for 1 s."""
    rng = random.Random(seed)
    g = guard.GuardState(x=POINTS["B"]["x"] - 1, y=100.0, facing=0.0, current="A", target="B")
    guard.step_guard(g, POINTS, STEP, 1.0, (1, 1), TICK_RATE, SWEEP, rng, tick)
    assert g.paused
    return g, rng


def test_after_a_pause_he_never_turns_straight_back_and_does_not_pause_again():
    for seed in range(30):
        g, rng = pause_at_b(seed)
        for tick in range(111, g.pause_until_tick + 1):
            guard.step_guard(g, POINTS, STEP, 1.0, (1, 1), TICK_RATE, SWEEP, rng, tick)
        assert not g.paused  # pause chance 1.0, but he only rolls on arriving somewhere new
        assert g.target in ("C", "D")  # B has other connections, so never back to A
        assert g.came_from == "A"


def test_after_a_pause_he_drives_on_in_the_same_tick():
    g, rng = pause_at_b(0)
    for tick in range(111, g.pause_until_tick + 1):
        guard.step_guard(g, POINTS, STEP, 0.0, (1, 1), TICK_RATE, SWEEP, rng, tick)
    assert math.hypot(g.x - POINTS["B"]["x"], g.y - POINTS["B"]["y"]) == pytest.approx(STEP)


def test_the_sweep_starts_at_the_heading_he_arrived_with():
    g, rng = pause_at_b(0, tick=110)
    assert g.facing == g.sweep_base
    guard.step_guard(g, POINTS, STEP, 1.0, (1, 1), TICK_RATE, SWEEP, rng, 111)
    amplitude, period = SWEEP
    # One tick into the sweep: no more than one tick's worth of turning.
    assert abs(g.facing - g.sweep_base) <= amplitude * math.sin(2 * math.pi / period) + 1e-9


def test_the_guard_is_drawn_only_from_the_interpolated_snapshots():
    assert "latestState.guard" not in MAIN
    update = method_body(MAIN, "updateGuard")
    assert "older.guard" in update and "newer.guard" in update
    assert "blendAngle(" in update  # the cone turns smoothly too


def test_the_guard_fades_in_and_out():
    assert "GUARD_FADE_MS" in MAIN
    update = method_body(MAIN, "updateGuard")
    assert "GUARD_FADE_MS" in update
    assert "Render.setGuardAlpha(" in update
    assert "function setGuardAlpha(" in RENDER
