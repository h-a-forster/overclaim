import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import toml_fuzz_lib  # noqa: E402
from toml_fuzz_lib import gen_doc, mutate, rand_value_text  # noqa: E402

import cfgkit
from cfgkit import Config, ConfigError, ParseError, load_file, load_layers, load_text, parse_ini
from cfgkit.toml import loads

ROOT = Path(cfgkit.__file__).resolve().parent.parent


def canon(v):
    if isinstance(v, bool):
        return ("bool", v)
    if isinstance(v, int):
        return ("int", v)
    if isinstance(v, float):
        return ("float", "nan" if v != v else repr(v))
    if isinstance(v, dict):
        return ("dict", {k: canon(x) for k, x in v.items()})
    if isinstance(v, list):
        return ("list", [canon(x) for x in v])
    return ("str", v) if isinstance(v, str) else ("other", repr(v))


class Base(unittest.TestCase):
    def ok(self, text, expected):
        got = loads(text)
        self.assertEqual(canon(got), canon(expected), text)
        # the expectation itself must be what a conforming parser says
        self.assertEqual(canon(tomllib.loads(text)), canon(expected), text)

    def bad(self, text, line=None):
        with self.assertRaises(ParseError, msg=text) as cm:
            loads(text)
        self.assertIsInstance(cm.exception, ConfigError)
        if line is not None:
            self.assertEqual(cm.exception.line, line, text)
        with self.assertRaises(tomllib.TOMLDecodeError):
            tomllib.loads(text)

    def same(self, text):
        try:
            want = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            want = None
        try:
            got = loads(text)
        except ParseError:
            got = None
        self.assertEqual(want is None, got is None, text)
        if want is not None:
            self.assertEqual(canon(got), canon(want), text)


