import random
import re
import time
import unittest

import minire
from minire import PatternError


def ours(m, n):
    if m is None:
        return None
    return (m.span(), tuple(m.span(i) for i in range(n + 1)), m.groups(), m.group(0))


def theirs(m, n):
    if m is None:
        return None
    return (m.span(), tuple(m.span(i) for i in range(n + 1)), m.groups(), m.group(0))


class Agree(unittest.TestCase):
    def agree(self, pat, strings):
        p = minire.compile(pat)
        r = re.compile(pat)
        self.assertEqual(p.groups, r.groups, pat)
        for s in strings:
            for name in ("match", "search", "fullmatch"):
                a = ours(getattr(p, name)(s), r.groups)
                b = theirs(getattr(r, name)(s), r.groups)
                self.assertEqual(a, b, (pat, s, name))


class Groups(Agree):
    def test_capture_basic(self):
        self.agree(r"(a)(b)(c)", ["abc", "xabcx", "ab"])

    def test_nested_groups_numbering(self):
        self.agree(r"((a)(b(c)))d", ["abcd", "zabcdz"])

    def test_noncapturing(self):
        self.agree(r"(?:ab)+(c)", ["ababc", "abc", "c"])

    def test_unset_group(self):
        self.agree(r"(a)|(b)", ["a", "b", "c"])
        self.agree(r"(a)?b", ["ab", "b"])

    def test_group_last_iteration(self):
        self.agree(r"(a|b)+", ["abab", "bba"])
        self.agree(r"(?:(a)|b)+", ["ab", "ba", "bb"])

    def test_group_api(self):
        m = minire.search(r"(\d+)-(\d+)?", "x12-y")
        self.assertEqual(m.groups(), ("12", None))
        self.assertEqual(m.group(1), "12")
        self.assertIsNone(m.group(2))
        self.assertEqual(m.span(2), (-1, -1))
        self.assertEqual((m.start(1), m.end(1)), (1, 3))
        self.assertEqual((m.start(2), m.end(2)), (-1, -1))
        self.assertEqual(minire.compile("(a)(b)").groups, 2)
        self.assertEqual(minire.compile("a").groups, 0)
        self.assertEqual(minire.search("a", "a").groups(), ())

    def test_bad_group_index(self):
        m = minire.search(r"(a)", "a")
        for bad in (2, -1):
            with self.assertRaises(IndexError):
                m.group(bad)
            with self.assertRaises(IndexError):
                m.span(bad)


class Alternation(Agree):
    def test_leftmost_alternative_wins(self):
        self.agree(r"a|ab", ["ab", "abc"])
        self.agree(r"(a|ab)(c|bcd)(d*)", ["abcd"])

    def test_alternation_backtracks(self):
        self.agree(r"(a|ab)c", ["abc"])
        self.agree(r"^(a|ab)$", ["ab"])

    def test_empty_branches(self):
        self.agree(r"a|", ["a", "b", ""])
        self.agree(r"|a", ["a", "b"])
        self.agree(r"(|a)b", ["ab", "b"])
        self.agree(r"()", ["", "x"])

    def test_alternation_precedence(self):
        self.agree(r"ab|cd", ["ab", "cd", "abcd", "ac"])
        self.agree(r"x(?:ab|cd)y", ["xaby", "xcdy", "xacy"])

    def test_nested_alternation(self):
        self.agree(r"((a|b)c|d(e|f))+", ["acbcdf", "dedf", "ac", "x"])


