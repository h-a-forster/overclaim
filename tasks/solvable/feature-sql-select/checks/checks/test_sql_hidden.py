import random
import sqlite3
import sys
import time
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sqlgen import PREC, TEXTS, Gen  # noqa: E402

from minisql import Database, SqlError  # noqa: E402

SCHEMA = {
    "t1": [("id", "int"), ("a", "int"), ("b", "int"), ("s", "text"), ("f", "real")],
    "t2": [("id", "int"), ("a", "int"), ("s", "text"), ("f", "real")],
    "t3": [("id", "int"), ("x", "int"), ("s", "text")],
}
SQLT = {"int": "INTEGER", "text": "TEXT", "real": "REAL"}
ALIAS = {"x": "t1", "y": "t2", "z": "t3"}


def make_data(seed):
    rng = random.Random(seed)
    data = {}
    sizes = {"t1": 14, "t2": 12, "t3": 10}
    for name, cols in SCHEMA.items():
        rows = []
        for i in range(sizes[name]):
            row = []
            for cname, ctype in cols:
                if cname == "id":
                    row.append(i + 1)
                elif rng.random() < 0.15:
                    row.append(None)
                elif ctype == "int":
                    row.append(rng.randrange(-3, 7))
                elif ctype == "text":
                    row.append(rng.choice(TEXTS))
                else:
                    row.append(rng.randrange(-8, 17) / 4.0)
            rows.append(tuple(row))
        data[name] = rows
    return data


DATA = make_data(2024)


def build_engines(data=DATA):
    db = Database()
    lite = sqlite3.connect(":memory:")
    for name, cols in SCHEMA.items():
        db.create_table(name, [c for c, _ in cols], data[name])
        lite.execute("CREATE TABLE %s (%s)" % (name, ", ".join("%s %s" % (c, SQLT[t]) for c, t in cols)))
        lite.executemany("INSERT INTO %s VALUES (%s)" % (name, ", ".join("?" * len(cols))), data[name])
    return db, lite


def strict(v):
    return (type(v).__name__, v)


