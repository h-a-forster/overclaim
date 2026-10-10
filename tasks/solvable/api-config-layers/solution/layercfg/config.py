"""Loading and querying configuration."""

from .layers import flatten


class ConfigError(Exception):
    def __init__(self, errors):
        self.errors = sorted(errors, key=lambda e: e[0])
        super().__init__("; ".join(f"{path}: {msg}" for path, msg in self.errors))


class Config:
    def __init__(self, schema, values, history):
        self._schema = schema
        self._values = values
        self._history = history

    def _check(self, path):
        if not self._schema.is_field(path):
            raise KeyError(path)

    def get(self, path):
        self._check(path)
        return self._values[path]

    __getitem__ = get

    def source(self, path):
        """Name of the layer that supplied the winning value, or None."""
        self._check(path)
        hist = self._history[path]
        return hist[-1][0] if hist else None

    def explain(self, path):
        """``[(layer_name, value), ...]`` from lowest to highest precedence."""
        self._check(path)
        return [(n, list(v) if isinstance(v, list) else v) for n, v in self._history[path]]

    def as_dict(self):
        out = {}
        for path in self._schema.paths():
            node = out
            *parents, leaf = path.split(".")
            for part in parents:
                node = node.setdefault(part, {})
            v = self._values[path]
            node[leaf] = list(v) if isinstance(v, list) else v
        return out


def load(schema, layers):
    values, history, errors = {}, {}, []
    for path in schema.paths():
        f = schema.field(path)
        values[path] = f.initial()
        history[path] = [("defaults", f.initial())] if f.default is not None else []
    for layer in layers:
        found, errs = flatten(schema, layer)
        errors.extend((p, f"{m} (layer {layer.name})") for p, m in errs)
        for path, value in found.items():
            values[path] = value
            history[path].append((layer.name, value))
    for path in schema.paths():
        if schema.field(path).required and not history[path]:
            errors.append((path, "required"))
    if errors:
        raise ConfigError(errors)
    return Config(schema, values, history)
