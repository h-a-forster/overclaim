from .matcher import match_at
from .parser import parse


class Match:
    def __init__(self, string, start, end):
        self.string = string
        self._span = (start, end)

    def group(self, n=0):
        if n != 0:
            raise IndexError("no such group")
        return self.string[self._span[0]:self._span[1]]

    def span(self, n=0):
        if n != 0:
            raise IndexError("no such group")
        return self._span

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def __repr__(self):
        return "<Match span=%r match=%r>" % (self._span, self.group())


class Pattern:
    def __init__(self, pattern):
        self.pattern = pattern
        self._node = parse(pattern)

    def match(self, string, pos=0):
        """Match at `pos` (anchored there)."""
        e = match_at(self._node, string, pos)
        return None if e is None else Match(string, pos, e)

    def fullmatch(self, string):
        e = match_at(self._node, string, 0, full=True)
        return None if e is None else Match(string, 0, e)

    def search(self, string, pos=0):
        for i in range(pos, len(string) + 1):
            m = self.match(string, i)
            if m:
                return m
        return None


def compile(pattern):
    return Pattern(pattern)


def match(pattern, string):
    return compile(pattern).match(string)


def search(pattern, string):
    return compile(pattern).search(string)


def fullmatch(pattern, string):
    return compile(pattern).fullmatch(string)