class Quantifiers(Agree):
    def test_lazy(self):
        self.agree(r"a*?b", ["aaab", "b"])
        self.agree(r"a+?", ["aaa"])
        self.agree(r"a??b", ["ab", "b"])
        self.agree(r"<.+?>", ["<a><b>"])
        self.agree(r"<.+>", ["<a><b>"])
        self.agree(r"(a+?)(a*)", ["aaaa"])

    def test_counted(self):
        self.agree(r"a{3}", ["aa", "aaa", "aaaa"])
        self.agree(r"a{2,}", ["a", "aa", "aaaaa"])
        self.agree(r"a{1,3}", ["aaaaa", "a"])
        self.agree(r"a{0}b", ["b", "ab"])
        self.agree(r"a{,2}b", ["aaab", "b"])
        self.agree(r"(ab){2,3}", ["abababab", "ab"])

    def test_counted_lazy(self):
        self.agree(r"a{1,3}?", ["aaa"])
        self.agree(r"a{2,}?b", ["aaaab"])
        self.agree(r"(a{1,2}?)(a{1,2})", ["aaa", "aaaa"])

    def test_counted_group_captures(self):
        self.agree(r"(a|b){3}", ["abba", "aba"])
        self.agree(r"(?:(a)|(b)){2,3}", ["aab", "bb", "ba"])

    def test_literal_braces(self):
        self.agree(r"a{", ["a{"])
        self.agree(r"a{x}", ["a{x}"])
        self.agree(r"a{1", ["a{1"])
        self.agree(r"{}", ["{}"])
        self.agree(r"a{1,x}", ["a{1,x}"])
        self.agree(r"}", ["}"])

    def test_braces_leading_quantifier_forms(self):
        self.agree(r"a{,}", ["", "aaa"])

    def test_big_counts(self):
        self.agree(r"a{50,200}", ["a" * 30, "a" * 120, "a" * 300])
        self.agree(r"(?:ab){100}", ["ab" * 120])

    def test_greedy_backtracking_interplay(self):
        self.agree(r"(a*)(ab)*(b*)", ["aabb", "abab", "bb"])
        self.agree(r"a*(a|b)*c", ["aabbac", "c"])

    def test_nullable_loop_terminates(self):
        # only the overall span is compared for bodies that can match the empty string
        for pat, subj in [(r"(a*)*b", "aaab"), (r"(a|)*c", "aaac"), (r"(?:a?)*b", "aab"),
                          (r"(a*)+$", "aaa"), (r"(?:a*|b)*c", "abac"), (r"(a?){3,}", "aa"),
                          (r"(?:^)*a", "a"), (r"(?:a*?)*b", "aab")]:
            p = minire.compile(pat)
            m1, m2 = p.search(subj), re.search(pat, subj)
            self.assertEqual(m1.span() if m1 else None, m2.span() if m2 else None, pat)


class Anchors(Agree):
    def test_anchors(self):
        self.agree(r"^a", ["a", "ba", "aa"])
        self.agree(r"a$", ["a", "ab", "ba", "aa"])
        self.agree(r"^$", ["", "a"])
        self.agree(r"^a*$", ["", "aaa", "aab"])
        self.agree(r"(^a|b$)+", ["ab", "bb", "aa"])
        self.agree(r"a|^b", ["b", "cb", "ca"])

    def test_dollar_is_strict_end(self):
        self.assertIsNone(minire.search(r"a$", "a\n"))
        self.assertEqual(minire.search(r"a\n$", "a\n").span(), (0, 2))
        self.assertEqual(minire.search(r"^b", "a\nb"), None)

    def test_caret_ignores_pos(self):
        p = minire.compile(r"^b")
        self.assertIsNone(p.search("ab", 1))
        self.assertIsNone(p.match("ab", 1))
        self.assertEqual(minire.compile(r"b").match("ab", 1).span(), (1, 2))
        self.assertEqual(minire.compile(r"b|c").search("abc", 2).span(), (2, 3))

    def test_dot_newline(self):
        self.assertEqual(minire.search(r"a.*b", "xa\nbab").span(), (4, 6))
        self.assertIsNone(minire.fullmatch(r".*", "a\nb"))


class Backrefs(Agree):
    def test_simple(self):
        self.agree(r"(a+)\1", ["aaaa", "aaa", "aa", "a"])
        self.agree(r"(.)\1", ["abccd", "ab"])
        self.agree(r"(a|b)\1", ["aa", "bb", "ab"])

    def test_unset_backref_fails(self):
        self.agree(r"(a)?b\1", ["b", "aba", "ab"])
        self.agree(r"(?:(a)|b)\1", ["aa", "b"])

    def test_multiple(self):
        self.agree(r"(a)(b)\2\1", ["abba", "abab"])
        self.agree(r"((a)b)\1\2", ["ababa", "abab"])

    def test_backref_after_loop(self):
        self.agree(r"(?:(a)|(b))+\1", ["aba", "abab", "bbb"])
        self.agree(r"([ab])+\1", ["abb", "aba", "aab"])

    def test_backref_backtracks(self):
        self.agree(r"(a*)b\1", ["aabaa", "aaba", "b"])
        self.agree(r"^(.+)\1$", ["abab", "ababab", "aba"])

    def test_digit_after_backref(self):
        self.agree(r"(a)\1b", ["aab"])

    def test_invalid_references(self):
        for bad in (r"\1", r"(a)\2", r"\1(a)", r"(a\1)", r"(?:a)\1"):
            with self.assertRaises(PatternError, msg=bad):
                minire.compile(bad)


