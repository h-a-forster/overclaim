import random
import time
import unittest

from editbuf import Buffer, History


class Model:
    """Reference semantics, written for clarity (plain str + lists)."""

    def __init__(self, text=""):
        self.t = text
        self.markers = []   # [pos, gravity, alive]
        self.undo = []
        self.redo = []
        self.depth = 0
        self.group = None

    def ins(self, pos, s):
        self.t = self.t[:pos] + s + self.t[pos:]
        for m in self.markers:
            if m[0] > pos or (m[0] == pos and m[1] == "right"):
                m[0] += len(s)

    def dele(self, a, b):
        self.t = self.t[:a] + self.t[b:]
        for m in self.markers:
            if m[0] >= b:
                m[0] -= b - a
            elif m[0] > a:
                m[0] = a

    def rep(self, a, b, s):
        self.dele(a, b)
        self.ins(a, s)

    def ok_pos(self, p):
        return 0 <= p <= len(self.t)

    def ok_range(self, a, b):
        return 0 <= a <= b <= len(self.t)

    def record(self, a, old, new):
        if not old and not new:
            return
        if self.depth:
            self.group.append((a, old, new))
        else:
            self.undo.append([(a, old, new)])
        self.redo.clear()


def lines_of(t):
    return t.split("\n")


class Facts(unittest.TestCase):
    def check_lines(self, b, text):
        lines = text.split("\n")
        self.assertEqual(b.line_count(), len(lines))
        starts = [0]
        for ln in lines[:-1]:
            starts.append(starts[-1] + len(ln) + 1)
        return lines, starts


class MarkerTests(unittest.TestCase):
    def test_insert_before_at_after(self):
        b = Buffer("abcdef")
        l = b.add_marker(3)
        r = b.add_marker(3, "right")
        before = b.add_marker(1, "right")
        after = b.add_marker(5, "left")
        b.insert(3, "XY")
        self.assertEqual((l.pos, r.pos, before.pos, after.pos), (3, 5, 1, 7))
        b.insert(1, "Z")
        self.assertEqual((l.pos, r.pos, before.pos, after.pos), (4, 6, 2, 8))
        b.insert(0, "Q")
        self.assertEqual((l.pos, r.pos, before.pos, after.pos), (5, 7, 3, 9))
        self.assertEqual(b.text(), "QaZbcXYdef")

    def test_default_gravity_is_left(self):
        b = Buffer("ab")
        m = b.add_marker(1)
        self.assertEqual(m.gravity, "left")
        b.insert(1, "xx")
        self.assertEqual(m.pos, 1)

    def test_delete(self):
        b = Buffer("0123456789")
        ms = {p: b.add_marker(p, g) for p in range(0, 11) for g in ("left",)}
        rs = {p: b.add_marker(p, "right") for p in range(0, 11)}
        b.delete(3, 7)
        for p, m in ms.items():
            want = p if p <= 3 else 3 if p <= 7 else p - 4
            self.assertEqual(m.pos, want, p)
        for p, m in rs.items():
            want = p if p <= 3 else 3 if p <= 7 else p - 4
            self.assertEqual(m.pos, want, p)

    def test_replace_is_delete_then_insert(self):
        b = Buffer("0123456789")
        marks = [(p, g, b.add_marker(p, g)) for p in (2, 3, 5, 7, 8) for g in ("left", "right")]
        b.replace(3, 7, "ABC")
        for p, g, m in marks:
            if p <= 2:
                want = p
            elif p <= 3:
                want = 3 if g == "left" else 6
            elif p <= 7:
                want = 3 if g == "left" else 6
            else:
                want = p - 4 + 3
            self.assertEqual(m.pos, want, (p, g))
        self.assertEqual(b.text(), "012ABC789")

    def test_replace_with_empty_and_pure_insert(self):
        b = Buffer("abcdef")
        m = b.add_marker(4, "right")
        b.replace(1, 3, "")
        self.assertEqual((b.text(), m.pos), ("adef", 2))
        b.replace(2, 2, "ZZ")
        self.assertEqual((b.text(), m.pos), ("adZZef", 4))

    def test_remove_marker(self):
        b = Buffer("abc")
        m = b.add_marker(2)
        k = b.add_marker(2)
        b.remove_marker(m)
        b.insert(0, "xx")
        self.assertEqual((m.pos, k.pos), (2, 4))
        self.assertFalse(m.alive)
        self.assertTrue(k.alive)
        b.remove_marker(m)  # idempotent

    def test_marker_validation(self):
        b = Buffer("abc")
        for args in [(4,), (-1,), (1, "up"), (1, None)]:
            with self.assertRaises(ValueError):
                b.add_marker(*args)
        self.assertEqual(b.add_marker(3).pos, 3)
        self.assertEqual(b.add_marker(0, "right").pos, 0)

    def test_empty_edits_do_not_move_markers(self):
        b = Buffer("abc")
        r = b.add_marker(1, "right")
        b.insert(1, "")
        b.delete(1, 1)
        b.replace(1, 1, "")
        self.assertEqual((r.pos, b.text()), (1, "abc"))

    def test_many_markers_same_position(self):
        b = Buffer("x" * 10)
        ms = [b.add_marker(5, "left" if i % 2 else "right") for i in range(100)]
        b.insert(5, "yy")
        self.assertEqual([m.pos for m in ms], [7 if i % 2 == 0 else 5 for i in range(100)])


