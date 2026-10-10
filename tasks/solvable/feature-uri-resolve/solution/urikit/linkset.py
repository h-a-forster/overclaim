"""Turn the href attributes found on a page into the set of pages to visit."""
from .errors import UriError
from .normalize import normalize
from .resolve import resolve
from .uri import parse

_WS = " \t\n\r\f"


def collect_links(base, hrefs):
    """Absolute, normalised, fragment-free, de-duplicated http(s) links in first-seen order."""
    if parse(base).scheme is None:
        raise UriError("base URI must have a scheme")
    seen = set()
    out = []
    for href in hrefs:
        try:
            link = resolve(base, href.strip(_WS))
            u = parse(link)
            link = normalize(str(u._replace(fragment=None)))
        except UriError:
            continue
        if parse(link).scheme not in ("http", "https"):
            continue
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out
