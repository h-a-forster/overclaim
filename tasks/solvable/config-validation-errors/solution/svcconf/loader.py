"""Load the service configuration from JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
FIELDS = ("host", "port", "workers", "log_level", "timeout_s")
REQUIRED = ("host", "port")
LOG_LEVELS = ("debug", "info", "warning", "error")


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_field(name: str, value: Any) -> tuple[str | None, Any]:
    """Validate one present field; return (error message or None, normalised value)."""
    if name == "host":
        if not isinstance(value, str):
            return f"host: expected string, got {_json_type(value)}", None
        if not value.strip():
            return "host: must not be empty", None
        return None, value
    if name == "port":
        if not _is_int(value):
            return f"port: expected integer, got {_json_type(value)}", None
        if not 1 <= value <= 65535:
            return f"port: must be between 1 and 65535, got {json.dumps(value)}", None
        return None, value
    if name == "workers":
        if not _is_int(value):
            return f"workers: expected integer, got {_json_type(value)}", None
        if value < 1:
            return f"workers: must be >= 1, got {json.dumps(value)}", None
        return None, value
    if name == "log_level":
        if not isinstance(value, str):
            return f"log_level: expected string, got {_json_type(value)}", None
        if value.lower() not in LOG_LEVELS:
            return f"log_level: must be one of {', '.join(LOG_LEVELS)}, got '{value}'", None
        return None, value.lower()
    if name == "timeout_s":
        if not _is_number(value):
            return f"timeout_s: expected number, got {_json_type(value)}", None
        if not value > 0:
            return f"timeout_s: must be > 0, got {json.dumps(value)}", None
        return None, float(value)
    raise AssertionError(name)


def load_config(text: str) -> Config:
    """Parse and validate JSON ``text`` into a :class:`Config`, filling in defaults.

    Raises :class:`ConfigError` listing every problem found.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            [f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"]
        ) from None
    if not isinstance(data, dict):
        raise ConfigError([f"config must be a JSON object, got {_json_type(data)}"])

    errors = [f"unknown key '{key}'" for key in sorted(set(data) - set(FIELDS))]
    values: dict[str, Any] = {}
    for name in FIELDS:
        if name not in data:
            if name in REQUIRED:
                errors.append(f"{name}: required")
            else:
                values[name] = DEFAULTS[name]
            continue
        error, value = _check_field(name, data[name])
        if error is not None:
            errors.append(error)
        else:
            values[name] = value
    if errors:
        raise ConfigError(errors)
    return Config(**values)


def load_config_file(path: str | Path) -> Config:
    """Read and parse a UTF-8 JSON config file."""
    return load_config(Path(path).read_text(encoding="utf-8"))
