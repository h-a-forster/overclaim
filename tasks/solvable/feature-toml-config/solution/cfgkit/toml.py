"""A TOML 1.0 parser (without date/time values) for Python 3.8+: `loads(text)` -> dict."""
import re

from .errors import ParseError

_BARE = re.compile(r"[A-Za-z0-9_-]+")
_DEC = re.compile(r"[+-]?(?:0|[1-9](?:_?[0-9])*)")
_HEX = re.compile(r"0x[0-9A-Fa-f](?:_?[0-9A-Fa-f])*")
_OCT = re.compile(r"0o[0-7](?:_?[0-7])*")
_BIN = re.compile(r"0b[01](?:_?[01])*")
_FLOAT = re.compile(r"[+-]?(?:0|[1-9](?:_?[0-9])*)(?:\.[0-9](?:_?[0-9])*)?(?:[eE][+-]?[0-9](?:_?[0-9])*)?")
_SPECIAL = re.compile(r"[+-]?(?:inf|nan)")
_BAD_CTRL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")
_BAD_CTRL_ML = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_ESC = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}
_WS = " \t"
_DELIMS = " \t\n,]}#"


class _Err(Exception):
    pass


class _Flags:
    def __init__(self):
        self.explicit = set()
        self.frozen = set()
        self.pending = []

    def is_explicit(self, path):
        return path in self.explicit

    def is_frozen(self, path):
        return any(path[:i] in self.frozen for i in range(1, len(path) + 1))

    def finalize(self):
        self.explicit.update(self.pending)
        self.pending = []

    def unset_all(self, path):
        n = len(path)
        self.explicit = {p for p in self.explicit if p[:n] != path}
        self.frozen = {p for p in self.frozen if p[:n] != path}


def _nest(root, path):
    cont = root
    for k in path:
        if k not in cont:
            cont[k] = {}
        cont = cont[k]
        if isinstance(cont, list):
            cont = cont[-1]
        if not isinstance(cont, dict):
            raise KeyError(k)
    return cont


def _assign(root, flags, header, key, value):
    parent = header + key[:-1]
    stem = key[-1]
    for i in range(1, len(key)):
        cont = header + key[:i]
        if flags.is_explicit(cont):
            raise _Err("cannot redefine table %s" % ".".join(cont))
        flags.pending.append(cont)
    if flags.is_frozen(parent):
        raise _Err("cannot add to an inline table or array")
    try:
        nest = _nest(root, parent)
    except KeyError:
        raise _Err("cannot overwrite a value with a table") from None
    if stem in nest:
        raise _Err("duplicate key %r" % stem)
    if isinstance(value, (dict, list)):
        flags.frozen.add(header + key)
    nest[stem] = value


