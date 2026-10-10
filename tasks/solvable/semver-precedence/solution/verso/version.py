"""Semantic version parsing and comparison (Semantic Versioning 2.0.0)."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from typing import Iterable

_NUM = r"(?:0|[1-9][0-9]*)"
_IDENT = r"[0-9A-Za-z-]+"
_SEMVER = re.compile(
    rf"(?P<major>{_NUM})\.(?P<minor>{_NUM})\.(?P<patch>{_NUM})"
    rf"(?:-(?P<pre>{_IDENT}(?:\.{_IDENT})*))?"
    rf"(?:\+(?P<build>{_IDENT}(?:\.{_IDENT})*))?",
    re.ASCII,
)
_NUMERIC = re.compile(r"[0-9]+", re.ASCII)


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
        # Build metadata does not affect equality, so it must not affect the hash either.
        return hash((self.major, self.minor, self.patch, _pre_key(self.prerelease)))


def parse(text: str) -> Version:
    """Parse a semantic version string such as ``1.4.2-rc.1+build.5``."""
    match = _SEMVER.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        raise ValueError(f"invalid version: {text!r}")
    pre = tuple(match["pre"].split(".")) if match["pre"] else ()
    for ident in pre:
        if _NUMERIC.fullmatch(ident) and len(ident) > 1 and ident[0] == "0":
            raise ValueError(f"invalid version: {text!r} (leading zero in {ident!r})")
    build = tuple(match["build"].split(".")) if match["build"] else ()
    return Version(int(match["major"]), int(match["minor"]), int(match["patch"]), pre, build)


def _pre_key(prerelease: tuple[str, ...]) -> tuple:
    # Numeric identifiers sort before alphanumeric ones: (0, n) < (1, s).
    return tuple((0, int(p), "") if _NUMERIC.fullmatch(p) else (1, 0, p) for p in prerelease)


def _cmp(x, y) -> int:
    return (x > y) - (x < y)


def compare(a: Version | str, b: Version | str) -> int:
    """Return -1, 0 or 1 as ``a`` has lower, equal or higher precedence than ``b``."""
    va = parse(a) if isinstance(a, str) else a
    vb = parse(b) if isinstance(b, str) else b
    core = _cmp((va.major, va.minor, va.patch), (vb.major, vb.minor, vb.patch))
    if core:
        return core
    if not va.prerelease or not vb.prerelease:
        # A normal version outranks any of its pre-releases.
        return _cmp(not va.prerelease, not vb.prerelease)
    # Tuple comparison gives "longer wins when the common prefix is equal" for free.
    return _cmp(_pre_key(va.prerelease), _pre_key(vb.prerelease))


def sort_versions(versions: Iterable[str]) -> list[str]:
    """Sort version strings from lowest to highest precedence (stable)."""
    return sorted(versions, key=parse)
