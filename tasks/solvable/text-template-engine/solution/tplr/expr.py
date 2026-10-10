"""Expressions: literals, variable paths, filters, comparisons and boolean logic."""

from __future__ import annotations

import re

from .errors import TemplateRenderError, TemplateSyntaxError
from .filters import FILTERS

_TOKEN = re.compile(
    r"""\s*(?:
        (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
      | (?P<num>-?\d+(?:\.\d+)?)
      | (?P<name>[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_0-9]+)*)
      | (?P<op>==|!=|<=|>=|<|>|\||\(|\)|,)
    )""",
    re.X,
)
_KEYWORDS = {"and", "or", "not", "in", "true", "false", "none"}
_CMP = {"==", "!=", "<", "<=", ">", ">="}
_ESCAPES = {"n": "\n", "t": "\t"}


def lookup(scopes: list[dict], path: str):
    """Resolve a dotted ``path`` in the scope stack; missing values are ``None``."""
    head, *rest = path.split(".")
    value = None
    for scope in reversed(scopes):
        if head in scope:
            value = scope[head]
            break
    for seg in rest:
        if isinstance(value, dict):
            value = value.get(seg)
        elif isinstance(value, (list, tuple)) and seg.isdigit() and int(seg) < len(value):
            value = value[int(seg)]
        elif value is not None and not seg.startswith("_") and hasattr(value, seg):
            value = getattr(value, seg)
        else:
            return None
    return value


def _compare(op: str, a, b):
    try:
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if op == "<":
            return a < b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        if op == ">=":
            return a >= b
        if op == "in":
            return False if b is None else a in b
        if op == "not in":
            return True if b is None else a not in b
    except TypeError:
        return False
    raise AssertionError(op)


class Expr:
    def __init__(self, node) -> None:
        self.node = node

    def eval(self, scopes: list[dict]):
        return self._eval(self.node, scopes)

    def _eval(self, node, scopes):
        kind = node[0]
        if kind == "lit":
            return node[1]
        if kind == "path":
            return lookup(scopes, node[1])
        if kind == "filter":
            _, inner, name, args = node
            value = self._eval(inner, scopes)
            try:
                return FILTERS[name][0](value, *args)
            except Exception as exc:
                raise TemplateRenderError(f"filter {name!r} failed: {exc}") from exc
        if kind == "not":
            return not self._eval(node[1], scopes)
        if kind == "and":
            return bool(self._eval(node[1], scopes) and self._eval(node[2], scopes))
        if kind == "or":
            return bool(self._eval(node[1], scopes) or self._eval(node[2], scopes))
        if kind == "cmp":
            return _compare(node[1], self._eval(node[2], scopes), self._eval(node[3], scopes))
        raise AssertionError(kind)


class _Parser:
    def __init__(self, source: str, line: int) -> None:
        self.line = line
        self.source = source
        self.toks: list[tuple[str, str]] = []
        pos = 0
        while pos < len(source) and source[pos:].strip():
            m = _TOKEN.match(source, pos)
            if not m:
                raise self.error(f"unexpected character in {source.strip()!r}")
            kind = m.lastgroup
            self.toks.append((kind, m.group(kind)))
            pos = m.end()
        self.i = 0

    def error(self, message: str) -> TemplateSyntaxError:
        return TemplateSyntaxError(message, self.line)

    def peek(self, offset: int = 0):
        j = self.i + offset
        return self.toks[j] if j < len(self.toks) else ("end", "")

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def is_kw(self, word: str, offset: int = 0) -> bool:
        return self.peek(offset) == ("name", word)

    def parse(self):
        if not self.toks:
            raise self.error("empty expression")
        node = self.or_expr()
        if self.peek()[0] != "end":
            raise self.error(f"unexpected {self.peek()[1]!r}")
        return node

    def or_expr(self):
        node = self.and_expr()
        while self.is_kw("or"):
            self.next()
            node = ("or", node, self.and_expr())
        return node

    def and_expr(self):
        node = self.not_expr()
        while self.is_kw("and"):
            self.next()
            node = ("and", node, self.not_expr())
        return node

    def not_expr(self):
        if self.is_kw("not"):
            self.next()
            return ("not", self.not_expr())
        return self.comparison()

    def _cmp_op(self):
        kind, text = self.peek()
        if kind == "op" and text in _CMP:
            self.next()
            return text
        if self.is_kw("in"):
            self.next()
            return "in"
        if self.is_kw("not") and self.is_kw("in", 1):
            self.next()
            self.next()
            return "not in"
        return None

    def comparison(self):
        left = self.filtered()
        op = self._cmp_op()
        if op is None:
            return left
        node = ("cmp", op, left, self.filtered())
        if self._cmp_op() is not None:
            raise self.error("comparisons cannot be chained")
        return node

    def filtered(self):
        node = self.atom()
        while self.peek() == ("op", "|"):
            self.next()
            kind, name = self.next()
            if kind != "name" or "." in name or name in _KEYWORDS:
                raise self.error("expected a filter name after '|'")
            args = []
            if self.peek() == ("op", "("):
                self.next()
                if self.peek() != ("op", ")"):
                    args.append(self.literal())
                    while self.peek() == ("op", ","):
                        self.next()
                        args.append(self.literal())
                if self.next() != ("op", ")"):
                    raise self.error("expected ')' after filter arguments")
            if name not in FILTERS:
                raise self.error(f"unknown filter {name!r}")
            _, lo, hi = FILTERS[name]
            if not lo <= len(args) <= hi:
                raise self.error(f"filter {name!r} got {len(args)} argument(s)")
            node = ("filter", node, name, tuple(args))
        return node

    def literal(self):
        kind, text = self.next()
        if kind == "str":
            return _unescape(text)
        if kind == "num":
            return float(text) if "." in text else int(text)
        if kind == "name" and text in ("true", "false", "none"):
            return {"true": True, "false": False, "none": None}[text]
        raise self.error("expected a literal filter argument")

    def atom(self):
        kind, text = self.peek()
        if kind in ("str", "num") or (kind == "name" and text in ("true", "false", "none")):
            return ("lit", self.literal())
        if kind == "name":
            if text in _KEYWORDS:
                raise self.error(f"unexpected keyword {text!r}")
            self.next()
            return ("path", text)
        if (kind, text) == ("op", "("):
            self.next()
            node = self.or_expr()
            if self.next() != ("op", ")"):
                raise self.error("expected ')'")
            return node
        raise self.error(f"unexpected {text or 'end of expression'!r}")


def _unescape(quoted: str) -> str:
    body = quoted[1:-1]
    out = []
    i = 0
    while i < len(body):
        if body[i] == "\\":
            i += 1
            out.append(_ESCAPES.get(body[i], body[i]))
        else:
            out.append(body[i])
        i += 1
    return "".join(out)


def parse_expr(source: str, line: int) -> Expr:
    return Expr(_Parser(source, line).parse())
