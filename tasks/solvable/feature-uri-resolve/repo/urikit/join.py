"""Resolving a reference against a base (simplified: no dot-segment handling)."""
from .uri import Uri, parse


def join(base, ref):
    r = parse(ref)
    if r.scheme is not None:
        return ref
    b = parse(base)
    if r.authority is not None:
        return str(Uri(b.scheme, r.authority, r.path, r.query, r.fragment))
    if r.path.startswith("/"):
        return str(Uri(b.scheme, b.authority, r.path, r.query, r.fragment))
    if r.path == "":
        return str(Uri(b.scheme, b.authority, b.path, r.query if r.query is not None else b.query, r.fragment))
    directory = b.path.rsplit("/", 1)[0] + "/" if "/" in b.path else "/"
    return str(Uri(b.scheme, b.authority, directory + r.path, r.query, r.fragment))
