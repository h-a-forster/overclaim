import unittest

from tplr import Template, TemplateError, TemplateRenderError, TemplateSyntaxError, render


def syntax_line(src):
    with unittest.TestCase().assertRaises(TemplateSyntaxError) as ctx:
        Template(src)
    return ctx.exception.line


class Lexing(unittest.TestCase):
    def test_close_delimiter_inside_string(self):
        self.assertEqual(render('{{ x|default("}}") }}'), "}}")
        self.assertEqual(render("{{ x|default('%}') }}|{% if 'a#}' %}y{% endif %}"), "%}|y")

    def test_escaped_quote_in_string(self):
        self.assertEqual(render(r'{{ x|default("a\"}}b") }}'), 'a"}}b')
        self.assertEqual(render(r"{{ 'it\'s' }}"), "it's")

    def test_string_escapes(self):
        self.assertEqual(render(r'{{ "a\nb\tc\\d\q" }}'), "a\nb\tc\\dq")

    def test_unterminated(self):
        self.assertEqual(syntax_line("ok\n{{ x"), 2)
        self.assertEqual(syntax_line("a\nb\n{% if x"), 3)
        self.assertEqual(syntax_line("{# never closed\n\n"), 1)
        self.assertEqual(syntax_line('{{ "abc }} still open'), 1)

    def test_comment_ends_at_first_close(self):
        self.assertEqual(render("a{# it's \"x #}b"), "ab")
        self.assertEqual(render("a{# {{ x }} #}b", x=1), "ab")

    def test_strip_before_and_after(self):
        self.assertEqual(render("a  \n  {{- x -}}  \n  b", x="X"), "aXb")
        self.assertEqual(render("a  {{- x }}  b", x="X"), "aX  b")
        self.assertEqual(render("a  {{ x -}}  b", x="X"), "a  Xb")

    def test_strip_tags_and_comments(self):
        src = "<ul>\n  {%- for i in xs %}\n  <li>{{ i }}</li>\n  {%- endfor %}\n</ul>"
        self.assertEqual(render(src, xs=[1, 2]), "<ul>\n  <li>1</li>\n  <li>2</li>\n</ul>")
        self.assertEqual(render("a \n{#- c -#}\n b"), "ab")
        self.assertEqual(render("x\n{%- if y -%}\n  yes\n{%- endif -%}\n z", y=1), "xyesz")

    def test_strip_only_adjacent_text(self):
        self.assertEqual(render("a {{- 1 }}{{ 2 -}} b"), "a12b")
        self.assertEqual(render("a\n\n{%- if x %} b {% endif -%}\n\nc", x=0), "ac")

    def test_lines_after_stripping(self):
        self.assertEqual(syntax_line("a\n\n\n{{- x -}}\n\n{% bogus %}"), 6)


