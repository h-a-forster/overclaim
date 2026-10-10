import unittest

from adventure import Command, Game, ParseError, SaveError, WorldDef, WorldError, parse
from adventure import save

SPEC = {
    "start": "hall",
    "capacity": 6,
    "rooms": {
        "hall": {"name": "Great Hall", "desc": "A big hall.", "exits": {"north": "library", "east": "garden"},
                 "items": ["lamp", "key"]},
        "library": {"name": "Library", "desc": "Books.", "exits": {"east": "vault", "up": "attic"}, "items": ["book"],
                    "locked_exits": {"east": "key"}},
        "vault": {"name": "Vault", "desc": "Shiny.", "items": ["diamond"]},
        "garden": {"name": "Garden", "desc": "Green.", "items": ["bench", "chest"], "dark": True},
        "attic": {"name": "Attic", "desc": "Dusty.", "items": ["gem"]},
    },
    "items": {
        "lamp": {"name": "brass lamp", "aliases": ["lamp"], "weight": 2, "light": True},
        "key": {"name": "key", "weight": 1},
        "book": {"weight": 2},
        "bench": {"takeable": False},
        "chest": {"container": True, "capacity": 3, "locked": True, "key": "key", "takeable": False},
        "diamond": {"treasure": 50, "weight": 1},
        "gem": {"treasure": 5},
    },
    "events": [{"id": "bell", "turn": 30, "text": "A bell rings."}],
}


def new_game():
    return Game(WorldDef.from_dict(SPEC))


class ParserTests(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(parse("take the lamp"), Command("take", "lamp"))
        self.assertEqual(parse("pick up the brass key"), Command("take", "brass key"))
        self.assertEqual(parse("n"), Command("go", "north"))
        self.assertEqual(parse("go up"), Command("go", "up"))
        self.assertEqual(parse("put book in chest"), Command("put", "book", "in", "chest"))
        self.assertEqual(parse("unlock east with the key"), Command("unlock", "east", "with", "key"))

    def test_errors(self):
        for bad in ("", "xyzzy now", "go sideways"):
            with self.assertRaises(ParseError):
                parse(bad)


class GameTests(unittest.TestCase):
    def test_look_and_move(self):
        g = new_game()
        self.assertEqual(g.execute("look"), "Great Hall\nA big hall.\nYou see a brass lamp and a key.\nExits: north, east.")
        self.assertEqual(g.execute("n").split("\n")[0], "Library")
        self.assertEqual(g.execute("s").split("\n")[0], "Great Hall")
        self.assertEqual(g.execute("w"), "You can't go that way.")

    def test_take_drop_inventory(self):
        g = new_game()
        self.assertEqual(g.execute("take the lamp"), "Taken.")
        self.assertEqual(g.execute("take lamp"), "You already have that.")
        self.assertEqual(g.execute("inventory"), "You are carrying a brass lamp. (2/6)")
        self.assertEqual(g.execute("drop lamp"), "Dropped.")
        self.assertEqual(g.execute("inventory"), "You are carrying nothing.")

    def test_locked_door_and_chest(self):
        g = new_game()
        g.run(["take key", "n"])
        self.assertEqual(g.execute("e"), "The way east is locked.")
        self.assertEqual(g.execute("unlock east with key"), "Unlocked.")
        self.assertEqual(g.execute("e").split("\n")[0], "Vault")
        self.assertEqual(g.execute("w").split("\n")[0], "Library")

    def test_dark_room_with_carried_lamp(self):
        g = new_game()
        g.run(["take lamp", "e"])
        self.assertTrue(g.execute("look").startswith("It is pitch dark"))
        self.assertEqual(g.execute("light lamp"), "The brass lamp is now lit.")
        self.assertIn("You see a bench and a chest.", g.execute("look"))

    def test_score_and_events(self):
        spec = dict(SPEC, events=[{"id": "bell", "turn": 3, "text": "A bell rings."}])
        g = Game(WorldDef.from_dict(spec))
        g.run(["n", "u"])
        self.assertEqual(g.execute("take gem"), "Taken. (+5 points)\nA bell rings.")
        self.assertEqual(g.execute("score"), "Score: 5 in 3 turns.")

    def test_save_restore(self):
        g = new_game()
        g.run(["n", "u", "take gem", "d"])
        again = Game.restore(g.world, g.save())
        self.assertEqual(again.state.score, 5)
        self.assertEqual(again.state.room, "library")
        self.assertEqual(again.execute("inventory"), "You are carrying a gem. (1/6)")
        with self.assertRaises(SaveError):
            Game.restore(g.world, "not json")

    def test_world_errors(self):
        for spec in ({"rooms": {}}, {"start": "x", "rooms": {}},
                     {"start": "a", "rooms": {"a": {"exits": {"north": "zzz"}}}},
                     {"start": "a", "rooms": {"a": {"items": ["nope"]}}}):
            with self.assertRaises(WorldError):
                WorldDef.from_dict(spec)


if __name__ == "__main__":
    unittest.main()
