import decimal
import random
import unittest

import dec
from dec import (ROUND_05UP, ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_DOWN, ROUND_HALF_EVEN,
                 ROUND_HALF_UP, ROUND_UP, Context, Dec, DivisionByZero, InvalidOperation)

MODES = [ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, ROUND_HALF_DOWN, ROUND_HALF_EVEN, ROUND_05UP]
OPS = [("add", "add"), ("sub", "subtract"), ("mul", "multiply"), ("div", "divide"), ("divint", "divide_int"),
       ("rem", "remainder"), ("quantize", "quantize"), ("sqrt", "sqrt")]


def oracle(op, prec, mode, a, b=None):
    ctx = decimal.Context(prec=prec, rounding=getattr(decimal, mode), Emax=999999999, Emin=-999999999,
                          traps=[decimal.InvalidOperation, decimal.DivisionByZero])
    name = dict(OPS)[op]
    try:
        r = getattr(ctx, name)(decimal.Decimal(a)) if op == "sqrt" else getattr(ctx, name)(decimal.Decimal(a), decimal.Decimal(b))
    except decimal.DivisionByZero:
        return "DZ"
    except decimal.InvalidOperation:
        return "IO"
    return r.as_tuple()[0], r.as_tuple()[1], r.as_tuple()[2], str(r)


def ours(op, prec, mode, a, b=None):
    c = Context(prec, mode)
    try:
        r = getattr(c, op)(a) if op == "sqrt" else getattr(c, op)(b if False else a, b)
    except DivisionByZero:
        return "DZ"
    except InvalidOperation:
        return "IO"
    t = r.as_tuple()
    return t[0], t[1], t[2], str(r)


def rnd_operand(rng, maxdigits=13, exp_range=(-8, 8)):
    r = rng.random()
    if r < 0.12:
        coef = 0
    elif r < 0.25:
        coef = rng.choice([1, 5, 15, 25, 35, 45, 50, 95, 99, 100, 105, 999, 1000, 9995, 10005]) * 10 ** rng.randrange(0, 4)
    elif r < 0.35:
        coef = int("9" * rng.randrange(1, maxdigits))
    else:
        coef = rng.randrange(1, 10 ** rng.randrange(1, maxdigits + 1))
    sign = "-" if rng.random() < 0.4 else ""
    return "%s%dE%d" % (sign, coef, rng.randrange(*exp_range))


class Constants(unittest.TestCase):
    def test_rounding_names_match_decimal(self):
        for m in MODES:
            self.assertEqual(getattr(dec, m), getattr(decimal, m))
        self.assertEqual(len(set(MODES)), 8)

    def test_context_validation(self):
        c = Context()
        self.assertEqual((c.prec, c.rounding), (28, ROUND_HALF_EVEN))
        c = Context(5, ROUND_UP)
        self.assertEqual((c.prec, c.rounding), (5, ROUND_UP))
        for bad in [(0,), (-3,), (1.5,), ("5",), (True,), (5, "ROUND_NEAREST"), (5, None), (5, "round_up")]:
            with self.assertRaises(ValueError, msg=bad):
                Context(*bad)

    def test_error_classes(self):
        self.assertTrue(issubclass(InvalidOperation, ArithmeticError))
        self.assertTrue(issubclass(DivisionByZero, ArithmeticError))
        self.assertFalse(issubclass(InvalidOperation, DivisionByZero))
        self.assertFalse(issubclass(DivisionByZero, InvalidOperation))