class Scalars(Base):
    def test_integers(self):
        self.ok("a = 0\nb = +17\nc = -17\nd = 1_000\ne = -0\nf = +0", dict(a=0, b=17, c=-17, d=1000, e=0, f=0))
        self.ok("a = 0xDEADbeef\nb = 0xdead_beef\nc = 0o755\nd = 0b1101_0110", dict(a=0xDEADBEEF, b=0xDEADBEEF, c=0o755, d=0b11010110))
        self.ok("a = 123456789012345678901234567890", dict(a=123456789012345678901234567890))

    def test_bad_integers(self):
        for t in ["a = 01", "a = 1__0", "a = _1", "a = 1_", "a = +0x1", "a = -0b1", "a = 0x", "a = 0xg", "a = 0o8",
                  "a = 0b2", "a = 0B1", "a = 0X1", "a = 00", "a = 0_1", "a = 1_000_", "a = 0x_1", "a = 1 2"]:
            with self.subTest(t=t):
                self.bad(t)

    def test_floats(self):
        self.ok("a = 1.5\nb = -0.01\nc = 1e3\nd = 1E-3\ne = 6.02e+23\nf = 1_0.2_5\ng = 5e1_0",
                dict(a=1.5, b=-0.01, c=1000.0, d=0.001, e=6.02e23, f=10.25, g=5e10))
        self.ok("a = +1.0\nb = 0.0\nc = -0.0\nd = 1e0\ne = 0e0\nf = 9.99e01", dict(a=1.0, b=0.0, c=-0.0, d=1.0, e=0.0, f=99.9))

    def test_float_types_are_float(self):
        v = loads("a = 1e3\nb = 1.0\nc = 7")
        self.assertIsInstance(v["a"], float)
        self.assertIsInstance(v["b"], float)
        self.assertIsInstance(v["c"], int)
        self.assertNotIsInstance(v["c"], bool)

    def test_inf_nan(self):
        v = loads("a = inf\nb = +inf\nc = -inf\nd = nan\ne = -nan\nf = +nan")
        self.assertEqual((v["a"], v["b"], v["c"]), (math.inf, math.inf, -math.inf))
        self.assertTrue(all(math.isnan(v[k]) for k in "def"))

    def test_bad_floats(self):
        for t in ["a = 1.", "a = .5", "a = 1.e3", "a = 1e", "a = 1e+", "a = 1._5", "a = 1_.5", "a = 01.5",
                  "a = 1.5_", "a = 1.5e_1", "a = inf1", "a = Inf", "a = NaN", "a = +-1", "a = 1.2.3", "a = 1e1.5", "a = --1"]:
            with self.subTest(t=t):
                self.bad(t)

    def test_booleans(self):
        self.ok("a = true\nb = false", dict(a=True, b=False))
        for t in ["a = True", "a = tru", "a = truee", "a = TRUE", "a = falsey", "a = yes"]:
            with self.subTest(t=t):
                self.bad(t)

    def test_dates_are_unsupported(self):
        for t in ["a = 1979-05-27", "a = 07:32:00", "a = 1979-05-27T07:32:00Z", "a = 1979-05-27 07:32:00"]:
            with self.subTest(t=t):
                with self.assertRaises(ParseError):
                    loads(t)

    def test_basic_strings(self):
        self.ok('a = "hi"\nb = ""\nc = "tab\\tq\\"b\\\\s\\/"'.replace("\\/", ""), dict(a="hi", b="", c='tab\tq"b\\s'))
        self.ok('a = "\\u00E9\\U0001F600\\b\\f\\n\\r"', dict(a="\u00e9\U0001F600\b\f\n\r"))
        self.ok('a = "caf\u00e9 # not a comment"', dict(a="caf\u00e9 # not a comment"))
        self.ok('a = "a\tb"', dict(a="a\tb"))

    def test_bad_basic_strings(self):
        for t in ['a = "x', 'a = "x\ny"', 'a = "\\q"', 'a = "\\u12"', 'a = "\\uD800"', 'a = "\\U00110000"',
                  'a = "\\x41"', 'a = "\\e"', 'a = "\\ "', 'a = "\x01"', 'a = "\x7f"', 'a = "x" y', "a = \"x\"\"", 'a = "\\u00zz"']:
            with self.subTest(t=t):
                self.bad(t)

    def test_literal_strings(self):
        self.ok("a = 'C:\\\\path\\n'\nb = ''\nc = 'say \"hi\"'", dict(a="C:\\\\path\\n", b="", c='say "hi"'))
        for t in ["a = 'x", "a = 'x\ny'", "a = 'x\x01'"]:
            self.bad(t)

    def test_multiline_basic(self):
        self.ok('a = """\nRoses\nViolets"""', dict(a="Roses\nViolets"))
        self.ok('a = """one\\\n   two  \\\n\n   three"""', dict(a="onetwo  three"))
        self.ok('a = """\\\n  x"""', dict(a="x"))
        self.ok('a = """a "" b ""\\"" c"""', dict(a='a "" b """" c'))
        self.ok('a = """""quoted"""""', dict(a='""quoted""'))
        self.ok('a = """x\\t\\u0041\\n"""', dict(a="x\tA\n"))
        self.ok('a = ""\n"""\nb"""'.replace('a = ""\n', 'a = ""\nc = '), dict(a="", c="b"))
        self.ok('a = """\r\nx\r\ny"""', dict(a="x\ny"))
        self.ok('a = """\n\nx"""', dict(a="\nx"))
        self.ok('a = """ \\   \n   x"""', dict(a=" x"))

    def test_bad_multiline_basic(self):
        for t in ['a = """x', 'a = """x""', 'a = """x""""""', 'a = """\\q"""', 'a = """x\x01"""', 'a = """x\\ y\n"""',
                  'a = """x"""""" ']:
            with self.subTest(t=t):
                self.bad(t)

    def test_multiline_literal(self):
        self.ok("a = '''\nx\\n\ny'''", dict(a="x\\n\ny"))
        self.ok("a = '''it's \"q\" ''quoted'' '''", dict(a="it's \"q\" ''quoted'' "))
        self.ok("a = ''''x''''", dict(a="'x'"))
        self.ok("a = '''x'''''", dict(a="x''"))
        self.ok("a = '''\r\nx\r\n'''", dict(a="x\n"))
        for t in ["a = '''x", "a = '''x''", "a = '''x''''''", "a = '''x\x01'''"]:
            self.bad(t)

    def test_unicode_values(self):
        self.ok('k\u00e9 = 1'.replace("k\u00e9", '"k\u00e9"'), {"k\u00e9": 1})
        self.ok("a = '\u4f60\u597d'", dict(a="\u4f60\u597d"))


