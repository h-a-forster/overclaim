import random
import re
import unittest

from urikit import (Uri, UriError, collect_links, equivalent, join, normalize, parse,
                    remove_dot_segments, resolve)

BASE = "http://a/b/c/d;p?q"

NORMAL = [
    ("g:h", "g:h"), ("g", "http://a/b/c/g"), ("./g", "http://a/b/c/g"), ("g/", "http://a/b/c/g/"),
    ("/g", "http://a/g"), ("//g", "http://g"), ("?y", "http://a/b/c/d;p?y"),
    ("g?y", "http://a/b/c/g?y"), ("#s", "http://a/b/c/d;p?q#s"), ("g#s", "http://a/b/c/g#s"),
    ("g?y#s", "http://a/b/c/g?y#s"), (";x", "http://a/b/c/;x"), ("g;x", "http://a/b/c/g;x"),
    ("g;x?y#s", "http://a/b/c/g;x?y#s"), ("", "http://a/b/c/d;p?q"), (".", "http://a/b/c/"),
    ("./", "http://a/b/c/"), ("..", "http://a/b/"), ("../", "http://a/b/"), ("../g", "http://a/b/g"),
    ("../..", "http://a/"), ("../../", "http://a/"), ("../../g", "http://a/g"),
]
ABNORMAL = [
    ("../../../g", "http://a/g"), ("../../../../g", "http://a/g"), ("/./g", "http://a/g"),
    ("/../g", "http://a/g"), ("g.", "http://a/b/c/g."), (".g", "http://a/b/c/.g"),
    ("g..", "http://a/b/c/g.."), ("..g", "http://a/b/c/..g"), ("./../g", "http://a/b/g"),
    ("./g/.", "http://a/b/c/g/"), ("g/./h", "http://a/b/c/g/h"), ("g/../h", "http://a/b/c/h"),
    ("g;x=1/./y", "http://a/b/c/g;x=1/y"), ("g;x=1/../y", "http://a/b/c/y"),
    ("g?y/./x", "http://a/b/c/g?y/./x"), ("g?y/../x", "http://a/b/c/g?y/../x"),
    ("g#s/./x", "http://a/b/c/g#s/./x"), ("g#s/../x", "http://a/b/c/g#s/../x"),
    ("http:g", "http:g"),
]


