from .errors import UriError
from .linkset import collect_links
from .normalize import equivalent, normalize
from .join import join
from .resolve import remove_dot_segments, resolve
from .uri import Uri, parse

__all__ = ["Uri", "UriError", "collect_links", "equivalent", "join", "normalize", "parse",
           "remove_dot_segments", "resolve"]
