"""Tests for spec 013 (start in the Main Entrance): every player is placed on a spawn
point when the host starts the match, instead of staying where they wandered in the lobby.
"""

import random

import pytest

from server.game import Game, GameError, load_map


def lobby(count, seed=0, campus=None):
    """A lobby with `count` players. players[0] joined first and is the host."""
    game = Game(campus or load_map(), rng=random.Random(seed))
    players = [game.join(f"Player {i}") for i in range(count)]
    return game, players


def positions_of(game):
    return [(p.id, p.x, p.y, p.dx, p.dy) for p in game.players.values()]


def walk_everyone(game, players):
    """Every player picks a direction and takes a few steps, as in a real lobby."""
    for i, player in enumerate(players):
        dx = [-1, 0, 1][i % 3]
        dy = [0, 1, -1][i % 3]
        game.set_input(player.id, {"type": "input", "dx": dx, "dy": dy})
    for _ in range(5):
        game.step()


# --- Accepted start: everyone lands in the Main Entrance ----------------------------


@pytest.mark.parametrize("count", [4, 10])
def test_start_places_everyone_in_the_main_entrance(count):
    game, players = lobby(count)
    walk_everyone(game, players)

    game.start(players[0].id)

    tiles = [(p.x, p.y) for p in game.players.values()]
    assert len(set(tiles)) == count  # every player on a different tile
    for player in game.players.values():
        assert game.area_at(player.x, player.y) == "Main Entrance"
        # on the centre of a tile, not wherever they happened to be walking
        assert (player.x / game.tile) % 1 == pytest.approx(0.5)
        assert (player.y / game.tile) % 1 == pytest.approx(0.5)


def test_start_clears_everyones_movement_input():
    game, players = lobby(4)
    walk_everyone(game, players)

    game.start(players[0].id)

    for player in game.players.values():
        assert (player.dx, player.dy) == (0, 0)


# --- Rejected start: nobody moves ----------------------------------------------------


def test_rejected_start_from_a_non_host_does_not_move_anyone():
    game, players = lobby(4)
    walk_everyone(game, players)
    before = positions_of(game)

    with pytest.raises(GameError, match="Only the host"):
        game.start(players[1].id)

    assert positions_of(game) == before


def test_rejected_start_with_too_few_players_does_not_move_anyone():
    game, players = lobby(3)
    walk_everyone(game, players)
    before = positions_of(game)

    with pytest.raises(GameError, match="at least 4 players"):
        game.start(players[0].id)

    assert positions_of(game) == before


def test_rejected_start_while_already_running_does_not_move_anyone():
    game, players = lobby(4)
    game.start(players[0].id)
    walk_everyone(game, players)  # a player moves after the round has started
    before = positions_of(game)

    with pytest.raises(GameError, match="already running"):
        game.start(players[0].id)

    assert positions_of(game) == before


# --- A new round starts in the Main Entrance again -----------------------------------


def test_restarting_and_starting_again_places_everyone_in_the_main_entrance():
    game, players = lobby(4)
    game.start(players[0].id)
    for _ in range(5):
        game.step()
    game.phase = "ended"  # skip to the end of the round, like a finished game

    game.restart(players[0].id)
    walk_everyone(game, players)  # walking around in the lobby again

    game.start(players[0].id)

    tiles = [(p.x, p.y) for p in game.players.values()]
    assert len(set(tiles)) == 4
    for player in game.players.values():
        assert game.area_at(player.x, player.y) == "Main Entrance"
        assert (player.dx, player.dy) == (0, 0)