class Rfc3986Examples(unittest.TestCase):
    def test_normal_examples(self):
        for ref, want in NORMAL:
            with self.subTest(ref=ref):
                self.assertEqual(resolve(BASE, ref), want)

    def test_abnormal_examples(self):
        for ref, want in ABNORMAL:
            with self.subTest(ref=ref):
                self.assertEqual(resolve(BASE, ref), want)

    def test_join_is_resolve(self):
        for ref, want in NORMAL + ABNORMAL:
            self.assertEqual(join(BASE, ref), want)

    def test_empty_ref_keeps_base_query_drops_fragment(self):
        self.assertEqual(resolve("http://a/b?q#frag", ""), "http://a/b?q")
        self.assertEqual(resolve("http://a/b?q#frag", "#n"), "http://a/b?q#n")
        self.assertEqual(resolve("http://a/b?q#frag", "?"), "http://a/b?")
        self.assertEqual(resolve("http://a/b?q#frag", "#"), "http://a/b?q#")
        self.assertEqual(resolve("http://a/b?q", "?r#"), "http://a/b?r#")

    def test_base_without_path(self):
        self.assertEqual(resolve("http://a", "g"), "http://a/g")
        self.assertEqual(resolve("http://a", "../g"), "http://a/g")
        self.assertEqual(resolve("http://a", ""), "http://a")
        self.assertEqual(resolve("http://a?x", ""), "http://a?x")
        self.assertEqual(resolve("http://a?x", "?y"), "http://a?y")
        self.assertEqual(resolve("http://a", "?y"), "http://a?y")
        self.assertEqual(resolve("http://a", "#f"), "http://a#f")
        self.assertEqual(resolve("http://a", "./"), "http://a/")
        self.assertEqual(resolve("http://a", "."), "http://a/")

    def test_base_without_authority(self):
        self.assertEqual(resolve("foo:a/b/c", "d"), "foo:a/b/d")
        self.assertEqual(resolve("foo:a/b/c", "../d"), "foo:a/d")
        self.assertEqual(resolve("foo:/a/b/c", "../../../d"), "foo:/d")
        self.assertEqual(resolve("mailto:x@y", "z"), "mailto:z")
        self.assertEqual(resolve("urn:a:b", ""), "urn:a:b")
        self.assertEqual(resolve("urn:a:b", "?q"), "urn:a:b?q")
        self.assertEqual(resolve("foo:", "bar"), "foo:bar")
        self.assertEqual(resolve("foo:a/b", "/c"), "foo:/c")
        self.assertEqual(resolve("foo:/a", "//h/p"), "foo://h/p")

    def test_relative_path_buffer_quirk(self):
        # RFC 5.2.4 is a buffer algorithm: a rootless merge result can gain a leading slash
        self.assertEqual(remove_dot_segments("a/../../b"), "/b")
        self.assertEqual(remove_dot_segments("../a"), "a")
        self.assertEqual(remove_dot_segments("./../a/./b/.."), "a/")
        self.assertEqual(remove_dot_segments("a/b/.."), "a/")
        self.assertEqual(remove_dot_segments("a/.."), "/")
        self.assertEqual(remove_dot_segments("/a/b/c/./../../g"), "/a/g")
        self.assertEqual(remove_dot_segments("mid/content=5/../6"), "mid/6")
        self.assertEqual(remove_dot_segments(""), "")
        self.assertEqual(remove_dot_segments("."), "")
        self.assertEqual(remove_dot_segments(".."), "")
        self.assertEqual(remove_dot_segments("/.."), "/")
        self.assertEqual(remove_dot_segments("/."), "/")
        self.assertEqual(remove_dot_segments("//a//../b"), "//a/b")
        self.assertEqual(remove_dot_segments("/a//b/../.."), "/a/")
        self.assertEqual(remove_dot_segments("/..a/.b/c.."), "/..a/.b/c..")

    def test_scheme_ref_dot_segments_are_removed(self):
        self.assertEqual(resolve(BASE, "x://h/a/./b/../c"), "x://h/a/c")
        self.assertEqual(resolve(BASE, "//h/a/../../b"), "http://h/b")
        self.assertEqual(resolve(BASE, "x:a/../../b"), "x:/b")

    def test_scheme_case_is_kept_by_resolve(self):
        self.assertEqual(resolve("HTTP://A/b", "c"), "HTTP://A/c")
        self.assertEqual(resolve("http://a/b", "HTTP:c"), "HTTP:c")

    def test_base_fragment_ignored_and_ref_percent_untouched(self):
        self.assertEqual(resolve("http://a/b#x", "c%2fd"), "http://a/c%2fd")
        self.assertEqual(resolve("http://a/b/%2e%2e/c", "d"), "http://a/b/%2e%2e/d")

    def test_base_must_be_absolute(self):
        for base in ("a/b", "/a", "", "//h/p", "?q", "#f"):
            with self.assertRaises(UriError, msg=base):
                resolve(base, "x")

    def test_invalid_inputs(self):
        with self.assertRaises(UriError):
            resolve("http://a/b c", "x")
        with self.assertRaises(UriError):
            resolve("http://a/b", "x y")
        with self.assertRaises(UriError):
            resolve("http://a/b", "%zz")


# ---- oracle: RFC 3986 pseudo-code transcribed literally -------------------------------------

APPX_B = re.compile(r"^(([^:/?#]+):)?(//([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?", re.S)


def o_split(u):
    m = APPX_B.match(u)
    return (m.group(2), m.group(4), m.group(5), m.group(7), m.group(9))


def o_rds(path):
    inp, out = path, ""
    while inp:
        if inp[:3] == "../":
            inp = inp[3:]
        elif inp[:2] == "./":
            inp = inp[2:]
        elif inp[:3] == "/./":
            inp = "/" + inp[3:]
        elif inp == "/.":
            inp = "/"
        elif inp[:4] == "/../":
            inp = "/" + inp[4:]
            out = out[: out.rfind("/")] if "/" in out else ""
        elif inp == "/..":
            inp = "/"
            out = out[: out.rfind("/")] if "/" in out else ""
        elif inp in (".", ".."):
            inp = ""
        else:
            start = 1 if inp[0] == "/" else 0
            k = inp.find("/", start)
            k = len(inp) if k < 0 else k
            out += inp[:k]
            inp = inp[k:]
    return out