class Arrays(Base):
    def test_arrays(self):
        self.ok("a = []\nb = [1, 2, 3]\nc = [ ]\nd = [1,2,]\ne = [[1], [2, 3], []]", dict(a=[], b=[1, 2, 3], c=[], d=[1, 2], e=[[1], [2, 3], []]))

    def test_mixed_types(self):
        self.ok('a = [1, "x", 2.5, true, [1], {b = 1}]', dict(a=[1, "x", 2.5, True, [1], {"b": 1}]))

    def test_multiline_and_comments(self):
        self.ok("a = [\n  1, # one\n  2,\n  # three\n  3,\n]\nb = 1", dict(a=[1, 2, 3], b=1))
        self.ok("a = [\n\n]", dict(a=[]))
        self.ok("a = [1\n,2\n]", dict(a=[1, 2]))
        self.ok("a = [ # c\n 1 ]", dict(a=[1]))
        self.ok("a = [\n'''x\ny''',\n]", dict(a=["x\ny"]))

    def test_bad_arrays(self):
        for t in ["a = [", "a = [1", "a = [1,", "a = [,]", "a = [1,,2]", "a = [1 2]", "a = [1]]", "a = [1;2]", "a = [1,\n", "a = ]"]:
            with self.subTest(t=t):
                self.bad(t)

    def test_array_of_inline_tables(self):
        self.ok("a = [{x = 1}, {x = 2, y = [3]}]", dict(a=[{"x": 1}, {"x": 2, "y": [3]}]))


class InlineTables(Base):
    def test_inline_tables(self):
        self.ok("a = {}\nb = {x = 1}\nc = { x = 1 , y = 'z' }\nd = {x.y = 1, x.z = 2}\ne = {x = {y = {z = 1}}}",
                dict(a={}, b={"x": 1}, c={"x": 1, "y": "z"}, d={"x": {"y": 1, "z": 2}}, e={"x": {"y": {"z": 1}}}))

    def test_bad_inline_tables(self):
        for t in ["a = {x = 1,}", "a = {x = 1", "a = {x}", "a = {x = }", "a = {,}", "a = {x = 1 y = 2}", "a = {\nx = 1}",
                  "a = {x = 1\n}", "a = {x = 1, x = 2}", "a = {x = 1, x.y = 2}", "a = {x.y = 1, x = 2}",
                  "a = {x = {}, x.y = 1}", "a = {x = [], x.y = 1}", "a = {x = 1} b", "a = {x = 1,\ny = 2}", "a = {# c\n}"]:
            with self.subTest(t=t):
                self.bad(t)

    def test_inline_tables_are_closed(self):
        for t in ["a = {x = 1}\n[a.y]", "a = {x = 1}\n[a]", "a = {x = 1}\na.y = 2", "a = {}\n[a.b]", "a = {x = {y = 1}}\n[a.x.z]",
                  "a = {x = {y = 1}}\na.x.z = 2", "a = [1]\n[[a]]", "a = []\n[[a]]", "a = [{b = 1}]\n[a.c]", "a = [{b = 1}]\n[[a]]"]:
            with self.subTest(t=t):
                self.bad(t)


class Keys(Base):
    def test_key_forms(self):
        self.ok("a = 1\nb-c_d = 2\n1234 = 3\n\"quoted key\" = 4\n'lit key' = 5\n\"\" = 6\n- = 7\n_ = 8",
                {"a": 1, "b-c_d": 2, "1234": 3, "quoted key": 4, "lit key": 5, "": 6, "-": 7, "_": 8})

    def test_dotted_keys(self):
        self.ok("a.b.c = 1\na.b.d = 2\na . e = 3\n\"a\".\"f\" = 4\n'g'.h = 5",
                {"a": {"b": {"c": 1, "d": 2}, "e": 3, "f": 4}, "g": {"h": 5}})
        self.ok('site."google.com" = true\n3.14159 = "pi"', {"site": {"google.com": True}, "3": {"14159": "pi"}})

    def test_bad_keys(self):
        for t in ["= 1", "a b = 1", "a. = 1", ".a = 1", "a..b = 1", "a.b. = 1", "\"a = 1", "'a = 1", "a = ", "a", "a ==  1",
                  "k\u00e9 = 1", "a.\n b = 1", "\"\"\"a\"\"\" = 1", "a = 1 = 2", "a = 1 b = 2", "[a] = 1"]:
            with self.subTest(t=t):
                self.bad(t)

    def test_duplicates(self):
        for t in ["a = 1\na = 2", "a = 1\na = 1", "a.b = 1\na.b = 2", "a = 1\na.b = 2", "a.b = 1\na = 2",
                  "\"a\" = 1\na = 2", "a = 1\n'a' = 2", "a = {}\na = {}", "a = []\na = 1"]:
            with self.subTest(t=t):
                self.bad(t)

    def test_quoted_and_bare_keys_are_same_key(self):
        self.ok("a.b = 1\n\"a\".c = 2", {"a": {"b": 1, "c": 2}})
        self.bad('a.b = 1\n"a"."b" = 2')


