import unittest

from urikit import Uri, collect_links, join, parse


class Basics(unittest.TestCase):
    def test_parse_components(self):
        u = parse("http://user@example.com:8080/a/b?x=1#frag")
        self.assertEqual(u, Uri("http", "user@example.com:8080", "/a/b", "x=1", "frag"))
        self.assertEqual(str(u), "http://user@example.com:8080/a/b?x=1#frag")

    def test_absent_vs_empty(self):
        u = parse("//h?#")
        self.assertEqual(u, Uri(None, "h", "", "", ""))
        self.assertEqual(str(u), "//h?#")
        self.assertEqual(parse("a/b"), Uri(None, None, "a/b", None, None))

    def test_join_simple(self):
        self.assertEqual(join("http://a/b/c/d", "e"), "http://a/b/c/e")
        self.assertEqual(join("http://a/b/c/d", "/e"), "http://a/e")
        self.assertEqual(join("http://a/b/c/d?q", "?r"), "http://a/b/c/d?r")
        self.assertEqual(join("http://a/b/c/d", "//h/p"), "http://h/p")
        self.assertEqual(join("http://a/b", "https://z/"), "https://z/")

    def test_collect_links(self):
        got = collect_links("http://a/x/y", ["z", "/z#top", "mailto:me@x", "http://b/", "z"])
        self.assertEqual(got, ["http://a/x/z", "http://a/z", "http://b/"])
