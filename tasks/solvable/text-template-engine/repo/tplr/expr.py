"""Expressions: a variable path followed by filters, e.g. ``user.name|title``."""

from __future__ import annotations

import re

from .errors import TemplateRenderError, TemplateSyntaxError
from .filters import FILTERS

_PATH = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*(\.[A-Za-z_0-9]+)*$")


def lookup(scopes: list[dict], path: str):
    """Resolve a dotted ``path`` in the scope stack; missing values are ``None``."""
    head, *rest = path.split(".")
    value = None
    for scope in reversed(scopes):
        if head in scope:
            value = scope[head]
            break
    for seg in rest:
        if isinstance(value, dict):
            value = value.get(seg)
        elif isinstance(value, (list, tuple)) and seg.isdigit() and int(seg) < len(value):
            value = value[int(seg)]
        elif value is not None and not seg.startswith("_") and hasattr(value, seg):
            value = getattr(value, seg)
        else:
            return None
    return value


class Expr:
    def __init__(self, path: str, filters: list[str]) -> None:
        self.path = path
        self.filters = filters

    def eval(self, scopes: list[dict]):
        value = lookup(scopes, self.path)
        for name in self.filters:
            try:
                value = FILTERS[name](value)
            except Exception as exc:
                raise TemplateRenderError(f"filter {name!r} failed: {exc}") from exc
        return value


def parse_expr(source: str, line: int) -> Expr:
    path, *filters = [part.strip() for part in source.split("|")]
    if not _PATH.match(path):
        raise TemplateSyntaxError(f"bad expression {source!r}", line)
    for name in filters:
        if name not in FILTERS:
            raise TemplateSyntaxError(f"unknown filter {name!r}", line)
    return Expr(path, filters)
