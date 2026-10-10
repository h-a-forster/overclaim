"""Load the service configuration from JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """The configuration is invalid. ``errors`` lists every problem found."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = list(errors)


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    workers: int = 4
    log_level: str = "info"
    timeout_s: float = 30.0


DEFAULTS = {"workers": 4, "log_level": "info", "timeout_s": 30.0}


def load_config(text: str) -> Config:
    """Parse JSON ``text`` into a :class:`Config`, filling in defaults."""
    data = json.loads(text)
    merged = {**DEFAULTS, **data}
    return Config(
        host=merged["host"],
        port=merged["port"],
        workers=merged["workers"],
        log_level=merged["log_level"],
        timeout_s=merged["timeout_s"],
    )


def load_config_file(path: str | Path) -> Config:
    """Read and parse a UTF-8 JSON config file."""
    return load_config(Path(path).read_text(encoding="utf-8"))
