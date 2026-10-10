import unittest

from udiff import PatchError, apply_patch, parse_patch


def hdr(old="a/f", new="b/f"):
    return f"--- {old}\n+++ {new}\n"


def parse_error(text):
    with unittest.TestCase().assertRaises(PatchError) as ctx:
        parse_patch(text)
    return ctx.exception


def apply_error(files, text, **kw):
    with unittest.TestCase().assertRaises(PatchError) as ctx:
        apply_patch(files, text, **kw)
    return ctx.exception


LINES = "".join(f"l{i}\n" for i in range(1, 21))


class NoNewline(unittest.TestCase):
    def test_remove_final_newline(self):
        p = hdr() + "@@ -1,2 +1,2 @@\n a\n-b\n+b\n\\ No newline at end of file\n"
        self.assertEqual(apply_patch({"f": "a\nb\n"}, p), {"f": "a\nb"})

    def test_add_final_newline(self):
        p = hdr() + "@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+b\n"
        self.assertEqual(apply_patch({"f": "a\nb"}, p), {"f": "a\nb\n"})

    def test_context_marker_applies_to_both_sides(self):
        p = hdr() + "@@ -1,2 +1,3 @@\n a\n-b\n+B\n+c\n"
        self.assertEqual(apply_patch({"f": "a\nb\n"}, p), {"f": "a\nB\nc\n"})
        p = hdr() + "@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+B\n\\ No newline at end of file\n"
        self.assertEqual(apply_patch({"f": "a\nb"}, p), {"f": "a\nB"})
        p = hdr() + "@@ -1,2 +1,2 @@\n-a\n+A\n b\n\\ No newline at end of file\n"
        self.assertEqual(apply_patch({"f": "a\nb"}, p), {"f": "A\nb"})

    def test_terminator_mismatch_does_not_match(self):
        p = hdr() + "@@ -1,2 +1,2 @@\n a\n-b\n+B\n"
        e = apply_error({"f": "a\nb"}, p)
        self.assertEqual((e.file, e.hunk), ("f", 1))
        p = hdr() + "@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+B\n"
        e = apply_error({"f": "a\nb\n"}, p)
        self.assertEqual(e.hunk, 1)

    def test_append_after_unterminated_line(self):
        p = hdr() + "@@ -1 +1,2 @@\n-a\n\\ No newline at end of file\n+a\n+b\n"
        self.assertEqual(apply_patch({"f": "a"}, p), {"f": "a\nb\n"})

    def test_create_without_newline(self):
        p = "--- /dev/null\n+++ b/n\n@@ -0,0 +1,2 @@\n+x\n+y\n\\ No newline at end of file\n"
        self.assertEqual(apply_patch({}, p), {"n": "x\ny"})

    def test_delete_unterminated_file(self):
        p = "--- a/n\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-x\n-y\n\\ No newline at end of file\n"
        self.assertEqual(apply_patch({"n": "x\ny", "k": "1\n"}, p), {"k": "1\n"})

    def test_marker_before_next_hunk_and_file(self):
        p = (hdr("a/f", "b/f") + "@@ -1 +1 @@\n-a\n\\ No newline at end of file\n+A\n\\ No newline at end of file\n"
             + hdr("a/g", "b/g") + "@@ -1 +1 @@\n-x\n+y\n")
        self.assertEqual(apply_patch({"f": "a", "g": "x\n"}, p), {"f": "A", "g": "y\n"})

    def test_marker_not_counted_and_misplaced(self):
        (fp,) = parse_patch(hdr() + "@@ -1,2 +1,2 @@\n a\n-b\n\\ x\n+c\n\\ x\n")
        self.assertEqual(len(fp.hunks), 1)
        self.assertEqual([t for t, _ in fp.hunks[0].lines], [" ", "-", "+"])
        e = parse_error(hdr() + "@@ -1 +1 @@\n\\ No newline at end of file\n-a\n+b\n")
        self.assertEqual(e.line, 4)

    def test_only_last_line_may_be_unterminated(self):
        p = hdr() + "@@ -1,2 +1,2 @@\n-a\n\\ No newline at end of file\n+A\n b\n"
        e = apply_error({"f": "a\nb\n"}, p)
        self.assertEqual(e.hunk, 1)