class Tables(Base):
    def test_tables(self):
        self.ok("top = 1\n[a]\nx = 1\n[a.b]\ny = 2\n[c]\n[ d . e ]\nz = 3\n['f g']\nw = 4\n[\"h\".'i']",
                {"top": 1, "a": {"x": 1, "b": {"y": 2}}, "c": {}, "d": {"e": {"z": 3}}, "f g": {"w": 4}, "h": {"i": {}}})

    def test_implicit_then_explicit(self):
        self.ok("[a.b.c]\nx = 1\n[a]\ny = 2\n[a.b]\nz = 3", {"a": {"b": {"c": {"x": 1}, "z": 3}, "y": 2}})
        self.ok("[x.y.z.w]\n[x]\nq = 1", {"x": {"y": {"z": {"w": {}}}, "q": 1}})

    def test_dotted_keys_extend_implicit_tables(self):
        self.ok("[a.b.c]\n[a]\nb.d = 1", {"a": {"b": {"c": {}, "d": 1}}})
        self.bad("[a.b.c]\n[a]\nb.c = 1")

    def test_table_defined_twice(self):
        for t in ["[a]\n[a]", "[a]\nx = 1\n[b]\n[a]", "[a.b]\n[a.b]", "[a]\nb = 1\n[a.b]", "a = 1\n[a]", "[a]\n[a.b]\n[a]",
                  "a.b = 1\n[a]", "a.b.c = 1\n[a.b]", "[a]\nb.c = 1\n[a.b]", "[a]\nb.c = 1\n[a.b.c]", "[a.b]\n[a]\nb.c = 1"]:
            with self.subTest(t=t):
                self.bad(t)

    def test_subtables_of_dotted_tables_are_fine(self):
        self.ok("[fruit]\napple.color = 'red'\napple.taste.sweet = true\n[fruit.apple.texture]\nsmooth = true",
                {"fruit": {"apple": {"color": "red", "taste": {"sweet": True}, "texture": {"smooth": True}}}})
        self.bad("[fruit]\napple.color = 'red'\n[fruit.apple]")
        self.bad("[fruit]\napple.taste.sweet = true\n[fruit.apple.taste]")
        self.ok("a.b.c = 1\n[a.x]\ny = 2", {"a": {"b": {"c": 1}, "x": {"y": 2}}})

    def test_root_keys_then_tables(self):
        self.ok("a = 1\n[t]\nb = 2", {"a": 1, "t": {"b": 2}})
        self.bad("[t]\nb = 2\n[t.b]")
        self.bad("[t]\nb = 2\n[t.b.c]")

    def test_header_syntax(self):
        for t in ["[a", "[a]]", "[]", "[a] x", "[a b]", "[a.]", "[.a]", "[a..b]", "[[a]", "[[a]]]", "[ [a] ]", "[a]=1", "[[]]", "[a]\n[", "[\"a]"]:
            with self.subTest(t=t):
                self.bad(t)

    def test_trailing_comments_and_blank_lines(self):
        self.ok("\n\n# top\n[a] # c\n\n  x = 1 # c\n\t# indented\n\n[b]#c\n", {"a": {"x": 1}, "b": {}})
        self.ok("  [a]  \n  b  =  1  ", {"a": {"b": 1}})

    def test_empty_and_comment_only(self):
        self.ok("", {})
        self.ok("# nothing\n\n   \n", {})
        self.ok("\r\n\r\n", {})

    def test_comment_with_control_char(self):
        self.bad("a = 1 # bad \x01 comment")
        self.bad("# \x00")
        self.ok("a = 1 # tab\there \u00e9", {"a": 1})


