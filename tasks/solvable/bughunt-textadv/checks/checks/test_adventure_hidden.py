import json
import unittest

from adventure import Command, Game, ParseError, SaveError, WorldDef, WorldError, parse
from adventure import hints, save
from adventure.directions import ALIASES, DIRECTIONS, OPPOSITE, normalize
from adventure.parser import strip_articles
from adventure.render import describe_items, join_list, with_article

SPEC = {
    "start": "hall",
    "capacity": 10,
    "rooms": {
        "hall": {"name": "Great Hall", "desc": "A big hall.", "exits": {"north": "library", "east": "garden", "down": "cellar"},
                 "items": ["lamp", "tea cup", "pizza box"]},
        "library": {"name": "Library", "desc": "Books.", "exits": {"east": "vault", "up": "attic"}, "items": ["book", "key"],
                    "locked_exits": {"east": "key"}},
        "vault": {"name": "Vault", "desc": "Shiny.", "items": ["diamond"]},
        "garden": {"name": "Garden", "desc": "Green.", "items": ["bench", "rose"]},
        "cellar": {"name": "Cellar", "desc": "Damp.", "dark": True, "items": ["gold coin", "chest"]},
        "attic": {"name": "Attic", "desc": "Dusty.", "items": ["anvil"]},
    },
    "items": {
        "lamp": {"name": "brass lamp", "aliases": ["lamp", "lantern"], "weight": 3, "light": True},
        "tea cup": {"name": "tea cup", "aliases": ["cup"], "weight": 1},
        "pizza box": {"name": "pizza box", "weight": 1, "container": True, "capacity": 2},
        "book": {"weight": 2},
        "key": {"name": "brass key", "aliases": ["key"], "weight": 1},
        "bench": {"takeable": False},
        "rose": {},
        "gold coin": {"name": "gold coin", "aliases": ["coin"], "treasure": 10},
        "chest": {"container": True, "capacity": 5, "locked": True, "key": "key", "takeable": False},
        "anvil": {"weight": 9},
        "diamond": {"treasure": 50, "weight": 2},
    },
    "events": [{"id": "bell", "turn": 40, "text": "A bell rings."}, {"id": "skitter", "enter": "cellar", "text": "Something skitters."}],
}


def world():
    return WorldDef.from_dict(SPEC)


def game():
    return Game(world())


def bell_game():
    spec = dict(SPEC, events=[{"id": "bell", "turn": 3, "text": "A bell rings."}, {"id": "skitter", "enter": "cellar", "text": "Something skitters."}])
    return Game(WorldDef.from_dict(spec))


class ArticleSymptoms(unittest.TestCase):
    def test_strip_articles(self):
        cases = {"the tea cup": "tea cup", "a lamp": "lamp", "an anvil": "anvil", "some bread": "bread", "tea cup": "tea cup",
                 "pizza box": "pizza box", "a  tea cup": "tea cup", "the": "", "a pizza box": "pizza box",
                 "sea salad": "sea salad", "the sea salad": "sea salad", "banana": "banana", "extra data": "extra data"}
        for text, expected in cases.items():
            self.assertEqual(strip_articles(text), expected, text)

    def test_parse_multiword_nouns(self):
        self.assertEqual(parse("take tea cup"), Command("take", "tea cup"))
        self.assertEqual(parse("take the tea cup"), Command("take", "tea cup"))
        self.assertEqual(parse("take a pizza box"), Command("take", "pizza box"))
        self.assertEqual(parse("put the tea cup in the pizza box"), Command("put", "tea cup", "in", "pizza box"))
        self.assertEqual(parse("examine a sea salad"), Command("examine", "sea salad"))
        self.assertEqual(parse("drop pizza box"), Command("drop", "pizza box"))

    def test_gameplay_with_multiword_items(self):
        g = game()
        self.assertEqual(g.execute("take the tea cup"), "Taken.")
        self.assertEqual(g.execute("take pizza box"), "Taken.")
        self.assertEqual(g.execute("open pizza box"), "Opened.")
        self.assertEqual(g.execute("put tea cup in the pizza box"), "Done.")
        self.assertEqual(g.execute("examine the pizza box"), "It looks ordinary. It contains a tea cup.")
        self.assertEqual(g.execute("drop a pizza box"), "Dropped.")
        self.assertIn("The pizza box contains a tea cup.", g.execute("look"))

    def test_unknown_noun_reports_what_was_typed(self):
        g = game()
        self.assertEqual(g.execute("take a banana split"), "You see no banana split here.")
        self.assertEqual(g.execute("drop the tea cup"), "You don't have a tea cup.")
        self.assertEqual(g.execute("examine sea salad"), "You see no sea salad here.")

    def test_single_word_items_still_work(self):
        g = game()
        self.assertEqual(g.execute("take a lamp"), "Taken.")
        self.assertEqual(g.execute("take the lantern"), "You already have that.")
        self.assertEqual(g.execute("take the cup"), "Taken.")