def o_merge(b, rpath):
    if b[1] is not None and b[2] == "":
        return "/" + rpath
    i = b[2].rfind("/")
    return b[2][: i + 1] + rpath


def o_recompose(s, a, p, q, f):
    r = ""
    if s is not None:
        r += s + ":"
    if a is not None:
        r += "//" + a
    r += p
    if q is not None:
        r += "?" + q
    if f is not None:
        r += "#" + f
    return r


def o_resolve(base, ref):
    B, R = o_split(base), o_split(ref)
    if R[0] is not None:
        return o_recompose(R[0], R[1], o_rds(R[2]), R[3], R[4])
    if R[1] is not None:
        return o_recompose(B[0], R[1], o_rds(R[2]), R[3], R[4])
    if R[2] == "":
        q = R[3] if R[3] is not None else B[3]
        return o_recompose(B[0], B[1], B[2], q, R[4])
    if R[2][0] == "/":
        path = o_rds(R[2])
    else:
        path = o_rds(o_merge(B, R[2]))
    return o_recompose(B[0], B[1], path, R[3], R[4])


SEGS = ["a", "b", ".", "..", "", "c%2e", "%2E%2e", "a%2Fb", "~x", "%7e", "%7E", "x.y", "..."]
HOSTS = ["a", "Example.COM", "ex.org", "[::1]", "%41b", "192.168.0.1", "h"]
PORTS = [None, None, "", "80", "443", "0080", "8080"]
SCHEMES = ["http", "HTTP", "Https", "ftp", "file", "urn", "x-y", "ws", "wss", "a+b.c"]
QS = [None, None, "", "a=b", "x%2fy", "%7e", "q?r/s", "a/./b"]


def rand_path(rng, absolute):
    n = rng.randrange(0, 5)
    segs = [rng.choice(SEGS) for _ in range(n)]
    p = "/".join(segs)
    return ("/" + p) if absolute and n else ("/" if absolute and rng.random() < 0.5 else p if not absolute else "")


def rand_uri(rng, scheme_prob=1.0, force_scheme=False):
    s = rng.choice(SCHEMES) if (force_scheme or rng.random() < scheme_prob) else None
    auth = None
    if rng.random() < 0.6:
        auth = rng.choice(HOSTS)
        if rng.random() < 0.2:
            auth = rng.choice(["u", "U%73er:p%41", "x:y"]) + "@" + auth
        port = rng.choice(PORTS)
        if port is not None:
            auth += ":" + port
    if auth is not None:
        path = rand_path(rng, True)
    else:
        path = rand_path(rng, rng.random() < 0.5)
        if s is None and path and ":" in path.split("/")[0]:
            path = "x" + path
    q = rng.choice(QS)
    f = rng.choice(QS)
    return o_recompose(s, auth, path, q, f)


def _add_row_tests():
    def mk_resolve(ref, want):
        def t(self):
            self.assertEqual(resolve(BASE, ref), want)
        return t

    def mk_norm(src, want):
        def t(self):
            self.assertEqual(normalize(src), want)
        return t

    for n, (ref, want) in enumerate(NORMAL + ABNORMAL):
        setattr(Rfc3986Examples, "test_row_%02d" % n, mk_resolve(ref, want))