class ArraysOfTables(Base):
    def test_aot(self):
        self.ok("[[p]]\nn = 1\n[[p]]\nn = 2\n[[p]]", {"p": [{"n": 1}, {"n": 2}, {}]})

    def test_nested_aot(self):
        text = "[[a]]\nx = 1\n[a.b]\ny = 1\n[[a.c]]\nz = 1\n[[a.c]]\nz = 2\n[[a]]\nx = 2\n[a.b]\ny = 2\n[[a.c]]\nz = 3"
        self.ok(text, {"a": [{"x": 1, "b": {"y": 1}, "c": [{"z": 1}, {"z": 2}]}, {"x": 2, "b": {"y": 2}, "c": [{"z": 3}]}]})

    def test_aot_errors(self):
        for t in ["a = 1\n[[a]]", "[a]\n[[a]]", "[[a]]\n[a]", "[[a]]\n[a.b]\n[a.b]", "[a.b]\n[[a]]", "a.b = 1\n[[a]]",
                  "[[a]]\n[[a.b]]\n[a.b]", "a = [{x = 1}]\n[[a]]", "[[a]]\nb = 1\n[[a.b]]", "[[a.b]]\nc = 1\n[a]\nb = 3"]:
            with self.subTest(t=t):
                self.bad(t)

    def test_aot_resets_subtable_flags(self):
        self.ok("[[a]]\n[a.b]\n[[a]]\n[a.b]", {"a": [{"b": {}}, {"b": {}}]})
        self.ok("[[a]]\nb.c = 1\n[[a]]\n[a.b]", {"a": [{"b": {"c": 1}}, {"b": {}}]})

    def test_keys_after_aot_header_go_to_last_element(self):
        self.ok("[[a]]\nx = 1\n[[a]]\nx = 2\ny.z = 3", {"a": [{"x": 1}, {"x": 2, "y": {"z": 3}}]})
        self.ok("[[a.b]]\n[[a.b]]", {"a": {"b": [{}, {}]}})
        self.ok("[x]\n[[x.y]]\nk = 1", {"x": {"y": [{"k": 1}]}})


class LineNumbers(Base):
    def test_lines(self):
        self.bad("a = 1\nb = \nc = 3", 2)
        self.bad("a = 1\n\n\nb = tru", 4)
        self.bad("a = 1\na = 2", 2)
        self.bad("[x]\n[y]\n[x]", 3)
        self.bad("# c\n# c\n[a\n", 3)
        self.bad("a = 1 b", 1)

    def test_line_is_statement_start_for_multiline_constructs(self):
        self.bad('x = 1\nk = """abc\ndef', 2)
        self.bad("x = 1\nk = [\n  1,\n  2\n  3,\n]\ny = 1", 2)
        self.bad("x = 1\nk = [\n  1,\n  2,\n", 2)
        self.bad("\n\nk = '''\n\nz'''  extra", 3)

    def test_crlf_lines(self):
        self.bad("a = 1\r\nb = 2\r\nc = \r\n", 3)

    def test_error_message_has_line(self):
        with self.assertRaises(ParseError) as cm:
            loads("a = 1\nb = !")
        self.assertIn("2", str(cm.exception))
        self.assertEqual(cm.exception.line, 2)

    def test_non_string_input(self):
        with self.assertRaises(ParseError):
            loads(b"a = 1")


class Newlines(Base):
    def test_crlf_equals_lf(self):
        doc = 'a = 1\n[t] # c\nb = """x\ny"""\nc = [\n1,\n2]\n'
        self.assertEqual(loads(doc.replace("\n", "\r\n")), loads(doc))
        self.assertEqual(loads(doc)["t"]["b"], "x\ny")

    def test_bare_cr_is_an_error(self):
        self.bad("a = 1\rb = 2")
        self.bad('a = "x\ry"')


