"""Hints and walkthrough helpers."""

from .directions import DIRECTIONS
from .engine import Game


def visible_exits(state):
    """Exit directions of the current room in compass order, including locked ones."""
    room = state.here()
    return [d for d in DIRECTIONS if d in room.exits]


def locked_ways(state):
    return [d for d in visible_exits(state) if (state.room, d) in state.locked_exits]


def unscored_treasures(state):
    """Ids of treasures the player has not scored yet, sorted."""
    return sorted(i for i, item in state.world.items.items() if item.treasure and i not in state.scored)


def hint(state):
    """One short suggestion for the player."""
    if not state.is_lit():
        return "Find a light source."
    ways = locked_ways(state)
    if ways:
        return "The way %s is locked; you need a key." % ways[0]
    left = unscored_treasures(state)
    if not left:
        return "You have found every treasure."
    return "There are %d treasures left to find." % len(left)


def replay(world, lines):
    """Play ``lines`` on a fresh game; returns ``(game, outputs)``."""
    game = Game(world)
    return game, game.run(lines)


def final_score(world, lines):
    game, _ = replay(world, lines)
    return game.state.score
