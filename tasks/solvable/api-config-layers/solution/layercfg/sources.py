"""Layers built from the environment and from command-line overrides."""

from .layers import Layer


def _put(tree, segments, value):
    """Set a nested value; on a scalar/section clash the more specific (deeper) key wins."""
    node = tree
    for seg in segments[:-1]:
        child = node.get(seg)
        if not isinstance(child, dict):
            child = node[seg] = {}
        node = child
    if not isinstance(node.get(segments[-1]), dict):
        node[segments[-1]] = value


def env_layer(environ, prefix, name="env"):
    """``PREFIX_DB__HOST=x`` becomes ``{"db": {"host": "x"}}`` (keys lower-cased)."""
    tree = {}
    lead = prefix + "_"
    for key in sorted(environ):
        if not key.startswith(lead):
            continue
        segments = key[len(lead):].lower().split("__")
        if any(not s for s in segments):
            continue
        _put(tree, segments, environ[key])
    return Layer(name, tree, coerce=True)


def args_layer(items, name="args"):
    """``["db.port=1", "debug=true"]`` becomes a nested layer; later items win."""
    tree = {}
    for item in items:
        key, eq, value = item.partition("=")
        segments = key.split(".")
        if not eq or any(not s for s in segments):
            raise ValueError(f"expected key=value, got {item!r}")
        _put(tree, segments, value)
    return Layer(name, tree, coerce=True)