class _Parser:
    def __init__(self, text):
        self.s = text.replace("\r\n", "\n")
        self.i = 0
        self.line = 1
        self.line_pos = 0

    # ---- helpers
    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ""

    def skip_ws(self):
        s, i = self.s, self.i
        while i < len(s) and s[i] in _WS:
            i += 1
        self.i = i

    def comment(self):
        """At '#': skip to end of line (exclusive)."""
        j = self.s.find("\n", self.i)
        if j < 0:
            j = len(self.s)
        if _BAD_CTRL.search(self.s, self.i, j):
            raise _Err("control character in comment")
        self.i = j

    def skip_ws_nl_comments(self):
        while True:
            c = self.peek()
            if c and c in _WS + "\n":
                self.i += 1
            elif c == "#":
                self.comment()
            else:
                return

    # ---- document
    def parse(self):
        root = {}
        flags = _Flags()
        header = ()
        s = self.s
        while True:
            self.skip_ws()
            c = self.peek()
            if c == "":
                break
            if c == "\n":
                self.i += 1
                continue
            if c == "#":
                try:
                    self.comment()
                except _Err as e:
                    raise ParseError(str(e), self.line_at(self.i)) from None
                continue
            start_line = self.line_at(self.i)
            try:
                if c == "[":
                    header = self.table_header(root, flags)
                else:
                    key = self.key()
                    self.skip_ws()
                    if self.peek() != "=":
                        raise _Err("expected '='")
                    self.i += 1
                    self.skip_ws()
                    value = self.value()
                    _assign(root, flags, header, key, value)
                self.skip_ws()
                c = self.peek()
                if c == "#":
                    self.comment()
                elif c not in ("", "\n"):
                    raise _Err("unexpected content after statement")
            except _Err as e:
                raise ParseError(str(e), start_line) from None
        return root

    def line_at(self, pos):
        self.line += self.s.count("\n", self.line_pos, pos)
        self.line_pos = pos
        return self.line

    def table_header(self, root, flags):
        s = self.s
        is_list = s.startswith("[[", self.i)
        self.i += 2 if is_list else 1
        flags.finalize()
        self.skip_ws()
        key = self.key()
        self.skip_ws()
        close = "]]" if is_list else "]"
        if not s.startswith(close, self.i):
            raise _Err("expected %r" % close)
        self.i += len(close)
        if is_list:
            if flags.is_frozen(key):
                raise _Err("cannot extend an immutable array")
            flags.unset_all(key)
            flags.explicit.add(key)
            try:
                cont = _nest(root, key[:-1])
                last = key[-1]
                if last in cont:
                    if not isinstance(cont[last], list):
                        raise KeyError(last)
                    cont[last].append({})
                else:
                    cont[last] = [{}]
            except KeyError:
                raise _Err("cannot overwrite a value with an array of tables") from None
        else:
            if flags.is_explicit(key) or flags.is_frozen(key):
                raise _Err("table %s defined twice" % ".".join(key))
            flags.explicit.add(key)
            try:
                _nest(root, key)
            except KeyError:
                raise _Err("cannot overwrite a value with a table") from None
        return key

    # ---- keys
    def key(self):
        parts = []
        while True:
            self.skip_ws()
            c = self.peek()
            if c == '"':
                parts.append(self.basic_string())
            elif c == "'":
                parts.append(self.literal_string())
            else:
                m = _BARE.match(self.s, self.i)
                if not m:
                    raise _Err("expected a key")
                parts.append(m.group())
                self.i = m.end()
            self.skip_ws()
            if self.peek() == ".":
                self.i += 1
                continue
            return tuple(parts)

    # ---- values
    def value(self):
        s = self.s
        c = self.peek()
        if c == '"':
            return self.ml_basic() if s.startswith('"""', self.i) else self.basic_string()
        if c == "'":
            return self.ml_literal() if s.startswith("'''", self.i) else self.literal_string()
        if c == "[":
            return self.array()
        if c == "{":
            return self.inline_table()
        j = self.i
        while j < len(s) and s[j] not in _DELIMS:
            j += 1
        tok = s[self.i:j]
        if not tok:
            raise _Err("expected a value")
        self.i = j
        if tok == "true":
            return True
        if tok == "false":
            return False
        return self.number(tok)

    def number(self, tok):
        if _DEC.fullmatch(tok):
            return int(tok.replace("_", ""))
        for rx, base in ((_HEX, 16), (_OCT, 8), (_BIN, 2)):
            if rx.fullmatch(tok):
                return int(tok.replace("_", ""), base)
        if _FLOAT.fullmatch(tok) or _SPECIAL.fullmatch(tok):
            return float(tok.replace("_", ""))
        raise _Err("invalid value %r" % tok)

    def basic_string(self):
        s = self.s
        i = self.i + 1
        out = []
        while True:
            if i >= len(s):
                raise _Err("unterminated string")
            c = s[i]
            if c == '"':
                self.i = i + 1
                return "".join(out)
            if c == "\\":
                ch, i = self.escape(i)
                out.append(ch)
                continue
            if _BAD_CTRL.match(c):
                raise _Err("control character in string")
            out.append(c)
            i += 1

    def escape(self, i):
        """s[i] is a backslash; return (char, next index)."""
        s = self.s
        e = s[i + 1:i + 2]
        if e in _ESC:
            return _ESC[e], i + 2
        if e in ("u", "U"):
            n = 4 if e == "u" else 8
            digits = s[i + 2:i + 2 + n]
            if len(digits) != n or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                raise _Err("bad unicode escape")
            cp = int(digits, 16)
            if cp > 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
                raise _Err("not a unicode scalar value")
            return chr(cp), i + 2 + n
        raise _Err("invalid escape sequence")

    def literal_string(self):
        s = self.s
        j = s.find("'", self.i + 1)
        if j < 0:
            raise _Err("unterminated string")
        body = s[self.i + 1:j]
        if "\n" in body or _BAD_CTRL.search(body):
            raise _Err("control character in string")
        self.i = j + 1
        return body

    def ml_basic(self):
        s = self.s
        i = self.i + 3
        if s.startswith("\n", i):
            i += 1
        out = []
        while True:
            if i >= len(s):
                raise _Err("unterminated string")
            c = s[i]
            if c == '"':
                j = i
                while j < len(s) and s[j] == '"':
                    j += 1
                n = j - i
                if n >= 3:
                    if n > 5:
                        raise _Err("too many quotes")
                    out.append('"' * (n - 3))
                    self.i = j
                    return "".join(out)
                out.append('"' * n)
                i = j
                continue
            if c == "\\":
                k = i + 1
                while k < len(s) and s[k] in _WS:
                    k += 1
                if k < len(s) and s[k] == "\n":
                    while k < len(s) and s[k] in _WS + "\n":
                        k += 1
                    i = k
                    continue
                ch, i = self.escape(i)
                out.append(ch)
                continue
            if _BAD_CTRL_ML.match(c):
                raise _Err("control character in string")
            out.append(c)
            i += 1

    def ml_literal(self):
        s = self.s
        i = self.i + 3
        if s.startswith("\n", i):
            i += 1
        j = s.find("'''", i)
        if j < 0:
            raise _Err("unterminated string")
        k = j
        while k < len(s) and s[k] == "'":
            k += 1
        n = k - j
        if n > 5:
            raise _Err("too many quotes")
        body = s[i:j] + "'" * (n - 3)
        if _BAD_CTRL_ML.search(body):
            raise _Err("control character in string")
        self.i = k
        return body

    def array(self):
        self.i += 1
        items = []
        while True:
            self.skip_ws_nl_comments()
            if self.peek() == "]":
                self.i += 1
                return items
            items.append(self.value())
            self.skip_ws_nl_comments()
            c = self.peek()
            if c == ",":
                self.i += 1
            elif c == "]":
                self.i += 1
                return items
            else:
                raise _Err("expected ',' or ']'")

    def inline_table(self):
        self.i += 1
        out = {}
        flags = _Flags()
        self.skip_ws()
        if self.peek() == "}":
            self.i += 1
            return out
        while True:
            key = self.key()
            self.skip_ws()
            if self.peek() != "=":
                raise _Err("expected '='")
            self.i += 1
            self.skip_ws()
            value = self.value()
            _assign(out, flags, (), key, value)
            self.skip_ws()
            c = self.peek()
            if c == ",":
                self.i += 1
                self.skip_ws()
            elif c == "}":
                self.i += 1
                return out
            else:
                raise _Err("expected ',' or '}'")


def loads(text):
    """Parse TOML text into a dict. Raises ParseError (with `.line`) on any problem."""
    if not isinstance(text, str):
        raise ParseError("text must be a str")
    return _Parser(text).parse()