class ResolveDifferential(unittest.TestCase):
    def test_random_pairs(self):
        rng = random.Random(11)
        for _ in range(4000):
            base = rand_uri(rng, force_scheme=True)
            ref = rand_uri(rng, scheme_prob=0.25)
            self.assertEqual(resolve(base, ref), o_resolve(base, ref), (base, ref))

    def test_random_relative_refs_only(self):
        rng = random.Random(12)
        for _ in range(4000):
            base = rand_uri(rng, force_scheme=True)
            ref = rand_uri(rng, scheme_prob=0.0)
            self.assertEqual(resolve(base, ref), o_resolve(base, ref), (base, ref))

    def test_random_remove_dot_segments(self):
        rng = random.Random(13)
        pieces = [".", "..", "a", "b", "", "...", ".a", "a."]
        for _ in range(5000):
            p = "/".join(rng.choice(pieces) for _ in range(rng.randrange(0, 7)))
            if rng.random() < 0.6:
                p = "/" + p
            if rng.random() < 0.3:
                p += "/"
            self.assertEqual(remove_dot_segments(p), o_rds(p), p)

    def test_resolve_result_is_valid_and_stable(self):
        rng = random.Random(14)
        for _ in range(1500):
            base = rand_uri(rng, force_scheme=True)
            ref = rand_uri(rng, scheme_prob=0.3)
            out = resolve(base, ref)
            self.assertEqual(str(parse(out)), out)
            if parse(ref).scheme is not None or parse(ref).authority is not None:
                continue
            # resolving an already resolved URI against anything absolute is the identity on
            # dot-free paths
            if "." not in parse(out).path.replace("%2e", "x"):
                self.assertEqual(resolve("http://z/q", out), out)


class ParseValidation(unittest.TestCase):
    VALID = ["http://a", "", "a", "?", "#", "//", "//a", "//a:", "//a:80", "//u:p@h", "//[::1]",
             "//[::1]:80", "//[v1.x]", "a%20b", "/a%2Fb", "mailto:x@y", "urn:a:b", "a/b:c",
             "./a:b", "?a=b/c?d", "#a/b?c", "http://a/b;p=1,2", "//a/b@c", "x:", "x:?", "//a.b.c.d",
             "tel:+1-816", "%41", "//%41", "//u:p:q@h", "http://[2001:db8::1]:8080/p",
             "//[::ffff:1.2.3.4]", "//[V1F.a:b]", "a;b", "/!$&'()*+,;=", "http://a/~x_y-z.w",
             "//:80", "//@h", "///", "////a", "a?b?c#d#e".replace("#d#e", "#d"), "f:/a:b"]
    INVALID = ["a b", "http://a/ b", "<x>", "http://a/%", "%zz", "http://a/%4", "a:b c", "1a:x",
               ":a", "http://a:80x/", "http://a:-1/", "//[::1", "//[::1]x", "//[zz]", "//[]",
               "//[1]", "//a]", "a[b", "http://a/b[1]", "http://a/?q[1]", "http://a/#f[", "\u00fc",
               "http://\u00fc/", "a\\b", "http://a@b@c/", "x y:z", "-a:b", "a_b:c", "http://a b/",
               "//h:1 /", "\t", "http://a/\n", "a\n", "http://a/{}", "http://a/|", "http://a/^",
               '"', "http://a/`", "//[::1]:x", "//[:::]x", "//u@[::1", "a:b:c d", "http://a/%%41",
               "//[v.x]", "//[g::1]", "//h%/p", "//%4/p"]

    def test_valid(self):
        for s in self.VALID:
            with self.subTest(s=s):
                self.assertEqual(str(parse(s)), s)

    def test_invalid(self):
        for s in self.INVALID:
            with self.subTest(s=repr(s)):
                with self.assertRaises(UriError):
                    parse(s)

    def test_uri_error_is_value_error(self):
        self.assertTrue(issubclass(UriError, ValueError))

    def test_non_string(self):
        with self.assertRaises(UriError):
            parse(None)

    def test_components(self):
        u = parse("http://u:p@h:81/p?q#f")
        self.assertEqual(tuple(u), ("http", "u:p@h:81", "/p", "q", "f"))
        self.assertEqual((u.userinfo, u.host, u.port), ("u:p", "h", 81))
        u = parse("//[::1]:8080/")
        self.assertEqual((u.userinfo, u.host, u.port), (None, "[::1]", 8080))
        u = parse("//h:/")
        self.assertEqual((u.userinfo, u.host, u.port), (None, "h", None))
        u = parse("//h")
        self.assertEqual((u.userinfo, u.host, u.port), (None, "h", None))
        u = parse("//@h:0080")
        self.assertEqual((u.userinfo, u.host, u.port), ("", "h", 80))
        u = parse("a/b?c")
        self.assertEqual((u.scheme, u.authority, u.userinfo, u.host, u.port), (None, None, None, None, None))
        self.assertTrue(parse("x:y").is_absolute)
        self.assertFalse(parse("//x").is_absolute)
        u = parse("//[::1]")
        self.assertEqual(u.port, None)

    def test_absent_vs_empty_survive(self):
        for s in ["//h?#", "//h", "//h?", "//h#", "a?", "a#", "x:?#", "x:", "//h:"]:
            self.assertEqual(str(parse(s)), s)
        self.assertEqual(parse("x:?#"), Uri("x", None, "", "", ""))

    def test_random_valid_roundtrip(self):
        rng = random.Random(21)
        for _ in range(3000):
            s = rand_uri(rng, scheme_prob=0.5)
            self.assertEqual(str(parse(s)), s)

    def test_random_invalid_character_injection(self):
        rng = random.Random(22)
        bad = ' <>"{}|\\^`[]%\u00e9\n'
        n = 0
        for _ in range(1500):
            s = rand_uri(rng, scheme_prob=0.5)
            k = rng.randrange(len(s) + 1)
            c = rng.choice(bad)
            t = s[:k] + c + s[k:]
            if c in "[]":
                # brackets are legal only around an IP literal host: just require no crash
                try:
                    parse(t)
                except UriError:
                    pass
                continue
            if c == "%" and re.match(r"[0-9A-Fa-f]{2}", t[k + 1:k + 3] or "zz"):
                continue
            with self.assertRaises(UriError, msg=repr(t)):
                parse(t)
            n += 1
        self.assertGreater(n, 1000)


