"""Query execution: FROM/JOIN -> WHERE -> GROUP BY/aggregates -> HAVING -> projection ->
DISTINCT -> ORDER BY -> LIMIT/OFFSET. Expressions are compiled to closures f(row, group)."""
from .errors import SqlError
from .parser import AGGREGATES, parse
from .table import Result, Table
from .values import (aggregate, arith, boolval, compare, in_list, like, rank_key, scalar_function, truth)


SCALARS = {"coalesce", "ifnull", "nullif", "abs", "length", "upper", "lower", "substr"}


class Scope:
    """Maps column names of the FROM sources onto positions of the flat row tuple."""

    def __init__(self):
        self.entries = []   # (alias, column, index)
        self.aliases = []
        self.width = 0

    def add(self, alias, table):
        if alias in self.aliases:
            raise SqlError("ambiguous table alias: %s" % alias)
        self.aliases.append(alias)
        for c in table.columns:
            self.entries.append((alias, c, self.width))
            self.width += 1

    def resolve(self, table, name):
        hits = [i for a, c, i in self.entries if c == name and (table is None or a == table)]
        if not hits:
            raise SqlError("no such column: %s" % (name if table is None else table + "." + name))
        if len(hits) > 1:
            raise SqlError("ambiguous column name: %s" % name)
        return hits[0]


def _has_aggregate(e):
    if isinstance(e, list):
        return any(_has_aggregate(x) for x in e)
    if not isinstance(e, tuple) or not e:
        return False
    if isinstance(e[0], str):
        if e[0] == "func" and _is_agg_call(e):
            return True
        return any(_has_aggregate(x) for x in e[1:])
    return any(_has_aggregate(x) for x in e)


def _is_agg_call(e):
    return e[0] == "func" and e[1] in AGGREGATES and not (e[1] in ("min", "max") and len(e[2]) != 1)


