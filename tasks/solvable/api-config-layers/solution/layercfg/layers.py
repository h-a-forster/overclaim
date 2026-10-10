"""Layers of configuration data and how they are merged."""

from dataclasses import dataclass, field


@dataclass
class Layer:
    name: str
    data: dict = field(default_factory=dict)
    coerce: bool = False  # True: string values are converted using the schema's field types


def flatten(schema, layer):
    """Validate one layer against the schema; return ({path: value}, [(path, message)])."""
    values, errors = {}, []

    def walk(data, prefix):
        for key, value in data.items():
            path = prefix + key
            if schema.is_field(path):
                try:
                    values[path] = schema.field(path).convert(value, layer.coerce)
                except ValueError as exc:
                    errors.append((path, str(exc)))
            elif schema.is_section(path):
                if isinstance(value, dict):
                    walk(value, path + ".")
                else:
                    errors.append((path, "expected a section"))
            elif layer.coerce:
                continue  # noisy sources (environment, CLI): ignore unknown keys
            else:
                errors.append((path, "unknown key"))

    walk(layer.data, "")
    return values, errors
