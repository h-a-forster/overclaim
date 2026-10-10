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

    def old_block(self) -> list[str]:
        return [text + "\n" for tag, text in self.lines if tag in " -"]

    def new_block(self) -> list[str]:
        return [text + "\n" for tag, text in self.lines if tag in " +"]


@dataclass
class FilePatch:
    old_path: str
    new_path: str
    hunks: list[Hunk] = field(default_factory=list)
