"""Pattern text -> AST.

Supported today: literals, `.`, escapes, classes, concatenation and the greedy
quantifiers `*`, `+`, `?`.
"""
from .errors import PatternError
from .nodes import Alt, Any, Assertion, Backref, CharClass, Concat, Group, Literal, Repeat

DIGIT = (("0", "9"),)
WORD = (("a", "z"), ("A", "Z"), ("0", "9"), ("_", "_"))
SPACE = ((" ", " "), ("\t", "\r"))  # \t \n \v \f \r are contiguous

_ESCAPE_CLASSES = {
    "d": (False, DIGIT), "D": (True, DIGIT),
    "w": (False, WORD), "W": (True, WORD),
    "s": (False, SPACE), "S": (True, SPACE),
}
_ESCAPE_CHARS = {"n": "\n", "t": "\t", "r": "\r", "f": "\f", "v": "\v"}



class Parser:
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.ngroups = 0
        self.closed = set()

    def peek(self):
        return self.text[self.pos] if self.pos < len(self.text) else None

    def parse(self):
        node = self.alternation()
        if self.pos < len(self.text):
            raise PatternError("unbalanced parenthesis at %d" % self.pos)
        return node

    def alternation(self):
        options = [self.sequence()]
        while self.peek() == "|":
            self.pos += 1
            options.append(self.sequence())
        return options[0] if len(options) == 1 else Alt(options)

    def sequence(self):
        items = []
        while self.pos < len(self.text) and self.text[self.pos] not in "|)":
            items.append(self.piece())
        return Concat(items)

    def bound(self):
        """If a `{...}` quantifier starts at self.pos return (lo, hi, newpos), else None."""
        t = self.text
        j = self.pos + 1
        k = j
        while k < len(t) and t[k] in "0123456789":
            k += 1
        lo = t[j:k]
        hi = lo
        if k < len(t) and t[k] == ",":
            k += 1
            m = k
            while k < len(t) and t[k] in "0123456789":
                k += 1
            hi = t[m:k]
        elif not lo:
            return None
        if k >= len(t) or t[k] != "}":
            return None
        lo_v = int(lo) if lo else 0
        hi_v = int(hi) if hi else None
        return lo_v, hi_v, k + 1

    def quantifier(self):
        c = self.peek()
        if c == "*":
            self.pos += 1
            return 0, None
        if c == "+":
            self.pos += 1
            return 1, None
        if c == "?":
            self.pos += 1
            return 0, 1
        if c == "{":
            b = self.bound()
            if b is not None:
                lo, hi, self.pos = b
                if hi is not None and lo > hi:
                    raise PatternError("min repeat greater than max repeat")
                return lo, hi
        return None

    def piece(self):
        c = self.peek()
        if c in ("*", "+", "?") or (c == "{" and self.bound() is not None):
            raise PatternError("nothing to repeat at %d" % self.pos)
        atom = self.atom()
        q = self.quantifier()
        if q is None:
            return atom
        if isinstance(atom, Assertion):
            raise PatternError("nothing to repeat")
        greedy = True
        if self.peek() == "?":
            greedy = False
            self.pos += 1
        c = self.peek()
        if c in ("*", "+", "?") or (c == "{" and self.bound() is not None):
            raise PatternError("multiple repeat at %d" % self.pos)
        return Repeat(atom, q[0], q[1], greedy)

    def atom(self):
        c = self.text[self.pos]
        self.pos += 1
        if c == ".":
            return Any()
        if c == "^":
            return Assertion("bol")
        if c == "$":
            return Assertion("eol")
        if c == "[":
            return self.char_class()
        if c == "\\":
            return self.escape()
        if c == "(":
            return self.group()
        return Literal(c)

    def group(self):
        index = None
        if self.text.startswith("?", self.pos):
            if not self.text.startswith("?:", self.pos):
                raise PatternError("unsupported group syntax at %d" % self.pos)
            self.pos += 2
        else:
            self.ngroups += 1
            index = self.ngroups
        inner = self.alternation()
        if self.peek() != ")":
            raise PatternError("missing )")
        self.pos += 1
        if index is None:
            return inner
        self.closed.add(index)
        return Group(index, inner)

    def escape(self):
        if self.pos >= len(self.text):
            raise PatternError("trailing backslash")
        c = self.text[self.pos]
        self.pos += 1
        if c in _ESCAPE_CLASSES:
            neg, ranges = _ESCAPE_CLASSES[c]
            return CharClass(neg, ranges)
        if c in "123456789":
            n = int(c)
            if n not in self.closed:
                raise PatternError("invalid group reference %d" % n)
            return Backref(n)
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
    p = Parser(text)
    node = p.parse()
    return node, p.ngroups
