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
    """`[...]`, `\\d`, `\\w`, `\\s` and their negations.

    ranges: tuple of (lo, hi) one-character strings, inclusive.
    """
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


class Repeat(Node):
    """Greedy repetition of `node`, `lo` to `hi` times (`hi` None means unbounded)."""
    __slots__ = ("node", "lo", "hi")

    def __init__(self, node, lo, hi):
        self.node = node
        self.lo = lo
        self.hi = hi
