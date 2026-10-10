"""Undo/redo (with groups) on top of a Buffer."""
from contextlib import contextmanager


class History:
    def __init__(self, buffer):
        self.buffer = buffer
        self._undo = []   # entries: lists of (start, old_text, new_text)
        self._redo = []
        self._group = None
        self._depth = 0

    # ---- recording
    def _record(self, start, old, new):
        if not old and not new:
            return
        if self._depth:
            self._group.append((start, old, new))
        else:
            self._undo.append([(start, old, new)])
        self._redo.clear()

    def insert(self, pos, s):
        self.buffer.insert(pos, s)
        self._record(pos, "", s)

    def delete(self, start, end):
        old = self.buffer.text(start, end)
        self.buffer.delete(start, end)
        self._record(start, old, "")

    def replace(self, start, end, s):
        old = self.buffer.text(start, end)
        self.buffer.replace(start, end, s)
        self._record(start, old, s)

    def begin_group(self):
        if self._depth == 0:
            self._group = []
        self._depth += 1

    def end_group(self):
        if self._depth == 0:
            raise RuntimeError("no open group")
        self._depth -= 1
        if self._depth == 0:
            if self._group:
                self._undo.append(self._group)
            self._group = None

    @contextmanager
    def group(self):
        self.begin_group()
        try:
            yield self
        finally:
            self.end_group()

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        if self._depth:
            raise RuntimeError("cannot undo inside a group")
        if not self._undo:
            return False
        entry = self._undo.pop()
        for start, old, new in reversed(entry):
            self.buffer.replace(start, start + len(new), old)
        self._redo.append(entry)
        return True

    def redo(self):
        if self._depth:
            raise RuntimeError("cannot redo inside a group")
        if not self._redo:
            return False
        entry = self._redo.pop()
        for start, old, new in entry:
            self.buffer.replace(start, start + len(old), new)
        self._undo.append(entry)
        return True