class ParseDetails(unittest.TestCase):
    def test_header_paths(self):
        (fp,) = parse_patch("--- a/x y.txt\t2020-01-01 10:00:00\n+++ b/x y.txt  \n@@ -1 +1 @@\n-a\n+b\n")
        self.assertEqual((fp.old_path, fp.new_path), ("a/x y.txt", "b/x y.txt"))

    def test_crlf_patch_text(self):
        p = "--- a/f\r\n+++ b/f\r\n@@ -1,2 +1,2 @@\r\n a\r\n-b\r\n+B\r\n"
        self.assertEqual(apply_patch({"f": "a\r\nb\r\n"}, p), {"f": "a\r\nB\r\n"})

    def test_removed_line_looking_like_header(self):
        p = hdr() + "@@ -1,3 +1,1 @@\n a\n--- b\n-c\n"
        self.assertEqual(apply_patch({"f": "a\n-- b\nc\n"}, p), {"f": "a\n"})
        (fp,) = parse_patch(p)
        self.assertEqual(len(fp.hunks[0].lines), 3)

    def test_added_line_looking_like_header(self):
        p = hdr() + "@@ -1,1 +1,3 @@\n a\n+++ b\n+@@ -1 +1 @@\n"
        self.assertEqual(apply_patch({"f": "a\n"}, p), {"f": "a\n++ b\n@@ -1 +1 @@\n"})

    def test_empty_line_is_empty_context(self):
        p = hdr() + "@@ -1,3 +1,3 @@\n a\n\n-c\n+C\n"
        self.assertEqual(apply_patch({"f": "a\n\nc\n"}, p), {"f": "a\n\nC\n"})

    def test_trailing_junk_ignored(self):
        p = hdr() + "@@ -1 +1 @@\n-a\n+b\nsome trailing text\n-- \n2.40.0\n"
        self.assertEqual(apply_patch({"f": "a\n"}, p), {"f": "b\n"})

    def test_no_file_patches(self):
        self.assertEqual(parse_patch("hello\nworld\n"), [])
        files = {"a": "1\n"}
        out = apply_patch(files, "")
        self.assertEqual(out, files)
        self.assertIsNot(out, files)

    def test_counts_default_and_zero(self):
        (fp,) = parse_patch("--- /dev/null\n+++ b/n\n@@ -0,0 +1 @@\n+x\n")
        h = fp.hunks[0]
        self.assertEqual((h.old_start, h.old_len, h.new_start, h.new_len), (0, 0, 1, 1))

    def test_hunk_before_header(self):
        self.assertEqual(parse_error("junk\n@@ -1 +1 @@\n-a\n+b\n").line, 2)

    def test_bad_line_in_hunk(self):
        self.assertEqual(parse_error(hdr() + "@@ -1,2 +1,2 @@\n a\nxb\n").line, 5)
        self.assertEqual(parse_error(hdr() + "@@ -1,2 +1,2 @@\n a\n@@ -5 +5 @@\n-q\n+r\n").line, 5)
        self.assertEqual(parse_error(hdr() + "@@ -1,2 +1,2 @@\n a\ndiff --git a/g b/g\n").line, 5)
        self.assertEqual(parse_error(hdr() + "@@ -1,2 +1,2 @@\n a\n!\n").line, 5)

    def test_truncated_hunk(self):
        self.assertEqual(parse_error(hdr() + "@@ -1,3 +1,3 @@\n a\n b\n").line, 3)
        self.assertEqual(parse_error("x\n" + hdr() + "@@ -1,3 +1,3 @@\n").line, 4)
        self.assertEqual(parse_error(hdr() + "@@ -1 +1,2 @@\n-a\n+b\n").line, 3)

    def test_overlong_hunk_side(self):
        self.assertEqual(parse_error(hdr() + "@@ -1 +1,2 @@\n a\n b\n").line, 5)
        self.assertEqual(parse_error(hdr() + "@@ -1,2 +1 @@\n a\n+b\n").line, 5)

    def test_parse_errors_have_no_file(self):
        e = parse_error(hdr() + "@@ -1,3 +1,3 @@\n a\n")
        self.assertIsNone(e.file)
        self.assertIsNone(e.hunk)
        self.assertIsInstance(e, ValueError)


