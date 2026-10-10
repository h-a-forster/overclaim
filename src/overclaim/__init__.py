"""Measure how often coding agents claim success they did not achieve."""

from __future__ import annotations


def __getattr__(name: str) -> str:
    # Lazy, so the Stop hook (which imports this package on every stop) skips importlib.metadata.
    if name == "__version__":
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("overclaim")
        except PackageNotFoundError:  # running from a source tree or the hook zipapp
            return "0.1.0"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
