"""Command implementations.  Each returns a Result(text, ok)."""

from .directions import DIRECTIONS, OPPOSITE
from .render import describe_items, join_list, with_article


class Result:
    def __init__(self, text, ok=True):
        self.text = text
        self.ok = ok

    def __repr__(self):
        return "Result(%r, ok=%r)" % (self.text, self.ok)


def _name(state, iid):
    return state.world.items[iid].name


def look(state):
    if not state.is_lit():
        return Result("It is pitch dark. You can't see a thing.")
    room = state.here()
    lines = [room.name]
    if room.description:
        lines.append(room.description)
    items = state.room_items[state.room]
    if items:
        lines.append("You see %s." % describe_items(state.world, items))
    for iid in items:
        if iid in state.open_containers:
            inside = state.contents.get(iid, [])
            if inside:
                lines.append("The %s contains %s." % (_name(state, iid), describe_items(state.world, inside)))
            else:
                lines.append("The %s is empty." % _name(state, iid))
    exits = [d for d in DIRECTIONS if d in room.exits]
    lines.append("Exits: %s." % ", ".join(exits) if exits else "There are no exits.")
    return Result("\n".join(lines))


def go(state, cmd):
    direction = cmd.noun
    if not direction:
        return Result("Go where?", False)
    room = state.here()
    dest = room.exits.get(direction)
    if dest is None:
        return Result("You can't go that way.", False)
    if (state.room, direction) in state.locked_exits:
        return Result("The way %s is locked." % direction, False)
    state.room = dest
    return Result(look(state).text)


def _take_one(state, iid):
    item = state.world.items[iid]
    if not item.takeable:
        return Result("You can't take the %s." % item.name, False)
    load = state.carried_weight()
    if load + item.weight + state.contained_weight(iid) >= state.world.capacity:
        return Result("The %s is too heavy: you carry %d of %d." % (item.name, load, state.world.capacity), False)
    for items in state.room_items.values():
        if iid in items:
            items.remove(iid)
    for items in state.contents.values():
        if iid in items:
            items.remove(iid)
    state.inventory.append(iid)
    text = "Taken."
    if item.treasure and iid not in state.scored:
        state.scored.add(iid)
        state.score += item.treasure
        text += " (+%d points)" % item.treasure
    return Result(text)


def take(state, cmd):
    if not state.is_lit():
        return Result("It is too dark to find anything.", False)
    if not cmd.noun:
        return Result("Take what?", False)
    if cmd.prep == "from":
        container = state.find_in(state.visible_items() + state.inventory, cmd.target or "")
        if container is None:
            return Result("You see no %s here." % (cmd.target or "such thing"), False)
        if not state.world.items[container].container:
            return Result("The %s is not a container." % _name(state, container), False)
        if container not in state.open_containers:
            return Result("The %s is closed." % _name(state, container), False)
        scope = list(state.contents[container])
    else:
        scope = state.visible_items()
    if cmd.noun == "all":
        direct = [i for i in scope if i not in state.inventory]
        if not direct:
            return Result("There is nothing to take.", False)
        lines = []
        taken_any = False
        for iid in list(direct):
            if not state.world.items[iid].takeable:
                continue
            result = _take_one(state, iid)
            lines.append("%s: %s" % (_name(state, iid), result.text))
            taken_any = taken_any or result.ok
        if not lines:
            return Result("There is nothing to take.", False)
        return Result("\n".join(lines), taken_any)
    iid = state.find_in(scope, cmd.noun)
    if iid is None:
        if state.find_in(state.inventory, cmd.noun):
            return Result("You already have that.", False)
        return Result("You see no %s here." % cmd.noun, False)
    return _take_one(state, iid)


def drop(state, cmd):
    if not cmd.noun:
        return Result("Drop what?", False)
    if cmd.noun == "all":
        if not state.inventory:
            return Result("You have nothing.", False)
        lines = []
        for iid in list(state.inventory):
            state.inventory.remove(iid)
            state.room_items[state.room].append(iid)
            lines.append("%s: Dropped." % _name(state, iid))
        return Result("\n".join(lines))
    iid = state.find_in(state.inventory, cmd.noun)
    if iid is None:
        return Result("You don't have %s." % with_article(cmd.noun), False)
    state.inventory.remove(iid)
    state.room_items[state.room].append(iid)
    return Result("Dropped.")


def put(state, cmd):
    if not cmd.noun or not cmd.target or cmd.prep != "in":
        return Result("Put what in what?", False)
    iid = state.find_in(state.inventory, cmd.noun)
    if iid is None:
        return Result("You don't have %s." % with_article(cmd.noun), False)
    box = state.find_in(state.visible_items() + state.inventory, cmd.target)
    if box is None:
        return Result("You see no %s here." % cmd.target, False)
    if box == iid:
        return Result("You can't put something inside itself.", False)
    box_item = state.world.items[box]
    if not box_item.container:
        return Result("The %s is not a container." % box_item.name, False)
    if box not in state.open_containers:
        return Result("The %s is closed." % box_item.name, False)
    item = state.world.items[iid]
    if state.contained_weight(box) + item.weight > box_item.capacity:
        return Result("The %s won't fit in the %s." % (item.name, box_item.name), False)
    state.inventory.remove(iid)
    state.contents[box].append(iid)
    return Result("Done.")


