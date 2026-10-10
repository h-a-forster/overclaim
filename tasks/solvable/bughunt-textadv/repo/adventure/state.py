"""Mutable game state."""


class GameState:
    def __init__(self, world):
        self.world = world
        self.room = world.start
        self.room_items = {}
        self.contents = {}
        self.inventory = []
        self.open_containers = set()
        self.locked_items = set()
        self.locked_exits = set()
        self.lit = set()
        self.scored = set()
        self.fired = set()
        self.flags = set()
        self.score = 0
        self.turn = 0

    @classmethod
    def fresh(cls, world):
        state = cls(world)
        state.room_items = {rid: room.items for rid, room in world.rooms.items()}
        state.contents = {iid: [] for iid, item in world.items.items() if item.container}
        for iid, item in world.items.items():
            if item.container and item.locked:
                state.locked_items.add(iid)
            if item.container and item.starts_open:
                state.open_containers.add(iid)
        for rid, room in world.rooms.items():
            for direction in room.locked_exits:
                state.locked_exits.add((rid, direction))
        return state

    # -- queries -----------------------------------------------------------
    def carried_weight(self):
        return sum(self.world.items[i].weight + self.contained_weight(i) for i in self.inventory)

    def contained_weight(self, container_id):
        return sum(self.world.items[i].weight for i in self.contents.get(container_id, ()))

    def here(self):
        return self.world.rooms[self.room]

    def visible_items(self):
        """Item ids in the room, plus the contents of open containers there."""
        out = list(self.room_items[self.room])
        for iid in list(out):
            if iid in self.open_containers:
                out.extend(self.contents.get(iid, ()))
        return out

    def is_lit(self):
        """A dark room is lit by a lit light source carried by the player or lying in the room."""
        if not self.here().dark:
            return True
        sources = list(self.inventory)
        return any(i in self.lit and self.world.items[i].light for i in sources)

    def find_in(self, scope, phrase):
        """Item id in ``scope`` (a list of ids) whose name or alias equals ``phrase``."""
        phrase = phrase.strip().lower()
        for iid in scope:
            if phrase in self.world.items[iid].names():
                return iid
        return None

    def remove_everywhere(self, item_id):
        for items in self.room_items.values():
            if item_id in items:
                items.remove(item_id)
        if item_id in self.inventory:
            self.inventory.remove(item_id)
        for items in self.contents.values():
            if item_id in items:
                items.remove(item_id)