class OffsetSearch(unittest.TestCase):
    def test_shifted_forward_and_back(self):
        p = hdr() + "@@ -5,3 +5,3 @@\n l5\n-l6\n+X6\n l7\n"
        shifted_down = "new1\nnew2\n" + LINES
        out = apply_patch({"f": shifted_down}, p)["f"]
        self.assertEqual(out, shifted_down.replace("l6\n", "X6\n"))
        shifted_up = "".join(f"l{i}\n" for i in range(4, 21))
        out = apply_patch({"f": shifted_up}, p)["f"]
        self.assertEqual(out, shifted_up.replace("l6\n", "X6\n"))

    def test_drift_carries_to_next_hunk(self):
        p = (hdr() + "@@ -3,3 +3,3 @@\n l3\n-l4\n+X4\n l5\n"
             "@@ -12,3 +12,3 @@\n l12\n-l13\n+X13\n l14\n")
        text = "a\nb\nc\n" + LINES
        out = apply_patch({"f": text}, p)["f"]
        self.assertEqual(out, text.replace("l4\n", "X4\n").replace("l13\n", "X13\n"))

    def test_nearest_candidate_wins_and_ties_go_earlier(self):
        text = "x\ny\nz\nx\ny\nz\nq\nx\ny\nz\n"
        p = hdr() + "@@ -4,2 +4,2 @@\n x\n-y\n+Y\n"
        out = apply_patch({"f": text}, p)["f"]
        self.assertEqual(out, "x\ny\nz\nx\nY\nz\nq\nx\ny\nz\n")
        # expected index 5: candidates 3 (distance 2) and 7 (distance 2) -> earlier one
        p = hdr() + "@@ -6,2 +6,2 @@\n x\n-y\n+Y\n"
        out = apply_patch({"f": text}, p)["f"]
        self.assertEqual(out, "x\ny\nz\nx\nY\nz\nq\nx\ny\nz\n")
        p = hdr() + "@@ -7,2 +7,2 @@\n x\n-y\n+Y\n"
        out = apply_patch({"f": text}, p)["f"]
        self.assertEqual(out, "x\ny\nz\nx\ny\nz\nq\nx\nY\nz\n")

    def test_no_overlap_with_previous_hunk(self):
        text = "a\nb\na\nb\n"
        p = hdr() + "@@ -1,2 +1,2 @@\n-a\n+A\n b\n@@ -1,2 +1,2 @@\n-a\n+A2\n b\n"
        self.assertEqual(apply_patch({"f": text}, p)["f"], "A\nb\nA2\nb\n")
        text2 = "a\nb\n"
        e = apply_error({"f": text2}, p)
        self.assertEqual(e.hunk, 2)

    def test_hunk_further_than_file_still_found(self):
        text = "\n".join(f"w{i}" for i in range(100)) + "\n"
        p = hdr() + "@@ -2,2 +2,2 @@\n w97\n-w98\n+W98\n"
        out = apply_patch({"f": text}, p)["f"]
        self.assertIn("W98\n", out)
        self.assertNotIn("w98\n", out)

    def test_failure_reports_file_and_hunk(self):
        p = (hdr() + "@@ -1,2 +1,2 @@\n l1\n-l2\n+X2\n@@ -10,2 +10,2 @@\n l10\n-nope\n+X\n")
        e = apply_error({"f": LINES}, p)
        self.assertEqual((e.file, e.hunk), ("f", 2))
        self.assertIsNone(e.line)

    def test_insertion_only_hunks(self):
        p = hdr() + "@@ -2,0 +3,1 @@\n+ins\n"
        self.assertEqual(apply_patch({"f": "a\nb\nc\n"}, p)["f"], "a\nb\nins\nc\n")
        p = hdr() + "@@ -0,0 +1,1 @@\n+top\n"
        self.assertEqual(apply_patch({"f": "a\n"}, p)["f"], "top\na\n")
        p = hdr() + "@@ -50,0 +51,1 @@\n+tail\n"
        self.assertEqual(apply_patch({"f": "a\nb\n"}, p)["f"], "a\nb\ntail\n")

    def test_insertion_after_drift(self):
        p = (hdr() + "@@ -2,2 +2,2 @@\n l2\n-l3\n+X3\n@@ -8,0 +9,1 @@\n+ins\n")
        text = "new\n" + LINES
        out = apply_patch({"f": text}, p)["f"]
        lines = out.split("\n")
        self.assertEqual(lines.index("X3"), 3)
        self.assertEqual(lines.index("ins"), 9)

    def test_ambiguous_context_prefers_nominal(self):
        text = "dup\ndup\ndup\ndup\n"
        p = hdr() + "@@ -3,1 +3,1 @@\n-dup\n+DUP\n"
        self.assertEqual(apply_patch({"f": text}, p)["f"], "dup\ndup\nDUP\ndup\n")