# ---- normalisation oracle -----------------------------------------------------------------

UNRES = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def o_pct(s):
    out, i = "", 0
    while i < len(s):
        if s[i] == "%":
            h = s[i + 1:i + 3]
            ch = chr(int(h, 16))
            out += ch if ch in UNRES else "%" + h.upper()
            i += 3
        else:
            out += s[i]
            i += 1
    return out


def o_normalize(u):
    sch, auth, path, q, f = o_split(u)
    sch = sch.lower()
    if auth is not None:
        ui = None
        hp = auth
        if "@" in auth:
            ui, hp = auth.rsplit("@", 1)
        if hp.endswith("]") or "]" not in hp:
            host, _, port = hp.rpartition(":") if (":" in hp and not hp.endswith("]")) and "[" not in hp else (hp, "", "")
        else:
            host, _, port = hp.rpartition("]:")
            host += "]"
        if "[" in hp and not hp.endswith("]"):
            host = hp[: hp.index("]") + 1]
            port = hp[hp.index("]") + 2:]
        host = o_pct(host).lower()
        default = {"http": 80, "https": 443, "ftp": 21, "ws": 80, "wss": 443}.get(sch)
        keep = port != "" and (default is None or int(port) != default)
        auth = (o_pct(ui) + "@" if ui is not None else "") + host + (":" + port if keep else "")
    path = o_rds(o_pct(path))
    if auth is not None and path == "" and sch in ("http", "https", "ftp", "ws", "wss"):
        path = "/"
    return o_recompose(sch, auth, path, None if q is None else o_pct(q), None if f is None else o_pct(f))


