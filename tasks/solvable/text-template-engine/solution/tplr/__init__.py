"""tplr: a tiny template engine."""

from .engine import Template, render
from .errors import TemplateError, TemplateRenderError, TemplateSyntaxError

__all__ = ["Template", "TemplateError", "TemplateRenderError", "TemplateSyntaxError", "render"]
