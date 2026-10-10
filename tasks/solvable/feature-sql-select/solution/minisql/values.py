"""SQL value semantics (SQLite flavour): NULL is None, comparisons are three-valued."""
import re

from .errors import SqlError


def rank_key(v):
    """Total order used by comparisons, ORDER BY, MIN/MAX: NULL < numbers < text."""
    if v is None:
        return (0, 0)
    if isinstance(v, str):
        return (2, v)
    return (1, v)


def compare(a, b):
    """-1/0/1 or None if either side is NULL."""
    if a is None or b is None:
        return None
    ka, kb = rank_key(a), rank_key(b)
    return (ka > kb) - (ka < kb)


def truth(v):
    if v is None:
        return None
    if isinstance(v, str):
        m = re.match(r"\s*[-+]?(\d+\.?\d*|\.\d+)", v)
        return bool(m and float(m.group().strip()) != 0)
    return v != 0


def boolval(b):
    return None if b is None else int(b)


def tonum(v):
    if isinstance(v, str):
        m = re.match(r"\s*[-+]?(\d+\.?\d*|\.\d+)", v)
        if not m:
            return 0
        s = m.group().strip()
        return float(s) if "." in s else int(s)
    return v


def arith(op, a, b):
    if a is None or b is None:
        return None
    a, b = tonum(a), tonum(b)
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            return None
        if isinstance(a, int) and isinstance(b, int):
            q = abs(a) // abs(b)
            return q if (a < 0) == (b < 0) else -q
        return a / b
    if op == "%":
        ai, bi = int(a), int(b)
        if bi == 0:
            return None
        r = abs(ai) % abs(bi)
        r = -r if ai < 0 else r
        return float(r) if isinstance(a, float) or isinstance(b, float) else r
    raise SqlError("bad operator %s" % op)


def like(value, pattern):
    if value is None or pattern is None:
        return None
    rx = "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in str(pattern))
    return int(re.fullmatch(rx, str(value), re.I | re.S) is not None)


def in_list(v, items):
    """Result of `v IN (items)` as 1/0/None."""
    if not items:
        return 0
    if v is None:
        return None
    saw_null = False
    for x in items:
        if x is None:
            saw_null = True
        elif compare(v, x) == 0:
            return 1
    return None if saw_null else 0


def substr(s, start, length=None):
    if s is None or start is None:
        return None
    s = str(s)
    n = len(s)
    start = int(start)
    if length is None:
        length = n + abs(start) + 1
    length = int(length)
    if start < 0:
        start += n
        if start < 0:
            length += start
            start = 0
    elif start > 0:
        start -= 1
    elif length > 0:
        length -= 1
    if length < 0:
        start += length
        length = -length
        if start < 0:
            length += start
            start = 0
    return s[start:start + max(length, 0)]


def scalar_function(name, args):
    n = len(args)
    if name == "coalesce":
        if n < 2:
            raise SqlError("coalesce needs at least 2 arguments")
        for a in args:
            if a is not None:
                return a
        return None
    if name == "ifnull":
        if n != 2:
            raise SqlError("ifnull needs 2 arguments")
        return args[0] if args[0] is not None else args[1]
    if name == "nullif":
        if n != 2:
            raise SqlError("nullif needs 2 arguments")
        return None if compare(args[0], args[1]) == 0 else args[0]
    if name in ("abs", "length", "upper", "lower"):
        if n != 1:
            raise SqlError("%s needs 1 argument" % name)
        v = args[0]
        if v is None:
            return None
        if name == "abs":
            return abs(tonum(v))
        if name == "length":
            return len(str(v))
        return str(v).upper() if name == "upper" else str(v).lower()
    if name == "substr":
        if n not in (2, 3):
            raise SqlError("substr needs 2 or 3 arguments")
        if any(a is None for a in args):
            return None
        return substr(*args)
    raise SqlError("no such function: %s" % name)


def aggregate(name, distinct, values, star=False, count=0):
    """values: argument values (already evaluated per row)."""
    if name == "count":
        if star:
            return count
        vals = [v for v in values if v is not None]
        return len(set(vals)) if distinct else len(vals)
    vals = [v for v in values if v is not None]
    if distinct:
        seen, uniq = set(), []
        for v in vals:
            if v not in seen:
                seen.add(v)
                uniq.append(v)
        vals = uniq
    if not vals:
        return 0.0 if name == "total" else None
    if name == "sum":
        return sum(tonum(v) for v in vals)
    if name == "total":
        return float(sum(tonum(v) for v in vals))
    if name == "avg":
        return float(sum(tonum(v) for v in vals)) / len(vals)
    if name == "min":
        return min(vals, key=rank_key)
    if name == "max":
        return max(vals, key=rank_key)
    raise SqlError("no such aggregate: %s" % name)
