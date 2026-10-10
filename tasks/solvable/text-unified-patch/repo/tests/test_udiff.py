import unittest

from udiff import PatchError, apply_patch, parse_patch

PATCH = """\
diff --git a/x.txt b/x.txt
index 111..222 100644
--- a/x.txt
+++ b/x.txt
@@ -1,3 +1,3 @@
 one
-two
+TWO
 three
"""


class ParseTests(unittest.TestCase):
    def test_parse(self):
        (fp,) = parse_patch(PATCH)
        self.assertEqual((fp.old_path, fp.new_path), ("a/x.txt", "b/x.txt"))
        (h,) = fp.hunks
        self.assertEqual((h.old_start, h.old_len, h.new_start, h.new_len), (1, 3, 1, 3))
        self.assertEqual(h.lines, [(" ", "one"), ("-", "two"), ("+", "TWO"), (" ", "three")])

    def test_default_counts(self):
        (fp,) = parse_patch("--- a/f\n+++ b/f\n@@ -2 +2 @@\n-x\n+y\n")
        self.assertEqual((fp.hunks[0].old_len, fp.hunks[0].new_len), (1, 1))

    def test_multiple_files(self):
        text = PATCH + "--- a/y.txt\n+++ b/y.txt\n@@ -1 +1 @@\n-a\n+b\n"
        self.assertEqual([f.new_path for f in parse_patch(text)], ["b/x.txt", "b/y.txt"])


class ApplyTests(unittest.TestCase):
    def test_modify(self):
        self.assertEqual(apply_patch({"x.txt": "one\ntwo\nthree\n"}, PATCH), {"x.txt": "one\nTWO\nthree\n"})

    def test_input_untouched(self):
        files = {"x.txt": "one\ntwo\nthree\n"}
        apply_patch(files, PATCH)
        self.assertEqual(files, {"x.txt": "one\ntwo\nthree\n"})

    def test_create_and_delete(self):
        create = "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,2 @@\n+a\n+b\n"
        self.assertEqual(apply_patch({}, create), {"new.txt": "a\nb\n"})
        delete = "--- a/old.txt\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-a\n-b\n"
        self.assertEqual(apply_patch({"old.txt": "a\nb\n", "k": "1\n"}, delete), {"k": "1\n"})

    def test_two_hunks(self):
        text = "--- a/f\n+++ b/f\n@@ -1,2 +1,2 @@\n-a\n+A\n b\n@@ -4,2 +4,2 @@\n d\n-e\n+E\n"
        self.assertEqual(apply_patch({"f": "a\nb\nc\nd\ne\n"}, text), {"f": "A\nb\nc\nd\nE\n"})

    def test_mismatch(self):
        with self.assertRaises(PatchError) as ctx:
            apply_patch({"x.txt": "one\nzzz\nthree\n"}, PATCH)
        self.assertEqual((ctx.exception.file, ctx.exception.hunk), ("x.txt", 1))

    def test_missing_file(self):
        with self.assertRaises(PatchError):
            apply_patch({}, PATCH)


if __name__ == "__main__":
    unittest.main()
