"""Syntax-based and scheme-based normalisation (RFC 3986 sections 6.2.2 and 6.2.3)."""
import re

from .errors import UriError
from .resolve import remove_dot_segments
from .uri import UNRESERVED, Uri, parse

_PCT = re.compile(r"%([0-9A-Fa-f]{2})")
DEFAULT_PORTS = {"http": 80, "https": 443, "ftp": 21, "ws": 80, "wss": 443}
_EMPTY_PATH_ROOT = {"http", "https", "ftp", "ws", "wss"}


def _pct(text):
    def repl(m):
        ch = chr(int(m.group(1), 16))
        return ch if ch in UNRESERVED else "%" + m.group(1).upper()

    return _PCT.sub(repl, text)


def normalize(text):
    u = parse(text)
    if u.scheme is None:
        raise UriError("normalize needs an absolute URI")
    scheme = u.scheme.lower()
    authority = u.authority
    if authority is not None:
        userinfo, host, port = u._authority_parts()
        out = ""
        if userinfo is not None:
            out += _pct(userinfo) + "@"
        out += _pct(host).lower()
        if port:
            if DEFAULT_PORTS.get(scheme) != int(port):
                out += ":" + port
        authority = out
    path = remove_dot_segments(_pct(u.path))
    if path == "" and authority is not None and scheme in _EMPTY_PATH_ROOT:
        path = "/"
    query = None if u.query is None else _pct(u.query)
    fragment = None if u.fragment is None else _pct(u.fragment)
    return str(Uri(scheme, authority, path, query, fragment))


def equivalent(a, b):
    return normalize(a) == normalize(b)
