from .matcher import Program, run
from .parser import parse


class Match:
    def __init__(self, string, slots, ngroups):
        self.string = string
        self._slots = slots
        self.lastgroup = None
        self._n = ngroups

    def _check(self, n):
        if not isinstance(n, int) or n < 0 or n > self._n:
            raise IndexError("no such group")

    def group(self, n=0):
        self._check(n)
        a, b = self._slots[2 * n], self._slots[2 * n + 1]
        if a < 0 or b < 0:
            return None
        return self.string[a:b]

    def groups(self):
        return tuple(self.group(i) for i in range(1, self._n + 1))

    def span(self, n=0):
        self._check(n)
        a, b = self._slots[2 * n], self._slots[2 * n + 1]
        if a < 0 or b < 0:
            return (-1, -1)
        return (a, b)

    def start(self, n=0):
        return self.span(n)[0]

    def end(self, n=0):
        return self.span(n)[1]

    def __repr__(self):
        return "<Match span=%r match=%r>" % (self.span(), self.group())


class Pattern:
    def __init__(self, pattern):
        self.pattern = pattern
        node, self.groups = parse(pattern)
        self._prog = Program(node, self.groups)

    def _wrap(self, string, slots):
        return None if slots is None else Match(string, slots, self.groups)

    def match(self, string, pos=0):
        return self._wrap(string, run(self._prog, string, pos))

    def fullmatch(self, string):
        return self._wrap(string, run(self._prog, string, 0, full=True))

    def search(self, string, pos=0):
        return self._search(string, pos, -1)

    def _search(self, string, pos, noempty_at):
        for i in range(pos, len(string) + 1):
            slots = run(self._prog, string, i, noempty=(i == noempty_at))
            if slots is not None:
                return Match(string, slots, self.groups)
        return None

    def _scan(self, string):
        pos = 0
        noempty = -1
        while pos <= len(string):
            m = self._search(string, pos, noempty)
            if m is None:
                return
            yield m
            s, e = m.span()
            noempty = e if s == e else -1
            pos = e

    def findall(self, string):
        out = []
        for m in self._scan(string):
            if self.groups == 0:
                out.append(m.group())
            elif self.groups == 1:
                out.append(m.group(1) or "")
            else:
                out.append(tuple(g or "" for g in m.groups()))
        return out

    def sub(self, repl, string, count=0):
        parts = []
        last = 0
        done = 0
        for m in self._scan(string):
            if count and done >= count:
                break
            s, e = m.span()
            parts.append(string[last:s])
            parts.append(repl(m) if callable(repl) else repl)
            last = e
            done += 1
        parts.append(string[last:])
        return "".join(parts)


def compile(pattern):
    return Pattern(pattern)


def match(pattern, string):
    return compile(pattern).match(string)


def search(pattern, string):
    return compile(pattern).search(string)


def fullmatch(pattern, string):
    return compile(pattern).fullmatch(string)


def findall(pattern, string):
    return compile(pattern).findall(string)


def sub(pattern, repl, string, count=0):
    return compile(pattern).sub(repl, string, count)
