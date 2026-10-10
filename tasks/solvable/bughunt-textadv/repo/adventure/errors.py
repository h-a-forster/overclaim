"""Exceptions raised by adventure."""


class AdventureError(Exception):
    """Base class."""


class WorldError(AdventureError):
    """The world definition is inconsistent (unknown room / item reference, ...)."""


class ParseError(AdventureError):
    """The player's input cannot be turned into a command."""


class SaveError(AdventureError):
    """A saved game does not fit the world it is loaded into."""