class Examples(unittest.TestCase):
    def check(self, op, prec, mode, a, b, want):
        c = Context(prec, mode)
        r = c.sqrt(a) if op == "sqrt" else getattr(c, op)(a, b)
        self.assertIsInstance(r, Dec)
        self.assertEqual(str(r), want, (op, prec, mode, a, b))

    def test_add_sub(self):
        h = ROUND_HALF_EVEN
        self.check("add", 9, h, "12", "7.00", "19.00")
        self.check("add", 9, h, "1E+2", "1E+4", "1.01E+4")
        self.check("add", 3, h, "1234", "0.5", "1.23E+3")
        self.check("add", 3, h, "0.00", "12345", "1.23E+4")
        self.check("add", 5, h, "1.00000", "2", "3.0000")
        self.check("sub", 9, h, "1.3", "1.07", "0.23")
        self.check("sub", 9, h, "1.3", "1.30", "0.00")
        self.check("sub", 9, h, "1.3", "2.07", "-0.77")
        self.check("add", 2, ROUND_CEILING, "1.234", "0", "1.3")
        self.check("add", 2, ROUND_FLOOR, "-1.234", "0", "-1.3")
        self.check("add", 2, ROUND_05UP, "1.04", "0", "1.1")
        self.check("add", 2, ROUND_05UP, "1.05", "0", "1.1")
        self.check("add", 2, ROUND_05UP, "1.5", "0.04", "1.6")
        self.check("add", 2, ROUND_05UP, "1.6", "0.04", "1.6")
        self.check("add", 1, ROUND_05UP, "6", "0.4", "6")
        self.check("add", 1, ROUND_05UP, "5", "0.4", "6")
        self.check("add", 3, ROUND_HALF_DOWN, "1.005", "0", "1.00")
        self.check("add", 3, ROUND_HALF_UP, "1.005", "0", "1.01")
        self.check("add", 3, ROUND_HALF_EVEN, "1.015", "0", "1.02")
        self.check("add", 3, ROUND_HALF_EVEN, "1.025", "0", "1.02")
        self.check("add", 3, ROUND_HALF_EVEN, "1.0251", "0", "1.03")
        self.check("add", 3, ROUND_HALF_EVEN, "9.995", "0", "10.0")
        self.check("add", 3, ROUND_UP, "9.991", "0", "10.0")

    def test_mul(self):
        h = ROUND_HALF_EVEN
        self.check("mul", 9, h, "1.20", "3", "3.60")
        self.check("mul", 9, h, "7", "3", "21")
        self.check("mul", 9, h, "0.9", "0.8", "0.72")
        self.check("mul", 9, h, "0.9", "-0", "-0.0")
        self.check("mul", 9, h, "654321", "654321", "4.28135971E+11")
        self.check("mul", 4, ROUND_DOWN, "12345", "10", "1.234E+5")
        self.check("mul", 9, h, "0E+3", "0.00", "0E+1")

    def test_div(self):
        h = ROUND_HALF_EVEN
        self.check("div", 9, h, "1", "3", "0.333333333")
        self.check("div", 9, h, "2", "3", "0.666666667")
        self.check("div", 9, h, "5", "2", "2.5")
        self.check("div", 9, h, "1", "10", "0.1")
        self.check("div", 9, h, "12", "12", "1")
        self.check("div", 9, h, "8.00", "2", "4.00")
        self.check("div", 9, h, "2.400", "2.0", "1.20")
        self.check("div", 9, h, "1000", "100", "10")
        self.check("div", 9, h, "1000", "1", "1000")
        self.check("div", 9, h, "2.40E+6", "2", "1.20E+6")
        self.check("div", 9, h, "1", "8", "0.125")
        self.check("div", 2, h, "1", "8", "0.12")
        self.check("div", 2, ROUND_HALF_UP, "1", "8", "0.13")
        self.check("div", 2, ROUND_UP, "1", "3", "0.34")
        self.check("div", 2, ROUND_FLOOR, "-1", "3", "-0.34")
        self.check("div", 3, h, "0.00", "5", "0.00")
        self.check("div", 3, h, "-0", "5", "-0")
        self.check("div", 3, h, "0", "-5", "-0")
        self.check("div", 3, h, "0E+5", "3E-2", "0E+7")
        self.check("div", 1, h, "1", "7", "0.1")
        self.check("div", 5, h, "100", "3E+1", "3.3333")
        self.check("div", 3, h, "1E+10", "1E+3", "1E+7")

    def test_divint_rem(self):
        h = ROUND_HALF_EVEN
        self.check("divint", 9, h, "2", "3", "0")
        self.check("divint", 9, h, "10", "3", "3")
        self.check("divint", 9, h, "1", "0.3", "3")
        self.check("divint", 9, h, "-10", "3", "-3")
        self.check("divint", 9, h, "-1", "3", "-0")
        self.check("divint", 9, h, "0.00", "3", "0")
        self.check("rem", 9, h, "2.1", "3", "2.1")
        self.check("rem", 9, h, "10", "3", "1")
        self.check("rem", 9, h, "-10", "3", "-1")
        self.check("rem", 9, h, "10", "-3", "1")
        self.check("rem", 9, h, "10.2", "1", "0.2")
        self.check("rem", 9, h, "10", "0.3", "0.1")
        self.check("rem", 9, h, "3.6", "1.3", "1.0")
        self.check("rem", 9, h, "-10", "5", "-0")
        self.check("rem", 9, h, "10.00", "5", "0.00")
        self.check("rem", 9, h, "0", "5.00", "0.00")
        self.check("rem", 3, h, "1.23456", "100", "1.23")
        self.check("rem", 3, ROUND_UP, "1.23456", "100", "1.24")

    def test_quantize(self):
        h = ROUND_HALF_EVEN
        self.check("quantize", 9, h, "2.17", "0.001", "2.170")
        self.check("quantize", 9, h, "2.17", "0.01", "2.17")
        self.check("quantize", 9, h, "2.17", "0.1", "2.2")
        self.check("quantize", 9, h, "2.17", "1e+0", "2")
        self.check("quantize", 9, h, "2.17", "1e+1", "0E+1")
        self.check("quantize", 9, h, "-0.1", "1", "-0")
        self.check("quantize", 9, h, "-0", "1e+5", "-0E+5")
        self.check("quantize", 9, h, "217", "1e-1", "217.0")
        self.check("quantize", 9, h, "2.5", "1", "2")
        self.check("quantize", 9, ROUND_HALF_UP, "2.5", "1", "3")
        self.check("quantize", 9, ROUND_CEILING, "-2.5", "1", "-2")
        self.check("quantize", 9, ROUND_FLOOR, "-2.5", "1", "-3")
        self.check("quantize", 3, h, "99.5", "1", "100")
        self.check("quantize", 9, h, "0.00", "1E+3", "0E+3")

    def test_sqrt(self):
        h = ROUND_HALF_EVEN
        self.check("sqrt", 9, h, "0", None, "0")
        self.check("sqrt", 9, h, "-0", None, "-0")
        self.check("sqrt", 9, h, "0.39", None, "0.624499800")
        self.check("sqrt", 9, h, "100", None, "10")
        self.check("sqrt", 9, h, "1", None, "1")
        self.check("sqrt", 9, h, "1.0", None, "1.0")
        self.check("sqrt", 9, h, "1.00", None, "1.0")
        self.check("sqrt", 9, h, "7", None, "2.64575131")
        self.check("sqrt", 9, h, "2", None, "1.41421356")
        self.check("sqrt", 9, h, "0.25", None, "0.5")
        self.check("sqrt", 9, h, "0.250", None, "0.50")
        self.check("sqrt", 9, h, "1E+4", None, "1E+2")
        self.check("sqrt", 9, h, "1E+5", None, "316.227766")
        self.check("sqrt", 9, h, "0E+5", None, "0E+2")
        self.check("sqrt", 9, h, "0E-5", None, "0.000")
        self.check("sqrt", 2, ROUND_UP, "2", None, "1.4")  # sqrt always rounds half-even
        self.check("sqrt", 3, ROUND_CEILING, "2", None, "1.41")
        self.check("sqrt", 1, ROUND_DOWN, "3", None, "2")
        self.check("sqrt", 5, h, "123456789", None, "11111")

    def test_zero_sign_of_sums(self):
        for mode in MODES:
            floor = mode == ROUND_FLOOR
            c = Context(9, mode)
            self.assertEqual(str(c.add("5", "-5")), "-0" if floor else "0", mode)
            self.assertEqual(str(c.sub("5", "5")), "-0" if floor else "0", mode)
            self.assertEqual(str(c.add("0", "-0")), "-0" if floor else "0", mode)
            self.assertEqual(str(c.add("-0", "-0")), "-0", mode)
            self.assertEqual(str(c.add("0", "0")), "0", mode)
            self.assertEqual(str(c.sub("-0", "0")), "-0", mode)
            self.assertEqual(str(c.sub("0", "-0")), "0", mode)
            self.assertEqual(str(c.add("0.00", "0E+2")), "0.00", mode)
            self.assertEqual(str(c.add("-0.00", "-0E+2")), "-0.00", mode)
            self.assertEqual(str(c.add("1.5", "-1.50")), "-0.00" if floor else "0.00", mode)

    def test_errors(self):
        c = Context(9)
        for op in ("div", "divint"):
            with self.assertRaises(DivisionByZero):
                getattr(c, op)("5", "0")
            with self.assertRaises(DivisionByZero):
                getattr(c, op)("-5", "-0.00")
            with self.assertRaises(InvalidOperation) as cm:
                getattr(c, op)("0", "0")
            self.assertNotIsInstance(cm.exception, DivisionByZero)
        for a, b in [("5", "0"), ("0", "0"), ("-5", "0E+3")]:
            with self.assertRaises(InvalidOperation):
                c.rem(a, b)
        with self.assertRaises(InvalidOperation):
            c.sqrt("-1")
        with self.assertRaises(InvalidOperation):
            c.sqrt("-0.0001")
        with self.assertRaises(InvalidOperation):
            Context(3).divint("1E+5", "1")
        with self.assertRaises(InvalidOperation):
            Context(3).divint("1000", "1")
        self.assertEqual(str(Context(3).divint("999", "1")), "999")
        with self.assertRaises(InvalidOperation):
            Context(3).rem("1E+5", "1")
        with self.assertRaises(InvalidOperation):
            Context(2).quantize("999", "1")
        with self.assertRaises(InvalidOperation):
            Context(2).quantize("99.5", "1")
        with self.assertRaises(InvalidOperation):
            Context(2).quantize("1", "1E-2")
        self.assertEqual(str(Context(3).quantize("99.5", "1E+1")), "1.0E+2")

    def test_argument_coercion(self):
        c = Context(5)
        self.assertEqual(str(c.add(1, "2.5")), "3.5")
        self.assertEqual(str(c.mul(Dec("1.5"), 4)), "6.0")
        self.assertEqual(str(c.div(1, 8)), "0.125")
        self.assertEqual(str(c.sqrt(16)), "4")
        with self.assertRaises(TypeError):
            c.add(1.5, 1)
        with self.assertRaises(ValueError):
            c.add("abc", 1)

    def test_results_are_new_dec_and_inputs_untouched(self):
        a, b = Dec("1.5"), Dec("2.25")
        c = Context(2)
        r = c.add(a, b)
        self.assertEqual((str(a), str(b), str(r)), ("1.5", "2.25", "3.8"))
        self.assertIsNot(r, a)

    def test_context_is_independent_of_operators(self):
        # operators on Dec stay exact whatever contexts exist
        Context(2, ROUND_UP)
        self.assertEqual(str(Dec("1.234567") * Dec("9.87654321")), "12.19325432114007")
        self.assertEqual(str(Dec("123456789") * 987654321), "121932631112635269")
        with self.assertRaises(TypeError):
            Dec("1") / Dec("3")


