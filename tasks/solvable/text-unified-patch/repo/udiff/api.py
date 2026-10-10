"""Apply a patch to a ``{path: text}`` mapping."""

from __future__ import annotations

from .errors import PatchError
from .matcher import apply_hunks
from .models import DEV_NULL
from .parser import parse_patch


def _strip(path: str, strip: int) -> str:
    if path == DEV_NULL:
        return path
    parts = path.split("/")
    return "/".join(parts[strip:]) if len(parts) > strip else parts[-1]


def _split(text: str) -> list[str]:
    lines = text.split("\n")
    out = [line + "\n" for line in lines[:-1]]
    if lines[-1]:
        out.append(lines[-1])
    return out


def apply_patch(files: dict[str, str], patch_text: str, strip: int = 1) -> dict[str, str]:
    """Return a new ``{path: text}`` mapping with the patch applied; ``files`` is untouched."""
    result = dict(files)
    for fp in parse_patch(patch_text):
        old, new = _strip(fp.old_path, strip), _strip(fp.new_path, strip)
        target = old if new == DEV_NULL else new
        if old == DEV_NULL:
            if new in result:
                raise PatchError("file already exists", file=new)
            source: list[str] = []
        else:
            if old not in result:
                raise PatchError("file does not exist", file=old)
            source = _split(result[old])
        lines = apply_hunks(source, fp.hunks, file=target)
        if new == DEV_NULL:
            if lines:
                raise PatchError("file is not empty after deletion", file=old)
            del result[old]
        else:
            if old not in (DEV_NULL, new):
                del result[old]
            result[new] = "".join(lines)
    return result
