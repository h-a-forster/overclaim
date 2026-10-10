import unittest

from editbuf import Buffer, History


class Basics(unittest.TestCase):
    def test_edit(self):
        b = Buffer("hello world")
        b.insert(5, ",")
        b.delete(0, 1)
        self.assertEqual(b.text(), "ello, world")
        self.assertEqual(len(b), 11)
        self.assertEqual(b.text(1, 4), "llo")
        for bad in (lambda: b.insert(12, "x"), lambda: b.delete(3, 2), lambda: b.text(0, 99)):
            with self.assertRaises(ValueError):
                bad()

    def test_lines(self):
        b = Buffer("ab\n\ncde\n")
        self.assertEqual(b.line_count(), 4)
        self.assertEqual([b.line_text(i) for i in range(4)], ["ab", "", "cde", ""])
        self.assertEqual(b.offset_to_line_col(0), (0, 0))
        self.assertEqual(b.offset_to_line_col(2), (0, 2))
        self.assertEqual(b.offset_to_line_col(3), (1, 0))
        self.assertEqual(b.offset_to_line_col(8), (3, 0))
        self.assertEqual(b.line_col_to_offset(2, 3), 7)
        self.assertEqual(b.line_range(2), (4, 7))
        with self.assertRaises(ValueError):
            b.line_col_to_offset(0, 3)

    def test_history(self):
        b = Buffer("abc")
        h = History(b)
        h.insert(1, "XY")
        h.delete(0, 2)
        self.assertEqual(b.text(), "Yabc"[0:0] + "Ybc")
        self.assertTrue(h.undo())
        self.assertEqual(b.text(), "aXYbc")
        self.assertTrue(h.undo())
        self.assertEqual(b.text(), "abc")
        self.assertFalse(h.undo())
        self.assertTrue(h.redo())
        self.assertEqual(b.text(), "aXYbc")
        h.insert(0, "!")
        self.assertFalse(h.can_redo)
