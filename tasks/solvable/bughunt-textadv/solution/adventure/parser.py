"""Turning a line of player input into a Command."""

from .directions import normalize
from .errors import ParseError

ARTICLES = {"a", "an", "the", "some"}
PREPOSITIONS = {"in": "in", "into": "in", "inside": "in", "on": "on", "from": "from", "with": "with", "to": "to"}

VERBS = {
    "look": "look", "l": "look", "inventory": "inventory", "i": "inventory", "inv": "inventory",
    "go": "go", "walk": "go", "move": "go", "run": "go",
    "take": "take", "get": "take", "grab": "take", "pick": "take",
    "drop": "drop", "discard": "drop",
    "put": "put", "place": "put", "insert": "put", "store": "put",
    "examine": "examine", "x": "examine", "inspect": "examine", "read": "examine",
    "open": "open", "close": "close", "shut": "close",
    "unlock": "unlock", "light": "light", "extinguish": "extinguish", "douse": "extinguish",
    "score": "score",
}


class Command:
    def __init__(self, verb, noun=None, prep=None, target=None):
        self.verb = verb
        self.noun = noun
        self.prep = prep
        self.target = target

    def __eq__(self, other):
        return isinstance(other, Command) and vars(self) == vars(other)

    def __repr__(self):
        return "Command(%r, %r, %r, %r)" % (self.verb, self.noun, self.prep, self.target)


def strip_articles(phrase):
    """Remove the words a / an / the / some from a noun phrase (whole words only)."""
    return " ".join(w for w in phrase.split() if w not in ARTICLES)


def _clean(text):
    cleaned = "".join(ch if ch.isalnum() or ch in " -'" else " " for ch in text.lower())
    return cleaned.split()


def parse(text):
    """Parse ``take the brass key``, ``put cup in chest``, ``n``, ``unlock north with key`` ...

    A bare direction word (``north``, ``n``) means ``go <direction>``.  ``pick up X`` is ``take X``.
    The words after the verb are split at the first preposition into a noun phrase and a target
    phrase; articles are removed from both.
    """
    words = _clean(text)
    if not words:
        raise ParseError("Say something.")
    direction = normalize(words[0]) if len(words) == 1 else None
    if direction:
        return Command("go", direction)
    verb = VERBS.get(words[0])
    if verb is None:
        raise ParseError("I don't know how to '%s'." % words[0])
    rest = words[1:]
    if words[0] == "pick" and rest[:1] == ["up"]:
        rest = rest[1:]
    prep = None
    noun_words, target_words = rest, []
    for index, word in enumerate(rest):
        if word in PREPOSITIONS and index > 0:
            prep = PREPOSITIONS[word]
            noun_words, target_words = rest[:index], rest[index + 1:]
            break
    noun = strip_articles(" ".join(noun_words)) or None
    target = strip_articles(" ".join(target_words)) or None
    if verb == "go" and noun:
        direction = normalize(noun)
        if direction is None:
            raise ParseError("'%s' is not a direction." % noun)
        noun = direction
    return Command(verb, noun, prep, target)