class ValidationTests(unittest.TestCase):
    def test_errors_leave_state_untouched(self):
        b = Buffer("hello")
        m = b.add_marker(2)
        for fn in [lambda: b.insert(6, "x"), lambda: b.insert(-1, "x"), lambda: b.delete(2, 1), lambda: b.delete(0, 6),
                   lambda: b.delete(-1, 2), lambda: b.replace(3, 9, "x"), lambda: b.replace(4, 2, "x"),
                   lambda: b.text(3, 2), lambda: b.text(-1), lambda: b.text(0, 6), lambda: b.offset_to_line_col(6),
                   lambda: b.offset_to_line_col(-1), lambda: b.line_text(1), lambda: b.line_text(-1),
                   lambda: b.line_col_to_offset(0, 6), lambda: b.line_col_to_offset(0, -1), lambda: b.line_range(1)]:
            with self.assertRaises(ValueError):
                fn()
        self.assertEqual((b.text(), len(b), m.pos), ("hello", 5, 2))

    def test_history_errors(self):
        b = Buffer("hello")
        h = History(b)
        for fn in [lambda: h.insert(9, "x"), lambda: h.delete(3, 9), lambda: h.replace(9, 9, "x"), lambda: h.replace(3, 2, "x")]:
            with self.assertRaises(ValueError):
                fn()
        self.assertFalse(h.can_undo)
        self.assertEqual(b.text(), "hello")


class LineTests(Facts):
    def test_basic_lines(self):
        b = Buffer("ab\n\ncde\n")
        self.assertEqual(b.line_count(), 4)
        self.assertEqual(b.line_range(1), (3, 3))
        self.assertEqual(b.line_range(3), (8, 8))
        self.assertEqual(b.offset_to_line_col(8), (3, 0))
        self.assertEqual(b.line_col_to_offset(3, 0), 8)
        self.assertEqual(Buffer("").line_count(), 1)
        self.assertEqual(Buffer("").line_range(0), (0, 0))
        self.assertEqual(Buffer("\n").line_count(), 2)
        self.assertEqual(Buffer("\r\nx\x0c\n").line_count(), 3)

    def run_sizes(self, sizes, seed, density):
        rng = random.Random(seed)
        for n in sizes:
            text = "".join("\n" if rng.random() < density else rng.choice("abcdef ") for _ in range(n))
            b = Buffer(text)
            self.assertEqual(len(b), n)
            self.assertEqual(b.text(), text)
            lines, starts = self.check_lines(b, text)
            probes = {0, n, max(0, n - 1)} | {rng.randrange(n + 1) for _ in range(60)}
            for k in (8191, 8192, 8193, 16383, 16384, 16385, 4095, 4096, 4097):
                if k <= n:
                    probes.add(k)
            for off in sorted(probes):
                line = text.count("\n", 0, off)
                col = off - (text.rfind("\n", 0, off) + 1)
                self.assertEqual(b.offset_to_line_col(off), (line, col), (n, off))
                self.assertEqual(b.line_col_to_offset(line, col), off)
            for line in {0, len(lines) - 1} | {rng.randrange(len(lines)) for _ in range(40)}:
                self.assertEqual(b.line_text(line), lines[line])
                self.assertEqual(b.line_range(line), (starts[line], starts[line] + len(lines[line])))
                with self.assertRaises(ValueError):
                    b.line_col_to_offset(line, len(lines[line]) + 1)
            for _ in range(20):
                a = rng.randrange(n + 1)
                c = rng.randrange(a, n + 1)
                self.assertEqual(b.text(a, c), text[a:c])

    def test_sizes_around_chunk_boundaries_dense_newlines(self):
        self.run_sizes([1, 100, 4097, 8191, 8192, 8193, 16384, 16385, 30000], 1, 0.2)

    def test_sizes_sparse_newlines(self):
        self.run_sizes([5000, 8192, 8193, 20000, 50000], 2, 0.0005)

    def test_no_newlines_and_only_newlines(self):
        self.run_sizes([20000], 3, 0.0)
        self.run_sizes([20000], 4, 1.0)

    def test_lines_after_edits(self):
        rng = random.Random(5)
        text = "".join(rng.choice("ab\n") for _ in range(40000))
        b = Buffer(text)
        for _ in range(300):
            p = rng.randrange(len(text) + 1)
            if rng.random() < 0.5:
                s = "".join(rng.choice("xy\n") for _ in range(rng.randrange(1, 30)))
                text = text[:p] + s + text[p:]
                b.insert(p, s)
            else:
                q = min(len(text), p + rng.randrange(0, 40))
                text = text[:p] + text[q:]
                b.delete(p, q)
        self.assertEqual(b.text(), text)
        lines, starts = self.check_lines(b, text)
        for _ in range(300):
            off = rng.randrange(len(text) + 1)
            self.assertEqual(b.offset_to_line_col(off), (text.count("\n", 0, off), off - text.rfind("\n", 0, off) - 1))


