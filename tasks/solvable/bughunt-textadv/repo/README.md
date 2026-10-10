# adventure

A small text adventure engine: a world definition (rooms, items, locked doors and chests, dark
rooms, scripted events), a verb/noun parser, command handlers, save/load and hints.

```python
from adventure import Game, WorldDef

world = WorldDef.from_dict({
    "start": "hall",
    "rooms": {"hall": {"name": "Hall", "desc": "A hall.", "exits": {"north": "library"}, "items": ["lamp"]},
              "library": {"name": "Library", "desc": "Books."}},
    "items": {"lamp": {"name": "brass lamp", "aliases": ["lamp"], "weight": 3, "light": True}},
})
game = Game(world)
print(game.execute("take the lamp"))    # Taken.
print(game.execute("n"))
```

Documented behaviour:

* **Parsing**: the words `a`, `an`, `the`, `some` are dropped from noun phrases, but only as whole
  words: `take the tea cup` and `take tea cup` both refer to the item called "tea cup".
* **Carrying**: the player may carry up to `capacity` weight, *including* exactly `capacity`
  (a container's contents count). `take all` skips what is too heavy and takes the rest.
* **Worlds are templates**: `WorldDef.instantiate()` / `Game(world)` give every game its own
  fresh state; playing one game never changes another game (or the world definition).
* **Exits are two-way**: `hall: {down: cellar}` also gives the cellar an `up` exit back to the hall; a
  locked exit is locked from both sides and unlocking it from one side unlocks both.
* **Turns**: the turn counter only advances when a turn-taking command succeeds (go, take, drop,
  put, open, close, unlock, light, extinguish). Unknown or refused commands and free actions
  (look, inventory, examine, score) cost no turn. A timed event with `turn: N` fires right after
  the N-th successful turn.
* **Score**: a treasure scores its points the first time it is taken, never again (dropping and
  re-taking it gives nothing), also across save / restore.
* **Darkness**: in a dark room you see nothing unless a lit light source is carried *or lying in
  the room*.

Run the tests with `python -m unittest discover -s tests -t .`.
