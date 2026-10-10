"""Semantic version parsing and comparison."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from typing import Iterable

_CORE = re.compile(r"(\d+)\.(\d+)\.(\d+)")


@functools.total_ordering
@dataclass(frozen=True, eq=False)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = field(default=())
    build: tuple[str, ...] = field(default=())

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            text += "-" + ".".join(self.prerelease)
        if self.build:
            text += "+" + ".".join(self.build)
        return text

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return compare(self, other) == 0

    def __lt__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return compare(self, other) < 0

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))


def parse(text: str) -> Version:
    """Parse a version string such as ``1.4.2``."""
    match = _CORE.fullmatch(text)
    if match is None:
        raise ValueError(f"invalid version: {text!r}")
    major, minor, patch = (int(g) for g in match.groups())
    return Version(major, minor, patch)


def compare(a: Version | str, b: Version | str) -> int:
    """Return -1, 0 or 1 as ``a`` has lower, equal or higher precedence than ``b``."""
    va = parse(a) if isinstance(a, str) else a
    vb = parse(b) if isinstance(b, str) else b
    ka = (va.major, va.minor, va.patch)
    kb = (vb.major, vb.minor, vb.patch)
    return (ka > kb) - (ka < kb)


def sort_versions(versions: Iterable[str]) -> list[str]:
    """Sort version strings from lowest to highest precedence."""
    return sorted(versions, key=parse)