class ModelBased(unittest.TestCase):
    def compare(self, b, m, tag):
        self.assertEqual(len(b), len(m.t), tag)
        self.assertEqual(b.text(), m.t, tag)
        self.assertEqual(b.line_count(), m.t.count("\n") + 1, tag)

    def run_ops(self, seed, steps, use_history, maxlen=60, base_len=40):
        rng = random.Random(seed)
        alpha = "abc\n d"
        text = "".join(rng.choice(alpha) for _ in range(base_len))
        b = Buffer(text)
        m = Model(text)
        h = History(b) if use_history else None
        handles = []

        def rtext():
            return "".join(rng.choice(alpha) for _ in range(rng.randrange(0, 5)))

        for step in range(steps):
            n = len(m.t)
            r = rng.random()
            tag = (seed, step)
            if r < 0.22:
                pos = rng.randrange(-1, n + 3)
                s = rtext()
                if m.ok_pos(pos):
                    (h or b).insert(pos, s)
                    m.ins(pos, s)
                    if use_history:
                        m.record(pos, "", s)
                else:
                    with self.assertRaises(ValueError):
                        (h or b).insert(pos, s)
            elif r < 0.40:
                a = rng.randrange(-1, n + 2)
                c = a + rng.randrange(-1, 12)
                if m.ok_range(a, c):
                    old = m.t[a:c]
                    (h or b).delete(a, c)
                    m.dele(a, c)
                    if use_history:
                        m.record(a, old, "")
                else:
                    with self.assertRaises(ValueError):
                        (h or b).delete(a, c)
            elif r < 0.55:
                a = rng.randrange(-1, n + 2)
                c = a + rng.randrange(-1, 12)
                s = rtext()
                if m.ok_range(a, c):
                    old = m.t[a:c]
                    (h or b).replace(a, c, s)
                    m.rep(a, c, s)
                    if use_history:
                        m.record(a, old, s)
                else:
                    with self.assertRaises(ValueError):
                        (h or b).replace(a, c, s)
            elif r < 0.65:
                pos = rng.randrange(0, n + 1)
                g = rng.choice(["left", "right"])
                handles.append((b.add_marker(pos, g), [pos, g, True]))
                m.markers.append(handles[-1][1])
            elif r < 0.68 and handles:
                mk, ref = handles.pop(rng.randrange(len(handles)))
                b.remove_marker(mk)
                m.markers = [x for x in m.markers if x is not ref]
            elif use_history and r < 0.78:
                if m.depth:
                    with self.assertRaises(RuntimeError):
                        h.undo()
                else:
                    did = h.undo()
                    self.assertEqual(did, bool(m.undo), tag)
                    if m.undo:
                        entry = m.undo.pop()
                        for a, old, new in reversed(entry):
                            m.rep(a, a + len(new), old)
                        m.redo.append(entry)
            elif use_history and r < 0.86:
                if m.depth:
                    with self.assertRaises(RuntimeError):
                        h.redo()
                else:
                    did = h.redo()
                    self.assertEqual(did, bool(m.redo), tag)
                    if m.redo:
                        entry = m.redo.pop()
                        for a, old, new in entry:
                            m.rep(a, a + len(old), new)
                        m.undo.append(entry)
            elif use_history and r < 0.92:
                h.begin_group()
                if m.depth == 0:
                    m.group = []
                m.depth += 1
            elif use_history and r < 0.97:
                if m.depth == 0:
                    with self.assertRaises(RuntimeError):
                        h.end_group()
                else:
                    h.end_group()
                    m.depth -= 1
                    if m.depth == 0:
                        if m.group:
                            m.undo.append(m.group)
                        m.group = None
            if use_history:
                self.assertEqual((h.can_undo, h.can_redo), (bool(m.undo), bool(m.redo)), tag)
            self.compare(b, m, tag)
            for mk, ref in handles:
                self.assertEqual(mk.pos, ref[0], tag)
            if len(m.t) > maxlen * 3:
                a = rng.randrange(0, len(m.t) // 2)
                (h or b).delete(a, a + len(m.t) // 2)
                old = m.t[a:a + len(m.t) // 2]
                m.dele(a, a + len(old))
                if use_history:
                    m.record(a, old, "")
                self.compare(b, m, tag)
            if step % 7 == 0:
                off = rng.randrange(len(m.t) + 1)
                line = m.t.count("\n", 0, off)
                col = off - (m.t.rfind("\n", 0, off) + 1)
                self.assertEqual(b.offset_to_line_col(off), (line, col), tag)
                self.assertEqual(b.line_col_to_offset(line, col), off, tag)
                ln = rng.randrange(line + 2)
                lines = m.t.split("\n")
                if ln < len(lines):
                    self.assertEqual(b.line_text(ln), lines[ln], tag)
                else:
                    with self.assertRaises(ValueError):
                        b.line_text(ln)
        if use_history:
            while m.depth:
                h.end_group()
                m.depth -= 1
                if m.depth == 0 and m.group:
                    m.undo.append(m.group)
            while True:
                did = h.undo()
                if not did:
                    break
                entry = m.undo.pop()
                for a, old, new in reversed(entry):
                    m.rep(a, a + len(new), old)
                m.redo.append(entry)
                self.compare(b, m, "final undo")
            self.assertEqual(b.text(), m.t)

    def test_direct_edits_a(self):
        self.run_ops(1, 1500, False)

    def test_direct_edits_b(self):
        self.run_ops(2, 1500, False, base_len=5)

    def test_history_a(self):
        self.run_ops(3, 1500, True)

    def test_history_b(self):
        self.run_ops(4, 1500, True, base_len=0)

    def test_history_c(self):
        self.run_ops(5, 1500, True, maxlen=15)

    def test_history_d(self):
        self.run_ops(6, 1500, True, base_len=200)

    def test_history_e(self):
        self.run_ops(7, 3000, True, maxlen=30)


def _more_seeds():
    def mk(seed, use_history, kw):
        def t(self):
            self.run_ops(seed, 900, use_history, **kw)
        return t

    for n, seed in enumerate(range(100, 110)):
        use_history = n % 3 != 0
        kw = {"base_len": (0, 3, 25, 80)[n % 4], "maxlen": (12, 40)[n % 2]}
        setattr(ModelBased, "test_extra_seed_%d" % seed, mk(seed, use_history, kw))


_more_seeds()


class HistoryTests(unittest.TestCase):
    def test_undo_restores_text(self):
        b = Buffer("abc")
        h = History(b)
        h.insert(1, "XY")
        h.delete(0, 2)
        h.replace(1, 3, "Q")
        self.assertEqual(b.text(), "YQ")
        texts = ["abc", "aXYbc", "Ybc", "YQ"]
        self.assertTrue(h.undo())
        self.assertEqual(b.text(), texts[2])
        self.assertTrue(h.undo())
        self.assertEqual(b.text(), texts[1])
        self.assertTrue(h.undo())
        self.assertEqual(b.text(), texts[0])
        self.assertFalse(h.undo())
        for t in texts[1:]:
            self.assertTrue(h.redo())
            self.assertEqual(b.text(), t)
        self.assertFalse(h.redo())

    def test_groups(self):
        b = Buffer("abc")
        h = History(b)
        with h.group():
            h.insert(0, "1")
            h.insert(4, "2")
            h.delete(1, 2)
        h.insert(0, "z")
        self.assertEqual(b.text(), "z1bc2")
        h.undo()
        self.assertEqual(b.text(), "1bc2")
        h.undo()
        self.assertEqual(b.text(), "abc")
        h.redo()
        self.assertEqual(b.text(), "1bc2")
        h.redo()
        self.assertEqual(b.text(), "z1bc2")

    def test_nested_groups_flatten(self):
        b = Buffer("")
        h = History(b)
        h.begin_group()
        h.insert(0, "a")
        h.begin_group()
        h.insert(1, "b")
        h.end_group()
        h.insert(2, "c")
        h.end_group()
        self.assertEqual(b.text(), "abc")
        self.assertTrue(h.undo())
        self.assertEqual(b.text(), "")
        self.assertFalse(h.can_undo)

    def test_empty_group_records_nothing(self):
        b = Buffer("a")
        h = History(b)
        h.insert(1, "b")
        h.undo()
        with h.group():
            pass
        self.assertTrue(h.can_redo)
        with h.group():
            h.insert(0, "")
            h.delete(0, 0)
        self.assertTrue(h.can_redo)
        self.assertFalse(h.can_undo)

    def test_new_edit_clears_redo(self):
        b = Buffer("a")
        h = History(b)
        h.insert(1, "b")
        h.undo()
        self.assertTrue(h.can_redo)
        h.insert(0, "x")
        self.assertFalse(h.can_redo)
        self.assertFalse(h.redo())

    def test_group_edit_clears_redo_only_when_recorded(self):
        b = Buffer("a")
        h = History(b)
        h.insert(1, "b")
        h.undo()
        h.begin_group()
        h.insert(0, "x")
        h.end_group()
        self.assertFalse(h.can_redo)

    def test_group_closed_on_exception(self):
        b = Buffer("")
        h = History(b)
        with self.assertRaises(KeyError):
            with h.group():
                h.insert(0, "a")
                raise KeyError
        self.assertTrue(h.undo())
        self.assertEqual(b.text(), "")
        h.insert(0, "z")

    def test_undo_redo_inside_group_and_unbalanced_end(self):
        h = History(Buffer("a"))
        with self.assertRaises(RuntimeError):
            h.end_group()
        h.begin_group()
        with self.assertRaises(RuntimeError):
            h.undo()
        with self.assertRaises(RuntimeError):
            h.redo()
        h.end_group()
        self.assertFalse(h.undo())

    def test_markers_follow_undo_as_normal_edits(self):
        b = Buffer("0123456789")
        h = History(b)
        left = b.add_marker(5, "left")
        right = b.add_marker(5, "right")
        inside = b.add_marker(6, "left")
        h.delete(3, 8)
        self.assertEqual((left.pos, right.pos, inside.pos), (3, 3, 3))
        h.undo()
        self.assertEqual(b.text(), "0123456789")
        self.assertEqual((left.pos, right.pos, inside.pos), (3, 8, 3))
        h.redo()
        self.assertEqual((left.pos, right.pos, inside.pos), (3, 3, 3))

    def test_replace_undo_markers(self):
        b = Buffer("abcdef")
        h = History(b)
        m1 = b.add_marker(2, "right")
        m2 = b.add_marker(4, "left")
        h.replace(1, 5, "XY")
        self.assertEqual((b.text(), m1.pos, m2.pos), ("aXYf", 3, 1))
        h.undo()
        self.assertEqual((b.text(), m1.pos, m2.pos), ("abcdef", 5, 1))

    def test_history_without_markers_matches_old_behaviour(self):
        b = Buffer("abc")
        h = History(b)
        h.insert(1, "XY")
        h.delete(0, 2)
        self.assertEqual(b.text(), "Ybc")
        self.assertTrue(h.undo())
        self.assertEqual(b.text(), "aXYbc")
        self.assertTrue(h.undo())
        self.assertFalse(h.undo())
        self.assertTrue(h.redo())
        h.insert(0, "!")
        self.assertFalse(h.can_redo)


class ChunkOracle:
    """Independent simple big-text oracle: list of 64K strings."""

    def __init__(self, text):
        self.parts = [text[i:i + 65536] for i in range(0, len(text), 65536)] or [""]

    def _find(self, pos):
        for i, p in enumerate(self.parts):
            if pos <= len(p):
                return i, pos
            pos -= len(p)
        raise AssertionError

    def insert(self, pos, s):
        i, o = self._find(pos)
        self.parts[i] = self.parts[i][:o] + s + self.parts[i][o:]

    def delete(self, a, b):
        i, o = self._find(a)
        need = b - a
        while need:
            p = self.parts[i]
            take = min(need, len(p) - o)
            self.parts[i] = p[:o] + p[o + take:]
            need -= take
            i += 1
            o = 0

    def text(self):
        return "".join(self.parts)


class Performance(unittest.TestCase):
    def big_text(self, lines):
        return "".join("line %d some text here\n" % i for i in range(lines))

    def test_big_buffer_many_edits(self):
        rng = random.Random(77)
        text = self.big_text(150000)
        t0 = time.perf_counter()
        b = Buffer(text)
        marks = [b.add_marker(rng.randrange(len(text)), rng.choice(["left", "right"])) for _ in range(20)]
        oracle = ChunkOracle(text)
        n = len(text)
        edits = []
        for i in range(20000):
            p = rng.randrange(n + 1)
            if i % 3 == 0:
                s = "xyz\n"
                edits.append(("i", p, s))
                n += len(s)
            elif i % 3 == 1:
                q = min(n, p + 5)
                edits.append(("d", p, q))
                n -= q - p
            else:
                edits.append(("i", p, "q"))
                n += 1
        start = time.perf_counter()
        for kind, p, x in edits:
            if kind == "i":
                b.insert(p, x)
            else:
                b.delete(p, x)
            if time.perf_counter() - start > 12.0:
                self.fail("edits are far too slow")
        elapsed = time.perf_counter() - start
        for kind, p, x in edits:
            if kind == "i":
                oracle.insert(p, x)
            else:
                oracle.delete(p, x)
        self.assertLess(elapsed, 6.0)
        self.assertEqual(len(b), n)
        self.assertEqual(b.text(), oracle.text())
        for mk in marks:
            self.assertTrue(0 <= mk.pos <= n)

    def test_big_buffer_line_queries(self):
        rng = random.Random(78)
        text = self.big_text(150000)
        b = Buffer(text)
        starts = None
        t = time.perf_counter()
        for _ in range(3000):
            off = rng.randrange(len(text) + 1)
            line, col = b.offset_to_line_col(off)
            self.assertEqual(b.line_col_to_offset(line, col), off)
            self.assertLess(time.perf_counter() - t, 12.0)
        for _ in range(2000):
            ln = rng.randrange(150001)
            s, e = b.line_range(ln)
            self.assertLess(time.perf_counter() - t, 12.0)
            if ln < 150000:
                self.assertEqual(text[s:e], "line %d some text here" % ln)
            else:
                self.assertEqual((s, e), (len(text), len(text)))
        self.assertEqual(b.line_count(), 150001)
        self.assertLess(time.perf_counter() - t, 5.0)

    def test_interleaved_edits_and_queries_with_history(self):
        rng = random.Random(79)
        b = Buffer(self.big_text(100000))
        h = History(b)
        n0 = len(b)
        t = time.perf_counter()
        for i in range(8000):
            p = rng.randrange(len(b) + 1)
            h.insert(p, "ab\ncd")
            if i % 4 == 0:
                line, col = b.offset_to_line_col(rng.randrange(len(b) + 1))
                self.assertGreaterEqual(col, 0)
            if i % 5 == 0:
                q = rng.randrange(len(b))
                h.delete(q, min(len(b), q + 7))
            self.assertLess(time.perf_counter() - t, 16.0)
        while h.undo():
            pass
        self.assertEqual(len(b), n0)
        self.assertLess(time.perf_counter() - t, 8.0)
        self.assertEqual(b.text(0, 30), "line 0 some text here\nline 1 s")
        while h.redo():
            pass
        self.assertGreater(len(b), n0)

    def test_construct_and_read_huge_text(self):
        text = "abc\n" * 1500000
        t = time.perf_counter()
        b = Buffer(text)
        self.assertEqual(len(b), 6000000)
        self.assertEqual(b.line_count(), 1500001)
        self.assertEqual(b.text(5999990, 6000000), "c\n" + "abc\n" * 2)
        self.assertEqual(b.offset_to_line_col(6000000), (1500000, 0))
        self.assertLess(time.perf_counter() - t, 5.0)

    def test_one_huge_line_edits(self):
        rng = random.Random(80)
        text = "x" * 3000000
        b = Buffer(text)
        n = len(text)
        t = time.perf_counter()
        for _ in range(6000):
            p = rng.randrange(n + 1)
            b.insert(p, "y")
            n += 1
            self.assertLess(time.perf_counter() - t, 12.0)
        self.assertLess(time.perf_counter() - t, 4.0)
        self.assertEqual(b.offset_to_line_col(n), (0, n))
        self.assertEqual(b.text().count("y"), 6000)


if __name__ == "__main__":
    unittest.main()