NORM = [
    ("HTTP://Example.COM/", "http://example.com/"),
    ("http://example.com", "http://example.com/"),
    ("http://example.com:80/", "http://example.com/"),
    ("http://example.com:/", "http://example.com/"),
    ("http://example.com:8080/", "http://example.com:8080/"),
    ("https://example.com:443/a", "https://example.com/a"),
    ("https://example.com:80/a", "https://example.com:80/a"),
    ("http://example.com:443/a", "http://example.com:443/a"),
    ("ftp://h:21", "ftp://h/"), ("ws://h:80", "ws://h/"), ("wss://h:443", "wss://h/"),
    ("foo://h:80", "foo://h:80"), ("foo://H", "foo://h"), ("foo://h:", "foo://h"),
    ("http://a/%7euser", "http://a/~user"), ("http://a/%7Euser", "http://a/~user"),
    ("http://a/%2f", "http://a/%2F"), ("http://a/%3a%3A", "http://a/%3A%3A"),
    ("http://a/b/./c/../d", "http://a/b/d"), ("http://a/%2e%2E/x", "http://a/x"),
    ("http://a/a%2Fb", "http://a/a%2Fb"),
    ("http://U%73er:P%61ss@Host/", "http://User:Pass@host/"),
    ("http://a?q", "http://a/?q"), ("http://a#f", "http://a/#f"),
    ("http://a/?", "http://a/?"), ("http://a/#", "http://a/#"), ("http://a?", "http://a/?"),
    ("mailto:Me@X.com", "mailto:Me@X.com"), ("URN:ISBN:1", "urn:ISBN:1"),
    ("file:///A/./b", "file:///A/b"), ("file://", "file://"),
    ("http://[::A]:80/", "http://[::a]/"), ("http://[::A]:81/", "http://[::a]:81/"),
    ("http://a/%e2%82%ac", "http://a/%E2%82%AC"),
    ("http://%41.%42/", "http://a.b/"), ("http://a:0080/", "http://a/"),
    ("http://a:00081/", "http://a:00081/"), ("x:/a/../../b", "x:/b"), ("x:a/../../b", "x:/b"),
    ("x:./a", "x:a"), ("http://a/?%7e=%7E&b=%3d", "http://a/?~=~&b=%3D"),
    ("http://a/#%7e%2f", "http://a/#~%2F"), ("HTTP://A/B/C", "http://a/B/C"),
    ("http://a/b/../../..", "http://a/"), ("http://a/b/..", "http://a/"),
    ("http://a//b///c", "http://a//b///c"), ("http://a/./", "http://a/"),
    ("http://a/%2E", "http://a/"), ("http://a/%2e%2e/b/%2E/c", "http://a/b/c"),
    ("http://User@a/", "http://User@a/"), ("http://:@a/", "http://:@a/"),
    ("tel:+1-816-555-1212", "tel:+1-816-555-1212"),
    ("a+b.c://H/%41", "a+b.c://h/A"),
    ("http://a/%5B%5d", "http://a/%5B%5D"),
]


class Normalize(unittest.TestCase):
    def test_table(self):
        for src, want in NORM:
            with self.subTest(src=src):
                self.assertEqual(normalize(src), want)

    def test_idempotent_on_table(self):
        for _, want in NORM:
            self.assertEqual(normalize(want), want)

    def test_requires_absolute(self):
        for s in ("a/b", "/a", "", "//h/p", "?q", "../a"):
            with self.assertRaises(UriError, msg=s):
                normalize(s)

    def test_invalid_raises(self):
        for s in ("http://a/ b", "http://a/%zz", "http://a:x/"):
            with self.assertRaises(UriError, msg=s):
                normalize(s)

    def test_equivalent(self):
        self.assertTrue(equivalent("HTTP://a:80/%7Ex", "http://A/~x"))
        self.assertTrue(equivalent("http://a", "http://a/"))
        self.assertTrue(equivalent("http://a/b/../c", "http://a/c"))
        self.assertFalse(equivalent("http://a/%2F", "http://a/"))
        self.assertFalse(equivalent("http://a/?", "http://a/"))
        self.assertFalse(equivalent("http://a/#", "http://a/"))
        self.assertFalse(equivalent("http://a/A", "http://a/a"))
        self.assertFalse(equivalent("http://U@a/", "http://u@a/"))
        self.assertFalse(equivalent("foo://a:80/", "foo://a/"))
        with self.assertRaises(UriError):
            equivalent("http://a", "b")

    def test_random_vs_oracle(self):
        rng = random.Random(31)
        for _ in range(4000):
            s = rand_uri(rng, force_scheme=True)
            self.assertEqual(normalize(s), o_normalize(s), s)

    def test_random_idempotent_and_valid(self):
        rng = random.Random(32)
        for _ in range(3000):
            s = rand_uri(rng, force_scheme=True)
            n = normalize(s)
            if parse(s).authority is None and parse(n).authority is not None:
                continue  # dot-segment removal produced a path starting with "//"
            self.assertEqual(normalize(n), n, s)
            parse(n)

    def test_percent_decoded_dots_then_removed(self):
        self.assertEqual(normalize("http://a/x/%2e%2e/%2E/y"), "http://a/y")
        self.assertEqual(normalize("http://a/x/.%2e/y"), "http://a/y")


