import unittest

from tplr import Template, TemplateSyntaxError, render


class RenderTests(unittest.TestCase):
    def test_text_and_vars(self):
        self.assertEqual(render("Hi {{ name }}!", name="Ada"), "Hi Ada!")
        self.assertEqual(render("{{ a.b.c }}", a={"b": {"c": 5}}), "5")
        self.assertEqual(render("[{{ missing }}][{{ none }}]", none=None), "[][]")

    def test_paths(self):
        self.assertEqual(render("{{ xs.1 }}{{ xs.9 }}", xs=["a", "b"]), "b")

        class Obj:
            title = "T"

        self.assertEqual(render("{{ o.title }}", o=Obj()), "T")

    def test_filters(self):
        self.assertEqual(render("{{ n|upper }} {{ n|title }}", n="ada lovelace"), "ADA LOVELACE Ada Lovelace")
        self.assertEqual(render("{{ xs|join }} {{ xs|length }}", xs=[1, 2, 3]), "1, 2, 3 3")

    def test_if(self):
        t = Template("{% if x %}yes{% else %}no{% endif %}")
        self.assertEqual(t.render(x=1), "yes")
        self.assertEqual(t.render(x=0), "no")
        self.assertEqual(t.render(), "no")

    def test_for(self):
        self.assertEqual(render("{% for x in xs %}<{{ x }}>{% endfor %}", xs=[1, 2]), "<1><2>")
        self.assertEqual(render("{% for x in xs %}<{{ x }}>{% endfor %}"), "")

    def test_nested(self):
        src = "{% for r in rows %}{% if r.ok %}{{ r.n }}{% else %}-{% endif %}{% endfor %}"
        self.assertEqual(render(src, rows=[{"ok": 1, "n": "a"}, {"ok": 0, "n": "b"}]), "a-")

    def test_comment(self):
        self.assertEqual(render("a{# hidden #}b"), "ab")

    def test_line_numbers(self):
        with self.assertRaises(TemplateSyntaxError) as ctx:
            Template("one\ntwo\n{% bogus %}")
        self.assertEqual(ctx.exception.line, 3)
        with self.assertRaises(TemplateSyntaxError) as ctx:
            Template("{% if x %}\nbody")
        self.assertEqual(ctx.exception.line, 1)

    def test_errors(self):
        for bad in ["{% endif %}", "{% else %}", "{{ x|nope }}", "{% for x xs %}{% endfor %}"]:
            with self.assertRaises(TemplateSyntaxError, msg=bad):
                Template(bad)


if __name__ == "__main__":
    unittest.main()
