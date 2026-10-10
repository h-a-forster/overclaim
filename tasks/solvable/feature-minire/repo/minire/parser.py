"""Pattern text -> AST.

Supported today: literals, `.`, escapes, classes, concatenation and the greedy
quantifiers `*`, `+`, `?`.
"""
from .errors import PatternError
from .nodes import Any, CharClass, Concat, Literal, Repeat

DIGIT = (("0", "9"),)
WORD = (("a", "z"), ("A", "Z"), ("0", "9"), ("_", "_"))
SPACE = ((" ", " "), ("\t", "\r"))  # \t \n \v \f \r are contiguous

_ESCAPE_CLASSES = {
    "d": (False, DIGIT), "D": (True, DIGIT),
    "w": (False, WORD), "W": (True, WORD),
    "s": (False, SPACE), "S": (True, SPACE),
}
_ESCAPE_CHARS = {"n": "\n", "t": "\t", "r": "\r", "f": "\f", "v": "\v"}
SPECIAL = set("\\.[]*+?")


class Parser:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def peek(self):
        return self.text[self.pos] if self.pos < len(self.text) else None

    def parse(self):
        items = []
        while self.pos < len(self.text):
            items.append(self.piece())
        return Concat(items)

    def piece(self):
        c = self.peek()
        if c in ("*", "+", "?"):
            raise PatternError("nothing to repeat at %d" % self.pos)
        atom = self.atom()
        c = self.peek()
        if c in ("*", "+", "?"):
            self.pos += 1
            lo, hi = {"*": (0, None), "+": (1, None), "?": (0, 1)}[c]
            atom = Repeat(atom, lo, hi)
            if self.peek() in ("*", "+", "?"):
                raise PatternError("multiple repeat at %d" % self.pos)
        return atom

    def atom(self):
        c = self.text[self.pos]
        self.pos += 1
        if c == ".":
            return Any()
        if c == "[":
            return self.char_class()
        if c == "\\":
            return self.escape()
        return Literal(c)

    def escape(self):
        if self.pos >= len(self.text):
            raise PatternError("trailing backslash")
        c = self.text[self.pos]
        self.pos += 1
        if c in _ESCAPE_CLASSES:
            neg, ranges = _ESCAPE_CLASSES[c]
            return CharClass(neg, ranges)
        return Literal(_ESCAPE_CHARS.get(c, c))

    def char_class(self):
        negated = False
        if self.peek() == "^":
            negated = True
            self.pos += 1
        ranges = []
        first = True
        while True:
            c = self.peek()
            if c is None:
                raise PatternError("unterminated character class")
            self.pos += 1
            if c == "]" and not first:
                break
            first = False
            if c == "\\":
                if self.pos >= len(self.text):
                    raise PatternError("trailing backslash")
                e = self.text[self.pos]
                self.pos += 1
                if e in _ESCAPE_CLASSES:
                    neg, rs = _ESCAPE_CLASSES[e]
                    if neg:
                        raise PatternError("negated escape in class not supported")
                    ranges.extend(rs)
                    continue
                c = _ESCAPE_CHARS.get(e, e)
            if self.peek() == "-" and self.pos + 1 < len(self.text) and self.text[self.pos + 1] != "]":
                self.pos += 1
                hi = self.text[self.pos]
                self.pos += 1
                if hi == "\\":
                    hi = self.text[self.pos]
                    self.pos += 1
                    hi = _ESCAPE_CHARS.get(hi, hi)
                if hi < c:
                    raise PatternError("bad character range")
                ranges.append((c, hi))
            else:
                ranges.append((c, c))
        return CharClass(negated, ranges)


def parse(text):
    return Parser(text).parse()
