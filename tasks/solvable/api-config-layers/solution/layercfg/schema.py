"""Schema: nested sections of typed fields."""

import math
import re
from dataclasses import dataclass
from typing import Any

TYPES = (str, int, float, bool, list)
_INT = re.compile(r"^[+-]?\d+$")
_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


def _from_text(typ, text):
    if typ is str:
        return text
    t = text.strip()
    if typ is int:
        if not _INT.match(t):
            raise ValueError(f"not an integer: {text!r}")
        return int(t)
    if typ is float:
        try:
            v = float(t)
        except ValueError:
            raise ValueError(f"not a number: {text!r}") from None
        if not math.isfinite(v):
            raise ValueError(f"not a finite number: {text!r}")
        return v
    low = t.lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    raise ValueError(f"not a boolean: {text!r}")


def _typed(typ, value):
    if typ is bool:
        ok = isinstance(value, bool)
    elif typ is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif typ is float:
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        if ok:
            return float(value)
    else:
        ok = isinstance(value, str)
    if not ok:
        raise ValueError(f"expected {typ.__name__}, got {type(value).__name__}")
    return value


@dataclass(frozen=True)
class Field:
    type: type = str
    default: Any = None
    required: bool = False
    choices: Any = None
    item: type = str  # element type of list fields

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f"unsupported field type {self.type!r}")
        if self.item not in (str, int, float, bool):
            raise ValueError(f"unsupported item type {self.item!r}")
        if self.required and self.default is not None:
            raise ValueError("a required field cannot have a default")

    def initial(self):
        return list(self.default) if isinstance(self.default, list) else self.default

    def convert(self, value, coerce=False):
        """Validate ``value`` (coercing strings when ``coerce``); returns the stored value."""
        if self.type is list:
            if coerce and isinstance(value, str):
                parts = [] if not value.strip() else [p.strip() for p in value.split(",")]
                out = [_from_text(self.item, p) for p in parts]
            elif isinstance(value, list):
                out = [_typed(self.item, v) for v in value]
            else:
                raise ValueError(f"expected list, got {type(value).__name__}")
            if self.choices is not None:
                for v in out:
                    if v not in self.choices:
                        raise ValueError(f"{v!r} is not one of {list(self.choices)!r}")
            return out
        if coerce and isinstance(value, str):
            out = _from_text(self.type, value)
        else:
            out = _typed(self.type, value)
        if self.choices is not None and out not in self.choices:
            raise ValueError(f"{out!r} is not one of {list(self.choices)!r}")
        return out

    check = convert


class Schema:
    def __init__(self, tree):
        self._fields = {}
        self._sections = set()
        self._walk(tree, "")

    def _walk(self, tree, prefix):
        for key, node in tree.items():
            if not key or "." in key:
                raise ValueError(f"bad key {key!r}")
            path = prefix + key
            if isinstance(node, Field):
                self._fields[path] = node
            elif isinstance(node, dict):
                self._sections.add(path)
                self._walk(node, path + ".")
            else:
                raise ValueError(f"bad schema node at {path!r}")

    def paths(self):
        return list(self._fields)

    def field(self, path):
        return self._fields[path]

    def is_field(self, path):
        return path in self._fields

    def is_section(self, path):
        return path in self._sections