class Compiler:
    def __init__(self, scope, allow_agg):
        self.scope = scope
        self.allow_agg = allow_agg

    def c(self, e):
        k = e[0]
        m = getattr(self, "c_" + k)
        return m(e)

    def c_lit(self, e):
        v = e[1]
        return lambda row, grp: v

    def c_col(self, e):
        i = self.scope.resolve(e[1], e[2])
        return lambda row, grp: row[i]

    def c_neg(self, e):
        f = self.c(e[1])

        def go(row, grp):
            v = f(row, grp)
            return None if v is None else -arith("+", v, 0)
        return go

    def c_pos(self, e):
        return self.c(e[1])

    def c_not(self, e):
        f = self.c(e[1])

        def go(row, grp):
            t = truth(f(row, grp))
            return None if t is None else int(not t)
        return go

    def c_and(self, e):
        f, g = self.c(e[1]), self.c(e[2])

        def go(row, grp):
            a = truth(f(row, grp))
            if a is False:
                return 0
            b = truth(g(row, grp))
            if b is False:
                return 0
            return None if a is None or b is None else 1
        return go

    def c_or(self, e):
        f, g = self.c(e[1]), self.c(e[2])

        def go(row, grp):
            a = truth(f(row, grp))
            if a is True:
                return 1
            b = truth(g(row, grp))
            if b is True:
                return 1
            return None if a is None or b is None else 0
        return go

    def c_bin(self, e):
        op = e[1]
        f, g = self.c(e[2]), self.c(e[3])
        if op in ("+", "-", "*", "/", "%"):
            return lambda row, grp: arith(op, f(row, grp), g(row, grp))
        if op == "||":
            def cat(row, grp):
                a, b = f(row, grp), g(row, grp)
                return None if a is None or b is None else str(a) + str(b)
            return cat
        tests = {"=": lambda c: c == 0, "<>": lambda c: c != 0, "<": lambda c: c < 0, "<=": lambda c: c <= 0,
                 ">": lambda c: c > 0, ">=": lambda c: c >= 0}
        t = tests[op]

        def cmp(row, grp):
            c = compare(f(row, grp), g(row, grp))
            return None if c is None else int(t(c))
        return cmp

    def c_is(self, e):
        f, g, neg = self.c(e[1]), self.c(e[2]), e[3]

        def go(row, grp):
            a, b = f(row, grp), g(row, grp)
            same = (a is None and b is None) or (a is not None and b is not None and compare(a, b) == 0)
            return int(same != neg)
        return go

    def c_isnull(self, e):
        f, neg = self.c(e[1]), e[2]
        return lambda row, grp: int((f(row, grp) is None) != neg)

    def c_in(self, e):
        f = self.c(e[1])
        items = [self.c(x) for x in e[2]]
        neg = e[3]

        def go(row, grp):
            r = in_list(f(row, grp), [g(row, grp) for g in items])
            return r if r is None else int(bool(r) != neg)
        return go

    def c_between(self, e):
        f, lo, hi, neg = self.c(e[1]), self.c(e[2]), self.c(e[3]), e[4]

        def go(row, grp):
            v = f(row, grp)
            c1, c2 = compare(v, lo(row, grp)), compare(v, hi(row, grp))
            a = None if c1 is None else c1 >= 0
            b = None if c2 is None else c2 <= 0
            if a is False or b is False:
                r = False
            elif a is None or b is None:
                return None
            else:
                r = True
            return int(r != neg)
        return go

    def c_like(self, e):
        f, g, neg = self.c(e[1]), self.c(e[2]), e[3]

        def go(row, grp):
            r = like(f(row, grp), g(row, grp))
            return r if r is None else int(bool(r) != neg)
        return go

    def c_case(self, e):
        operand = self.c(e[1]) if e[1] is not None else None
        whens = [(self.c(w), self.c(t)) for w, t in e[2]]
        other = self.c(e[3]) if e[3] is not None else None

        def go(row, grp):
            base = operand(row, grp) if operand else None
            for w, t in whens:
                if operand:
                    hit = compare(base, w(row, grp)) == 0
                else:
                    hit = truth(w(row, grp)) is True
                if hit:
                    return t(row, grp)
            return other(row, grp) if other else None
        return go

    def c_func(self, e):
        _, name, args, distinct, star = e
        if _is_agg_call(e):
            if not self.allow_agg:
                raise SqlError("misuse of aggregate function %s()" % name)
            if not star and len(args) != 1:
                raise SqlError("%s takes exactly one argument" % name)
            inner = Compiler(self.scope, False)
            f = None if star else inner.c(args[0])

            def agg(row, grp):
                if star:
                    return aggregate(name, False, [], star=True, count=len(grp))
                return aggregate(name, distinct, [f(r, None) for r in grp])
            return agg
        if distinct or star:
            raise SqlError("bad use of %s" % name)
        fs = [self.c(a) for a in args]
        if name not in SCALARS:
            raise SqlError("no such function: %s" % name)
        return lambda row, grp: scalar_function(name, [f(row, grp) for f in fs])


