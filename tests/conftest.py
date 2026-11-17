"""Shared pytest fixtures.

Without this, every WebSocket test in tests/ would share the one game created at import
of server/main.py for the whole test session: players from an earlier test could still be
mid-disconnect when the next test starts, so color numbers, host and player counts could
occasionally come out wrong (spec 001 review).
"""

import pytest

from server import main as server_main
from server.game import Game, load_map


@pytest.fixture(autouse=True)
def fresh_game(monkeypatch):
    """A new Game and an empty connections dict, used by every test in this session."""
    game = Game(load_map())
    monkeypatch.setattr(server_main, "game", game)
    monkeypatch.setattr(server_main, "connections", {})
    return game