class Differential(unittest.TestCase):
    def run_op(self, op, seed, n, prec_range, maxdigits=13, exp_range=(-8, 8), modes=MODES):
        rng = random.Random(seed)
        for _ in range(n):
            prec = rng.randrange(*prec_range)
            mode = rng.choice(modes)
            a = rnd_operand(rng, maxdigits, exp_range)
            b = rnd_operand(rng, maxdigits, exp_range)
            if op == "quantize" and rng.random() < 0.5:
                b = "1E%d" % rng.randrange(-10, 10)
            args = (op, prec, mode, a, b)
            self.assertEqual(ours(*args), oracle(*args), args)

    def test_add_small_prec(self):
        self.run_op("add", 1, 5000, (1, 8))

    def test_add_wide_prec(self):
        self.run_op("add", 2, 3000, (8, 30), 25, (-20, 20))

    def test_sub(self):
        self.run_op("sub", 3, 5000, (1, 12))

    def test_mul_small_prec(self):
        self.run_op("mul", 4, 5000, (1, 8))

    def test_mul_wide_prec(self):
        self.run_op("mul", 5, 3000, (5, 40), 25, (-30, 30))

    def test_div_small_prec(self):
        self.run_op("div", 6, 6000, (1, 9), 8)

    def test_div_wide_prec(self):
        self.run_op("div", 7, 3000, (5, 40), 25, (-20, 20))

    def test_divint(self):
        self.run_op("divint", 8, 6000, (1, 12), 10, (-6, 6))

    def test_rem(self):
        self.run_op("rem", 9, 6000, (1, 12), 10, (-6, 6))

    def test_quantize(self):
        self.run_op("quantize", 10, 6000, (1, 14), 12, (-10, 10))

    def test_sqrt_small_prec(self):
        self.run_op("sqrt", 11, 6000, (1, 10), 12, (-9, 9))

    def test_sqrt_wide_prec(self):
        self.run_op("sqrt", 12, 1500, (10, 120), 60, (-60, 60))

    def test_each_mode_on_ties(self):
        rng = random.Random(13)
        for mode in MODES:
            for _ in range(800):
                digits = rng.randrange(2, 8)
                coef = rng.randrange(10 ** (digits - 1), 10 ** digits)
                coef = (coef // 10) * 10 + rng.choice([0, 5, 5, 5, 1, 4, 6, 9])
                a = "%s%dE%d" % ("-" if rng.random() < 0.5 else "", coef, rng.randrange(-3, 3))
                prec = rng.randrange(1, digits)
                for op, b in (("add", "0"), ("mul", "1"), ("div", "1"), ("quantize", "1E%d" % rng.randrange(-3, 3))):
                    args = (op, prec, mode, a, b)
                    self.assertEqual(ours(*args), oracle(*args), args)

    def test_huge_precisions(self):
        rng = random.Random(14)
        for prec in (100, 250, 400):
            for op in ("add", "mul", "div", "sqrt", "divint", "rem"):
                for _ in range(40):
                    a = "%d.%dE%d" % (rng.randrange(10 ** 120), rng.randrange(10 ** 120), rng.randrange(-5, 5))
                    b = "%d.%d" % (rng.randrange(1, 10 ** 100), rng.randrange(10 ** 100))
                    args = (op, prec, rng.choice(MODES), a, b)
                    self.assertEqual(ours(*args), oracle(*args), args)

    def test_zero_heavy_operands(self):
        rng = random.Random(15)
        zeros = ["0", "-0", "0.00", "-0.00", "0E+3", "-0E-4", "0E+1", "-0E+2"]
        mixed = zeros + ["1", "-1", "5", "1.50", "-2.5E+1", "10", "0.1"]
        for op, _ in OPS:
            for mode in MODES:
                for _ in range(60):
                    a, b = rng.choice(mixed), rng.choice(mixed)
                    prec = rng.randrange(1, 6)
                    args = (op, prec, mode, a, b)
                    self.assertEqual(ours(*args), oracle(*args), args)


def _mode_tests():
    def mk(mode, seed):
        def t(self):
            rng = random.Random(seed)
            for op, _ in OPS:
                for _ in range(350):
                    prec = rng.randrange(1, 10)
                    a, b = rnd_operand(rng, 11, (-6, 6)), rnd_operand(rng, 11, (-6, 6))
                    args = (op, prec, mode, a, b)
                    self.assertEqual(ours(*args), oracle(*args), args)
        return t

    for n, mode in enumerate(MODES):
        setattr(Differential, "test_mode_%s" % mode.lower(), mk(mode, 200 + n))


_mode_tests()


def _op_seed_tests():
    def mk(op, seed, prec_range):
        def t(self):
            self.run_op(op, seed, 600, prec_range, 9, (-5, 5))
        return t

    for n, (op, _) in enumerate(OPS):
        setattr(Differential, "test_extra_%s_narrow" % op, mk(op, 700 + n, (1, 5)))
        setattr(Differential, "test_extra_%s_medium" % op, mk(op, 800 + n, (5, 16)))


_op_seed_tests()


class NoStdlibDecimal(unittest.TestCase):
    def test_package_does_not_use_decimal_or_fractions(self):
        import re
        from pathlib import Path
        root = Path(dec.__file__).resolve().parent
        pat = re.compile(r"^\s*(?:import|from)\s+(?:decimal|fractions|cdecimal|mpmath|gmpy2?)\b", re.M)
        dyn = re.compile(r"(?:__import__|import_module)\s*\(\s*['\"](?:decimal|fractions)")
        for p in root.rglob("*.py"):
            src = p.read_text(encoding="utf-8")
            self.assertIsNone(pat.search(src), p)
            self.assertIsNone(dyn.search(src), p)

    def test_decimal_module_not_loaded_by_import(self):
        import os
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        root = Path(dec.__file__).resolve().parent.parent
        code = ("import sys; sys.path.insert(0, %r)\n"
                "import dec\n"
                "c = dec.Context(5)\n"
                "r = [c.add('1', '2'), c.div('1', '3'), c.sqrt('2'), c.quantize('1.234', '0.1'), c.rem('7', '3')]\n"
                "print([m for m in ('decimal', '_decimal', '_pydecimal', 'fractions') if m in sys.modules])\n" % str(root))
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tempfile.gettempdir(),
                             env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), "[]")


