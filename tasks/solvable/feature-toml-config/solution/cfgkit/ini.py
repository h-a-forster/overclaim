"""A small INI parser: `[section]` headers, `key = value`, `#`/`;` comment lines."""
from .errors import ParseError


def parse_ini(text):
    """Return {section: {key: str}}; keys before the first section go to the top level."""
    data = {}
    current = data
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("["):
            if not line.endswith("]") or len(line) < 3:
                raise ParseError("bad section header", n)
            name = line[1:-1].strip()
            if name in data and not isinstance(data[name], dict):
                raise ParseError("section clashes with a key", n)
            current = data.setdefault(name, {})
            continue
        key, sep, value = line.partition("=")
        if not sep or not key.strip():
            raise ParseError("expected key = value", n)
        current[key.strip()] = value.strip()
    return data
