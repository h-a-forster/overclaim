"""Static world definition: rooms, items and how to start a game in them."""

from .directions import DIRECTIONS, OPPOSITE
from .errors import WorldError


class ItemDef:
    def __init__(self, item_id, spec):
        self.id = item_id
        self.name = spec.get("name", item_id).lower()
        self.aliases = [a.lower() for a in spec.get("aliases", [])]
        self.description = spec.get("desc", "It looks ordinary.")
        self.weight = int(spec.get("weight", 1))
        self.takeable = bool(spec.get("takeable", True))
        self.container = bool(spec.get("container", False))
        self.capacity = int(spec.get("capacity", 0))
        self.locked = bool(spec.get("locked", False))
        self.key = spec.get("key")
        self.treasure = int(spec.get("treasure", 0))
        self.light = bool(spec.get("light", False))
        self.starts_open = bool(spec.get("open", False))
        if self.weight < 0:
            raise WorldError("item %s has negative weight" % item_id)
        if self.locked and not self.container:
            raise WorldError("only containers can be locked (%s)" % item_id)

    def names(self):
        return [self.name] + self.aliases


class RoomDef:
    def __init__(self, room_id, spec):
        self.id = room_id
        self.name = spec.get("name", room_id)
        self.description = spec.get("desc", "")
        self.exits = dict(spec.get("exits", {}))
        self.items = list(spec.get("items", []))
        self.dark = bool(spec.get("dark", False))
        self.locked_exits = dict(spec.get("locked_exits", {}))  # direction -> key item id


class WorldDef:
    """Rooms and items.  Exits are two-way: declaring ``hall: {north: library}`` also gives the
    library a ``south`` exit back to the hall (unless that direction is already declared)."""

    def __init__(self, rooms, items, start, capacity=10):
        self.rooms = rooms
        self.items = items
        self.start = start
        self.capacity = capacity
        self._link_reverse_exits()
        self._validate()

    @classmethod
    def from_dict(cls, spec):
        items = {iid: ItemDef(iid, s) for iid, s in spec.get("items", {}).items()}
        rooms = {rid: RoomDef(rid, s) for rid, s in spec.get("rooms", {}).items()}
        if "start" not in spec:
            raise WorldError("a world needs a start room")
        world = cls(rooms, items, spec["start"], int(spec.get("capacity", 10)))
        world.events = list(spec.get("events", []))
        return world

    events = ()

    def _link_reverse_exits(self):
        for room in list(self.rooms.values()):
            for direction, target in list(room.exits.items()):
                if direction not in DIRECTIONS:
                    raise WorldError("room %s: bad direction %r" % (room.id, direction))
                if target not in self.rooms:
                    raise WorldError("room %s: exit %s leads to unknown room %s" % (room.id, direction, target))
                back = OPPOSITE[direction]
                other = self.rooms[target]
                if back not in other.exits:
                    other.exits[back] = room.id
                if direction in room.locked_exits and back not in other.locked_exits:
                    other.locked_exits[back] = room.locked_exits[direction]

    def _validate(self):
        if self.start not in self.rooms:
            raise WorldError("unknown start room %s" % self.start)
        for room in self.rooms.values():
            for iid in room.items:
                if iid not in self.items:
                    raise WorldError("room %s contains unknown item %s" % (room.id, iid))
            for direction, key in room.locked_exits.items():
                if key not in self.items:
                    raise WorldError("room %s: lock on %s needs unknown key %s" % (room.id, direction, key))
        for item in self.items.values():
            if item.key is not None and item.key not in self.items:
                raise WorldError("item %s needs unknown key %s" % (item.id, item.key))

    def instantiate(self):
        """A fresh game state for this world; games never share mutable data."""
        from .state import GameState

        return GameState.fresh(self)
