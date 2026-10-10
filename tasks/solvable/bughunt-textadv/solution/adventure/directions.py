"""Compass directions."""

DIRECTIONS = ("north", "south", "east", "west", "up", "down")

ALIASES = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down"}

OPPOSITE = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "down",
    "down": "up",
}


def normalize(word):
    """Canonical direction for a word (``"n"`` -> ``"north"``) or ``None``."""
    word = word.strip().lower()
    word = ALIASES.get(word, word)
    return word if word in DIRECTIONS else None
