"""URI reference parsing with validation (RFC 3986) and recomposition (section 5.3)."""
import re
from collections import namedtuple

from .errors import UriError

_SPLIT = re.compile(r"^(?:([^:/?#]+):)?(?://([^/?#]*))?([^?#]*)(?:\?([^#]*))?(?:#(.*))?$", re.S)
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*$")
_DIGITS = "0123456789"
_ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
UNRESERVED = _ALPHA + _DIGITS + "-._~"
SUB_DELIMS = "!$&'()*+,;="
_HEX = "0123456789abcdefABCDEF"
_USERINFO = set(UNRESERVED + SUB_DELIMS + ":")
_REG_NAME = set(UNRESERVED + SUB_DELIMS)
_PCHAR = set(UNRESERVED + SUB_DELIMS + ":@")
_PATH = _PCHAR | {"/"}
_QUERY = _PCHAR | {"/", "?"}
_IPV6 = re.compile(r"^[0-9A-Fa-f:.]+$")
_IPVFUTURE = re.compile(r"^[vV][0-9A-Fa-f]+\.[A-Za-z0-9\-._~!$&'()*+,;=:]+$")


def _check(text, allowed, what):
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "%":
            if i + 2 >= n or text[i + 1] not in _HEX or text[i + 2] not in _HEX:
                raise UriError("bad percent-encoding in %s: %r" % (what, text))
            i += 3
            continue
        if c not in allowed:
            raise UriError("illegal character %r in %s" % (c, what))
        i += 1


class Uri(namedtuple("Uri", "scheme authority path query fragment")):
    __slots__ = ()

    def __str__(self):
        out = []
        if self.scheme is not None:
            out.append(self.scheme + ":")
        if self.authority is not None:
            out.append("//" + self.authority)
        out.append(self.path)
        if self.query is not None:
            out.append("?" + self.query)
        if self.fragment is not None:
            out.append("#" + self.fragment)
        return "".join(out)

    @property
    def is_absolute(self):
        return self.scheme is not None

    def _authority_parts(self):
        a = self.authority
        if a is None:
            return None, None, None
        userinfo = None
        hostport = a
        if "@" in a:
            userinfo, hostport = a.rsplit("@", 1)
        if hostport.startswith("["):
            j = hostport.find("]")
            host = hostport[:j + 1]
            rest = hostport[j + 1:]
            port = rest[1:] if rest.startswith(":") else None
        else:
            host, sep, port = hostport.partition(":")
            if not sep:
                port = None
        return userinfo, host, port

    @property
    def userinfo(self):
        return self._authority_parts()[0]

    @property
    def host(self):
        return self._authority_parts()[1]

    @property
    def port(self):
        p = self._authority_parts()[2]
        return int(p) if p else None


def _validate_authority(a):
    userinfo = None
    hostport = a
    if "@" in a:
        userinfo, hostport = a.rsplit("@", 1)
        _check(userinfo, _USERINFO, "userinfo")
    port = None
    if hostport.startswith("["):
        j = hostport.find("]")
        if j < 0:
            raise UriError("unterminated IP literal")
        inner = hostport[1:j]
        if not (
            (_IPV6.fullmatch(inner) and inner.count(":") >= 2) or _IPVFUTURE.fullmatch(inner)
        ):
            raise UriError("bad IP literal %r" % inner)
        rest = hostport[j + 1:]
        if rest:
            if not rest.startswith(":"):
                raise UriError("junk after IP literal")
            port = rest[1:]
    else:
        host, sep, port = hostport.partition(":")
        _check(host, _REG_NAME, "host")
        if not sep:
            port = None
    if port is not None and any(c not in _DIGITS for c in port):
        raise UriError("bad port %r" % port)


def parse(text):
    """Split `text` into a Uri, raising UriError if it is not a valid URI reference."""
    if not isinstance(text, str):
        raise UriError("not a string")
    m = _SPLIT.match(text)
    uri = Uri(*m.groups())
    if text.find(":") >= 0 and uri.scheme is None and uri.authority is None:
        first = uri.path.split("/", 1)[0]
        if ":" in first:
            raise UriError("colon in first path segment of a relative reference")
    if uri.scheme is not None and not _SCHEME.fullmatch(uri.scheme):
        raise UriError("bad scheme %r" % uri.scheme)
    if uri.authority is not None:
        _validate_authority(uri.authority)
    _check(uri.path, _PATH, "path")
    if uri.query is not None:
        _check(uri.query, _QUERY, "query")
    if uri.fragment is not None:
        _check(uri.fragment, _QUERY, "fragment")
    return uri
