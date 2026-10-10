"""Arithmetic rounded to a precision, following the General Decimal Arithmetic specification."""
from math import isqrt

from .number import Dec

ROUND_UP = "ROUND_UP"
ROUND_DOWN = "ROUND_DOWN"
ROUND_CEILING = "ROUND_CEILING"
ROUND_FLOOR = "ROUND_FLOOR"
ROUND_HALF_UP = "ROUND_HALF_UP"
ROUND_HALF_DOWN = "ROUND_HALF_DOWN"
ROUND_HALF_EVEN = "ROUND_HALF_EVEN"
ROUND_05UP = "ROUND_05UP"
ROUNDINGS = (ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, ROUND_HALF_DOWN,
             ROUND_HALF_EVEN, ROUND_05UP)


class InvalidOperation(ArithmeticError):
    """Result undefined or not representable (0/0, quantize overflow, sqrt of a negative, ...)."""


class DivisionByZero(ArithmeticError):
    """A non-zero number divided by zero."""


def _ndigits(n):
    return len(str(n))


def _round_drop(sign, q, r, base, mode, sticky=False):
    """Round `q` given the dropped remainder `r` out of `base` (and a sticky lower part)."""
    if r == 0 and not sticky:
        return q
    if mode == ROUND_DOWN:
        inc = False
    elif mode == ROUND_UP:
        inc = True
    elif mode == ROUND_CEILING:
        inc = sign == 0
    elif mode == ROUND_FLOOR:
        inc = sign == 1
    elif mode == ROUND_05UP:
        inc = q % 10 in (0, 5)
    else:
        twice = 2 * r
        if twice > base or (twice == base and sticky):
            inc = True
        elif twice < base:
            inc = False
        elif mode == ROUND_HALF_UP:
            inc = True
        elif mode == ROUND_HALF_DOWN:
            inc = False
        else:
            inc = q % 2 == 1
    return q + 1 if inc else q


def _round_prec(sign, coef, exp, prec, mode, sticky=False):
    n = _ndigits(coef)
    if n <= prec:
        return coef, exp
    drop = n - prec
    base = 10 ** drop
    q, r = divmod(coef, base)
    q = _round_drop(sign, q, r, base, mode, sticky)
    if _ndigits(q) > prec:
        q //= 10
        drop += 1
    return q, exp + drop


