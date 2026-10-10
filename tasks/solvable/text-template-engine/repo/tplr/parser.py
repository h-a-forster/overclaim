"""Build a node tree from tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import TemplateSyntaxError
from .expr import Expr, parse_expr
from .lexer import Token, tokenize


@dataclass
class Text:
    text: str


@dataclass
class Output:
    expr: Expr


@dataclass
class If:
    cond: Expr
    body: list = field(default_factory=list)
    else_body: list = field(default_factory=list)
    line: int = 0


@dataclass
class For:
    name: str
    iterable: Expr
    body: list = field(default_factory=list)
    line: int = 0


_FOR = re.compile(r"^for\s+([A-Za-z_]\w*)\s+in\s+(.+)$", re.S)


def parse(source: str) -> list:
    root: list = []
    stack: list = []  # open If/For nodes
    target = root  # list currently being filled
    in_else = False
    for tok in tokenize(source):
        if tok.kind == "text":
            target.append(Text(tok.text))
        elif tok.kind == "var":
            target.append(Output(parse_expr(tok.text, tok.line)))
        else:
            word = tok.text.split(None, 1)[0] if tok.text else ""
            if word == "if":
                node = If(parse_expr(tok.text[2:].strip(), tok.line), line=tok.line)
                target.append(node)
                stack.append(node)
                target, in_else = node.body, False
            elif word == "else":
                if not stack or not isinstance(stack[-1], If) or in_else:
                    raise TemplateSyntaxError("unexpected 'else'", tok.line)
                target, in_else = stack[-1].else_body, True
            elif word == "endif":
                if not stack or not isinstance(stack[-1], If):
                    raise TemplateSyntaxError("unexpected 'endif'", tok.line)
                stack.pop()
                target = _container(root, stack)
                in_else = False
            elif word == "for":
                m = _FOR.match(tok.text)
                if not m:
                    raise TemplateSyntaxError("malformed 'for' tag", tok.line)
                node = For(m.group(1), parse_expr(m.group(2), tok.line), line=tok.line)
                target.append(node)
                stack.append(node)
                target = node.body
            elif word == "endfor":
                if not stack or not isinstance(stack[-1], For):
                    raise TemplateSyntaxError("unexpected 'endfor'", tok.line)
                stack.pop()
                target = _container(root, stack)
                in_else = False
            else:
                raise TemplateSyntaxError(f"unknown tag {word!r}", tok.line)
    if stack:
        raise TemplateSyntaxError(f"unclosed block", stack[-1].line)
    return root


def _container(root: list, stack: list) -> list:
    if not stack:
        return root
    top = stack[-1]
    return top.body