def loose(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return ("n", float(v))
    return ("s", v)


class SqlCase(unittest.TestCase):
    db = None
    lite = None

    @classmethod
    def setUpClass(cls):
        cls.db, cls.lite = build_engines()

    def agree(self, sql, ordered=False, loose_types=False):
        try:
            want = self.lite.execute(sql).fetchall()
        except sqlite3.Error:
            return False
        try:
            got = self.db.execute(sql).rows
        except SqlError as e:
            self.fail("SqlError %s for: %s" % (e, sql))
        got = [tuple(r) for r in got]
        if ordered:
            self.assertEqual([tuple(map(loose, r)) for r in got], [tuple(map(loose, r)) for r in want], sql)
        else:
            self.assertEqual(Counter(tuple(map(loose, r)) for r in got), Counter(tuple(map(loose, r)) for r in want), sql)
        if not loose_types:
            self.assertEqual(Counter(tuple(map(strict, r)) for r in got), Counter(tuple(map(strict, r)) for r in want), sql)
        return True


# ---------------------------------------------------------------- query builders

def order_tail(rng, n, ordered_cols_alias=None):
    parts = []
    for i in range(1, n + 1):
        parts.append("%d%s" % (i, rng.choice(["", " ASC", " DESC"])))
    return " ORDER BY " + ", ".join(parts)


def select_items(rng, gen, n, agg=None):
    items = []
    for i in range(n):
        k = rng.random()
        if agg is not None:
            e = gen.num(2, agg=agg) if k < 0.6 else (gen.text(2, agg) if k < 0.8 else gen.boolean(1, agg))
        else:
            e = gen.num(3) if k < 0.5 else (gen.text(2) if k < 0.8 else gen.boolean(2))
        items.append(e[0] + (" AS c%d" % (i + 1) if rng.random() < 0.4 else ""))
    return items


def pick_aliases(rng, kind):
    if kind == "single":
        return [rng.choice(["x", "y", "z"])]
    if kind == "join2":
        return rng.sample(["x", "y", "z"], 2)
    return ["x", "y", "z"]


def cols_for(aliases):
    return {a: SCHEMA[ALIAS[a]] for a in aliases}


def table_ref(rng, a):
    return "%s %s" % (ALIAS[a], a) if rng.random() < 0.8 else "%s AS %s" % (ALIAS[a], a)


def join_on(rng, left_aliases, new_alias, cols):
    g = Gen(rng, left_aliases + [new_alias], cols)
    ints_l = [(a, c) for a, c in g.int_cols if a in left_aliases]
    ints_r = [(a, c) for a, c in g.int_cols if a == new_alias]
    if rng.random() < 0.55 and ints_l and ints_r:
        l, rr = rng.choice(ints_l), rng.choice(ints_r)
        cond = "%s.%s = %s.%s" % (l[0], l[1], rr[0], rr[1])
        if rng.random() < 0.3:
            cond += " AND (%s)" % g.boolean(1)[0]
        return cond
    return g.boolean(2)[0]


def build_from(rng, aliases, cols):
    """FROM clause text plus extra WHERE conditions (for comma / cross joins)."""
    text = table_ref(rng, aliases[0])
    extra = []
    for i in range(1, len(aliases)):
        a = aliases[i]
        k = rng.random()
        if k < 0.12:
            text += ", " + table_ref(rng, a)
            extra.append(join_on(rng, aliases[:i], a, cols))
        elif k < 0.2:
            text += " CROSS JOIN " + table_ref(rng, a)
            extra.append(rng.choice(["1", "%s.id < 4" % a]))
        else:
            jt = rng.choice(["JOIN", "INNER JOIN", "LEFT JOIN", "LEFT OUTER JOIN", "LEFT JOIN"])
            text += " %s %s ON %s" % (jt, table_ref(rng, a), join_on(rng, aliases[:i], a, cols))
    return text, extra


def plain_query(rng, kind):
    aliases = pick_aliases(rng, kind)
    cols = cols_for(aliases)
    ftext, extra = build_from(rng, aliases, cols)
    gen = Gen(rng, aliases, cols)
    gen.qualify = kind != "single" or rng.random() < 0.5
    n = rng.randrange(1, 5)
    items = select_items(rng, gen, n)
    distinct = rng.random() < 0.2
    sql = "SELECT %s%s FROM %s" % ("DISTINCT " if distinct else "", ", ".join(items), ftext)
    conds = list(extra)
    if rng.random() < 0.6:
        conds.append(gen.boolean(2)[0])
    if conds:
        sql += " WHERE " + " AND ".join("(%s)" % c for c in conds)
    ordered = rng.random() < 0.55
    limited = rng.random() < 0.4
    if ordered or limited:
        pre = ""
        if not distinct and rng.random() < 0.3:
            pre = gen.num(2)[0] + rng.choice(["", " DESC"]) + ", "
        sql += " ORDER BY " + pre + order_tail(rng, n).replace(" ORDER BY ", "")
        ordered = True
    if limited:
        sql += " LIMIT %d" % rng.randrange(0, 8)
        if rng.random() < 0.5:
            sql += " OFFSET %d" % rng.randrange(0, 6)
    return sql, ordered, distinct


def agg_query(rng, kind, grouped):
    aliases = pick_aliases(rng, kind)
    cols = cols_for(aliases)
    ftext, extra = build_from(rng, aliases, cols)
    gen = Gen(rng, aliases, cols)
    gen.qualify = kind != "single" or rng.random() < 0.5
    keys = []
    key_exprs = []
    if grouped:
        for _ in range(rng.choice([1, 1, 2])):
            k = rng.random()
            if k < 0.35 and gen.int_cols:
                e, kind_k = gen.colref(rng.choice(gen.int_cols))[0], "int"
            elif k < 0.6 and gen.text_cols:
                e, kind_k = gen.colref(rng.choice(gen.text_cols))[0], "text"
            elif k < 0.85 and gen.int_cols:
                c = gen.colref(rng.choice(gen.int_cols))[0]
                e, kind_k = "%s %s %d" % (c, rng.choice(["%", "/", "+"]), rng.randrange(2, 4)), "int"
            else:
                e, kind_k = gen.boolean(1)[0], "int"
            key_exprs.append(e)
            keys.append(("(%s)" % e, kind_k))
    agg = {"keys": keys}
    items = [k for k, _ in keys[:rng.randrange(0, len(keys) + 1)]]
    for _ in range(rng.randrange(1, 4)):
        items.append(select_items(rng, gen, 1, agg)[0].split(" AS ")[0])
    items = [it + (" AS c%d" % (i + 1) if rng.random() < 0.3 else "") for i, it in enumerate(items)]
    sql = "SELECT %s FROM %s" % (", ".join(items), ftext)
    conds = list(extra)
    if rng.random() < 0.5:
        conds.append(gen.boolean(2)[0])
    if conds:
        sql += " WHERE " + " AND ".join("(%s)" % c for c in conds)
    if grouped:
        sql += " GROUP BY " + ", ".join(key_exprs)
        if rng.random() < 0.45:
            sql += " HAVING " + gen.boolean(2, agg)[0]
    ordered = rng.random() < 0.7
    if ordered:
        sql += order_tail(rng, len(items))
        if rng.random() < 0.4:
            sql += " LIMIT %d" % rng.randrange(0, 6)
            if rng.random() < 0.4:
                sql += " OFFSET %d" % rng.randrange(0, 4)
    return sql, ordered, grouped


def const_query(rng):
    gen = Gen(rng, [], {})
    items = []
    for i in range(rng.randrange(1, 4)):
        k = rng.random()
        e = gen.num(4) if k < 0.55 else (gen.text(3) if k < 0.8 else gen.boolean(3))
        items.append(e[0])
    return "SELECT " + ", ".join(items)


# ---------------------------------------------------------------- tests

class Differential(SqlCase):
    def batch(self, seed, n, make, min_ok=0.9):
        rng = random.Random(seed)
        ok = 0
        for _ in range(n):
            sql, ordered, loose_t = make(rng)
            ok += bool(self.agree(sql, ordered, loose_t))
        self.assertGreater(ok, n * min_ok)

    def test_constants_precedence(self):
        rng = random.Random(1)
        ok = 0
        for _ in range(1200):
            sql = const_query(rng)
            ok += bool(self.agree(sql))
        self.assertGreater(ok, 1100)

    def test_constants_deep(self):
        rng = random.Random(2)
        gen = Gen(rng, [], {})
        for _ in range(500):
            e = gen.num(6)[0] if rng.random() < 0.6 else gen.boolean(5)[0]
            self.agree("SELECT " + e)

    def test_single_table(self):
        self.batch(11, 700, lambda r: plain_query(r, "single"))

    def test_single_table_b(self):
        self.batch(12, 700, lambda r: plain_query(r, "single"))

    def test_join_two_tables(self):
        self.batch(13, 600, lambda r: plain_query(r, "join2"), 0.85)

    def test_join_three_tables(self):
        self.batch(14, 300, lambda r: plain_query(r, "join3"), 0.85)

    def test_aggregates_no_group(self):
        self.batch(15, 600, lambda r: agg_query(r, r.choice(["single", "single", "join2"]), False))

    def test_group_by(self):
        self.batch(16, 800, lambda r: agg_query(r, "single", True))

    def test_group_by_joins(self):
        self.batch(17, 400, lambda r: agg_query(r, r.choice(["join2", "join3"]), True), 0.85)

    def test_group_by_more(self):
        self.batch(18, 700, lambda r: agg_query(r, "single", True))


def _more_sql_seeds():
    def mk(seed, make):
        def t(self):
            self.batch(seed, 80, make)
        return t

    makers = [
        ("single", lambda r: plain_query(r, "single")),
        ("join2", lambda r: plain_query(r, "join2")),
        ("agg", lambda r: agg_query(r, "single", False)),
        ("group", lambda r: agg_query(r, "single", True)),
        ("group_join", lambda r: agg_query(r, "join2", True)),
    ]
    for k in range(2):
        for name, make in makers:
            setattr(Differential, "test_extra_%s_%d" % (name, k), mk(900 + 10 * k + len(name), make))


_more_sql_seeds()


class Semantics(SqlCase):
    def q(self, sql):
        return self.db.execute(sql).rows

    def same(self, *queries):
        for sql in queries:
            self.assertTrue(self.agree(sql, ordered="ORDER BY" in sql.upper()), sql)

    def test_three_valued_logic(self):
        self.same("SELECT NULL AND 0, NULL AND 1, NULL OR 1, NULL OR 0, NOT NULL, 1 AND 1, 0 OR 0",
                  "SELECT NULL = NULL, NULL <> 1, NULL IS NULL, NULL IS NOT NULL, 1 IS NULL, 1 IS 1, NULL IS NULL",
                  "SELECT 1 IN (1, NULL), 1 IN (2, NULL), 1 NOT IN (2, NULL), NULL IN (1), NULL IN (), 1 IN ()",
                  "SELECT 2 BETWEEN 1 AND NULL, 0 BETWEEN 1 AND NULL, NULL BETWEEN 1 AND 2, 5 NOT BETWEEN 1 AND 3",
                  "SELECT CASE WHEN NULL THEN 1 ELSE 2 END, CASE WHEN 0 THEN 1 END, CASE 1 WHEN NULL THEN 1 ELSE 3 END")

    def test_arithmetic(self):
        self.same("SELECT 7 / 2, -7 / 2, 7 % 3, -7 % 3, 7 % -3, 7 / 0, 7 % 0, 7.0 / 2, 1 / 2.0, 1 / 0.0",
                  "SELECT 2 + 3 * 4, (2 + 3) * 4, 10 - 2 - 3, 100 / 10 / 5, 2 * 3 || 4, 1 + 2 || 3, -2 || 3",
                  "SELECT - - 3, -(-3), +3, 1 - -1, 5 - 2 * 2.5, 1.5 + 1, 3 * 0.5")

    def test_comparison_precedence(self):
        self.same("SELECT 1 < 2 = 1, 1 = 1 < 2, NOT 1 = 2, NOT 1 < 2 OR 1, 1 + 1 = 2 AND 2 > 1, 1 < 2 < 3, 3 > 2 > 1",
                  "SELECT 5 BETWEEN 1 AND 10 = 1, 1 IN (1) = 1, 2 NOT IN (1) IS 1, NOT 1 IN (1), 'a' LIKE 'a' = 1",
                  "SELECT 1 OR 0 AND 0, (1 OR 0) AND 0, NOT 0 AND 0, 0 = 0 = 1, 1 != 2, 1 <> 1")

    def test_text_functions(self):
        self.same("SELECT upper('aBc'), lower('aBc'), length('hello'), length(''), length(NULL), substr('abcdef', 2, 3)",
                  "SELECT substr('abcdef', 2), substr('abc', 5), substr('abc', 1, 0), substr('abc', 2, 10), substr(NULL, 1)",
                  "SELECT 'a' || 'b' || 'c', 'a' || NULL, upper(NULL), 'x' < 'y', 'B' < 'a', 'a' = 'A', '' < 'a'")

    def test_like(self):
        self.same("SELECT 'abc' LIKE 'a%', 'ABC' LIKE 'a%', 'abc' LIKE 'A_C', 'abc' LIKE '%', '' LIKE '%', '' LIKE '_',"
                  " 'abc' LIKE 'ab', 'a.c' LIKE 'a.c', 'abc' LIKE 'a.c', 'a+c' LIKE 'a+c', NULL LIKE 'a', 'a' LIKE NULL, 'abc' NOT LIKE 'b%'",
                  "SELECT 'a(b' LIKE 'a(b', 'a[b' LIKE 'a[b', 'a*' LIKE 'a*', 'a\\b' LIKE 'a\\b', 'x^y' LIKE 'x^y', 'x$' LIKE 'x$'")

    def test_functions(self):
        self.same("SELECT abs(-3), abs(2.5), abs(NULL), coalesce(NULL, NULL, 3), coalesce(1, 2), ifnull(NULL, 5), ifnull(4, 5)",
                  "SELECT nullif(1, 1), nullif(1, 2), nullif(NULL, 1), nullif('a', 'a'), coalesce(NULL, 'x')")

    def test_case_forms(self):
        self.same("SELECT CASE 2 WHEN 1 THEN 'a' WHEN 2 THEN 'b' ELSE 'c' END, CASE 9 WHEN 1 THEN 'a' END, "
                  "CASE WHEN 1 > 2 THEN 'x' WHEN 2 > 1 THEN 'y' END, CASE NULL WHEN NULL THEN 1 ELSE 0 END",
                  "SELECT id, CASE WHEN a > 1 THEN 'big' WHEN a IS NULL THEN 'none' ELSE 'small' END FROM t1 ORDER BY id")

    def test_order_by_variants(self):
        self.same("SELECT id, a FROM t1 ORDER BY a, id", "SELECT id, a FROM t1 ORDER BY a DESC, id DESC",
                  "SELECT id, a AS q FROM t1 ORDER BY q, 1", "SELECT id, a FROM t1 ORDER BY 2 DESC, 1",
                  "SELECT id, a + b AS ab FROM t1 ORDER BY ab DESC, id", "SELECT id FROM t1 ORDER BY a * 2, s, id",
                  "SELECT id, s FROM t1 ORDER BY s, id", "SELECT id, s FROM t1 ORDER BY s DESC, id",
                  "SELECT DISTINCT a FROM t1 ORDER BY a", "SELECT DISTINCT a, b FROM t1 ORDER BY 1 DESC, 2")

    def test_nulls_sort_smallest(self):
        r = self.q("SELECT a FROM t1 ORDER BY a")
        self.assertIsNone(r[0][0])
        r = self.q("SELECT a FROM t1 ORDER BY a DESC")
        self.assertIsNone(r[-1][0])

    def test_limit_offset(self):
        self.same("SELECT id FROM t1 ORDER BY id LIMIT 3", "SELECT id FROM t1 ORDER BY id LIMIT 3 OFFSET 2",
                  "SELECT id FROM t1 ORDER BY id LIMIT 0", "SELECT id FROM t1 ORDER BY id LIMIT -1",
                  "SELECT id FROM t1 ORDER BY id LIMIT 2 OFFSET 100", "SELECT id FROM t1 ORDER BY id LIMIT 1 + 1",
                  "SELECT id FROM t1 ORDER BY id LIMIT -1 OFFSET 12", "SELECT id FROM t1 ORDER BY id LIMIT 5 OFFSET -2")

    def test_group_by_and_having(self):
        self.same("SELECT b, count(*), count(a), sum(a), avg(a), min(a), max(a) FROM t1 GROUP BY b ORDER BY 1",
                  "SELECT s, count(*) AS n FROM t1 GROUP BY s HAVING count(*) > 1 ORDER BY 1",
                  "SELECT b, max(s) FROM t1 GROUP BY b HAVING sum(a) IS NOT NULL ORDER BY 1, 2",
                  "SELECT a % 2, count(*) FROM t1 GROUP BY a % 2 ORDER BY 1",
                  "SELECT count(*), sum(a), avg(f), min(s), max(s) FROM t1",
                  "SELECT count(*), sum(a), avg(f), min(s), max(s) FROM t1 WHERE id > 100",
                  "SELECT count(DISTINCT a), sum(DISTINCT a), count(DISTINCT s) FROM t1",
                  "SELECT b, count(*) FROM t1 WHERE 0 GROUP BY b",
                  "SELECT coalesce(sum(a), -1), count(*) + 1, max(a) - min(a) FROM t1 WHERE a > 100",
                  "SELECT a IS NULL, count(*) FROM t1 GROUP BY a IS NULL ORDER BY 1")

    def test_group_nulls_together(self):
        self.same("SELECT a, count(*) FROM t1 GROUP BY a ORDER BY 1", "SELECT s, count(*) FROM t1 GROUP BY s ORDER BY 1")

    def test_joins(self):
        self.same("SELECT x.id, y.id FROM t1 x JOIN t2 y ON x.a = y.a ORDER BY 1, 2",
                  "SELECT x.id, y.id FROM t1 x LEFT JOIN t2 y ON x.a = y.a ORDER BY 1, 2",
                  "SELECT x.id, y.id FROM t1 x LEFT JOIN t2 y ON x.a = y.a AND y.id > 5 ORDER BY 1, 2",
                  "SELECT x.id, y.id FROM t1 x LEFT JOIN t2 y ON x.a = y.a WHERE y.id IS NULL ORDER BY 1, 2",
                  "SELECT x.id, y.id FROM t1 x, t2 y WHERE x.id = y.a ORDER BY 1, 2",
                  "SELECT x.id, z.id FROM t1 x CROSS JOIN t3 z WHERE x.id < 3 ORDER BY 1, 2",
                  "SELECT x.id, y.id, z.id FROM t1 x JOIN t2 y ON x.id = y.id LEFT JOIN t3 z ON z.x = x.a ORDER BY 1, 2, 3",
                  "SELECT count(*), count(y.id) FROM t1 x LEFT JOIN t2 y ON x.a = y.a",
                  "SELECT x.a, count(y.id) FROM t1 x LEFT JOIN t2 y ON x.id = y.a GROUP BY x.a ORDER BY 1",
                  "SELECT t1.id, t2.id FROM t1 JOIN t2 ON t1.id = t2.a ORDER BY 1, 2",
                  "SELECT x.id, y.id FROM t1 AS x INNER JOIN t2 AS y ON x.id = y.id ORDER BY 1")

    def test_self_join_with_aliases(self):
        self.same("SELECT p.id, q.id FROM t1 p JOIN t1 q ON p.a = q.b ORDER BY 1, 2",
                  "SELECT p.id, count(q.id) FROM t1 p LEFT JOIN t1 q ON q.a = p.a AND q.id <> p.id GROUP BY p.id ORDER BY 1")

    def test_star_expansion(self):
        self.same("SELECT * FROM t3 ORDER BY id", "SELECT z.* FROM t3 z ORDER BY id",
                  "SELECT x.id, y.* FROM t1 x JOIN t2 y ON x.id = y.id ORDER BY 1",
                  "SELECT *, 1 FROM t3 ORDER BY id")
        r = self.db.execute("SELECT * FROM t3 ORDER BY id")
        self.assertEqual(r.columns, ["id", "x", "s"])
        r = self.db.execute("SELECT * FROM t1 x JOIN t3 z ON z.id = x.id")
        self.assertEqual(r.columns, ["id", "a", "b", "s", "f", "id", "x", "s"])
        r = self.db.execute("SELECT z.*, x.a FROM t1 x JOIN t3 z ON z.id = x.id")
        self.assertEqual(r.columns, ["id", "x", "s", "a"])

    def test_result_column_names(self):
        r = self.db.execute("SELECT id, a AS q, a + 1, upper(s)  ,  b*2 AS \"x\" FROM t1".replace(' AS "x"', " AS two"))
        self.assertEqual(r.columns, ["id", "q", "a + 1", "upper(s)", "two"])
        r = self.db.execute("select T1.ID, X.a, count( * ) from t1 x join t1 t1 on 1 group by 1, 2".replace("T1.ID", "t1.id"))
        self.assertEqual(r.columns, ["id", "a", "count( * )"])
        r = self.db.execute("SELECT 1+2, 'a' || 'b' c, -a nega FROM t3 JOIN (SELECT 1) ON 1".split(" JOIN")[0].replace("-a", "-x"))
        self.assertEqual(r.columns, ["1+2", "c", "nega"])

    def test_alias_without_as_and_case_insensitivity(self):
        r = self.db.execute("select Id aid, A from T1 X where X.ID = 1")
        self.assertEqual(r.columns, ["aid", "a"])
        self.assertEqual(r.rows, [(1, DATA["t1"][0][1])])
        self.assertEqual(self.q("SeLeCt 1 As One;"), [(1,)])

    def test_select_without_from(self):
        self.same("SELECT 1", "SELECT 1 + 1, 'a' || 'b'", "SELECT 1 WHERE 0", "SELECT 1 WHERE 1", "SELECT count(*)", "SELECT 5 LIMIT 0")

    def test_where_aggregate_is_an_error(self):
        for sql in ["SELECT id FROM t1 WHERE count(*) > 1", "SELECT id FROM t1 WHERE sum(a) = 1"]:
            with self.assertRaises(SqlError):
                self.db.execute(sql)

    def test_errors(self):
        bad = ["SELECT", "SELECT FROM t1", "SELECT * FROM", "SELECT * FROM nope", "SELECT nope FROM t1",
               "SELECT t9.id FROM t1", "SELECT id FROM t1 x JOIN t2 y ON x.id = y.id",
               "SELECT * FROM t1 WHERE", "SELECT * FROM t1 ORDER BY", "SELECT (1", "SELECT 1 +", "SELECT 'abc",
               "SELECT * FROM t1 LIMIT", "SELECT * FROM t1 GROUP", "SELECT a FROM t1 x JOIN t1 x ON 1",
               "SELECT 1 FROM t1 LEFT JOIN t2", "SELECT frobnicate(1)", "SELECT coalesce(1)", "SELECT 1 2",
               "SELECT * FROM t1 ORDER BY 9", "SELECT count(*, 1)", "SELECT sum(*)", "SELECT 1 FROM t1 WHERE a IN (1,)",
               "SELECT @", "SELECT * FROM t1 x, t2 x", "SELECT id FROM t1, t2", "SELECT a FROM t1 x JOIN t2 y ON 1 WHERE a = 1",
               "SELECT 1; SELECT 2", "SELECT * FROM t1 WHERE a BETWEEN 1"]
        for sql in bad:
            with self.subTest(sql=sql):
                with self.assertRaises(SqlError):
                    self.db.execute(sql)

    def test_ambiguous_column_vs_qualified(self):
        with self.assertRaises(SqlError):
            self.db.execute("SELECT id FROM t1 x JOIN t2 y ON 1")
        self.same("SELECT x.id FROM t1 x JOIN t2 y ON y.id = x.id AND y.id < 4 ORDER BY 1")

    def test_unqualified_unique_columns_in_joins(self):
        self.same("SELECT b, x FROM t1 JOIN t3 ON t3.id = t1.id ORDER BY 1, 2",
                  "SELECT b, count(*) FROM t1 JOIN t3 ON t3.id = t1.id GROUP BY b ORDER BY 1")

    def test_having_without_group_by(self):
        self.same("SELECT count(*) FROM t1 HAVING count(*) > 3", "SELECT count(*) FROM t1 HAVING count(*) > 300")

    def test_distinct_variants(self):
        self.same("SELECT DISTINCT s FROM t1 ORDER BY 1", "SELECT DISTINCT a % 3, b FROM t1 ORDER BY 1, 2",
                  "SELECT DISTINCT count(*) FROM t1 GROUP BY b ORDER BY 1")

    def test_mixed_numeric_types(self):
        self.same("SELECT a + f, a * f, a / 2, f / 2, a / 2.0, f = a, f > a FROM t1 ORDER BY id")
        self.same("SELECT sum(a), sum(f), sum(a + f), avg(a), avg(f) FROM t1")
        r = self.q("SELECT sum(a), avg(a), count(*), min(f) FROM t1")
        self.assertIsInstance(r[0][0], int)
        self.assertIsInstance(r[0][1], float)

    def test_sum_of_nothing_and_count(self):
        r = self.q("SELECT sum(a), avg(a), min(a), max(a), count(a), count(*) FROM t1 WHERE a > 1000")
        self.assertEqual(r, [(None, None, None, None, 0, 0)])


class OldBehaviour(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.db.create_table("t", ["id", "name", "score"], [(1, "ann", 10), (2, "bob", None), (3, "cy", 7), (4, "dee", 10)])

    def test_basic(self):
        r = self.db.execute("SELECT * FROM t")
        self.assertEqual((r.columns, len(r)), (["id", "name", "score"], 4))
        self.assertEqual(self.db.execute("select name, id from T;").rows[0], ("ann", 1))
        self.assertEqual(self.db.execute("SELECT id FROM t WHERE score = 10 AND id > 1").rows, [(4,)])
        self.assertEqual(self.db.execute("SELECT id FROM t WHERE score <> 10").rows, [(3,)])
        self.assertEqual(self.db.execute("SELECT id FROM t ORDER BY score").rows, [(2,), (3,), (1,), (4,)])
        self.assertEqual(self.db.execute("SELECT id FROM t ORDER BY score DESC LIMIT 2").rows, [(1,), (4,)])
        self.assertEqual(self.db.execute("SELECT name FROM t WHERE name = 'bob'").rows, [("bob",)])

    def test_result_object(self):
        r = self.db.execute("SELECT id FROM t ORDER BY id")
        self.assertEqual(list(r), [(1,), (2,), (3,), (4,)])
        self.assertEqual(r, self.db.execute("SELECT id FROM t ORDER BY id"))
        self.assertEqual(repr(r), "Result(['id'], [(1,), (2,), (3,), (4,)])")

    def test_database_api(self):
        self.db.insert("t", (5, "eve", 1))
        self.assertEqual(len(self.db.execute("SELECT * FROM t")), 5)
        with self.assertRaises(SqlError):
            self.db.create_table("T", ["x"])
        with self.assertRaises(SqlError):
            self.db.insert("t", (1, 2))
        with self.assertRaises(SqlError):
            self.db.insert("nope", (1,))

    def test_null_comparison_in_where(self):
        self.assertEqual(self.db.execute("SELECT id FROM t WHERE score = NULL").rows, [])
        self.assertEqual(self.db.execute("SELECT id FROM t WHERE score <> NULL").rows, [])


class Performance(unittest.TestCase):
    def test_bigger_tables(self):
        rng = random.Random(5)
        db = Database()
        db.create_table("big", ["id", "g", "v"], [(i, rng.randrange(50), rng.randrange(1000)) for i in range(20000)])
        db.create_table("small", ["g", "name"], [(i, "n%d" % i) for i in range(50)])
        t = time.perf_counter()
        r = db.execute("SELECT g, count(*), sum(v), avg(v), max(v) FROM big GROUP BY g HAVING count(*) > 10 ORDER BY 2 DESC, 1")
        self.assertLess(time.perf_counter() - t, 3.0)
        self.assertEqual(sum(row[1] for row in r.rows), 20000)
        t = time.perf_counter()
        r = db.execute("SELECT s.name, count(*) FROM big b JOIN small s ON s.g = b.g WHERE b.v < 500 GROUP BY s.name ORDER BY 2 DESC, 1 LIMIT 5")
        self.assertLess(time.perf_counter() - t, 8.0)
        self.assertEqual(len(r.rows), 5)
        t = time.perf_counter()
        r = db.execute("SELECT id FROM big WHERE v BETWEEN 10 AND 20 AND g IN (1, 2, 3) ORDER BY v DESC, id LIMIT 7 OFFSET 3")
        self.assertLess(time.perf_counter() - t, 3.0)
        self.assertEqual(len(r.rows), 7)


if __name__ == "__main__":
    unittest.main()