class CapacitySymptoms(unittest.TestCase):
    def test_carry_exactly_capacity(self):
        g = game()
        g.run(["take tea cup", "n", "u"])
        self.assertEqual(g.execute("take anvil"), "Taken.")
        self.assertEqual(g.execute("inventory"), "You are carrying a tea cup and an anvil. (10/10)")

    def test_one_over_is_too_heavy(self):
        g = game()
        g.run(["take lamp", "take tea cup", "n", "u"])
        self.assertEqual(g.execute("take anvil"), "The anvil is too heavy: you carry 4 of 10.")
        self.assertEqual(g.state.carried_weight(), 4)

    def test_exact_fit_with_several_items(self):
        g = game()
        self.assertEqual(g.run(["take lamp", "take tea cup", "take pizza box", "n"])[:3], ["Taken."] * 3)
        self.assertEqual(g.run(["take book", "take key"]), ["Taken.", "Taken."])
        self.assertEqual(g.state.carried_weight(), 8)
        g.execute("u")
        self.assertEqual(g.execute("take anvil"), "The anvil is too heavy: you carry 8 of 10.")

    def test_container_contents_count(self):
        g = game()
        g.run(["take pizza box", "open pizza box", "take tea cup"])
        g.execute("put tea cup in pizza box")
        self.assertEqual(g.state.carried_weight(), 2)
        g.run(["drop pizza box"])
        self.assertEqual(g.execute("take pizza box"), "Taken.")
        self.assertEqual(g.state.carried_weight(), 2)

    def test_take_all_fills_to_the_limit(self):
        g = game()
        g.run(["n", "u"])
        self.assertEqual(g.execute("take all"), "anvil: Taken.")
        g.execute("d")
        g.execute("s")
        out = g.execute("take all")
        self.assertEqual(out, "brass lamp: The brass lamp is too heavy: you carry 9 of 10.\ntea cup: Taken.\npizza box: The pizza box is too heavy: you carry 10 of 10.")
        self.assertEqual(g.state.carried_weight(), 10)

    def test_take_all_skips_heavy_and_continues(self):
        g = game()
        g.run(["take lamp", "n"])
        out = g.execute("take all")
        self.assertEqual(out, "book: Taken.\nbrass key: Taken.")
        g.run(["u"])
        self.assertEqual(g.execute("take all"), "anvil: The anvil is too heavy: you carry 6 of 10.")


class AliasSymptoms(unittest.TestCase):
    def test_games_do_not_share_items(self):
        w = world()
        g1, g2 = Game(w), Game(w)
        g1.execute("take lamp")
        self.assertIn("a brass lamp", g2.execute("look"))
        self.assertEqual(g2.execute("take lamp"), "Taken.")

    def test_world_definition_untouched(self):
        w = world()
        g = Game(w)
        g.run(["take lamp", "take tea cup", "drop lamp", "n", "take key"])
        self.assertEqual(w.rooms["hall"].items, ["lamp", "tea cup", "pizza box"])
        self.assertEqual(w.rooms["library"].items, ["book", "key"])
        self.assertEqual(Game(w).state.room_items["hall"], ["lamp", "tea cup", "pizza box"])

    def test_drop_in_one_game_invisible_in_other(self):
        w = world()
        a, b = Game(w), Game(w)
        a.run(["take lamp", "n", "drop lamp"])
        self.assertEqual(b.state.room_items["library"], ["book", "key"])
        self.assertEqual(a.state.room_items["library"], ["book", "key", "lamp"])

    def test_instantiate_and_restore_are_independent(self):
        w = world()
        g = Game(w)
        g.run(["take lamp"])
        saved = g.save()
        fresh = w.instantiate()
        self.assertEqual(fresh.room_items["hall"], ["lamp", "tea cup", "pizza box"])
        restored = Game.restore(w, saved)
        restored.execute("take tea cup")
        self.assertEqual(w.rooms["hall"].items, ["lamp", "tea cup", "pizza box"])
        self.assertEqual(g.state.room_items["hall"], ["tea cup", "pizza box"])

    def test_container_contents_not_shared(self):
        w = world()
        a, b = Game(w), Game(w)
        a.state.contents["chest"].append("rose")
        self.assertEqual(b.state.contents["chest"], [])
        a.state.flags.add("x")
        self.assertEqual(b.state.flags, set())


