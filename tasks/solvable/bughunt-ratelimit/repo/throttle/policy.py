"""Rate-limit policy: which rule applies to which route."""

from .errors import PolicyError

ALGORITHMS = ("token_bucket", "sliding_window", "fixed_window", "leaky_bucket")


class Rule:
    """One limiting rule.

    ``pattern`` is an exact route (``"/login"``) or a prefix pattern ending in ``/*``
    (``"/api/*"``).  Routes matched by the same rule share the same budget (per client).
    """

    def __init__(self, pattern, algo, **params):
        if algo not in ALGORITHMS:
            raise PolicyError("unknown algorithm %r" % (algo,))
        self.pattern = pattern
        self.algo = algo
        self.params = params
        if algo in ("token_bucket", "leaky_bucket"):
            self._need("capacity", "rate")
        else:
            self._need("limit", "window")

    def _need(self, *names):
        for name in names:
            value = self.params.get(name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise PolicyError("rule %r needs a positive %s" % (self.pattern, name))

    @property
    def key(self):
        return self.pattern

    @property
    def limit(self):
        return self.params["capacity"] if "capacity" in self.params else self.params["limit"]

    def matches(self, route):
        if self.pattern.endswith("/*"):
            return route.startswith(self.pattern[:-1])
        return route == self.pattern

    def specificity(self):
        """Longer prefixes win; an exact route beats any prefix of the same text."""
        if self.pattern.endswith("/*"):
            return (0, len(self.pattern))
        return (1, len(self.pattern))

    def __repr__(self):
        return "Rule(%r, %r)" % (self.pattern, self.algo)


DEFAULT_KEY = "<default>"


class Policy:
    def __init__(self, rules, default):
        patterns = [r.pattern for r in rules]
        if len(set(patterns)) != len(patterns):
            raise PolicyError("duplicate rule patterns")
        self.rules = list(rules)
        self.default = default

    @classmethod
    def from_config(cls, config):
        """Build from ``{"default": {...}, "rules": {"/login": {...}, ...}}``.

        Each rule dict has an ``"algo"`` key plus the parameters of that algorithm.
        """
        if "default" not in config:
            raise PolicyError("a policy needs a default rule")
        default = cls._make(DEFAULT_KEY, config["default"])
        rules = [cls._make(pattern, spec) for pattern, spec in config.get("rules", {}).items()]
        return cls(rules, default)

    @staticmethod
    def _make(pattern, spec):
        spec = dict(spec)
        algo = spec.pop("algo", "token_bucket")
        return Rule(pattern, algo, **spec)

    def match(self, route):
        """The most specific rule for ``route`` (or the default rule)."""
        found = [r for r in self.rules if r.matches(route)]
        if not found:
            return self.default
        return max(found, key=lambda r: r.specificity())
