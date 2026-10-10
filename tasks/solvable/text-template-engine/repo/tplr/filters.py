"""Built-in filters. Each entry is ``name -> function(value, *args)``."""

from __future__ import annotations

FILTERS = {
    "upper": lambda v: str(v).upper(),
    "lower": lambda v: str(v).lower(),
    "title": lambda v: str(v).title(),
    "trim": lambda v: str(v).strip(),
    "length": lambda v: len(v),
    "join": lambda v: ", ".join(str(i) for i in v),
    "default": lambda v: v,
}
