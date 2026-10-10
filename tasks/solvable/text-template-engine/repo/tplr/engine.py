"""Compile and render templates."""

from __future__ import annotations

from .parser import For, If, Output, Text, parse


def _to_text(value) -> str:
    return "" if value is None else str(value)


class Template:
    def __init__(self, source: str) -> None:
        self.nodes = parse(source)

    def render(self, **context) -> str:
        out: list[str] = []
        self._render(self.nodes, [context], out)
        return "".join(out)

    def _render(self, nodes: list, scopes: list[dict], out: list[str]) -> None:
        for node in nodes:
            if isinstance(node, Text):
                out.append(node.text)
            elif isinstance(node, Output):
                out.append(_to_text(node.expr.eval(scopes)))
            elif isinstance(node, If):
                branch = node.body if node.cond.eval(scopes) else node.else_body
                self._render(branch, scopes, out)
            elif isinstance(node, For):
                items = node.iterable.eval(scopes)
                for item in list(items or ()):
                    self._render(node.body, scopes + [{node.name: item}], out)


def render(source: str, **context) -> str:
    return Template(source).render(**context)
