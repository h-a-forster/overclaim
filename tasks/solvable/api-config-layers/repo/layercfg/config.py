"""Loading and querying configuration."""

from .layers import flatten


class ConfigError(Exception):
    pass


class Config:
    def __init__(self, schema, values, sources):
        self._schema = schema
        self._values = values
        self._sources = sources

    def get(self, path):
        if not self._schema.is_field(path):
            raise KeyError(path)
        return self._values[path]

    __getitem__ = get

    def source(self, path):
        """Name of the layer that supplied the value ("defaults" for schema defaults)."""
        if not self._schema.is_field(path):
            raise KeyError(path)
        return self._sources.get(path)

    def as_dict(self):
        out = {}
        for path in self._schema.paths():
            node = out
            *parents, leaf = path.split(".")
            for part in parents:
                node = node.setdefault(part, {})
            node[leaf] = self._values[path]
        return out


def load(schema, layers):
    values, sources = {}, {}
    for path in schema.paths():
        f = schema.field(path)
        values[path] = f.default
        if f.default is not None:
            sources[path] = "defaults"
    for layer in layers:
        found, errors = flatten(schema, layer)
        if errors:
            path, message = errors[0]
            raise ConfigError(f"{path}: {message} (layer {layer.name})")
        for path, value in found.items():
            values[path] = value
            sources[path] = layer.name
    for path in schema.paths():
        if schema.field(path).required and path not in sources:
            raise ConfigError(f"{path}: required")
    return Config(schema, values, sources)