class FileOps(unittest.TestCase):
    def test_create_existing_fails(self):
        p = "--- /dev/null\n+++ b/n\n@@ -0,0 +1 @@\n+x\n"
        e = apply_error({"n": "old\n"}, p)
        self.assertEqual(e.file, "n")

    def test_delete_requires_empty_remainder(self):
        p = "--- a/n\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-x\n"
        e = apply_error({"n": "x\ny\n"}, p)
        self.assertEqual(e.file, "n")
        self.assertEqual(apply_patch({"n": "x\n"}, p), {})

    def test_modify_missing_file(self):
        e = apply_error({}, hdr() + "@@ -1 +1 @@\n-a\n+b\n")
        self.assertEqual(e.file, "f")

    def test_rename_with_changes(self):
        p = "--- a/old.txt\n+++ b/new.txt\n@@ -1,2 +1,2 @@\n a\n-b\n+B\n"
        out = apply_patch({"old.txt": "a\nb\n", "k": "1\n"}, p)
        self.assertEqual(out, {"new.txt": "a\nB\n", "k": "1\n"})

    def test_pure_rename_and_collision(self):
        p = "--- a/old.txt\n+++ b/new.txt\n"
        self.assertEqual(apply_patch({"old.txt": "z"}, p), {"new.txt": "z"})
        e = apply_error({"old.txt": "z", "new.txt": "q"}, p)
        self.assertEqual(e.file, "new.txt")

    def test_sequential_patches_see_previous_results(self):
        p = (hdr("a/f", "b/g") + "@@ -1 +1 @@\n-a\n+b\n" + hdr("a/g", "b/g") + "@@ -1 +1 @@\n-b\n+c\n")
        self.assertEqual(apply_patch({"f": "a\n"}, p), {"g": "c\n"})

    def test_strip_levels(self):
        p = "--- a/dir/x.txt\n+++ b/dir/x.txt\n@@ -1 +1 @@\n-a\n+b\n"
        self.assertEqual(apply_patch({"dir/x.txt": "a\n"}, p), {"dir/x.txt": "b\n"})
        self.assertEqual(apply_patch({"x.txt": "a\n"}, p, strip=2), {"x.txt": "b\n"})
        self.assertEqual(apply_patch({"x.txt": "a\n"}, p, strip=5), {"x.txt": "b\n"})
        q = "--- x.txt\n+++ x.txt\n@@ -1 +1 @@\n-a\n+b\n"
        self.assertEqual(apply_patch({"x.txt": "a\n"}, q, strip=0), {"x.txt": "b\n"})

    def test_dev_null_not_stripped_with_strip_2(self):
        p = "--- /dev/null\n+++ b/d/n\n@@ -0,0 +1 @@\n+x\n"
        self.assertEqual(apply_patch({}, p, strip=2), {"n": "x\n"})

    def test_atomic_on_error(self):
        files = {"f": "a\n", "g": "zzz\n"}
        p = hdr("a/f", "b/f") + "@@ -1 +1 @@\n-a\n+b\n" + hdr("a/g", "b/g") + "@@ -1 +1 @@\n-nope\n+x\n"
        e = apply_error(files, p)
        self.assertEqual((e.file, e.hunk), ("g", 1))
        self.assertEqual(files, {"f": "a\n", "g": "zzz\n"})

    def test_empty_file_edits(self):
        p = hdr() + "@@ -0,0 +1,2 @@\n+a\n+b\n"
        self.assertEqual(apply_patch({"f": ""}, p), {"f": "a\nb\n"})


class Reverse(unittest.TestCase):
    def test_reverse_modify(self):
        p = hdr() + "@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n"
        self.assertEqual(apply_patch({"f": "a\nB\nc\n"}, p, reverse=True), {"f": "a\nb\nc\n"})

    def test_reverse_roundtrip_with_markers(self):
        p = hdr() + "@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+b\n"
        before = {"f": "a\nb"}
        after = apply_patch(before, p)
        self.assertEqual(after, {"f": "a\nb\n"})
        self.assertEqual(apply_patch(after, p, reverse=True), before)

    def test_reverse_create_and_delete(self):
        create = "--- /dev/null\n+++ b/n\n@@ -0,0 +1,2 @@\n+x\n+y\n"
        self.assertEqual(apply_patch({"n": "x\ny\n", "k": "1\n"}, create, reverse=True), {"k": "1\n"})
        delete = "--- a/n\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-x\n-y\n"
        self.assertEqual(apply_patch({}, delete, reverse=True), {"n": "x\ny\n"})

    def test_reverse_rename_and_order(self):
        p = (hdr("a/f", "b/g") + "@@ -1 +1 @@\n-a\n+b\n" + hdr("a/g", "b/g") + "@@ -1 +1 @@\n-b\n+c\n")
        self.assertEqual(apply_patch({"g": "c\n"}, p, reverse=True), {"f": "a\n"})

    def test_reverse_uses_new_positions_and_offsets(self):
        p = hdr() + "@@ -5,3 +7,3 @@\n l5\n-l6\n+X6\n l7\n"
        text = LINES.replace("l6\n", "X6\n")
        padded = "p1\np2\n" + text
        self.assertEqual(apply_patch({"f": padded}, p, reverse=True)["f"], "p1\np2\n" + LINES)

    def test_reverse_multi_hunk_roundtrip(self):
        p = ("--- a/f\n+++ b/f\n@@ -1,3 +1,4 @@\n l1\n+ins\n l2\n l3\n"
             "@@ -9,3 +10,2 @@\n l9\n-l10\n l11\n")
        after = apply_patch({"f": LINES}, p)
        self.assertNotEqual(after["f"], LINES)
        self.assertEqual(apply_patch(after, p, reverse=True), {"f": LINES})


if __name__ == "__main__":
    unittest.main()
