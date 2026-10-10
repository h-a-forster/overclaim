"""URI reference splitting and recomposition (RFC 3986 section 3, appendix B and section 5.3)."""
import re
from collections import namedtuple

# RFC 3986 appendix B. Components that are absent are None; present-but-empty are "".
_SPLIT = re.compile(r"^(?:([^:/?#]+):)?(?://([^/?#]*))?([^?#]*)(?:\?([^#]*))?(?:#(.*))?$", re.S)


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


def parse(text):
    """Split `text` into a Uri. No validation is done: any string splits somehow."""
    return Uri(*_SPLIT.match(text).groups())