_add_row_tests()


class Links(unittest.TestCase):
    def test_collect(self):
        got = collect_links("http://Ex.com/a/b", [
            "c", " d ", "../e#x", "HTTP://EX.COM:80/a/c", "#top", "", "javascript:void(0)",
            "mailto:a@b", "ftp://f/", "//other.org/x", "bad link", "http://ex.com/%7Ex",
            "http://[::1/", "\n\t./c\n"])
        self.assertEqual(got, ["http://ex.com/a/c", "http://ex.com/a/d", "http://ex.com/e",
                               "http://ex.com/a/b", "http://other.org/x", "http://ex.com/~x"])

    def test_https_and_ports(self):
        got = collect_links("https://h:443/p/", ["x", "https://h/p/x", "http://h:80/p/x", "?q", "//h:8443/"])
        self.assertEqual(got, ["https://h/p/x", "http://h/p/x", "https://h/p/?q", "https://h:8443/"])

    def test_fragment_only_dedupes(self):
        self.assertEqual(collect_links("http://h/p#a", ["#b", "#c", "q#d", "q#e"]), ["http://h/p", "http://h/q"])

    def test_empty_and_order(self):
        self.assertEqual(collect_links("http://h/", []), [])
        self.assertEqual(collect_links("http://h/", ["b", "a", "b"]), ["http://h/b", "http://h/a"])

    def test_base_errors_propagate(self):
        for base in ("a/b", "http://h/ x", ""):
            with self.assertRaises(UriError):
                collect_links(base, ["x"])

    def test_query_normalised_and_kept(self):
        self.assertEqual(collect_links("http://h/a", ["?x=%7e#f", "b?%2f"]), ["http://h/a?x=~", "http://h/b?%2F"])

    def test_dot_segments_in_links(self):
        self.assertEqual(collect_links("http://h/a/b/c", ["../../..", "./", ".", "x/../y"]),
                         ["http://h/", "http://h/a/b/", "http://h/a/b/y"])

    def test_random_links_are_normal_forms(self):
        rng = random.Random(41)
        for _ in range(300):
            base = "http://h/%s" % "/".join(rng.choice(SEGS) for _ in range(3))
            refs = [rand_uri(rng, scheme_prob=0.3) for _ in range(6)]
            expect, seen = [], set()
            for r in refs:
                full = o_resolve(base, r)
                s, a, p, q, f = o_split(full)
                n = o_normalize(o_recompose(s, a, p, q, None))
                if n.split(":", 1)[0] in ("http", "https") and n not in seen:
                    seen.add(n)
                    expect.append(n)
            self.assertEqual(collect_links(base, refs), expect, (base, refs))


class Regression(unittest.TestCase):
    def test_uri_value_object(self):
        u = parse("http://user@example.com:8080/a/b?x=1#frag")
        self.assertEqual(u, Uri("http", "user@example.com:8080", "/a/b", "x=1", "frag"))
        self.assertEqual(u.scheme, "http")
        self.assertEqual(u.fragment, "frag")
        self.assertEqual(parse("//h?#"), Uri(None, "h", "", "", ""))
        self.assertEqual(parse("a/b"), Uri(None, None, "a/b", None, None))

    def test_join_old_cases(self):
        self.assertEqual(join("http://a/b/c/d", "e"), "http://a/b/c/e")
        self.assertEqual(join("http://a/b/c/d", "/e"), "http://a/e")
        self.assertEqual(join("http://a/b/c/d?q", "?r"), "http://a/b/c/d?r")
        self.assertEqual(join("http://a/b/c/d", "//h/p"), "http://h/p")
        self.assertEqual(join("http://a/b", "https://z/"), "https://z/")

    def test_collect_links_old_case(self):
        got = collect_links("http://a/x/y", ["z", "/z#top", "mailto:me@x", "http://b/", "z"])
        self.assertEqual(got, ["http://a/x/z", "http://a/z", "http://b/"])


if __name__ == "__main__":
    unittest.main()