class Classes(Agree):
    def test_classes(self):
        self.agree(r"[abc]+", ["xxcbaxx"])
        self.agree(r"[^abc]+", ["abxyzc"])
        self.agree(r"[a-cx-z]+", ["qaxbyc"])
        self.agree(r"[]a]+", ["]a]"])
        self.agree(r"[^]a]+", ["]ab"])
        self.agree(r"[a\-z]+", ["a-z"])
        self.agree(r"[a-]+", ["a-a"])
        self.agree(r"[-a]+", ["-a-"])
        self.agree(r"[\]]", ["]"])
        self.agree(r"[\\]", ["\\"])
        self.agree(r"[.*+?]+", ["a.*+?b"])
        self.agree(r"[\w.]+@[\w.]+", ["me me.x@y.org ok"])

    def test_escapes_outside(self):
        self.agree(r"\d+\.\d+", ["x3.14y"])
        self.agree(r"\(a\|b\)", ["(a|b)"])
        self.agree(r"\^\$\{\}", ["^${}"])
        self.agree(r"\w\W\s\S\D", ["a-\tbc", "a b c"])
        self.agree(r"\\", ["\\"])
        self.agree(r"a\tb", ["a\tb"])

    def test_class_in_groups(self):
        self.agree(r"([a-c]+)([0-9]*)", ["abc123", "xyz"])


class Errors(unittest.TestCase):
    def test_pattern_errors(self):
        bad = ["(", ")", "a)", "(a", "(()", "(a|b", "a|b)", "*", "+a", "?", "a|*", "(*)", "(+a)",
               "(?=a)", "(?P<n>a)", "(?", "a**", "a{2}{3}", "a+*", "a*{2}", "a{3,2}", "{2}a",
               "a{2,1}?", "[", "[a", "[a-", "[b-a]", "a\\", "^*", "$+", "^{2}",
               "x{3}*", "a??*"]
        for pat in bad:
            with self.subTest(pat=pat):
                with self.assertRaises(PatternError):
                    minire.compile(pat)

    def test_pattern_error_is_value_error(self):
        self.assertTrue(issubclass(PatternError, ValueError))

    def test_error_not_raised_for_valid_edge_cases(self):
        for pat in ["", "|", "()", "(|)", "a{0}", "a{0,0}", "(?:)", "a|b|", "[]]", "[^]]", "a?", "a??",
                    "(a*)*", "(a|b*)*", "a{1,1}?", "\\{", "\\}"]:
            with self.subTest(pat=pat):
                minire.compile(pat)


def gen_pattern(rng, alphabet="abc", max_depth=3, backrefs=True, anchors=True):
    state = {"n": 0, "closed": []}

    def lit():
        return rng.choice(alphabet)

    def klass():
        kind = rng.randrange(5)
        if kind == 0:
            return "[%s%s]" % (lit(), lit())
        if kind == 1:
            return "[^%s]" % lit()
        if kind == 2:
            return "[a-%s]" % rng.choice("bc")
        if kind == 3:
            return "\\w"
        return "[%s\\d]" % lit()

    def quant():
        k = rng.randrange(10)
        lo = 0
        if k < 2:
            q = "*"
        elif k < 4:
            q = "+"
            lo = 1
        elif k < 5:
            q = "?"
        elif k < 6:
            lo = rng.randrange(0, 3)
            q = "{%d}" % lo
        elif k < 7:
            lo = rng.randrange(0, 3)
            q = "{%d,}" % lo
        else:
            lo = rng.randrange(0, 3)
            q = "{%d,%d}" % (lo, lo + rng.randrange(0, 3))
        if rng.random() < 0.35:
            q += "?"
        return q, lo == 0

    def alt(depth):
        n = rng.choice([1, 1, 1, 2, 2, 3])
        branches = [seq(depth) for _ in range(n)]
        text = "|".join(b[0] for b in branches)
        return text, any(b[1] for b in branches)

    def seq(depth):
        parts = []
        nullable = True
        for _ in range(rng.choice([1, 2, 2, 3, 4])):
            t, nl = piece(depth)
            parts.append(t)
            nullable = nullable and nl
        return "".join(parts), nullable

    def piece(depth):
        r = rng.random()
        if anchors and r < 0.05:
            return rng.choice("^$"), True
        small = [g for g in state["closed"] if g < 10]
        if backrefs and small and r < 0.14:
            return "\\%d" % rng.choice(small), True
        if depth > 0 and r < 0.42:
            if rng.random() < 0.75:
                state["n"] += 1
                idx = state["n"]
                inner, nl = alt(depth - 1)
                state["closed"].append(idx)
                atom = "(%s)" % inner
            else:
                inner, nl = alt(depth - 1)
                atom = "(?:%s)" % inner
        else:
            kind = rng.randrange(8)
            nl = False
            if kind < 5:
                atom = lit()
            elif kind == 5:
                atom = "."
            else:
                atom = klass()
        if not nl and rng.random() < 0.45:
            q, qnull = quant()
            return atom + q, qnull
        # a quantified nullable atom is never generated
        return atom, nl

    text, _ = alt(max_depth)
    return text


