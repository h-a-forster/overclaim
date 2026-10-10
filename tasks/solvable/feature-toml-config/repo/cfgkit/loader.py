"""Reading configuration files by format."""
import json
from pathlib import Path

from .config import Config
from .errors import ConfigError, ParseError
from .ini import parse_ini


def load_text(text, fmt):
    """Parse `text` written in format `fmt` ("ini" or "json") into a plain dict."""
    if fmt == "ini":
        return parse_ini(text)
    if fmt == "json":
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ParseError(str(exc)) from None
        if not isinstance(data, dict):
            raise ParseError("top level must be an object")
        return data
    raise ConfigError("unsupported format %r" % (fmt,))


def load_file(path):
    """Load a configuration file; the format comes from the suffix. Returns a Config."""
    p = Path(path)
    fmt = p.suffix.lower().lstrip(".")
    return Config(load_text(p.read_text(encoding="utf-8"), fmt))


def load_layers(paths):
    """Merge several files, later ones win."""
    result = Config()
    for path in paths:
        result = result.merge(load_file(path))
    return result
