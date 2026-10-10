"""Built-in filters: ``name -> (function(value, *args), min_args, max_args)``."""

from __future__ import annotations


def _s(value) -> str:
    return "" if value is None else str(value)


def _length(value):
    return 0 if value is None else len(value)


def _join(value, sep=", "):
    if value is None:
        return ""
    return _s(sep).join(_s(i) for i in value)


def _default(value, fallback):
    return fallback if value is None or value == "" else value


def _truncate(value, n):
    text = _s(value)
    if len(text) <= n:
        return text
    return text[: max(n - 3, 0)] + "..."


def _first(value):
    return value[0] if value else None


def _last(value):
    return value[-1] if value else None


FILTERS = {
    "upper": (lambda v: _s(v).upper(), 0, 0),
    "lower": (lambda v: _s(v).lower(), 0, 0),
    "title": (lambda v: _s(v).title(), 0, 0),
    "trim": (lambda v: _s(v).strip(), 0, 0),
    "length": (_length, 0, 0),
    "join": (_join, 0, 1),
    "default": (_default, 1, 1),
    "truncate": (_truncate, 1, 1),
    "replace": (lambda v, a, b: _s(v).replace(a, b), 2, 2),
    "first": (_first, 0, 0),
    "last": (_last, 0, 0),
}