class Expressions(unittest.TestCase):
    def test_literals(self):
        self.assertEqual(render('{{ 5 }}|{{ -3 }}|{{ 2.5 }}|{{ "s" }}|{{ true }}|{{ false }}|[{{ none }}]'),
                         "5|-3|2.5|s|True|False|[]")

    def test_comparisons(self):
        ctx = {"n": 5, "s": "abc", "xs": [1, 2], "d": {"k": 1}}
        for expr, want in [
            ("n == 5", True), ("n != 5", False), ("n < 6", True), ("n <= 4", False), ("n > 4", True),
            ("n >= 5", True), ("s == 'abc'", True), ("s < 'abd'", True), ("1 in xs", True),
            ("3 in xs", False), ("3 not in xs", True), ("'b' in s", True), ("'k' in d", True),
            ("'z' not in d", True), ("n == 5.0", True),
        ]:
            self.assertEqual(render("{{ %s }}" % expr, **ctx), str(want), expr)

    def test_precedence(self):
        self.assertEqual(render("{{ true or false and false }}"), "True")
        self.assertEqual(render("{{ (true or false) and false }}"), "False")
        self.assertEqual(render("{{ not false and false }}"), "False")
        self.assertEqual(render("{{ not (false and false) }}"), "True")
        self.assertEqual(render("{{ not 1 == 2 }}"), "True")
        self.assertEqual(render("{{ 1 == 1 and 2 == 2 or 3 == 4 }}"), "True")
        self.assertEqual(render("{{ not not 3 }}"), "True")

    def test_bool_results_are_bools(self):
        self.assertEqual(render("{{ 5 and 'x' }}|{{ 0 or '' }}|{{ not 0 }}"), "True|False|True")

    def test_type_errors_are_false(self):
        self.assertEqual(render("{{ none < 3 }}|{{ 5 in 3 }}|{{ missing >= 1 }}|{{ 'a' < 1 }}"),
                         "False|False|False|False")
        self.assertEqual(render("{{ 1 in none }}|{{ 1 not in none }}|{{ 1 in missing }}"), "False|True|False")
        self.assertEqual(render("{{ none == none }}|{{ missing == none }}|{{ missing != 1 }}"), "True|True|True")

    def test_filters_in_conditions(self):
        self.assertEqual(render("{% if xs|length > 2 %}big{% else %}small{% endif %}", xs=[1, 2, 3]), "big")
        self.assertEqual(render("{{ name|upper == 'ADA' }}", name="ada"), "True")
        self.assertEqual(render("{{ xs|join('-') == '1-2' }}", xs=[1, 2]), "True")

    def test_filter_chain_and_args(self):
        self.assertEqual(render("{{ '  ada  '|trim|upper }}"), "ADA")
        self.assertEqual(render("{{ xs|join }}|{{ xs|join(' + ') }}|{{ xs|join('') }}", xs=[1, 2, 3]),
                         "1, 2, 3|1 + 2 + 3|123")
        self.assertEqual(render("{{ 'a-b-c'|replace('-', '+') }}"), "a+b+c")
        self.assertEqual(render("{{ xs|first }}{{ xs|last }}", xs=[7, 8, 9]), "79")
        self.assertEqual(render("[{{ xs|first }}][{{ missing|last }}]", xs=[]), "[][]")

    def test_default(self):
        self.assertEqual(render("{{ a|default('n/a') }}|{{ b|default('n/a') }}|{{ c|default('n/a') }}", b="", c="x"),
                         "n/a|n/a|x")
        self.assertEqual(render("{{ z|default(1) }}|{{ f|default(1) }}", z=0, f=False), "0|False")
        self.assertEqual(render("{{ a|default(none)|default('x') }}"), "x")

    def test_truncate(self):
        self.assertEqual(render("{{ s|truncate(5) }}|{{ s|truncate(10) }}|{{ s|truncate(12) }}", s="abcdefghij"),
                         "ab...|abcdefghij|abcdefghij")
        self.assertEqual(render("{{ s|truncate(2) }}|{{ s|truncate(0) }}", s="abcdefghij"), "...|...")
        self.assertEqual(render("[{{ n|truncate(3) }}]", n=None), "[]")

    def test_none_inputs(self):
        self.assertEqual(render("[{{ a|upper }}][{{ a|title }}][{{ a|length }}][{{ a|join }}][{{ a|trim }}]"),
                         "[][][0][][]")

    def test_filter_errors(self):
        for src in ("{{ 5|length }}", "{{ 5|join }}", "{{ 5|first }}", "{{ x|replace(1, 2) }}"):
            with self.assertRaises(TemplateRenderError, msg=src):
                render(src, x="abc")

    def test_parse_time_filter_errors(self):
        self.assertEqual(syntax_line("a\n{{ x|nope }}"), 2)
        self.assertEqual(syntax_line("a\nb\n{{ x|upper(1) }}"), 3)
        self.assertEqual(syntax_line("{{ x|default }}"), 1)
        self.assertEqual(syntax_line("{{ x|replace('a') }}"), 1)
        self.assertEqual(syntax_line("{{ x|join(1, 2) }}"), 1)
        self.assertEqual(syntax_line("{{ x|truncate(y) }}"), 1)

    def test_malformed(self):
        for src in ("{{ }}", "{{ a == }}", "{{ (a }}", "{{ a b }}", "{{ a < b < c }}", "{{ a == b != c }}",
                    "{{ a in b in c }}", "{% if %}x{% endif %}", "{{ and }}", "{{ a && b }}", "{{ x| }}",
                    "{{ 'abc }}", "{{ a = b }}", "{{ not }}", "{{ a not b }}"):
            with self.assertRaises(TemplateSyntaxError, msg=src):
                Template(src)
        Template("{{ (a < b) == (c < d) }}")

    def test_exception_hierarchy(self):
        self.assertTrue(issubclass(TemplateSyntaxError, TemplateError))
        self.assertTrue(issubclass(TemplateRenderError, TemplateError))


