"""Configuration container with dotted-path access."""
from .errors import ConfigError

MISSING = object()


class Config:
    def __init__(self, data=None):
        self._data = {} if data is None else data

    def get(self, path, default=MISSING):
        """Look up a dotted path such as "server.port"; KeyError if missing and no default."""
        cur = self._data
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif default is MISSING:
                raise KeyError(path)
            else:
                return default
        return cur

    def __contains__(self, path):
        try:
            self.get(path)
        except KeyError:
            return False
        return True

    def section(self, path):
        value = self.get(path)
        if not isinstance(value, dict):
            raise ConfigError("%s is not a section" % path)
        return Config(value)

    def merge(self, other):
        """New Config: `other` wins; nested dicts are merged recursively, everything else replaced."""
        return Config(_merge(self._data, other._data))

    def as_dict(self):
        return self._data


def _merge(a, b):
    out = dict(a)
    for key, value in b.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out