def gen_subject(rng, alphabet="abc", maxlen=10):
    pool = alphabet + "1"
    return "".join(rng.choice(pool) for _ in range(rng.randrange(maxlen + 1)))


class Differential(Agree):
    def run_batch(self, seed, count, **kw):
        rng = random.Random(seed)
        done = 0
        for _ in range(count):
            pat = gen_pattern(rng, **kw)
            try:
                r = re.compile(pat)
            except re.error:
                continue
            p = minire.compile(pat)
            self.assertEqual(p.groups, r.groups, pat)
            for _ in range(5):
                s = gen_subject(rng, maxlen=9)
                for name in ("match", "search", "fullmatch"):
                    a = ours(getattr(p, name)(s), r.groups)
                    b = theirs(getattr(r, name)(s), r.groups)
                    self.assertEqual(a, b, (pat, s, name))
            done += 1
        self.assertGreater(done, count * 0.8)

    def test_random_plain(self):
        self.run_batch(1, 500, backrefs=False, anchors=False, max_depth=1)

    def test_random_groups_alt(self):
        self.run_batch(2, 700, backrefs=False, max_depth=2)

    def test_random_anchors(self):
        self.run_batch(3, 500, max_depth=2)

    def test_random_backrefs(self):
        self.run_batch(4, 800, max_depth=3)

    def test_random_deep(self):
        self.run_batch(5, 500, max_depth=4)

    def test_random_two_letters(self):
        self.run_batch(6, 800, alphabet="ab", max_depth=3)

    def test_random_unicode_free_wide_alphabet(self):
        self.run_batch(7, 400, alphabet="abcxyz", max_depth=2)

    def test_random_findall_and_sub(self):
        rng = random.Random(8)
        for _ in range(500):
            pat = gen_pattern(rng, max_depth=2)
            r = re.compile(pat)
            p = minire.compile(pat)
            for _ in range(4):
                s = gen_subject(rng, maxlen=8)
                self.assertEqual(p.findall(s), r.findall(s), (pat, s))
                self.assertEqual(p.sub("<>", s), r.sub(lambda m: "<>", s), (pat, s))
                self.assertEqual(p.sub("-", s, 2), r.sub(lambda m: "-", s, 2), (pat, s))


class FindallSub(unittest.TestCase):
    def check(self, pat, s):
        r = re.compile(pat)
        p = minire.compile(pat)
        self.assertEqual(p.findall(s), r.findall(s), (pat, s))
        self.assertEqual(minire.findall(pat, s), r.findall(s))
        self.assertEqual(p.sub("#", s), r.sub(lambda m: "#", s), (pat, s))

    def test_empty_matches(self):
        for pat, s in [("x*", "axxb"), ("", "abc"), ("a*", "baac"), ("^|\\w+", "foo bar"),
                       ("a*?", "aa"), ("b*|a", "aab"), ("$", "abc"),
                       ("^", "abc"), ("(a)|", "ab"), ("a|b*", "bab"), ("(?:)", "")]:
            with self.subTest(pat=pat):
                self.check(pat, s)

    def test_group_shapes(self):
        self.check(r"(\d)", "a1b2")
        self.check(r"(\d)(\w)", "1a2b3")
        self.check(r"(a)|(b)", "abc")
        self.check(r"a(b)?", "aab")
        self.assertEqual(minire.findall(r"(a)|(b)", "ab"), [("a", ""), ("", "b")])

    def test_sub_basic(self):
        self.assertEqual(minire.sub(r"\s+", " ", "a  b \t c"), "a b c")
        self.assertEqual(minire.sub(r"x", "y", "xxxx", 2), "yyxx")
        self.assertEqual(minire.sub(r"(\d)", lambda m: str(int(m.group(1)) * 2), "a1b9"), "a2b18")
        self.assertEqual(minire.sub("a", "\\1", "a"), "\\1")
        self.assertEqual(minire.compile(r"(?:)").sub("-", "ab"), "-a-b-")

    def test_pos_argument(self):
        p = minire.compile(r"a+")
        self.assertEqual(p.search("aabaa", 2).span(), (3, 5))
        self.assertEqual(p.match("aabaa", 3).span(), (3, 5))
        self.assertIsNone(p.match("aabaa", 2))