class ReverseExitSymptoms(unittest.TestCase):
    def test_down_has_up_back(self):
        w = world()
        self.assertEqual(w.rooms["cellar"].exits, {"up": "hall"})
        self.assertEqual(w.rooms["attic"].exits, {"down": "library"})
        self.assertEqual(w.rooms["vault"].exits, {"west": "library"})
        self.assertEqual(w.rooms["library"].exits["south"], "hall")
        self.assertEqual(w.rooms["hall"].exits["down"], "cellar")

    def test_walk_down_and_back_up(self):
        g = game()
        self.assertTrue(g.execute("down").startswith("It is pitch dark"))
        self.assertEqual(g.state.room, "cellar")
        self.assertEqual(g.execute("u").split("\n")[0], "Great Hall")
        g.run(["n", "up"])
        self.assertEqual(g.state.room, "attic")
        self.assertEqual(g.execute("down").split("\n")[0], "Library")

    def test_cellar_has_no_down(self):
        g = game()
        g.execute("d")
        self.assertEqual(g.execute("d"), "You can't go that way.")
        self.assertEqual(g.state.room, "cellar")

    def test_opposite_table_is_symmetric(self):
        for direction in DIRECTIONS:
            self.assertEqual(OPPOSITE[OPPOSITE[direction]], direction)
            self.assertNotEqual(OPPOSITE[direction], direction)

    def test_locked_vertical_exit_both_sides(self):
        spec = {"start": "hall", "rooms": {"hall": {"name": "Hall", "exits": {"down": "cellar"}, "items": ["key"],
                                                     "locked_exits": {"down": "key"}}, "cellar": {"name": "Cellar"}},
                "items": {"key": {}}}
        g = Game(WorldDef.from_dict(spec))
        self.assertEqual(g.world.rooms["cellar"].locked_exits, {"up": "key"})
        g.execute("take key")
        self.assertEqual(g.execute("down"), "The way down is locked.")
        self.assertEqual(g.execute("unlock down with key"), "Unlocked.")
        self.assertEqual(g.state.locked_exits, set())
        g.execute("down")
        self.assertEqual(g.execute("up").split("\n")[0], "Hall")

    def test_locked_vertical_unlocked_from_below(self):
        spec = {"start": "cellar", "rooms": {"hall": {"name": "Hall", "exits": {"down": "cellar"}, "locked_exits": {"down": "key"}},
                                              "cellar": {"name": "Cellar", "items": ["key"]}}, "items": {"key": {}}}
        g = Game(WorldDef.from_dict(spec))
        g.execute("take key")
        self.assertEqual(g.execute("up"), "The way up is locked.")
        g.execute("unlock up with key")
        self.assertEqual(g.execute("up").split("\n")[0], "Hall")
        self.assertEqual(g.execute("down").split("\n")[0], "Cellar")


