"""Pattern AST. Nodes are plain immutable-ish value objects."""


class Node:
    __slots__ = ()

    def __eq__(self, other):
        return type(self) is type(other) and all(
            getattr(self, n) == getattr(other, n) for n in self.__slots__
        )

    def __hash__(self):
        return hash((type(self).__name__,) + tuple(repr(getattr(self, n)) for n in self.__slots__))

    def __repr__(self):
        args = ", ".join(repr(getattr(self, n)) for n in self.__slots__)
        return f"{type(self).__name__}({args})"


class Literal(Node):
    __slots__ = ("ch",)

    def __init__(self, ch):
        self.ch = ch


class Any(Node):
    """`.`: any character except newline."""
    __slots__ = ()


class CharClass(Node):
    """`[...]`, `\\d`, `\\w`, `\\s` and their negations."""
    __slots__ = ("negated", "ranges")

    def __init__(self, negated, ranges):
        self.negated = negated
        self.ranges = tuple(ranges)

    def matches(self, ch):
        hit = any(lo <= ch <= hi for lo, hi in self.ranges)
        return hit != self.negated


class Concat(Node):
    __slots__ = ("items",)

    def __init__(self, items):
        self.items = tuple(items)


class Alt(Node):
    __slots__ = ("options",)

    def __init__(self, options):
        self.options = tuple(options)


class Group(Node):
    """Capturing group number `index` (1-based)."""
    __slots__ = ("index", "node")

    def __init__(self, index, node):
        self.index = index
        self.node = node


class Assertion(Node):
    """`kind` is "bol" (`^`) or "eol" (`$`)."""
    __slots__ = ("kind",)

    def __init__(self, kind):
        self.kind = kind


class Backref(Node):
    __slots__ = ("index",)

    def __init__(self, index):
        self.index = index


class Repeat(Node):
    """Repetition of `node`, `lo` to `hi` times (`hi` None means unbounded)."""
    __slots__ = ("node", "lo", "hi", "greedy")

    def __init__(self, node, lo, hi, greedy=True):
        self.node = node
        self.lo = lo
        self.hi = hi
        self.greedy = greedy
