"""Turn the href attributes found on a page into the set of pages to visit."""
from .join import join
from .uri import parse


def collect_links(base, hrefs):
    """Absolute, fragment-free, de-duplicated links in first-seen order."""
    seen = set()
    out = []
    for href in hrefs:
        link = join(base, href)
        link = link.split("#", 1)[0]
        if parse(link).scheme not in ("http", "https"):
            continue
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out