class TurnSymptoms(unittest.TestCase):
    def test_failures_cost_nothing(self):
        g = game()
        for line in ("xyzzy", "w", "take sword", "drop lamp", "unlock north with key", "put lamp in chest", "open sword", "go sideways"):
            g.execute(line)
        self.assertEqual(g.state.turn, 0)
        self.assertEqual(g.execute("score"), "Score: 0 in 0 turns.")

    def test_event_fires_after_third_successful_turn(self):
        g = bell_game()
        out = [g.execute("take lamp"), g.execute("xyzzy"), g.execute("w"), g.execute("take sword"), g.execute("n")]
        self.assertNotIn("A bell rings.", "\n".join(out))
        self.assertEqual(g.state.turn, 2)
        self.assertEqual(g.execute("take key"), "Taken.\nA bell rings.")
        self.assertEqual(g.state.turn, 3)

    def test_event_fires_once(self):
        g = bell_game()
        g.run(["take lamp", "take tea cup"])
        self.assertEqual(g.execute("take pizza box"), "Taken.\nA bell rings.")
        self.assertEqual(g.execute("n").count("A bell rings."), 0)
        g.run(["s", "n", "s"])
        self.assertNotIn("A bell rings.", g.execute("n"))

    def test_free_actions_cost_nothing(self):
        g = game()
        g.run(["look", "inventory", "examine lamp", "score", "x lamp", "i", "l"])
        self.assertEqual(g.state.turn, 0)

    def test_score_pluralisation(self):
        g = game()
        g.execute("take lamp")
        self.assertEqual(g.execute("score"), "Score: 0 in 1 turn.")
        g.execute("drop lamp")
        self.assertEqual(g.execute("score"), "Score: 0 in 2 turns.")

    def test_failed_moves_between_successes(self):
        g = game()
        g.run(["w", "w", "w", "n", "w", "w", "s", "w"])
        self.assertEqual(g.state.turn, 2)
        self.assertEqual(g.state.room, "hall")

    def test_enter_event_needs_successful_move(self):
        g = game()
        g.execute("d")
        self.assertIn("Something skitters.", g.transcript[-1][1])
        self.assertEqual(g.state.turn, 1)


class SaveSymptoms(unittest.TestCase):
    def play_to_coin(self):
        g = game()
        g.run(["take lamp", "d", "light lamp", "take coin"])
        return g

    def test_scored_is_saved(self):
        g = self.play_to_coin()
        data = save.dump(g.state)
        self.assertEqual(data["scored"], ["gold coin"])
        self.assertEqual(json.loads(g.save())["scored"], ["gold coin"])

    def test_retake_after_restore_scores_nothing(self):
        g = self.play_to_coin()
        again = Game.restore(g.world, g.save())
        self.assertEqual(again.state.scored, {"gold coin"})
        self.assertEqual(again.execute("drop coin"), "Dropped.")
        self.assertEqual(again.execute("take coin"), "Taken.")
        self.assertEqual(again.state.score, 10)
        self.assertEqual(again.execute("score"), "Score: 10 in 6 turns.")

    def test_multiple_treasures_and_chain(self):
        g = self.play_to_coin()
        g.run(["u", "n", "take key", "unlock east with key", "e", "take diamond"])
        self.assertEqual(g.state.score, 60)
        again = Game.restore(g.world, g.save())
        again.run(["drop diamond", "take diamond"])
        self.assertEqual(again.state.score, 60)
        third = Game.restore(g.world, again.save())
        third.run(["drop diamond", "take diamond", "drop coin"])
        self.assertEqual(third.state.score, 60)

    def test_roundtrip_is_lossless(self):
        g = self.play_to_coin()
        again = Game.restore(g.world, g.save())
        self.assertEqual(save.dump(again.state), save.dump(g.state))
        self.assertEqual(again.save(), g.save())

    def test_old_saves_without_scored_still_load(self):
        g = self.play_to_coin()
        data = save.dump(g.state)
        del data["scored"]
        state = save.load(g.world, data)
        self.assertEqual(state.scored, set())
        self.assertEqual(state.score, 10)


