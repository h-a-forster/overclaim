# tplr

A tiny template engine for generated emails and reports.

```python
from tplr import render

render("Hello {{ user.name|title }}!{% if admin %} (admin){% endif %}", user={"name": "ada"}, admin=True)
# 'Hello Ada! (admin)'
```

Supported today: `{{ path|filter }}`, `{% if %}...{% else %}...{% endif %}`,
`{% for x in items %}...{% endfor %}`, `{# comments #}`.

Run the tests with `python -m unittest discover -s tests -t .`.
