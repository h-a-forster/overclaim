"""tinycsv: a small, dependency-free CSV reader."""

from .reader import CSVError, parse
from .records import parse_records

__all__ = ["CSVError", "parse", "parse_records"]
