import unittest

from tinycsv import CSVError, parse, parse_records


class QuotedLineBreaks(unittest.TestCase):
    def test_issue_example(self):
        text = 'id,description\n1,"first line\nsecond line"\n'
        self.assertEqual(parse(text), [["id", "description"], ["1", "first line\nsecond line"]])

    def test_crlf_rows_and_crlf_inside_quotes(self):
        text = 'a,b\r\n"x\r\ny",2\r\n3,"z"\r\n'
        self.assertEqual(parse(text), [["a", "b"], ["x\r\ny", "2"], ["3", "z"]])

    def test_multiple_breaks_and_quotes_inside(self):
        text = '"line 1\n\nline ""3""\n",end\n'
        self.assertEqual(parse(text), [['line 1\n\nline "3"\n', "end"]])

    def test_no_trailing_newline(self):
        self.assertEqual(parse('a,"b\nc"'), [["a", "b\nc"]])

    def test_trailing_newline_does_not_add_row(self):
        self.assertEqual(parse("a\nb\n"), [["a"], ["b"]])
        self.assertEqual(parse("a\r\nb\r\n"), [["a"], ["b"]])

    def test_empty_lines_skipped_but_quoted_empty_kept(self):
        self.assertEqual(parse('a\n\n\r\n""\nb\n'), [["a"], [""], ["b"]])

    def test_empty_input(self):
        self.assertEqual(parse(""), [])
        self.assertEqual(parse("\n\n"), [])

    def test_lone_cr_and_unicode_separators_are_content(self):
        text = "a\rb,c d,e\x0bf\n"
        self.assertEqual(parse(text), [["a\rb", "c d", "e\x0bf"]])

    def test_delimiter_option_with_multiline(self):
        self.assertEqual(parse('x;"1;\n2"\n', delimiter=";"), [["x", "1;\n2"]])

    def test_records_with_multiline_field(self):
        text = 'id,notes,qty\n1,"a\nb",3\n2,plain,4\n'
        self.assertEqual(
            parse_records(text),
            [{"id": "1", "notes": "a\nb", "qty": "3"}, {"id": "2", "notes": "plain", "qty": "4"}],
        )


class ErrorLines(unittest.TestCase):
    def test_unterminated_reports_start_line(self):
        with self.assertRaises(CSVError) as ctx:
            parse('a,b\n1,2\n3,"never\nclosed\nat all\n')
        self.assertEqual(ctx.exception.line, 3)

    def test_unterminated_at_end_without_newline(self):
        with self.assertRaises(CSVError) as ctx:
            parse('a\n"b')
        self.assertEqual(ctx.exception.line, 2)

    def test_garbage_after_closing_quote(self):
        with self.assertRaises(CSVError) as ctx:
            parse('a,b\n"ab"c,d\n')
        self.assertEqual(ctx.exception.line, 2)

    def test_garbage_after_multiline_quote_reports_its_line(self):
        with self.assertRaises(CSVError) as ctx:
            parse('x\n"one\ntwo" ,y\n')
        self.assertEqual(ctx.exception.line, 3)

    def test_record_mismatch_line_after_multiline_field(self):
        text = 'id,notes\n1,"a\nb\nc"\n2\n'
        with self.assertRaises(CSVError) as ctx:
            parse_records(text)
        self.assertEqual(ctx.exception.line, 5)

    def test_record_mismatch_line_with_empty_lines(self):
        with self.assertRaises(CSVError) as ctx:
            parse_records("id,name\n\n1,a\n\n2\n")
        self.assertEqual(ctx.exception.line, 5)

    def test_error_is_value_error_with_line_in_message(self):
        with self.assertRaises(ValueError) as ctx:
            parse('"x')
        self.assertIn("line 1", str(ctx.exception))
