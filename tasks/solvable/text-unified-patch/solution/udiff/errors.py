"""Error types."""

from __future__ import annotations


class PatchError(ValueError):
    """A patch is malformed or does not apply.

    ``line`` is the 1-based line of the patch text for parse errors; ``file`` and ``hunk``
    (1-based) say where an apply error happened. Unused attributes are ``None``.
    """

    def __init__(self, message: str, *, line: int | None = None, file: str | None = None,
                 hunk: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.file = file
        self.hunk = hunk
