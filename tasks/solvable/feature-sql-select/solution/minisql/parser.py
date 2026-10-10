"""SELECT parser producing tuple-based ASTs.

Expressions: ("lit", v) ("col", table|None, name) ("neg", e) ("pos", e) ("not", e)
("bin", op, l, r) for + - * / % || < <= > >= = <> ("and", l, r) ("or", l, r)
("is", l, r, negated) ("isnull", e, negated) ("in", e, [items], negated)
("between", e, lo, hi, negated) ("like", e, pattern, negated)
("case", operand|None, [(when, then)], else|None)
("func", name, [args], distinct, star)
"""
from .errors import SqlError
from .lexer import tokenize

RESERVED = {
    "SELECT", "FROM", "WHERE", "GROUP", "BY", "HAVING", "ORDER", "LIMIT", "OFFSET", "JOIN", "INNER", "LEFT",
    "OUTER", "CROSS", "ON", "AS", "AND", "OR", "NOT", "IN", "IS", "LIKE", "BETWEEN", "CASE", "WHEN", "THEN",
    "ELSE", "END", "DISTINCT", "ALL", "NULL", "ASC", "DESC", "UNION", "NATURAL", "USING",
}
AGGREGATES = {"count", "sum", "avg", "min", "max", "total"}


class Parser:
    def __init__(self, sql):
        self.sql = sql
        self.tokens = tokenize(sql)
        self.i = 0

    # ---- token helpers
    def peek(self, k=0):
        return self.tokens[min(self.i + k, len(self.tokens) - 1)]

    def next(self):
        t = self.tokens[self.i]
        if t[0] != "eof":
            self.i += 1
        return t

    def is_op(self, text, k=0):
        t = self.peek(k)
        return t[0] == "op" and t[1] == text

    def is_kw(self, word, k=0):
        t = self.peek(k)
        return t[0] == "ident" and t[1].upper() == word

    def accept_op(self, text):
        if self.is_op(text):
            self.i += 1
            return True
        return False

    def accept_kw(self, word):
        if self.is_kw(word):
            self.i += 1
            return True
        return False

    def expect_kw(self, word):
        if not self.accept_kw(word):
            raise SqlError("expected %s near %r" % (word, self.peek()[1]))

    def expect_op(self, text):
        if not self.accept_op(text):
            raise SqlError("expected %r near %r" % (text, self.peek()[1]))

    def ident(self):
        t = self.peek()
        if t[0] != "ident" or t[1].upper() in RESERVED:
            raise SqlError("expected an identifier near %r" % t[1])
        self.i += 1
        return t[1].lower()

    # ---- statement
    def parse(self):
        q = self.select()
        self.accept_op(";")
        if self.peek()[0] != "eof":
            raise SqlError("unexpected %r" % self.peek()[1])
        return q

    def select(self):
        self.expect_kw("SELECT")
        distinct = False
        if self.accept_kw("DISTINCT"):
            distinct = True
        else:
            self.accept_kw("ALL")
        items = [self.select_item()]
        while self.accept_op(","):
            items.append(self.select_item())
        sources = None
        if self.accept_kw("FROM"):
            sources = self.from_clause()
        where = self.expr() if self.accept_kw("WHERE") else None
        group = []
        if self.accept_kw("GROUP"):
            self.expect_kw("BY")
            group.append(self.expr())
            while self.accept_op(","):
                group.append(self.expr())
        having = self.expr() if self.accept_kw("HAVING") else None
        order = []
        if self.accept_kw("ORDER"):
            self.expect_kw("BY")
            while True:
                e = self.expr()
                desc = False
                if self.accept_kw("DESC"):
                    desc = True
                else:
                    self.accept_kw("ASC")
                order.append((e, desc))
                if not self.accept_op(","):
                    break
        limit = offset = None
        if self.accept_kw("LIMIT"):
            limit = self.expr()
            if self.accept_kw("OFFSET"):
                offset = self.expr()
        return {"distinct": distinct, "items": items, "from": sources, "where": where, "group": group,
                "having": having, "order": order, "limit": limit, "offset": offset}

    def select_item(self):
        if self.is_op("*"):
            self.i += 1
            return ("star", None)
        if self.peek()[0] == "ident" and self.is_op(".", 1) and self.is_op("*", 2):
            name = self.ident()
            self.i += 2
            return ("star", name)
        start = self.peek()[2]
        e = self.expr()
        end = self.tokens[self.i - 1][3]
        text = self.sql[start:end]
        alias = None
        if self.accept_kw("AS"):
            alias = self.ident()
        elif self.peek()[0] == "ident" and self.peek()[1].upper() not in RESERVED:
            alias = self.ident()
        return ("expr", e, alias, text)

    def table_ref(self):
        name = self.ident()
        alias = name
        if self.accept_kw("AS"):
            alias = self.ident()
        elif self.peek()[0] == "ident" and self.peek()[1].upper() not in RESERVED:
            alias = self.ident()
        return (name, alias)

    def from_clause(self):
        sources = [("first", self.table_ref(), None)]
        while True:
            if self.accept_op(","):
                sources.append(("cross", self.table_ref(), None))
                continue
            kind = None
            if self.accept_kw("LEFT"):
                self.accept_kw("OUTER")
                kind = "left"
            elif self.accept_kw("INNER"):
                kind = "inner"
            elif self.accept_kw("CROSS"):
                kind = "cross"
            if kind is None and not self.is_kw("JOIN"):
                return sources
            self.expect_kw("JOIN")
            kind = kind or "inner"
            ref = self.table_ref()
            on = self.expr() if self.accept_kw("ON") else None
            if kind == "left" and on is None:
                raise SqlError("LEFT JOIN needs ON")
            sources.append((kind, ref, on))

    # ---- expressions (lowest to highest precedence)
    def expr(self):
        left = self.and_expr()
        while self.accept_kw("OR"):
            left = ("or", left, self.and_expr())
        return left

    def and_expr(self):
        left = self.not_expr()
        while self.accept_kw("AND"):
            left = ("and", left, self.not_expr())
        return left

    def not_expr(self):
        if self.accept_kw("NOT"):
            return ("not", self.not_expr())
        return self.equality()

    def equality(self):
        left = self.relational()
        while True:
            t = self.peek()
            if t[0] == "op" and t[1] in ("=", "<>", "!="):
                self.i += 1
                left = ("bin", "<>" if t[1] == "!=" else t[1], left, self.relational())
            elif self.is_kw("IS"):
                self.i += 1
                neg = self.accept_kw("NOT")
                if self.accept_kw("NULL"):
                    left = ("isnull", left, neg)
                else:
                    left = ("is", left, self.relational(), neg)
            else:
                neg = False
                save = self.i
                if self.is_kw("NOT") and (self.is_kw("IN", 1) or self.is_kw("LIKE", 1) or self.is_kw("BETWEEN", 1)):
                    self.i += 1
                    neg = True
                if self.accept_kw("IN"):
                    self.expect_op("(")
                    items = []
                    if not self.is_op(")"):
                        items.append(self.expr())
                        while self.accept_op(","):
                            items.append(self.expr())
                    self.expect_op(")")
                    left = ("in", left, items, neg)
                elif self.accept_kw("LIKE"):
                    left = ("like", left, self.relational(), neg)
                elif self.accept_kw("BETWEEN"):
                    lo = self.relational()
                    self.expect_kw("AND")
                    hi = self.relational()
                    left = ("between", left, lo, hi, neg)
                else:
                    self.i = save
                    return left

    def relational(self):
        left = self.additive()
        while self.peek()[0] == "op" and self.peek()[1] in ("<", "<=", ">", ">="):
            op = self.next()[1]
            left = ("bin", op, left, self.additive())
        return left

    def additive(self):
        left = self.multiplicative()
        while self.peek()[0] == "op" and self.peek()[1] in ("+", "-"):
            op = self.next()[1]
            left = ("bin", op, left, self.multiplicative())
        return left

    def multiplicative(self):
        left = self.concat()
        while self.peek()[0] == "op" and self.peek()[1] in ("*", "/", "%"):
            op = self.next()[1]
            left = ("bin", op, left, self.concat())
        return left

    def concat(self):
        left = self.unary()
        while self.is_op("||"):
            self.i += 1
            left = ("bin", "||", left, self.unary())
        return left

    def unary(self):
        if self.accept_op("-"):
            return ("neg", self.unary())
        if self.accept_op("+"):
            return ("pos", self.unary())
        return self.primary()

    def primary(self):
        t = self.next()
        kind, text = t[0], t[1]
        if kind == "num":
            return ("lit", float(text) if "." in text else int(text))
        if kind == "str":
            return ("lit", text[1:-1].replace("''", "'"))
        if kind == "op" and text == "(":
            e = self.expr()
            self.expect_op(")")
            return e
        if kind != "ident":
            raise SqlError("unexpected %r" % (text or "end of input"))
        up = text.upper()
        if up == "NULL":
            return ("lit", None)
        if up == "CASE":
            return self.case()
        if up in RESERVED:
            raise SqlError("unexpected keyword %s" % up)
        if self.is_op("("):
            return self.call(text.lower())
        if self.is_op(".") and self.peek(1)[0] == "ident":
            self.i += 1
            col = self.ident()
            return ("col", text.lower(), col)
        return ("col", None, text.lower())

    def call(self, name):
        self.expect_op("(")
        if self.accept_op("*"):
            self.expect_op(")")
            if name != "count":
                raise SqlError("%s(*) is not allowed" % name)
            return ("func", name, [], False, True)
        distinct = self.accept_kw("DISTINCT")
        args = []
        if not self.is_op(")"):
            args.append(self.expr())
            while self.accept_op(","):
                args.append(self.expr())
        self.expect_op(")")
        return ("func", name, args, distinct, False)

    def case(self):
        operand = None
        if not self.is_kw("WHEN"):
            operand = self.expr()
        whens = []
        while self.accept_kw("WHEN"):
            cond = self.expr()
            self.expect_kw("THEN")
            whens.append((cond, self.expr()))
        if not whens:
            raise SqlError("CASE needs WHEN")
        other = self.expr() if self.accept_kw("ELSE") else None
        self.expect_kw("END")
        return ("case", operand, whens, other)


def parse(sql):
    return Parser(sql).parse()
