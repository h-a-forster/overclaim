"""Saving and loading games as plain dicts / JSON."""

import json

from .errors import SaveError


def dump(state):
    """A JSON-friendly snapshot of everything that can change during play."""
    return {
        "room": state.room,
        "inventory": list(state.inventory),
        "room_items": {rid: list(items) for rid, items in sorted(state.room_items.items())},
        "contents": {iid: list(items) for iid, items in sorted(state.contents.items())},
        "open_containers": sorted(state.open_containers),
        "locked_items": sorted(state.locked_items),
        "locked_exits": sorted([room, direction] for room, direction in state.locked_exits),
        "lit": sorted(state.lit),
        "fired": sorted(state.fired),
        "flags": sorted(state.flags),
        "score": state.score,
        "turn": state.turn,
    }


def load(world, data):
    """A new GameState for ``world`` restored from ``data``; validates references."""
    from .state import GameState

    state = GameState.fresh(world)
    try:
        if data["room"] not in world.rooms:
            raise SaveError("unknown room %r" % data["room"])
        state.room = data["room"]
        state.inventory = [_item(world, i) for i in data["inventory"]]
        state.room_items = {rid: [_item(world, i) for i in items] for rid, items in data["room_items"].items()}
        if set(state.room_items) != set(world.rooms):
            raise SaveError("saved rooms do not match the world")
        state.contents = {cid: [_item(world, i) for i in items] for cid, items in data["contents"].items()}
        state.open_containers = {_item(world, i) for i in data["open_containers"]}
        state.locked_items = {_item(world, i) for i in data["locked_items"]}
        state.locked_exits = {(room, direction) for room, direction in data["locked_exits"]}
        state.lit = {_item(world, i) for i in data["lit"]}
        state.scored = {_item(world, i) for i in data.get("scored", [])}
        state.fired = set(data["fired"])
        state.flags = set(data["flags"])
        state.score = int(data["score"])
        state.turn = int(data["turn"])
    except KeyError as exc:
        raise SaveError("missing field %s" % exc) from None
    return state


def _item(world, item_id):
    if item_id not in world.items:
        raise SaveError("unknown item %r" % (item_id,))
    return item_id


def to_json(state):
    return json.dumps(dump(state), sort_keys=True)


def from_json(world, text):
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise SaveError("not valid JSON: %s" % exc) from None
    return load(world, data)