class Differential(Base):
    def test_structure_random(self):
        rng = random.Random(101)
        ok = 0
        for _ in range(12000):
            doc = gen_doc(rng)
            self.same(doc)
            try:
                tomllib.loads(doc)
                ok += 1
            except tomllib.TOMLDecodeError:
                pass
        self.assertGreater(ok, 2500)

    def test_structure_random_longer(self):
        rng = random.Random(102)
        for _ in range(4000):
            self.same(gen_doc(rng, rng.randrange(6, 14)))

    def test_values_random(self):
        rng = random.Random(103)
        for _ in range(8000):
            self.same("k = %s\n" % rand_value_text(rng))

    def test_values_in_tables_random(self):
        rng = random.Random(104)
        for _ in range(3000):
            doc = "top = %s\n[t]\nk = %s\n[[u]]\nj = %s\n" % tuple(rand_value_text(rng) for _ in range(3))
            self.same(doc)

    def test_mutated_documents(self):
        rng = random.Random(105)
        for _ in range(10000):
            base = "# c\n[t]\nk = %s\nx.y = 1\n[[z]]\nq = 'a'\n" % rand_value_text(rng)
            self.same(mutate(rng, base))

    def test_mutated_structure(self):
        rng = random.Random(106)
        for _ in range(6000):
            self.same(mutate(rng, gen_doc(rng, rng.randrange(1, 6))))


class Integration(unittest.TestCase):
    def write(self, d, name, text):
        p = Path(d) / name
        p.write_text(text, encoding="utf-8", newline="")
        return p

    def test_load_text_toml(self):
        self.assertEqual(load_text("[a]\nb = 1", "toml"), {"a": {"b": 1}})
        with self.assertRaises(ParseError) as cm:
            load_text("a = 1\nb", "toml")
        self.assertEqual(cm.exception.line, 2)

    def test_load_file_toml(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.write(d, "app.toml", '[server]\nhost = "h\u00e9"\nport = 8080\n[[server.ssl]]\nca = "x"\n')
            c = load_file(p)
            self.assertIsInstance(c, Config)
            self.assertEqual(c.get("server.port"), 8080)
            self.assertEqual(c.get("server.host"), "h\u00e9")
            self.assertEqual(c.get("server.ssl.0.ca"), "x")
            self.assertEqual(c.get("server.ssl.1.ca", "none"), "none")
            self.assertEqual(c.get("server.ssl.x", "none"), "none")
            self.assertIn("server.ssl.0", c)
            self.assertNotIn("server.ssl.1", c)
            q = self.write(d, "UP.TOML", "x = 1")
            self.assertEqual(load_file(q).get("x"), 1)

    def test_load_file_toml_error_has_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.write(d, "bad.toml", "a = 1\n\n[x\n")
            with self.assertRaises(ParseError) as cm:
                load_file(p)
            self.assertEqual(cm.exception.line, 3)

    def test_layers_mix_formats(self):
        with tempfile.TemporaryDirectory() as d:
            a = self.write(d, "a.ini", "[s]\nk = 1\nm = old\n")
            b = self.write(d, "b.toml", "[s]\nk = 2\nlist = [1, 2]\n[s.sub]\nz = true\n")
            c = self.write(d, "c.json", '{"s": {"sub": {"y": 1}}}')
            cfg = load_layers([a, b, c])
            self.assertEqual(cfg.as_dict(), {"s": {"k": 2, "m": "old", "list": [1, 2], "sub": {"z": True, "y": 1}}})

    def test_from_toml(self):
        c = Config.from_toml("a = 1\n[b]\nc = [10, 20]")
        self.assertEqual(c.get("b.c.1"), 20)
        self.assertEqual(c.get("b.c.2", "d"), "d")
        self.assertEqual(c.get("a"), 1)

    def test_list_index_paths(self):
        c = Config({"a": [{"b": [5, 6]}, 7], "s": "str"})
        self.assertEqual(c.get("a.0.b.1"), 6)
        self.assertEqual(c.get("a.1"), 7)
        self.assertEqual(c.get("a.2", None), None)
        self.assertEqual(c.get("a.-1", "d"), "d")
        self.assertEqual(c.get("a.x", "d"), "d")
        self.assertEqual(c.get("s.0", "d"), "d")
        with self.assertRaises(KeyError):
            c.get("a.5")

    def test_package_exports(self):
        self.assertTrue(callable(cfgkit.loads_toml))
        self.assertEqual(cfgkit.loads_toml("a = 1"), {"a": 1})

    def test_unknown_format_still_errors(self):
        with self.assertRaises(ConfigError):
            load_text("a = 1", "yaml")


class NoStdlibToml(unittest.TestCase):
    BANNED = r"(?:tomllib|tomli|tomli_w|toml|tomlkit|pytoml|rtoml)"

    def test_no_banned_imports_in_sources(self):
        pat = re.compile(r"^\s*(?:import|from)\s+" + self.BANNED + r"\b", re.M)
        dyn = re.compile(r"(?:__import__|import_module)\s*\(\s*['\"]" + self.BANNED)
        for p in (ROOT / "cfgkit").rglob("*.py"):
            src = p.read_text(encoding="utf-8")
            self.assertIsNone(pat.search(src), p)
            self.assertIsNone(dyn.search(src), p)

    def test_banned_modules_not_loaded(self):
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "import cfgkit\n"
            "d = cfgkit.loads_toml('a = [1, {b = 2}]\\n[t]\\nx = 1')\n"
            "assert d['t']['x'] == 1\n"
            "bad = [m for m in ('tomllib', 'tomli', 'toml', 'tomlkit') if m in sys.modules]\n"
            "print(bad)\n" % str(ROOT)
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tempfile.gettempdir(),
                             env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "[]")


