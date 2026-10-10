"""Parsed patch structures."""

from __future__ import annotations

from dataclasses import dataclass, field

DEV_NULL = "/dev/null"


@dataclass
class Hunk:
    old_start: int
    old_len: int
    new_start: int
    new_len: int
    lines: list[tuple[str, str]] = field(default_factory=list)  # (tag, text) with tag in " +-"
    no_newline: set[int] = field(default_factory=set)  # indexes into ``lines`` lacking "\n"

    def _block(self, tags: str) -> list[str]:
        return [
            text + ("" if i in self.no_newline else "\n")
            for i, (tag, text) in enumerate(self.lines)
            if tag in tags
        ]

    def old_block(self) -> list[str]:
        return self._block(" -")

    def new_block(self) -> list[str]:
        return self._block(" +")

    def reversed(self) -> "Hunk":
        swap = {" ": " ", "+": "-", "-": "+"}
        return Hunk(
            self.new_start, self.new_len, self.old_start, self.old_len,
            [(swap[tag], text) for tag, text in self.lines], set(self.no_newline),
        )


@dataclass
class FilePatch:
    old_path: str
    new_path: str
    hunks: list[Hunk] = field(default_factory=list)

    def reversed(self) -> "FilePatch":
        return FilePatch(self.new_path, self.old_path, [h.reversed() for h in self.hunks])
