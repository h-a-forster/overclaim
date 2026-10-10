class ConfigError(Exception):
    """Base class for configuration problems."""


class ParseError(ConfigError):
    """Syntax or semantic error in a configuration document. `line` is 1-based (or None)."""

    def __init__(self, message, line=None):
        super().__init__(message if line is None else "line %d: %s" % (line, message))
        self.message = message
        self.line = line