class Context:
    def __init__(self, prec=28, rounding=ROUND_HALF_EVEN):
        if not isinstance(prec, int) or isinstance(prec, bool) or prec < 1:
            raise ValueError("prec must be a positive integer")
        if rounding not in ROUNDINGS:
            raise ValueError("unknown rounding mode %r" % (rounding,))
        self.prec = prec
        self.rounding = rounding

    def _fix(self, sign, coef, exp):
        coef, exp = _round_prec(sign, coef, exp, self.prec, self.rounding)
        return Dec._make(sign, coef, exp)

    def add(self, a, b):
        a, b = Dec(a), Dec(b)
        e = min(a.exp, b.exp)
        total = (-a.coef if a.sign else a.coef) * 10 ** (a.exp - e) + (-b.coef if b.sign else b.coef) * 10 ** (b.exp - e)
        if total == 0:
            if a.sign and b.sign:
                sign = 1
            elif a.sign != b.sign or (a.coef != 0 or b.coef != 0):
                sign = 1 if self.rounding == ROUND_FLOOR else 0
            else:
                sign = 0
            return Dec._make(sign, 0, e)
        return self._fix(int(total < 0), abs(total), e)

    def sub(self, a, b):
        b = Dec(b)
        return self.add(a, Dec._make(1 - b.sign, b.coef, b.exp))

    def mul(self, a, b):
        a, b = Dec(a), Dec(b)
        sign = a.sign ^ b.sign
        if a.coef == 0 or b.coef == 0:
            return Dec._make(sign, 0, a.exp + b.exp)
        return self._fix(sign, a.coef * b.coef, a.exp + b.exp)

    def div(self, a, b):
        a, b = Dec(a), Dec(b)
        sign = a.sign ^ b.sign
        if b.coef == 0:
            if a.coef == 0:
                raise InvalidOperation("0 / 0")
            raise DivisionByZero("division by zero")
        ideal = a.exp - b.exp
        if a.coef == 0:
            return Dec._make(sign, 0, ideal)
        shift = _ndigits(b.coef) - _ndigits(a.coef) + self.prec + 1
        exp = ideal - shift
        if shift >= 0:
            q, r = divmod(a.coef * 10 ** shift, b.coef)
        else:
            q, r = divmod(a.coef, b.coef * 10 ** -shift)
        if r:
            coef, exp2 = _round_prec(sign, q, exp, self.prec, self.rounding, sticky=True)
            return Dec._make(sign, coef, exp2)
        while exp < ideal and q % 10 == 0:
            q //= 10
            exp += 1
        return self._fix(sign, q, exp)

    def _int_div(self, a, b):
        """(sign of quotient, |quotient| truncated, remainder magnitude, exponent of remainder)."""
        e = min(a.exp, b.exp)
        na = a.coef * 10 ** (a.exp - e)
        nb = b.coef * 10 ** (b.exp - e)
        q, r = divmod(na, nb)
        return q, r, e

    def divint(self, a, b):
        a, b = Dec(a), Dec(b)
        sign = a.sign ^ b.sign
        if b.coef == 0:
            if a.coef == 0:
                raise InvalidOperation("0 // 0")
            raise DivisionByZero("division by zero")
        if a.coef == 0:
            return Dec._make(sign, 0, 0)
        q, _, _ = self._int_div(a, b)
        if _ndigits(q) > self.prec and q:
            raise InvalidOperation("quotient too large")
        return Dec._make(sign, q, 0)

    def rem(self, a, b):
        a, b = Dec(a), Dec(b)
        if b.coef == 0:
            raise InvalidOperation("remainder by zero")
        e = min(a.exp, b.exp)
        if a.coef == 0:
            return Dec._make(a.sign, 0, e)
        q, r, e = self._int_div(a, b)
        if q and _ndigits(q) > self.prec:
            raise InvalidOperation("quotient too large")
        if r == 0:
            return Dec._make(a.sign, 0, e)
        return self._fix(a.sign, r, e)

    def quantize(self, a, b):
        a, b = Dec(a), Dec(b)
        exp = b.exp
        if a.coef == 0:
            return Dec._make(a.sign, 0, exp)
        if a.exp >= exp:
            coef = a.coef * 10 ** (a.exp - exp)
        else:
            drop = exp - a.exp
            base = 10 ** drop
            q, r = divmod(a.coef, base)
            coef = _round_drop(a.sign, q, r, base, self.rounding)
        if _ndigits(coef) > self.prec:
            raise InvalidOperation("quantize result does not fit the precision")
        return Dec._make(a.sign, coef, exp)

    def sqrt(self, a):
        a = Dec(a)
        ideal = a.exp >> 1
        if a.coef == 0:
            return Dec._make(a.sign, 0, ideal)
        if a.sign:
            raise InvalidOperation("square root of a negative number")
        coef, exp = a.coef, a.exp
        if exp & 1:
            coef *= 10
            exp -= 1
        s = max(0, (2 * self.prec + 1 - _ndigits(coef) + 1) // 2)
        n = coef * 100 ** s
        r = isqrt(n)
        exact = r * r == n
        e = exp // 2 - s
        if exact:
            while e < ideal and r % 10 == 0:
                r //= 10
                e += 1
            r, e = _round_prec(0, r, e, self.prec, ROUND_HALF_EVEN)
        else:
            r, e = _round_prec(0, r, e, self.prec, ROUND_HALF_EVEN, sticky=True)
        return Dec._make(0, r, e)
