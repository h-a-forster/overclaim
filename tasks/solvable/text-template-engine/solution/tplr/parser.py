"""Build a node tree from tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import TemplateSyntaxError
from .expr import Expr, parse_expr
from .lexer import tokenize


@dataclass
class Text:
    text: str


@dataclass
class Output:
    expr: Expr


@dataclass
class If:
    branches: list = field(default_factory=list)  # [(Expr, body)]
    else_body: list | None = None
    line: int = 0


@dataclass
class For:
    names: list
    iterable: Expr
    body: list = field(default_factory=list)
    else_body: list | None = None
    line: int = 0


class _Frame:
    def __init__(self, node, outer: list) -> None:
        self.node = node
        self.outer = outer  # list the node was appended to
        self.seen_else = False


_TAG = re.compile(r"^(\w+)\s*(.*)$", re.S)
_FOR = re.compile(r"^([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s+in\s+(.+)$", re.S)


def parse(source: str) -> list:
    root: list = []
    stack: list[_Frame] = []
    cur = root
    for tok in tokenize(source):
        if tok.kind == "text":
            cur.append(Text(tok.text))
            continue
        if tok.kind == "var":
            cur.append(Output(parse_expr(tok.text, tok.line)))
            continue
        m = _TAG.match(tok.text)
        if not m:
            raise TemplateSyntaxError("empty or malformed tag", tok.line)
        word, rest = m.group(1), m.group(2).strip()
        top = stack[-1] if stack else None
        if word == "if":
            body: list = []
            node = If([(parse_expr(rest, tok.line), body)], None, tok.line)
            cur.append(node)
            stack.append(_Frame(node, cur))
            cur = body
        elif word == "for":
            fm = _FOR.match(rest)
            if not fm:
                raise TemplateSyntaxError("malformed 'for' tag", tok.line)
            names = [n.strip() for n in fm.group(1).split(",")]
            node = For(names, parse_expr(fm.group(2), tok.line), line=tok.line)
            cur.append(node)
            stack.append(_Frame(node, cur))
            cur = node.body
        elif word == "elif":
            if top is None or not isinstance(top.node, If) or top.seen_else:
                raise TemplateSyntaxError("unexpected 'elif'", tok.line)
            body = []
            top.node.branches.append((parse_expr(rest, tok.line), body))
            cur = body
        elif word == "else":
            if rest:
                raise TemplateSyntaxError("'else' takes no arguments", tok.line)
            if top is None or top.seen_else:
                raise TemplateSyntaxError("unexpected 'else'", tok.line)
            top.seen_else = True
            top.node.else_body = []
            cur = top.node.else_body
        elif word in ("endif", "endfor"):
            want = If if word == "endif" else For
            if top is None or not isinstance(top.node, want):
                raise TemplateSyntaxError(f"unexpected {word!r}", tok.line)
            stack.pop()
            cur = top.outer
        else:
            raise TemplateSyntaxError(f"unknown tag {word!r}", tok.line)
    if stack:
        raise TemplateSyntaxError("unclosed block", stack[-1].node.line)
    return root
