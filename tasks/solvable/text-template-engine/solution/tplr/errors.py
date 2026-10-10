"""Error types."""

from __future__ import annotations


class TemplateError(Exception):
    """Base class for all template errors."""


class TemplateSyntaxError(TemplateError):
    """The template source is malformed. ``line`` is the 1-based line of the problem."""

    def __init__(self, message: str, line: int) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line


class TemplateRenderError(TemplateError):
    """Rendering failed (for example a filter was applied to a value it cannot handle)."""
