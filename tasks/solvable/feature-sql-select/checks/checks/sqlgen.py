"""Random SQL generator (typed, so SQLite and a faithful engine must agree)."""
import random

PREC = {"atom": 10, "unary": 9, "cat": 8, "mul": 7, "add": 6, "rel": 5, "eq": 4, "not": 3, "and": 2, "or": 1}
TEXTS = ["a", "B", "abc", "ABC", "b_c", "", "xyz", "Abc", "ca"]
PATTERNS = ["a%", "%b%", "_b%", "%c", "abc", "A_C", "%", "_", "b_c", "%a%", "x%z"]


def wrap(item, min_prec):
    text, prec = item
    return "(%s)" % text if prec < min_prec else text


class Gen:
    def __init__(self, rng, aliases, cols):
        """aliases: list of table aliases; cols: dict alias -> list of (name, type) with
        type in {"int", "real", "text"}."""
        self.rng = rng
        self.aliases = aliases
        self.cols = cols
        self.qualify = True
        self.int_cols = [(a, c) for a in aliases for c, t in cols[a] if t == "int"]
        self.num_cols = [(a, c) for a in aliases for c, t in cols[a] if t in ("int", "real")]
        self.text_cols = [(a, c) for a in aliases for c, t in cols[a] if t == "text"]

    def colref(self, ac):
        a, c = ac
        return (("%s.%s" % (a, c)) if self.qualify else c, PREC["atom"])

    # ---- numbers
    def num(self, d, ints=False, agg=None):
        rng = self.rng
        leaf = d <= 0 or rng.random() < 0.22
        if agg is not None:
            return self.agg_num(d, ints, agg, leaf)
        if leaf:
            k = rng.random()
            cols = self.int_cols if ints else self.num_cols
            if cols and k < 0.55:
                return self.colref(rng.choice(cols))
            if not ints and k < 0.75:
                return (rng.choice(["0.5", "1.5", "2.0", "0.25", "3.75", "10.5"]), PREC["atom"])
            v = rng.randrange(-3, 10)
            return (str(v), PREC["unary"] if v < 0 else PREC["atom"])
        return self.num_op(d, ints, agg)

    def num_op(self, d, ints, agg):
        rng = self.rng
        r = rng.random()
        sub = lambda **kw: self.num(d - 1, ints=kw.get("ints", ints), agg=agg)
        if r < 0.40:
            op = rng.choice(["+", "-", "*", "/", "%", "+", "-", "*"])
            prec = {"+": "add", "-": "add", "*": "mul", "/": "mul", "%": "mul"}[op]
            if op == "%":
                l, rr = self.num(d - 1, True, agg), self.num(d - 1, True, agg)
            else:
                l, rr = sub(), sub()
            return ("%s %s %s" % (wrap(l, PREC[prec]), op, wrap(rr, PREC[prec] + 1)), PREC[prec])
        if r < 0.47:
            return ("-%s" % wrap(sub(), PREC["atom"]), PREC["unary"])
        if r < 0.55:
            return ("abs(%s)" % sub()[0], PREC["atom"])
        if r < 0.62:
            return ("length(%s)" % self.text(d - 1, agg)[0], PREC["atom"])
        if r < 0.70:
            n = rng.choice([2, 2, 3])
            return ("coalesce(%s)" % ", ".join(sub()[0] for _ in range(n)), PREC["atom"])
        if r < 0.74:
            return ("nullif(%s, %s)" % (sub()[0], sub()[0]), PREC["atom"])
        if r < 0.88:
            whens = " ".join("WHEN %s THEN %s" % (self.boolean(d - 1, agg)[0], sub()[0]) for _ in range(rng.choice([1, 1, 2])))
            other = " ELSE %s" % sub()[0] if rng.random() < 0.7 else ""
            return ("CASE %s%s END" % (whens, other), PREC["atom"])
        if r < 0.93:
            whens = " ".join("WHEN %s THEN %s" % (sub()[0], sub()[0]) for _ in range(rng.choice([1, 2])))
            other = " ELSE %s" % sub()[0] if rng.random() < 0.6 else ""
            return ("CASE %s %s%s END" % (sub()[0], whens, other), PREC["atom"])
        return self.boolean(d - 1, agg)

    # ---- aggregates context: agg = {"keys": [(text, kind)], "cols": gen over columns}
    def agg_num(self, d, ints, agg, leaf):
        rng = self.rng
        if leaf or d <= 0:
            k = rng.random()
            keys = [t for t, kind in agg["keys"] if kind == "int" or (kind == "num" and not ints)]
            if keys and k < 0.35:
                return (rng.choice(keys), PREC["atom"])   # keys are stored parenthesised
            if k < 0.80:
                return self.agg_call(ints, agg)
            v = rng.randrange(-2, 6)
            return (str(v), PREC["unary"] if v < 0 else PREC["atom"])
        return self.num_op(d, ints, agg)

    def agg_call(self, ints, agg):
        rng = self.rng
        inner = Gen(rng, self.aliases, self.cols)
        inner.qualify = self.qualify
        k = rng.random()
        if k < 0.2:
            return ("count(*)", PREC["atom"])
        if k < 0.35:
            e = inner.num(2, ints=False)[0] if rng.random() < 0.5 else inner.text(1, None)[0]
            return ("count(%s)" % e, PREC["atom"])
        if k < 0.42:
            e = inner.colref(rng.choice(inner.num_cols + inner.text_cols))[0]
            return ("count(DISTINCT %s)" % e, PREC["atom"])
        if k < 0.67:
            e = inner.num(2, ints=ints)[0]
            return ("%s(%s%s)" % ("sum", "DISTINCT " if rng.random() < 0.2 else "", e), PREC["atom"])
        if k < 0.77 and not ints:
            e = inner.num(2)[0]
            return ("avg(%s%s)" % ("DISTINCT " if rng.random() < 0.15 else "", e), PREC["atom"])
        e = inner.num(2, ints=ints)[0]
        return ("%s(%s)" % (rng.choice(["min", "max"]), e), PREC["atom"])

    # ---- text
    def text(self, d, agg=None):
        rng = self.rng
        if agg is not None:
            k = rng.random()
            keys = [t for t, kind in agg["keys"] if kind == "text"]
            if keys and k < 0.4:
                return (rng.choice(keys), PREC["atom"])
            if k < 0.65:
                inner = Gen(rng, self.aliases, self.cols)
                inner.qualify = self.qualify
                if inner.text_cols:
                    return ("%s(%s)" % (rng.choice(["min", "max"]), inner.colref(rng.choice(inner.text_cols))[0]), PREC["atom"])
            if d <= 0 or k < 0.8:
                return ("'%s'" % rng.choice(TEXTS), PREC["atom"])
            return self.text_op(d, agg)
        if d <= 0 or rng.random() < 0.3:
            if self.text_cols and rng.random() < 0.6:
                return self.colref(rng.choice(self.text_cols))
            return ("'%s'" % rng.choice(TEXTS), PREC["atom"])
        return self.text_op(d, agg)

    def text_op(self, d, agg):
        rng = self.rng
        r = rng.random()
        sub = lambda: self.text(d - 1, agg)
        if r < 0.25:
            return ("%s(%s)" % (rng.choice(["upper", "lower"]), sub()[0]), PREC["atom"])
        if r < 0.45:
            start = rng.randrange(1, 4)
            if rng.random() < 0.5:
                return ("substr(%s, %d, %d)" % (sub()[0], start, rng.randrange(0, 4)), PREC["atom"])
            return ("substr(%s, %d)" % (sub()[0], start), PREC["atom"])
        if r < 0.75:
            return ("%s || %s" % (wrap(sub(), PREC["cat"]), wrap(sub(), PREC["cat"] + 1)), PREC["cat"])
        if r < 0.85:
            return ("coalesce(%s, %s)" % (sub()[0], sub()[0]), PREC["atom"])
        whens = " ".join("WHEN %s THEN %s" % (self.boolean(d - 1, agg)[0], sub()[0]) for _ in range(rng.choice([1, 2])))
        other = " ELSE %s" % sub()[0] if rng.random() < 0.7 else ""
        return ("CASE %s%s END" % (whens, other), PREC["atom"])

    # ---- booleans
    def boolean(self, d, agg=None):
        rng = self.rng
        if d <= 0:
            return self.compare(0, agg)
        r = rng.random()
        if r < 0.30:
            return self.compare(d - 1, agg)
        if r < 0.42:
            e = self.any_expr(d - 1, agg)
            return ("%s IS %sNULL" % (wrap(e, PREC["rel"]), "NOT " if rng.random() < 0.5 else ""), PREC["eq"])
        if r < 0.50:
            e1, e2 = self.pair(d - 1, agg)
            return ("%s IS %s%s" % (wrap(e1, PREC["eq"]), "NOT " if rng.random() < 0.4 else "", wrap(e2, PREC["rel"])), PREC["eq"])
        if r < 0.62:
            kind = rng.choice(["num", "text"])
            e = self.num(d - 1, agg=agg) if kind == "num" else self.text(d - 1, agg)
            n = rng.choice([0, 1, 2, 3, 3]) if agg is None else rng.choice([1, 2, 3])  # SQLite folds `x IN ()` away
            items = []
            for _ in range(n):
                if rng.random() < 0.15:
                    items.append("NULL")
                else:
                    items.append((self.num(d - 1, agg=agg) if kind == "num" else self.text(d - 1, agg))[0] if rng.random() < 0.4
                                 else (str(rng.randrange(-2, 8)) if kind == "num" else "'%s'" % rng.choice(TEXTS)))
            return ("%s %sIN (%s)" % (wrap(e, PREC["eq"]), "NOT " if rng.random() < 0.4 else "", ", ".join(items)), PREC["eq"])
        if r < 0.70:
            e, lo, hi = (self.num(d - 1, agg=agg) for _ in range(3))
            return ("%s %sBETWEEN %s AND %s" % (wrap(e, PREC["eq"]), "NOT " if rng.random() < 0.3 else "",
                                                 wrap(lo, PREC["rel"]), wrap(hi, PREC["rel"])), PREC["eq"])
        if r < 0.78:
            e = self.text(d - 1, agg)
            return ("%s %sLIKE '%s'" % (wrap(e, PREC["eq"]), "NOT " if rng.random() < 0.3 else "", rng.choice(PATTERNS)), PREC["eq"])
        if r < 0.86:
            return ("NOT %s" % wrap(self.boolean(d - 1, agg), PREC["not"]), PREC["not"])
        op = rng.choice(["AND", "OR"])
        p = PREC[op.lower()]
        return ("%s %s %s" % (wrap(self.boolean(d - 1, agg), p), op, wrap(self.boolean(d - 1, agg), p + 1)), p)

    def pair(self, d, agg):
        if self.rng.random() < 0.5:
            return self.num(d, agg=agg), self.num(d, agg=agg)
        return self.text(d, agg), self.text(d, agg)

    def any_expr(self, d, agg):
        return self.num(d, agg=agg) if self.rng.random() < 0.6 else self.text(d, agg)

    def compare(self, d, agg):
        rng = self.rng
        e1, e2 = self.pair(d, agg)
        op = rng.choice(["=", "<>", "!=", "<", "<=", ">", ">="])
        prec = PREC["eq"] if op in ("=", "<>", "!=") else PREC["rel"]
        return ("%s %s %s" % (wrap(e1, prec), op, wrap(e2, prec + 1)), prec)
