"""udiff: parse and apply unified diffs to in-memory files."""

from .api import apply_patch
from .errors import PatchError
from .parser import parse_patch

__all__ = ["PatchError", "apply_patch", "parse_patch"]