def inventory(state):
    if not state.inventory:
        return Result("You are carrying nothing.")
    text = "You are carrying %s. (%d/%d)" % (
        describe_items(state.world, state.inventory), state.carried_weight(), state.world.capacity)
    return Result(text)


def examine(state, cmd):
    if not cmd.noun:
        return Result("Examine what?", False)
    if not state.is_lit() and state.find_in(state.inventory, cmd.noun) is None:
        return Result("It is too dark to see.", False)
    iid = state.find_in(state.inventory + state.visible_items(), cmd.noun)
    if iid is None:
        return Result("You see no %s here." % cmd.noun, False)
    item = state.world.items[iid]
    text = item.description
    if item.light:
        text += " It is %s." % ("lit" if iid in state.lit else "not lit")
    if item.container:
        if iid in state.open_containers:
            inside = state.contents[iid]
            text += " It contains %s." % describe_items(state.world, inside) if inside else " It is empty."
        elif iid in state.locked_items:
            text += " It is locked."
        else:
            text += " It is closed."
    return Result(text)


def _container_target(state, cmd):
    if not cmd.noun:
        return None, Result("%s what?" % cmd.verb.capitalize(), False)
    iid = state.find_in(state.visible_items() + state.inventory, cmd.noun)
    if iid is None:
        return None, Result("You see no %s here." % cmd.noun, False)
    if not state.world.items[iid].container:
        return None, Result("The %s can't be %sed." % (_name(state, iid), cmd.verb), False)
    return iid, None


def open_(state, cmd):
    iid, error = _container_target(state, cmd)
    if error:
        return error
    if iid in state.locked_items:
        return Result("The %s is locked." % _name(state, iid), False)
    if iid in state.open_containers:
        return Result("It is already open.", False)
    state.open_containers.add(iid)
    return Result("Opened.")


def close(state, cmd):
    iid, error = _container_target(state, cmd)
    if error:
        return error
    if iid not in state.open_containers:
        return Result("It is already closed.", False)
    state.open_containers.discard(iid)
    return Result("Closed.")


def unlock(state, cmd):
    if not cmd.noun or not cmd.target or cmd.prep != "with":
        return Result("Unlock what with what?", False)
    key = state.find_in(state.inventory, cmd.target)
    if key is None:
        return Result("You don't have %s." % with_article(cmd.target), False)
    if cmd.noun in DIRECTIONS:
        direction = cmd.noun
        if (state.room, direction) not in state.locked_exits:
            return Result("There is nothing to unlock that way.", False)
        if state.here().locked_exits.get(direction) != key:
            return Result("The %s doesn't fit." % _name(state, key), False)
        dest = state.here().exits[direction]
        state.locked_exits.discard((state.room, direction))
        state.locked_exits.discard((dest, OPPOSITE[direction]))
        return Result("Unlocked.")
    iid = state.find_in(state.visible_items() + state.inventory, cmd.noun)
    if iid is None:
        return Result("You see no %s here." % cmd.noun, False)
    if iid not in state.locked_items:
        return Result("The %s is not locked." % _name(state, iid), False)
    if state.world.items[iid].key != key:
        return Result("The %s doesn't fit." % _name(state, key), False)
    state.locked_items.discard(iid)
    return Result("Unlocked.")


def light(state, cmd, on=True):
    if not cmd.noun:
        return Result("%s what?" % cmd.verb.capitalize(), False)
    iid = state.find_in(state.inventory + state.room_items[state.room], cmd.noun)
    if iid is None:
        return Result("You see no %s here." % cmd.noun, False)
    item = state.world.items[iid]
    if not item.light:
        return Result("The %s can't be %s." % (item.name, "lit" if on else "extinguished"), False)
    if on:
        if iid in state.lit:
            return Result("It is already lit.", False)
        state.lit.add(iid)
        return Result("The %s is now lit." % item.name)
    if iid not in state.lit:
        return Result("It is not lit.", False)
    state.lit.discard(iid)
    return Result("The %s goes out." % item.name)


def score(state):
    return Result("Score: %d in %d turn%s." % (state.score, state.turn, "" if state.turn == 1 else "s"))


TURN_COMMANDS = {"go", "take", "drop", "put", "open", "close", "unlock", "light", "extinguish"}


def run(state, cmd):
    verb = cmd.verb
    if verb == "look":
        return look(state)
    if verb == "go":
        return go(state, cmd)
    if verb == "take":
        return take(state, cmd)
    if verb == "drop":
        return drop(state, cmd)
    if verb == "put":
        return put(state, cmd)
    if verb == "inventory":
        return inventory(state)
    if verb == "examine":
        return examine(state, cmd)
    if verb == "open":
        return open_(state, cmd)
    if verb == "close":
        return close(state, cmd)
    if verb == "unlock":
        return unlock(state, cmd)
    if verb == "light":
        return light(state, cmd, True)
    if verb == "extinguish":
        return light(state, cmd, False)
    if verb == "score":
        return score(state)
    return Result("Nothing happens.", False)
