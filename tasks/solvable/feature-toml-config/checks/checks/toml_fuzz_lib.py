import random
KEYS = ["a", "b", "c", '"a"', "'b'", "a . b", "a.b", "a.b.c", "b.a", "c.a.b", '"x y"', "d"]
VALS = ["1", '"s"', "[]", "[1, 2]", "{}", "{x = 1}", "{x.y = 1}", "{x = {y = 1}}", "[{a = 1}]", "true", "'l'",
        "{a.b = 1, a.c = 2}", "[[1], [2]]", "{a = 1, a.b = 2}", "{a.b = 1, a = {}}", "{x = 1,}"]
HEADS = ["[a]", "[a.b]", "[a.b.c]", "[[a]]", "[[a.b]]", "[ a . 'b' ]", "[[a.b.c]]", "[b]", "[b.a]", "[[b]]", "[c]", "[d]", "[a.b.d]", "[[c.a]]", '["a"]']
def gen_doc(rng, n=None):
    lines = []
    for _ in range(n or rng.randrange(1, 8)):
        if rng.random() < 0.4:
            lines.append(rng.choice(HEADS))
        else:
            lines.append("%s = %s" % (rng.choice(KEYS), rng.choice(VALS)))
    return "\n".join(lines) + "\n"

def rand_value_text(rng, depth=0):
    r = rng.randrange(12 if depth < 2 else 9)
    if r == 0:
        return rng.choice(["0", "1", "-1", "+5", "1_000", "0x1F", "0xdead_beef", "0o17", "0b101", "-0", "+0", "123456789012345678901"])
    if r == 1:
        return rng.choice(["1.5", "-0.01", "1e3", "1E-3", "6.02e+23", "1_0.2_5", "0.0", "-0.0", "inf", "-inf", "+inf", "5e0_1", "3.14159"])
    if r == 2:
        return rng.choice(["true", "false"])
    if r == 3:
        body = "".join(rng.choice(['a', 'b', ' ', '\\n', '\\t', '\\"', '\\\\', '\\u00e9', '\\U0001F600', '#', "'", '\\b', '\\f', '\\r', 'é', '\t']) for _ in range(rng.randrange(6)))
        return '"%s"' % body
    if r == 4:
        body = "".join(rng.choice(['a', ' ', '\\', '"', '#', 'é', '\t', '\\n']) for _ in range(rng.randrange(6)))
        return "'%s'" % body
    if r == 5:
        body = "".join(rng.choice(['a', ' ', '\n', '"', '""', '\\\n  ', '\\n', '\\"', '\t', '\\\\', "'"]) for _ in range(rng.randrange(7)))
        return '"""%s"""' % (rng.choice(["", "\n"]) + body + rng.choice(["", '"', '""']))
    if r == 6:
        body = "".join(rng.choice(['a', ' ', '\n', '"', "''", '\\', '\t', "'", '\\n']) for _ in range(rng.randrange(7)))
        return "'''%s'''" % (rng.choice(["", "\n"]) + body + rng.choice(["", "'", "''"]))
    if r == 7:
        items = [rand_value_text(rng, depth + 1) for _ in range(rng.randrange(4))]
        if rng.random() < 0.6:
            return "[" + ", ".join(items) + rng.choice(["", ",", " ,"]) + "]"
        return "[\n  " + ",\n  ".join(items) + ",\n]"
    if r == 8:
        return "{" + ", ".join("%s = %s" % (rng.choice(["a", "b", "c", "a.b", '"q"', "x . y"]), rand_value_text(rng, depth + 1)) for _ in range(rng.randrange(4))) + "}"
    if r == 9:
        return rng.choice(["nan", "-nan", "1e400", "1__0", "01", "0x", "1.", ".5", "1.e3", "+0x1", "0B1", "tru", "True", "inf1", "0_1", "1_", "_1", "'", '"', "9223372036854775808", "0xg"])
    return "[" + rand_value_text(rng, depth + 1) + "]"

def mutate(rng, doc):
    pool = list("=[]{},.'\"# \n_+-eE0x\\1")
    d = list(doc)
    for _ in range(rng.randrange(1, 3)):
        if not d: break
        k = rng.randrange(len(d) + 1)
        r = rng.random()
        if r < 0.4: d.insert(k, rng.choice(pool))
        elif r < 0.7 and k < len(d): del d[k]
        elif k < len(d): d[k] = rng.choice(pool)
    return "".join(d)
