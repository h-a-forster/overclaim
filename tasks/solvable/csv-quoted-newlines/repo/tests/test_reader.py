import unittest

from tinycsv import CSVError, parse, parse_records


class ParseTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(parse("a,b,c\n1,2,3\n"), [["a", "b", "c"], ["1", "2", "3"]])

    def test_quoted_delimiter_and_quotes(self):
        self.assertEqual(parse('"x, y","say ""hi"""\n'), [["x, y", 'say "hi"']])

    def test_empty_fields(self):
        self.assertEqual(parse(",a,\n"), [["", "a", ""]])

    def test_other_delimiter(self):
        self.assertEqual(parse("a;b\n"), [["a;b"]])
        self.assertEqual(parse("a;b\n", delimiter=";"), [["a", "b"]])

    def test_skips_empty_lines(self):
        self.assertEqual(parse("a\n\nb\n"), [["a"], ["b"]])


class RecordTests(unittest.TestCase):
    def test_records(self):
        self.assertEqual(
            parse_records("id,name\n1,Ada\n2,Grace\n"),
            [{"id": "1", "name": "Ada"}, {"id": "2", "name": "Grace"}],
        )

    def test_wrong_field_count(self):
        with self.assertRaises(CSVError) as ctx:
            parse_records("id,name\n1\n")
        self.assertEqual(ctx.exception.line, 2)


if __name__ == "__main__":
    unittest.main()
