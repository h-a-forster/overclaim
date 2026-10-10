"""Tokenizer. A token is (kind, text, start, end); kind is one of
"num", "str", "ident", "op", "eof". Keywords are plain identifiers (compare upper-cased)."""
import re

from .errors import SqlError

_TOKEN = re.compile(
    r"""\s*(?:
        (?P<num>\d+\.\d*|\.\d+|\d+)
      | (?P<str>'(?:[^']|'')*')
      | (?P<ident>[A-Za-z_][A-Za-z_0-9]*)
      | (?P<op><=|>=|<>|!=|\|\||[-+*/%=<>(),.;])
    )""",
    re.X,
)


def tokenize(sql):
    tokens = []
    pos = 0
    while True:
        m = _TOKEN.match(sql, pos)
        if m is None:
            if sql[pos:].strip() == "":
                tokens.append(("eof", "", len(sql), len(sql)))
                return tokens
            raise SqlError("unexpected character %r" % sql[pos:].strip()[0])
        kind = m.lastgroup
        tokens.append((kind, m.group(kind), m.start(kind), m.end(kind)))
        pos = m.end()