class LightSymptoms(unittest.TestCase):
    def dark_game(self):
        g = game()
        g.run(["take lamp", "d", "light lamp"])
        return g

    def test_dropped_lit_lamp_lights_the_room(self):
        g = self.dark_game()
        self.assertEqual(g.execute("drop lamp"), "Dropped.")
        self.assertTrue(g.state.is_lit())
        self.assertIn("You see a gold coin, a chest and a brass lamp.", g.execute("look"))
        self.assertEqual(g.execute("take coin"), "Taken. (+10 points)")
        self.assertEqual(g.execute("examine coin"), "It looks ordinary.")

    def test_lamp_in_room_unlit_stays_dark(self):
        g = game()
        g.run(["take lamp", "d", "drop lamp"])
        self.assertFalse(g.state.is_lit())
        self.assertTrue(g.execute("look").startswith("It is pitch dark"))
        self.assertEqual(g.execute("take coin"), "It is too dark to find anything.")
        g.execute("light lamp")
        self.assertEqual(g.execute("take coin"), "Taken. (+10 points)")

    def test_extinguish_dropped_lamp(self):
        g = self.dark_game()
        g.run(["drop lamp", "extinguish lamp"])
        self.assertFalse(g.state.is_lit())
        self.assertEqual(g.execute("take coin"), "It is too dark to find anything.")
        self.assertEqual(g.execute("take lamp"), "It is too dark to find anything.")
        self.assertEqual(g.execute("light lamp"), "The brass lamp is now lit.")
        self.assertTrue(g.state.is_lit())

    def test_lit_lamp_elsewhere_does_not_help(self):
        g = game()
        g.run(["take lamp", "light lamp", "drop lamp", "d"])
        self.assertTrue(g.state.is_lit() is False)

    def test_carried_lit_lamp(self):
        g = self.dark_game()
        self.assertTrue(g.state.is_lit())
        self.assertEqual(g.execute("take coin"), "Taken. (+10 points)")

    def test_lamp_not_a_light_source_when_not_light_item(self):
        g = game()
        g.run(["take tea cup", "d"])
        self.assertFalse(g.state.is_lit())
        self.assertEqual(g.execute("light cup"), "The tea cup can't be lit.")