class Blocks(unittest.TestCase):
    def test_elif_chain(self):
        t = Template("{% if n < 0 %}neg{% elif n == 0 %}zero{% elif n < 10 %}small{% else %}big{% endif %}")
        self.assertEqual([t.render(n=n) for n in (-1, 0, 5, 50)], ["neg", "zero", "small", "big"])

    def test_elif_without_else_and_first_match_only(self):
        t = Template("{% if a %}A{% elif b %}B{% elif c %}C{% endif %}")
        self.assertEqual(t.render(a=1, b=1, c=1), "A")
        self.assertEqual(t.render(b=1, c=1), "B")
        self.assertEqual(t.render(), "")

    def test_nested_if_in_elif(self):
        src = "{% if a %}1{% elif b %}{% if c %}2{% else %}3{% endif %}{% else %}4{% endif %}"
        t = Template(src)
        self.assertEqual([t.render(a=a, b=b, c=c) for a, b, c in
                          [(1, 0, 0), (0, 1, 1), (0, 1, 0), (0, 0, 0)]], ["1", "2", "3", "4"])

    def test_loop_variables(self):
        src = "{% for x in xs %}{{ loop.index }}/{{ loop.index0 }}/{{ loop.length }}/{{ loop.first }}/{{ loop.last }} {% endfor %}"
        self.assertEqual(render(src, xs="ab"), "1/0/2/True/False 2/1/2/False/True ")

    def test_loop_single_item(self):
        self.assertEqual(render("{% for x in xs %}{{ loop.first and loop.last }}{% endfor %}", xs=[1]), "True")

    def test_loop_in_conditions(self):
        src = "{% for x in xs %}{{ x }}{% if not loop.last %}, {% endif %}{% endfor %}"
        self.assertEqual(render(src, xs=[1, 2, 3]), "1, 2, 3")
        src = "{% for x in xs %}{% if loop.index > 1 and loop.index0 < 3 %}{{ x }}{% endif %}{% endfor %}"
        self.assertEqual(render(src, xs="abcd"), "bc")

    def test_nested_loops_innermost_loop(self):
        src = "{% for a in as %}{{ loop.index }}:{% for b in bs %}{{ loop.index }}{% endfor %}{{ loop.index }};{% endfor %}"
        self.assertEqual(render(src, **{"as": [1, 2], "bs": "xy"}), "1:121;2:122;")

    def test_loop_scope_restored(self):
        src = "{{ x }}{% for x in xs %}{{ x }}{% endfor %}{{ x }}|{{ loop.index }}"
        self.assertEqual(render(src, x="o", xs=[1, 2]), "o12o|")
        self.assertEqual(render("{% for y in xs %}{% endfor %}{{ y }}", xs=[1]), "")

    def test_for_else(self):
        t = Template("{% for x in xs %}{{ x }}{% else %}none{% endfor %}")
        self.assertEqual(t.render(xs=[]), "none")
        self.assertEqual(t.render(xs=None), "none")
        self.assertEqual(t.render(), "none")
        self.assertEqual(t.render(xs=[1, 2]), "12")
        self.assertEqual(t.render(xs=""), "none")

    def test_if_inside_for_else_inside_if(self):
        src = "{% if a %}{% for x in xs %}{% if x %}{{ x }}{% else %}_{% endif %}{% else %}empty{% endfor %}{% else %}off{% endif %}"
        t = Template(src)
        self.assertEqual(t.render(a=1, xs=[1, 0, 2]), "1_2")
        self.assertEqual(t.render(a=1, xs=[]), "empty")
        self.assertEqual(t.render(a=0, xs=[1]), "off")

    def test_unpacking(self):
        self.assertEqual(render("{% for k, v in pairs %}{{ k }}={{ v }};{% endfor %}", pairs=[("a", 1), ["b", 2]]),
                         "a=1;b=2;")
        self.assertEqual(render("{% for a,b,c in rows %}{{ c }}{{ b }}{{ a }}{% endfor %}", rows=["xyz", [1, 2, 3]]),
                         "zyx321")
        self.assertEqual(render("{% for k, v in d.items %}{{ k }}{% endfor %}", d={"items": [(1, 2)]}), "1")

    def test_unpacking_errors(self):
        for xs in ([(1, 2, 3)], [(1,)], [5]):
            with self.assertRaises(TemplateRenderError):
                render("{% for a, b in xs %}x{% endfor %}", xs=xs)

    def test_iteration_kinds(self):
        self.assertEqual(render("{% for c in s %}[{{ c }}]{% endfor %}", s="hi"), "[h][i]")
        self.assertEqual(render("{% for k in d %}{{ k }}{% endfor %}", d={"a": 1, "b": 2}), "ab")
        self.assertEqual(render("{% for x in xs|first %}{{ x }}{% endfor %}", xs=[[1, 2], [3]]), "12")
        with self.assertRaises(TemplateRenderError):
            render("{% for x in n %}{% endfor %}", n=5)

    def test_for_over_literal_and_expression(self):
        self.assertEqual(render("{% for x in 'ab' %}{{ x }}{% endfor %}"), "ab")
        self.assertEqual(render("{% for x in a.b %}{{ x }}{% endfor %}", a={"b": [1, 2]}), "12")

    def test_loop_over_loop_data_modified_not_shared(self):
        t = Template("{% for x in xs %}{{ loop.length }}{% endfor %}")
        self.assertEqual(t.render(xs=[1, 2, 3]), "333")
        self.assertEqual(t.render(xs=[1]), "1")

    def test_context_not_mutated(self):
        ctx = {"xs": [1, 2]}
        Template("{% for x in xs %}{% endfor %}").render(**ctx)
        self.assertEqual(ctx, {"xs": [1, 2]})