class EngString(unittest.TestCase):
    def test_examples(self):
        cases = {
            "123": "123", "1.23E+3": "1.23E+3", "1.23E+5": "123E+3", "12.3E+6": "12.3E+6", "0": "0", "0E+3": "0E+3",
            "0E+4": "0.00E+6", "0E+5": "0.0E+6", "0E-7": "0.0E-6", "0.00": "0.00", "1E-7": "100E-9", "1E+1": "10",
            "1E+2": "100", "1E+3": "1E+3", "-1.5E+7": "-15E+6", "1.2E-9": "1.2E-9", "5E-8": "50E-9",
            "0.000001": "0.000001", "0E-8": "0.00E-6",
            "12345678E3": "12.345678E+9", "100E-10": "10.0E-9", "-0E+2": "-0.0E+3",
        }
        for text, want in cases.items():
            self.assertEqual(Dec(text).to_eng_string(), want, text)

    def test_random_against_decimal(self):
        rng = random.Random(16)
        for _ in range(20000):
            text = "%s%dE%d" % ("-" if rng.random() < 0.5 else "", rng.choice([0, 1, 5, 12, 123, rng.randrange(10 ** rng.randrange(1, 12))]),
                         rng.randrange(-20, 21))
            self.assertEqual(Dec(text).to_eng_string(), decimal.Decimal(text).to_eng_string(), text)
            self.assertEqual(str(Dec(text)), str(decimal.Decimal(text)), text)

    def test_results_format_like_decimal(self):
        rng = random.Random(17)
        c = Context(6, ROUND_HALF_UP)
        for _ in range(3000):
            a, b = rnd_operand(rng, 10, (-12, 12)), rnd_operand(rng, 10, (-12, 12))
            r = c.mul(a, b)
            d = decimal.Context(prec=6, rounding=decimal.ROUND_HALF_UP).multiply(decimal.Decimal(a), decimal.Decimal(b))
            self.assertEqual(r.to_eng_string(), d.to_eng_string())


