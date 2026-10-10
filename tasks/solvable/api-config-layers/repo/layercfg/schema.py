"""Schema: nested sections of typed fields."""

from dataclasses import dataclass
from typing import Any

TYPES = (str, int, float, bool)


@dataclass(frozen=True)
class Field:
    type: type = str
    default: Any = None
    required: bool = False

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f"unsupported field type {self.type!r}")
        if self.required and self.default is not None:
            raise ValueError("a required field cannot have a default")

    def check(self, value):
        """Return ``value`` if it has the right type, else raise ValueError."""
        if self.type is bool:
            ok = isinstance(value, bool)
        elif self.type is int:
            ok = isinstance(value, int) and not isinstance(value, bool)
        elif self.type is float:
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            if ok:
                return float(value)
        else:
            ok = isinstance(value, str)
        if not ok:
            raise ValueError(f"expected {self.type.__name__}, got {type(value).__name__}")
        return value


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
        """Dotted paths of all fields, in declaration order."""
        return list(self._fields)

    def field(self, path):
        return self._fields[path]

    def is_field(self, path):
        return path in self._fields

    def is_section(self, path):
        return path in self._sections
