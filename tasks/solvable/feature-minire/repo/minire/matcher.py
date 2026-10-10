"""Backtracking matcher (recursive, continuation passing)."""
from .nodes import Any, CharClass, Concat, Literal, Repeat


def _m(node, s, i, k):
    """Match `node` at s[i:]; call k(j) for each way of matching, return first truthy result."""
    if isinstance(node, Literal):
        return i < len(s) and s[i] == node.ch and k(i + 1)
    if isinstance(node, Any):
        return i < len(s) and s[i] != "\n" and k(i + 1)
    if isinstance(node, CharClass):
        return i < len(s) and node.matches(s[i]) and k(i + 1)
    if isinstance(node, Concat):
        return _seq(node.items, 0, s, i, k)
    if isinstance(node, Repeat):
        return _rep(node, 0, s, i, k)
    raise TypeError(node)


def _seq(items, n, s, i, k):
    if n == len(items):
        return k(i)
    return _m(items[n], s, i, lambda j: _seq(items, n + 1, s, j, k))


def _rep(node, count, s, i, k):
    hi = node.hi
    if hi is None or count < hi:
        r = _m(node.node, s, i, lambda j: j > i and _rep(node, count + 1, s, j, k))
        if r:
            return r
    return count >= node.lo and k(i)


def match_at(node, s, i, full=False):
    """Return the end index of the first match of `node` at s[i:], or None."""
    end = []

    def done(j):
        if full and j != len(s):
            return False
        end.append(j)
        return True

    return end[0] if _m(node, s, i, done) else None
