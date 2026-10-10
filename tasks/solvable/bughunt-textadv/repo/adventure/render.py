"""Text helpers."""


def with_article(name):
    return ("an " if name[:1] in "aeiou" else "a ") + name


def join_list(names):
    """``['a', 'b', 'c']`` -> ``'a, b and c'``."""
    names = list(names)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def describe_items(world, item_ids):
    return join_list(with_article(world.items[i].name) for i in item_ids)