class Legacy(unittest.TestCase):
    def test_old_behaviour(self):
        for text, out in [("1.50", "1.50"), ("-0", "-0"), ("00012", "12"), ("1E+3", "1E+3"), (".5", "0.5"),
                          ("5.", "5"), ("0.000001", "0.000001"), ("0.0000001", "1E-7"), ("123E-2", "1.23"),
                          ("-1.5e-10", "-1.5E-10"), ("0E-3", "0.000"), ("12.5E3", "1.25E+4"), (" 7 ", "7")]:
            self.assertEqual(str(Dec(text)), out)
        self.assertEqual(str(Dec("1.10") + Dec("2.205")), "3.305")
        self.assertEqual(str(Dec("1.10") * Dec("2.0")), "2.200")
        self.assertEqual(str(Dec("5") - Dec("7.25")), "-2.25")
        self.assertEqual(Dec("1.0"), Dec("1"))
        self.assertEqual(hash(Dec("1.0")), hash(Dec("1.000")))
        self.assertEqual(Dec("-12.30").as_tuple(), (1, (1, 2, 3, 0), -2))
        self.assertEqual(str(Dec("2.345").round_places(2)), "2.35")
        self.assertEqual(str(Dec("-2.345").round_places(2)), "-2.35")
        for bad in ["", "abc", "1.2.3", "1e", "NaN", "1_000"]:
            with self.assertRaises(ValueError):
                Dec(bad)


if __name__ == "__main__":
    unittest.main()
