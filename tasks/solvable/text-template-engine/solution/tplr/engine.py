"""Compile and render templates."""

from __future__ import annotations

from .errors import TemplateRenderError
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
                for cond, body in node.branches:
                    if cond.eval(scopes):
                        self._render(body, scopes, out)
                        break
                else:
                    if node.else_body is not None:
                        self._render(node.else_body, scopes, out)
            elif isinstance(node, For):
                self._render_for(node, scopes, out)

    def _render_for(self, node: For, scopes: list[dict], out: list[str]) -> None:
        seq = node.iterable.eval(scopes)
        try:
            items = [] if seq is None else list(seq)
        except TypeError:
            raise TemplateRenderError(f"cannot iterate over {type(seq).__name__}") from None
        if not items:
            if node.else_body is not None:
                self._render(node.else_body, scopes, out)
            return
        total = len(items)
        for idx, item in enumerate(items):
            scope: dict = {}
            if len(node.names) == 1:
                scope[node.names[0]] = item
            else:
                try:
                    parts = list(item)
                except TypeError:
                    raise TemplateRenderError("cannot unpack a non-iterable item") from None
                if len(parts) != len(node.names):
                    raise TemplateRenderError(
                        f"expected {len(node.names)} values to unpack, got {len(parts)}"
                    )
                scope.update(zip(node.names, parts))
            scope["loop"] = {
                "index": idx + 1,
                "index0": idx,
                "first": idx == 0,
                "last": idx == total - 1,
                "length": total,
            }
            self._render(node.body, scopes + [scope], out)


def render(source: str, **context) -> str:
    return Template(source).render(**context)