class Performance(unittest.TestCase):
    def test_big_documents(self):
        lines = []
        for i in range(400):
            lines.append("[sec%d]" % i)
            for j in range(40):
                lines.append("key%d = %d" % (j, j * i))
            lines.append('name = "section %d"' % i)
            lines.append("[[sec%d.items]]" % i)
            lines.append("v = [1, 2, 3]")
        doc = "\n".join(lines) + "\n"
        t = time.perf_counter()
        d = loads(doc)
        self.assertLess(time.perf_counter() - t, 3.0)
        self.assertEqual(len(d), 400)
        self.assertEqual(d["sec7"]["key5"], 35)

    def test_long_array_and_string(self):
        doc = "a = [" + ", ".join(str(i) for i in range(50000)) + "]\nb = \"" + "x" * 200000 + "\"\nc = '''" + "y\n" * 50000 + "'''\n"
        t = time.perf_counter()
        d = loads(doc)
        self.assertLess(time.perf_counter() - t, 3.0)
        self.assertEqual(len(d["a"]), 50000)
        self.assertEqual(len(d["b"]), 200000)

    def test_many_statements_line_numbers_do_not_go_quadratic(self):
        doc = "".join("k%d = %d\n" % (i, i) for i in range(60000)) + "k0 = 1\n"
        t = time.perf_counter()
        with self.assertRaises(ParseError) as cm:
            loads(doc)
        self.assertLess(time.perf_counter() - t, 3.0)
        self.assertEqual(cm.exception.line, 60001)


class Regression(unittest.TestCase):
    def test_ini_unchanged(self):
        self.assertEqual(parse_ini("top = 1\n[a]\nx = y # not a comment\n; c\n[b]\nk=v"),
                         {"top": "1", "a": {"x": "y # not a comment"}, "b": {"k": "v"}})
        with self.assertRaises(ParseError) as cm:
            parse_ini("[a]\nx = 1\noops\n")
        self.assertEqual(cm.exception.line, 3)

    def test_config_unchanged(self):
        c = Config({"a": {"b": 1, "c": {"d": 2}}, "x": 1})
        self.assertEqual(c.get("a.c.d"), 2)
        self.assertEqual(c.get("a.zz", 7), 7)
        self.assertIn("a.b", c)
        self.assertNotIn("a.b.c", c)
        with self.assertRaises(KeyError):
            c.get("nope")
        m = c.merge(Config({"a": {"c": {"e": 3}}, "x": [1]}))
        self.assertEqual(m.as_dict(), {"a": {"b": 1, "c": {"d": 2, "e": 3}}, "x": [1]})
        with self.assertRaises(ConfigError):
            c.section("x")
        self.assertEqual(c.section("a.c").as_dict(), {"d": 2})

    def test_json_loading_unchanged(self):
        self.assertEqual(load_text('{"a": {"b": 1}}', "json"), {"a": {"b": 1}})
        with self.assertRaises(ParseError):
            load_text("[1]", "json")
        with self.assertRaises(ParseError):
            load_text("{", "json")

    def test_parse_error_shape(self):
        e = ParseError("boom", 4)
        self.assertEqual((e.line, e.message), (4, "boom"))
        self.assertEqual(str(e), "line 4: boom")
        self.assertIsNone(ParseError("x").line)


if __name__ == "__main__":
    unittest.main()
