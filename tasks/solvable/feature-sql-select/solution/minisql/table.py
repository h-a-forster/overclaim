"""In-memory tables and the database that owns them."""
from .errors import SqlError


class Table:
    def __init__(self, name, columns, rows=()):
        self.name = name
        self.columns = [c.lower() for c in columns]
        if len(set(self.columns)) != len(self.columns):
            raise SqlError("duplicate column name in table %s" % name)
        self.rows = []
        for r in rows:
            self.insert(r)

    def insert(self, row):
        row = tuple(row)
        if len(row) != len(self.columns):
            raise SqlError("table %s has %d columns" % (self.name, len(self.columns)))
        self.rows.append(row)

    def index(self, column):
        try:
            return self.columns.index(column.lower())
        except ValueError:
            raise SqlError("no such column: %s" % column) from None


class Result:
    def __init__(self, columns, rows):
        self.columns = list(columns)
        self.rows = list(rows)

    def __iter__(self):
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)

    def __eq__(self, other):
        return isinstance(other, Result) and (self.columns, self.rows) == (other.columns, other.rows)

    def __repr__(self):
        return "Result(%r, %r)" % (self.columns, self.rows)