class SyntaxErrors(unittest.TestCase):
    def test_unknown_tag(self):
        self.assertEqual(syntax_line("a\n{% while x %}"), 2)
        self.assertEqual(syntax_line("{% %}"), 1)

    def test_mismatched_ends(self):
        self.assertEqual(syntax_line("{% if x %}\n{% endfor %}"), 2)
        self.assertEqual(syntax_line("{% for x in y %}\n\n{% endif %}"), 3)
        self.assertEqual(syntax_line("{% endif %}"), 1)
        self.assertEqual(syntax_line("x\n{% endfor %}"), 2)

    def test_else_and_elif_misuse(self):
        self.assertEqual(syntax_line("{% if a %}\n{% else %}\n{% else %}{% endif %}"), 3)
        self.assertEqual(syntax_line("{% if a %}\n{% else %}\n\n{% elif b %}{% endif %}"), 4)
        self.assertEqual(syntax_line("{% for x in y %}\n{% elif b %}{% endfor %}"), 2)
        self.assertEqual(syntax_line("{% for x in y %}{% else %}\n{% else %}{% endfor %}"), 2)
        self.assertEqual(syntax_line("\n{% elif b %}"), 2)
        self.assertEqual(syntax_line("{% else %}"), 1)

    def test_unclosed_block_line(self):
        self.assertEqual(syntax_line("{% if x %}\nbody"), 1)
        self.assertEqual(syntax_line("a\n{% for x in y %}\n{% if x %}\n{% endif %}"), 2)
        self.assertEqual(syntax_line("{% for x in y %}\n{% if x %}\n{% else %}\n"), 2)

    def test_malformed_for(self):
        for src in ("{% for %}{% endfor %}", "{% for x %}{% endfor %}", "{% for x in %}{% endfor %}",
                    "{% for 1 in y %}{% endfor %}", "{% for x, in y %}{% endfor %}",
                    "{% for x y in z %}{% endfor %}"):
            with self.assertRaises(TemplateSyntaxError, msg=src):
                Template(src)

    def test_bad_condition_line(self):
        self.assertEqual(syntax_line("a\n{% if x %}\n{% elif %}{% endif %}"), 3)
        self.assertEqual(syntax_line("{% if x < %}{% endif %}"), 1)


class Legacy(unittest.TestCase):
    def test_existing_behaviour(self):
        self.assertEqual(render("Hello {{ user.name|title }}!{% if admin %} (admin){% endif %}",
                                user={"name": "ada"}, admin=True), "Hello Ada! (admin)")
        self.assertEqual(render("{% for x in xs %}<{{ x }}>{% endfor %}", xs=[1, 2]), "<1><2>")
        self.assertEqual(render("{{ xs|join }} {{ xs|length }}", xs=[1, 2, 3]), "1, 2, 3 3")
        self.assertEqual(render("[{{ missing }}][{{ none }}]", none=None), "[][]")
        self.assertEqual(render("{{ xs.1 }}{{ xs.9 }}", xs=["a", "b"]), "b")


if __name__ == "__main__":
    unittest.main()
