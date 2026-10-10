"""Parser for: SELECT (* | col, ...) FROM table [WHERE col op literal [AND ...]]
[ORDER BY col [ASC|DESC]] [LIMIT n]. Returns a plain dict describing the query."""
from .errors import SqlError
from .lexer import tokenize

_OPS = {"=", "<>", "!=", "<", "<=", ">", ">="}


class Parser:
    def __init__(self, sql):
        self.tokens = tokenize(sql)
        self.i = 0

    def peek(self):
        return self.tokens[self.i]

    def next(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def kw(self, word):
        t = self.peek()
        return t[0] == "ident" and t[1].upper() == word

    def accept(self, word):
        if self.kw(word):
            self.i += 1
            return True
        return False

    def expect(self, word):
        if not self.accept(word):
            raise SqlError("expected %s" % word)

    def ident(self):
        t = self.next()
        if t[0] != "ident":
            raise SqlError("expected an identifier")
        return t[1].lower()

    def literal(self):
        t = self.next()
        if t[0] == "num":
            return float(t[1]) if "." in t[1] else int(t[1])
        if t[0] == "str":
            return t[1][1:-1].replace("''", "'")
        if t[0] == "ident" and t[1].upper() == "NULL":
            return None
        raise SqlError("expected a literal")

    def parse(self):
        self.expect("SELECT")
        if self.peek()[:2] == ("op", "*"):
            self.next()
            columns = None
        else:
            columns = [self.ident()]
            while self.peek()[:2] == ("op", ","):
                self.next()
                columns.append(self.ident())
        self.expect("FROM")
        table = self.ident()
        where = []
        if self.accept("WHERE"):
            while True:
                col = self.ident()
                op = self.next()
                if op[0] != "op" or op[1] not in _OPS:
                    raise SqlError("expected a comparison operator")
                where.append((col, "<>" if op[1] == "!=" else op[1], self.literal()))
                if not self.accept("AND"):
                    break
        order = None
        if self.accept("ORDER"):
            self.expect("BY")
            col = self.ident()
            desc = self.accept("DESC")
            if not desc:
                self.accept("ASC")
            order = (col, desc)
        limit = None
        if self.accept("LIMIT"):
            limit = self.literal()
            if not isinstance(limit, int):
                raise SqlError("LIMIT needs an integer")
        if self.peek()[:2] == ("op", ";"):
            self.next()
        if self.peek()[0] != "eof":
            raise SqlError("unexpected %r" % self.peek()[1])
        return {"columns": columns, "table": table, "where": where, "order": order, "limit": limit}


def parse(sql):
    return Parser(sql).parse()