class Performance(unittest.TestCase):
    def timed(self, fn, limit):
        t = time.perf_counter()
        r = fn()
        self.assertLess(time.perf_counter() - t, limit)
        return r

    def test_long_dot_star(self):
        s = "a" * 60000 + "x"
        m = self.timed(lambda: minire.compile(r".*x").match(s), 4)
        self.assertEqual(m.span(), (0, 60001))

    def test_long_alternation_loop(self):
        s = "ab" * 30000 + "c"
        m = self.timed(lambda: minire.compile(r"(?:a|b)*c").fullmatch(s), 4)
        self.assertEqual(m.span(), (0, 60001))
        m = self.timed(lambda: minire.compile(r"(a|b)*c").search(s), 4)
        self.assertEqual(m.span(1), (59999, 60000))

    def test_long_lazy_and_class(self):
        s = "x" * 50000 + "y"
        m = self.timed(lambda: minire.compile(r"x*?y").match(s), 4)
        self.assertEqual(m.span(), (0, 50001))
        m = self.timed(lambda: minire.compile(r"[a-z]+").fullmatch(s), 4)
        self.assertEqual(m.span(), (0, 50001))

    def test_long_group_repeat_backtracking(self):
        s = "ab" * 20000
        m = self.timed(lambda: minire.compile(r"(?:ab)+ab").fullmatch(s), 4)
        self.assertEqual(m.span(), (0, 40000))
        m = self.timed(lambda: minire.compile(r"(ab)*b?").match(s), 4)
        self.assertEqual(m.span(1), (39998, 40000))

    def test_findall_many(self):
        s = "word " * 20000
        out = self.timed(lambda: minire.findall(r"\w+", s), 4)
        self.assertEqual(len(out), 20000)
        out = self.timed(lambda: minire.sub(r"\s", "_", s), 4)
        self.assertEqual(out, "word_" * 20000)

    def test_search_many_starts(self):
        s = "b" * 3000 + "a" * 30 + "c"
        m = self.timed(lambda: minire.search(r"a{30}c", s), 4)
        self.assertEqual(m.span(), (3000, 3031))

    def test_backref_long(self):
        s = "xy" * 10000 + "|" + "xy" * 10000
        m = self.timed(lambda: minire.compile(r"^((?:xy)*)\|\1$").match(s), 4)
        self.assertEqual(m.span(1), (0, 20000))


class Regression(unittest.TestCase):
    def test_old_behaviour(self):
        self.assertEqual(minire.search("bc", "abcd").span(), (1, 3))
        self.assertIsNone(minire.match("a.c", "a\nc"))
        self.assertEqual(minire.search(r"[^a-c]+", "abxyc").group(), "xy")
        self.assertEqual(minire.search(r"[\d_]+", "ab1_2c").group(), "1_2")
        self.assertEqual(minire.match("a*a", "aaa").span(), (0, 3))
        self.assertEqual(minire.match("a?ab", "ab").span(), (0, 2))
        self.assertIsNone(minire.fullmatch("a+", "aaab"))
        self.assertEqual(minire.match(r"\t", "\t").span(), (0, 1))
        self.assertEqual(minire.match(r"a\.b", "a.b").group(), "a.b")
        self.assertIsNone(minire.match(r"a\.b", "axb"))

    def test_old_errors(self):
        for bad in ("*a", "a**", "[a", "a\\", "[b-a]"):
            with self.assertRaises(PatternError):
                minire.compile(bad)

    def test_module_functions(self):
        self.assertEqual(minire.match("ab", "abc").span(), (0, 2))
        self.assertEqual(minire.search("b", "abc").span(), (1, 2))
        self.assertEqual(minire.fullmatch("abc", "abc").span(), (0, 3))
        self.assertIsNone(minire.fullmatch("ab", "abc"))
        self.assertEqual(minire.compile("ab").pattern, "ab")
        self.assertEqual(minire.search("x*", "").span(), (0, 0))


if __name__ == "__main__":
    unittest.main()
