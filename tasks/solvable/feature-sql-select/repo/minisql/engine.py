"""Executes the parsed query dict against a Database."""
import operator

from .errors import SqlError
from .parser import parse
from .table import Result, Table

_CMP = {"=": operator.eq, "<>": operator.ne, "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


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
        q = parse(sql)
        table = self._table(q["table"])
        rows = list(table.rows)
        for col, op, value in q["where"]:
            idx = table.index(col)
            # a NULL on either side never satisfies a comparison
            rows = [r for r in rows if r[idx] is not None and value is not None and _CMP[op](r[idx], value)]
        if q["order"]:
            idx = table.index(q["order"][0])
            nulls = [r for r in rows if r[idx] is None]
            rest = sorted((r for r in rows if r[idx] is not None), key=lambda r: r[idx], reverse=q["order"][1])
            rows = rest + nulls if q["order"][1] else nulls + rest
        if q["limit"] is not None and q["limit"] >= 0:
            rows = rows[:q["limit"]]
        if q["columns"] is None:
            return Result(table.columns, rows)
        idxs = [table.index(c) for c in q["columns"]]
        return Result(q["columns"], [tuple(r[i] for i in idxs) for r in rows])
