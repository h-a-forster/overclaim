"""Reference resolution (RFC 3986 section 5.2)."""
from .errors import UriError
from .uri import Uri, parse


def remove_dot_segments(path):
    """RFC 3986 section 5.2.4, the input-buffer / output-buffer algorithm."""
    inp = path
    out = []
    while inp:
        if inp.startswith("../"):
            inp = inp[3:]
        elif inp.startswith("./"):
            inp = inp[2:]
        elif inp.startswith("/./"):
            inp = inp[2:]
        elif inp == "/.":
            inp = "/"
        elif inp.startswith("/../"):
            inp = inp[3:]
            if out:
                out.pop()
        elif inp == "/..":
            inp = "/"
            if out:
                out.pop()
        elif inp in (".", ".."):
            inp = ""
        else:
            j = inp.find("/", 1)
            if j < 0:
                j = len(inp)
            out.append(inp[:j])
            inp = inp[j:]
    return "".join(out)


def _merge(base, ref_path):
    if base.authority is not None and base.path == "":
        return "/" + ref_path
    head, sep, _ = base.path.rpartition("/")
    return head + sep + ref_path


def resolve(base, ref):
    b = parse(str(base))
    r = parse(str(ref))
    if b.scheme is None:
        raise UriError("base URI must have a scheme")
    if r.scheme is not None:
        t = Uri(r.scheme, r.authority, remove_dot_segments(r.path), r.query, r.fragment)
    elif r.authority is not None:
        t = Uri(b.scheme, r.authority, remove_dot_segments(r.path), r.query, r.fragment)
    elif r.path == "":
        t = Uri(b.scheme, b.authority, b.path, r.query if r.query is not None else b.query, r.fragment)
    else:
        if r.path.startswith("/"):
            path = remove_dot_segments(r.path)
        else:
            path = remove_dot_segments(_merge(b, r.path))
        t = Uri(b.scheme, b.authority, path, r.query, r.fragment)
    return str(t)


def join(base, ref):
    return resolve(base, ref)