class ParserRegression(unittest.TestCase):
    def test_directions(self):
        for word, direction in {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down", "North": "north", "DOWN": "down"}.items():
            self.assertEqual(parse(word), Command("go", direction))
            self.assertEqual(parse("go " + word), Command("go", direction))
        self.assertEqual(normalize("x"), None)
        self.assertEqual(ALIASES["n"], "north")

    def test_verbs_and_synonyms(self):
        cases = {
            "look": Command("look"), "l": Command("look"), "i": Command("inventory"), "inv": Command("inventory"),
            "get key": Command("take", "key"), "grab the key": Command("take", "key"), "pick up lamp": Command("take", "lamp"),
            "x lamp": Command("examine", "lamp"), "inspect the lamp": Command("examine", "lamp"),
            "shut chest": Command("close", "chest"), "douse lamp": Command("extinguish", "lamp"),
            "take key from chest": Command("take", "key", "from", "chest"),
            "put key into chest": Command("put", "key", "in", "chest"),
            "unlock chest with key": Command("unlock", "chest", "with", "key"),
            "TAKE The Lamp!": Command("take", "lamp"), "  drop   all ": Command("drop", "all"),
            "take": Command("take"),
        }
        for text, expected in cases.items():
            self.assertEqual(parse(text), expected, text)

    def test_errors(self):
        for text in ("", "   ", "!!!", "dance wildly", "go sideways", "fly"):
            with self.assertRaises(ParseError, msg=text):
                parse(text)

    def test_parse_error_messages(self):
        g = game()
        self.assertEqual(g.execute("dance"), "I don't know how to 'dance'.")
        self.assertEqual(g.execute(""), "Say something.")
        self.assertEqual(g.execute("go left"), "'left' is not a direction.")


class WorldRegression(unittest.TestCase):
    def test_validation(self):
        bad = [
            {"rooms": {}}, {"start": "x", "rooms": {}},
            {"start": "a", "rooms": {"a": {"exits": {"north": "zzz"}}}},
            {"start": "a", "rooms": {"a": {"exits": {"sideways": "a"}}}},
            {"start": "a", "rooms": {"a": {"items": ["nope"]}}},
            {"start": "a", "rooms": {"a": {"exits": {"north": "b"}, "locked_exits": {"north": "k"}}, "b": {}}, "items": {}},
            {"start": "a", "rooms": {"a": {}}, "items": {"c": {"locked": True}}},
            {"start": "a", "rooms": {"a": {}}, "items": {"c": {"container": True, "key": "ghost"}}},
            {"start": "a", "rooms": {"a": {}}, "items": {"c": {"weight": -1}}},
        ]
        for spec in bad:
            with self.assertRaises(WorldError, msg=str(spec)):
                WorldDef.from_dict(spec)

    def test_reverse_exit_not_overwritten(self):
        spec = {"start": "a", "rooms": {"a": {"exits": {"north": "b"}}, "b": {"exits": {"south": "c"}}, "c": {}}}
        w = WorldDef.from_dict(spec)
        self.assertEqual(w.rooms["b"].exits["south"], "c")
        self.assertEqual(w.rooms["c"].exits["north"], "b")
        self.assertNotIn("south", w.rooms["a"].exits)

    def test_item_defaults(self):
        w = world()
        coin = w.items["gold coin"]
        self.assertEqual((coin.weight, coin.treasure, coin.takeable, coin.names()), (1, 10, True, ["gold coin", "coin"]))
        self.assertEqual(w.items["rose"].description, "It looks ordinary.")
        self.assertEqual(w.items["rose"].name, "rose")


class CommandRegression(unittest.TestCase):
    def test_look_formats(self):
        g = game()
        self.assertEqual(g.execute("look"), "Great Hall\nA big hall.\nYou see a brass lamp, a tea cup and a pizza box.\nExits: north, east, down.")
        g.run(["n", "u"])
        self.assertEqual(g.execute("look"), "Attic\nDusty.\nYou see an anvil.\nExits: down.")
        g.run(["take anvil"])
        self.assertEqual(g.execute("look"), "Attic\nDusty.\nExits: down.")

    def test_containers(self):
        g = game()
        g.run(["d", "take lamp"])
        g.run(["u", "take lamp", "d", "light lamp"])
        self.assertEqual(g.execute("open chest"), "The chest is locked.")
        g.run(["u", "n", "take key", "s", "d"])
        self.assertEqual(g.execute("unlock chest with key"), "Unlocked.")
        self.assertEqual(g.execute("unlock chest with key"), "The chest is not locked.")
        self.assertEqual(g.execute("open chest"), "Opened.")
        self.assertEqual(g.execute("open chest"), "It is already open.")
        self.assertEqual(g.execute("take coin"), "Taken. (+10 points)")
        self.assertEqual(g.execute("put coin in chest"), "Done.")
        self.assertIn("The chest contains a gold coin.", g.execute("look"))
        self.assertEqual(g.execute("take coin from chest"), "Taken.")
        self.assertEqual(g.execute("close chest"), "Closed.")
        self.assertEqual(g.execute("put key in chest"), "The chest is closed.")
        self.assertEqual(g.execute("take coin from chest"), "The chest is closed.")
        self.assertEqual(g.execute("close chest"), "It is already closed.")

    def test_put_rules(self):
        g = game()
        g.run(["take pizza box", "open pizza box", "take tea cup", "take lamp"])
        self.assertEqual(g.execute("put lamp in pizza box"), "The brass lamp won't fit in the pizza box.")
        self.assertEqual(g.execute("put lamp in tea cup"), "The tea cup is not a container.")
        self.assertEqual(g.execute("put tea cup in pizza box"), "Done.")
        self.assertEqual(g.execute("put pizza box in pizza box"), "You can't put something inside itself.")
        self.assertEqual(g.execute("put rose in pizza box"), "You don't have a rose.")
        self.assertEqual(g.execute("put lamp"), "Put what in what?")

    def test_take_rules(self):
        g = game()
        g.run(["e"])
        self.assertEqual(g.execute("take bench"), "You can't take the bench.")
        self.assertEqual(g.execute("take rose"), "Taken.")
        self.assertEqual(g.execute("take rose"), "You already have that.")
        self.assertEqual(g.execute("take all"), "There is nothing to take.")
        self.assertEqual(g.execute("take"), "Take what?")

    def test_drop_all_and_inventory(self):
        g = game()
        g.run(["take lamp", "take tea cup"])
        self.assertEqual(g.execute("inventory"), "You are carrying a brass lamp and a tea cup. (4/10)")
        self.assertEqual(g.execute("drop all"), "brass lamp: Dropped.\ntea cup: Dropped.")
        self.assertEqual(g.execute("drop all"), "You have nothing.")
        self.assertEqual(g.execute("inventory"), "You are carrying nothing.")

    def test_examine(self):
        g = game()
        self.assertEqual(g.execute("examine lamp"), "It looks ordinary. It is not lit.")
        g.run(["take lamp", "light lamp"])
        self.assertEqual(g.execute("x lamp"), "It looks ordinary. It is lit.")
        self.assertEqual(g.execute("light lamp"), "It is already lit.")
        self.assertEqual(g.execute("examine pizza box"), "It looks ordinary. It is closed.")
        self.assertEqual(g.execute("examine"), "Examine what?")

    def test_unlock_errors(self):
        g = game()
        self.assertEqual(g.execute("unlock north with key"), "You don't have a key.")
        g.run(["n", "take key"])
        self.assertEqual(g.execute("unlock west with key"), "There is nothing to unlock that way.")
        self.assertEqual(g.execute("unlock"), "Unlock what with what?")
        self.assertEqual(g.execute("e"), "The way east is locked.")

    def test_events_on_enter(self):
        g = game()
        out = g.execute("d")
        self.assertEqual(out, "It is pitch dark. You can't see a thing.\nSomething skitters.")
        g.run(["u"])
        self.assertEqual(g.execute("d"), "It is pitch dark. You can't see a thing.")


class SaveRegression(unittest.TestCase):
    def test_restore_continues_game(self):
        g = game()
        g.run(["take lamp", "n", "take key", "unlock east with key", "e"])
        again = Game.restore(g.world, g.save())
        self.assertEqual(again.state.room, "vault")
        self.assertEqual(again.state.inventory, ["lamp", "key"])
        self.assertEqual(again.state.locked_exits, set())
        self.assertEqual(again.execute("take diamond"), "Taken. (+50 points)")
        self.assertEqual(again.execute("w").split("\n")[0], "Library")

    def test_events_do_not_refire_after_restore(self):
        g = bell_game()
        g.run(["take lamp", "take tea cup", "take pizza box"])
        again = Game.restore(g.world, g.save())
        self.assertNotIn("A bell rings.", again.execute("n"))

    def test_validation(self):
        g = game()
        data = save.dump(g.state)
        for mutate in (lambda d: d.update(room="nowhere"), lambda d: d["inventory"].append("ghost"),
                       lambda d: d.pop("turn"), lambda d: d["room_items"].pop("hall")):
            broken = json.loads(json.dumps(data))
            mutate(broken)
            with self.assertRaises(SaveError):
                save.load(g.world, broken)
        with self.assertRaises(SaveError):
            save.from_json(g.world, "{oops")

    def test_dump_shape(self):
        g = game()
        data = save.dump(g.state)
        self.assertEqual(sorted(data), ["contents", "fired", "flags", "inventory", "lit", "locked_exits", "locked_items",
                                        "open_containers", "room", "room_items", "score", "scored", "turn"])
        self.assertEqual(data["locked_items"], ["chest"])
        self.assertEqual(data["locked_exits"], [["library", "east"], ["vault", "west"]])
        self.assertEqual(data["room"], "hall")


class HintsAndRenderRegression(unittest.TestCase):
    def test_render(self):
        w = world()
        self.assertEqual(join_list([]), "")
        self.assertEqual(join_list(["a"]), "a")
        self.assertEqual(join_list(["a", "b"]), "a and b")
        self.assertEqual(join_list(["a", "b", "c"]), "a, b and c")
        self.assertEqual(with_article("anvil"), "an anvil")
        self.assertEqual(with_article("lamp"), "a lamp")
        self.assertEqual(describe_items(w, ["lamp", "anvil"]), "a brass lamp and an anvil")

    def test_hints(self):
        g = game()
        self.assertEqual(hints.visible_exits(g.state), ["north", "east", "down"])
        self.assertEqual(hints.hint(g.state), "There are 2 treasures left to find.")
        g.run(["n"])
        self.assertEqual(hints.locked_ways(g.state), ["east"])
        self.assertEqual(hints.hint(g.state), "The way east is locked; you need a key.")
        g.run(["s", "d"])
        self.assertEqual(hints.hint(g.state), "Find a light source.")
        self.assertEqual(hints.unscored_treasures(g.state), ["diamond", "gold coin"])

    def test_replay_and_final_score(self):
        w = world()
        lines = ["take lamp", "d", "light lamp", "take coin"]
        game_, outputs = hints.replay(w, lines)
        self.assertEqual(outputs[-1], "Taken. (+10 points)")
        self.assertEqual(hints.final_score(w, lines), 10)
        self.assertEqual(hints.final_score(w, lines), 10)


if __name__ == "__main__":
    unittest.main()