class Database:
    def __init__(self):
        self.tables = {}

    def create_table(self, name, columns, rows=()):
        if name.lower() in self.tables:
            raise SqlError("table %s already exists" % name)
        self.tables[name.lower()] = Table(name, columns, rows)

    def insert(self, name, row):
        self._table(name).insert(row)

    def _table(self, name):
        try:
            return self.tables[name.lower()]
        except KeyError:
            raise SqlError("no such table: %s" % name) from None

    def execute(self, sql):
        return self._run(parse(sql))

    # ---- FROM
    def _source(self, sources):
        if sources is None:
            return Scope(), [()]
        scope = Scope()
        rows = None
        for kind, (tname, alias), on in sources:
            table = self._table(tname)
            scope.add(alias, table)
            if rows is None:
                rows = [tuple(r) for r in table.rows]
                continue
            cond = Compiler(scope, False).c(on) if on is not None else None
            out = []
            for left in rows:
                matched = False
                for right in table.rows:
                    row = left + tuple(right)
                    if cond is None or truth(cond(row, None)) is True:
                        out.append(row)
                        matched = True
                if kind == "left" and not matched:
                    out.append(left + (None,) * len(table.columns))
            rows = out
        return scope, rows

    def _run(self, q):
        scope, rows = self._source(q["from"])
        if q["where"] is not None:
            if _has_aggregate(q["where"]):
                raise SqlError("aggregate functions are not allowed in the WHERE clause")
            f = Compiler(scope, False).c(q["where"])
            rows = [r for r in rows if truth(f(r, None)) is True]
        # expand the select list
        items = []   # (name, ast or index)
        for it in q["items"]:
            if it[0] == "star":
                if q["from"] is None:
                    raise SqlError("no tables specified")
                found = False
                for alias, col, idx in scope.entries:
                    if it[1] is None or it[1] == alias:
                        items.append((col, ("col", alias, col)))
                        found = True
                if not found:
                    raise SqlError("no such table: %s" % it[1])
            else:
                _, e, alias, text = it
                if alias is not None:
                    name = alias
                elif e[0] == "col":
                    name = e[2]
                else:
                    name = text.strip()
                items.append((name, e))
        is_agg = bool(q["group"]) or any(_has_aggregate(e) for _, e in items) or \
            (q["having"] is not None and _has_aggregate(q["having"])) or any(_has_aggregate(o) for o, _ in q["order"])
        comp = Compiler(scope, is_agg)
        item_fns = [comp.c(e) for _, e in items]
        order_specs = []
        names = [n for n, _ in items]
        for e, desc in q["order"]:
            if e[0] == "lit" and isinstance(e[1], int) and not isinstance(e[1], bool):
                if not 1 <= e[1] <= len(items):
                    raise SqlError("ORDER BY term out of range")
                order_specs.append(("out", e[1] - 1, desc))
            elif e[0] == "col" and e[1] is None and e[2] in [n.lower() for n in names] and \
                    not any(it[0] == "expr" and it[2] is None and it[1][0] == "col" and it[1][2] == e[2] for it in q["items"]):
                order_specs.append(("out", [n.lower() for n in names].index(e[2]), desc))
            else:
                order_specs.append(("fn", comp.c(e), desc))
        having = comp.c(q["having"]) if q["having"] is not None else None
        group_fns = [Compiler(scope, False).c(g) for g in q["group"]]
        produced = []   # (output tuple, order-key list)
        null_row = (None,) * scope.width
        if is_agg:
            groups = {}
            if group_fns:
                for r in rows:
                    key = tuple(g(r, None) for g in group_fns)
                    groups.setdefault(key, []).append(r)
            else:
                groups[()] = rows
            units = [(g[0] if g else null_row, g) for g in groups.values()]
        else:
            units = [(r, None) for r in rows]
        for row, grp in units:
            if having is not None and truth(having(row, grp)) is not True:
                continue
            out = tuple(f(row, grp) for f in item_fns)
            keys = [out[s[1]] if s[0] == "out" else s[1](row, grp) for s in order_specs]
            produced.append((out, keys))
        if q["distinct"]:
            seen = set()
            uniq = []
            for out, keys in produced:
                if out not in seen:
                    seen.add(out)
                    uniq.append((out, keys))
            produced = uniq
        for n in range(len(order_specs) - 1, -1, -1):
            produced.sort(key=lambda p, n=n: rank_key(p[1][n]), reverse=order_specs[n][2])
        result = [p[0] for p in produced]
        offset = self._const_int(q["offset"], 0)
        limit = self._const_int(q["limit"], -1)
        if offset < 0:
            offset = 0
        result = result[offset:] if limit < 0 else result[offset:offset + limit]
        return Result(names, result)

    @staticmethod
    def _const_int(e, default):
        if e is None:
            return default
        v = Compiler(Scope(), False).c(e)((), None)
        if isinstance(v, float) and v == int(v):
            v = int(v)
        if not isinstance(v, int) or isinstance(v, bool):
            raise SqlError("LIMIT/OFFSET must be an integer")
        return v
