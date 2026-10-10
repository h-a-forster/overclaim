"""The Game: one world, one state, one command at a time."""

from . import commands, events, save
from .errors import ParseError
from .parser import parse


class Game:
    def __init__(self, world, state=None):
        self.world = world
        self.state = state if state is not None else world.instantiate()
        self.transcript = []

    def execute(self, line):
        """Run one line of input and return the text to show.

        The turn counter only advances when a turn-taking command (moving, taking, dropping,
        putting, opening, closing, unlocking, lighting) succeeds; refused or unknown commands and
        free actions (look, inventory, examine, score) cost nothing.  Scripted events fire
        after the turn that triggers them.
        """
        try:
            command = parse(line)
        except ParseError as exc:
            return self._record(line, str(exc))
        result = commands.run(self.state, command)
        out = [result.text]
        if command.verb in commands.TURN_COMMANDS and result.ok:
            self.state.turn += 1
            if command.verb == "go":
                out.extend(events.on_enter(self.state))
            out.extend(events.after_turn(self.state))
        return self._record(line, "\n".join(out))

    def _record(self, line, text):
        self.transcript.append((line, text))
        return text

    def run(self, lines):
        """Execute several lines; returns the list of outputs."""
        return [self.execute(line) for line in lines]

    def save(self):
        return save.to_json(self.state)

    @classmethod
    def restore(cls, world, text):
        return cls(world, save.from_json(world, text))
