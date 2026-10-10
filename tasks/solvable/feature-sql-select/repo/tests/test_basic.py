import unittest

from minisql import Database, SqlError


class Basics(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.db.create_table("t", ["id", "name", "score"], [
            (1, "ann", 10), (2, "bob", None), (3, "cy", 7), (4, "dee", 10)])

    def test_star_and_columns(self):
        r = self.db.execute("SELECT * FROM t")
        self.assertEqual(r.columns, ["id", "name", "score"])
        self.assertEqual(len(r), 4)
        r = self.db.execute("select name, id from T;")
        self.assertEqual(r.columns, ["name", "id"])
        self.assertEqual(r.rows[0], ("ann", 1))

    def test_where_and_null(self):
        r = self.db.execute("SELECT id FROM t WHERE score = 10 AND id > 1")
        self.assertEqual(r.rows, [(4,)])
        self.assertEqual(self.db.execute("SELECT id FROM t WHERE score <> 10").rows, [(3,)])

    def test_order_limit(self):
        self.assertEqual(self.db.execute("SELECT id FROM t ORDER BY score").rows, [(2,), (3,), (1,), (4,)])
        self.assertEqual(self.db.execute("SELECT id FROM t ORDER BY score DESC LIMIT 2").rows, [(1,), (4,)])
        self.assertEqual(self.db.execute("SELECT name FROM t WHERE name = 'bob'").rows, [("bob",)])

    def test_errors(self):
        for bad in ["SELECT x FROM t", "SELECT * FROM nope", "SELECT * t", "SELECT * FROM t WHERE", "SELECT"]:
            with self.assertRaises(SqlError):
                self.db.execute(bad)
