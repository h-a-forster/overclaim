"""Decimal numbers as (sign, coefficient, exponent) triples: value = (-1)**sign * coef * 10**exp.

Trailing zeros are significant: Dec("1.50") and Dec("1.5") are equal but print differently.
All arithmetic here is exact; there is no rounding or precision limit.
"""
import re

_NUM = re.compile(r"\s*([+-]?)(?:(\d+)(?:\.(\d*))?|\.(\d+))(?:[eE]([+-]?\d+))?\s*")


class Dec:
    __slots__ = ("_sign", "_coef", "_exp")

    def __init__(self, value=0):
        if isinstance(value, Dec):
            self._sign, self._coef, self._exp = value._sign, value._coef, value._exp
        elif isinstance(value, bool):
            raise TypeError("bool is not a valid Dec value")
        elif isinstance(value, int):
            self._sign, self._coef, self._exp = int(value < 0), abs(value), 0
        elif isinstance(value, str):
            m = _NUM.fullmatch(value)
            if not m:
                raise ValueError("invalid decimal literal: %r" % (value,))
            sign, whole, frac, frac_only, exp = m.groups()
            if whole is None:
                whole, frac = "", frac_only
            frac = frac or ""
            self._sign = int(sign == "-")
            self._coef = int(whole + frac)
            self._exp = int(exp or 0) - len(frac)
        else:
            raise TypeError("cannot make a Dec from %s" % type(value).__name__)

    @classmethod
    def _make(cls, sign, coef, exp):
        d = object.__new__(cls)
        d._sign, d._coef, d._exp = sign, coef, exp
        return d

    # ---- inspection
    @property
    def sign(self):
        return self._sign

    @property
    def coef(self):
        return self._coef

    @property
    def exp(self):
        return self._exp

    def is_zero(self):
        return self._coef == 0

    def as_tuple(self):
        """(sign, digits, exponent) with digits a tuple of ints; zero has digits (0,)."""
        return self._sign, tuple(int(c) for c in str(self._coef)), self._exp

    def adjusted(self):
        """Exponent of the most significant digit."""
        return self._exp + len(str(self._coef)) - 1

    # ---- text
    def __str__(self):
        digits = str(self._coef)
        left = self._exp + len(digits)
        if self._exp <= 0 and left > -6:
            dot = left
        else:
            dot = 1
        if dot <= 0:
            body = "0." + "0" * -dot + digits
        elif dot >= len(digits):
            body = digits + "0" * (dot - len(digits))
        else:
            body = digits[:dot] + "." + digits[dot:]
        if left != dot:
            body += "E%+d" % (left - dot)
        return ("-" if self._sign else "") + body

    def __repr__(self):
        return "Dec('%s')" % self

    # ---- exact arithmetic
    def _signed(self):
        return -self._coef if self._sign else self._coef

    def __neg__(self):
        return Dec._make(1 - self._sign, self._coef, self._exp)

    def __abs__(self):
        return Dec._make(0, self._coef, self._exp)

    def __add__(self, other):
        other = _coerce(other)
        if other is NotImplemented:
            return other
        e = min(self._exp, other._exp)
        total = self._signed() * 10 ** (self._exp - e) + other._signed() * 10 ** (other._exp - e)
        sign = int(total < 0 or (total == 0 and self._sign and other._sign))
        return Dec._make(sign, abs(total), e)

    __radd__ = __add__

    def __sub__(self, other):
        other = _coerce(other)
        if other is NotImplemented:
            return other
        return self + (-other)

    def __rsub__(self, other):
        other = _coerce(other)
        if other is NotImplemented:
            return other
        return other + (-self)

    def __mul__(self, other):
        other = _coerce(other)
        if other is NotImplemented:
            return other
        return Dec._make(self._sign ^ other._sign, self._coef * other._coef, self._exp + other._exp)

    __rmul__ = __mul__

    # ---- comparison (numeric: Dec("1.0") == Dec("1"))
    def _cmp(self, other):
        other = _coerce(other)
        if other is NotImplemented:
            return other
        e = min(self._exp, other._exp)
        a = self._signed() * 10 ** (self._exp - e)
        b = other._signed() * 10 ** (other._exp - e)
        return (a > b) - (a < b)

    def __eq__(self, other):
        c = self._cmp(other)
        return c if c is NotImplemented else c == 0

    def __lt__(self, other):
        c = self._cmp(other)
        return c if c is NotImplemented else c < 0

    def __le__(self, other):
        c = self._cmp(other)
        return c if c is NotImplemented else c <= 0

    def __gt__(self, other):
        c = self._cmp(other)
        return c if c is NotImplemented else c > 0

    def __ge__(self, other):
        c = self._cmp(other)
        return c if c is NotImplemented else c >= 0

    def __hash__(self):
        coef, exp = self._coef, self._exp
        while coef and coef % 10 == 0:
            coef //= 10
            exp += 1
        return hash((self._sign if coef else 0, coef, exp if coef else 0))

    # ---- legacy rounding helper (round half up, away from zero on ties)
    def round_places(self, places):
        """Round to `places` digits after the decimal point; ties go away from zero."""
        target = -places
        if self._exp >= target:
            return Dec._make(self._sign, self._coef * 10 ** (self._exp - target), target)
        drop = 10 ** (target - self._exp)
        q, r = divmod(self._coef, drop)
        if 2 * r >= drop:
            q += 1
        return Dec._make(self._sign, q, target)


def _coerce(x):
    if isinstance(x, Dec):
        return x
    if isinstance(x, int) and not isinstance(x, bool):
        return Dec(x)
    return NotImplemented
