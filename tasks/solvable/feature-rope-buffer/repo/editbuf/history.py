"""Linear undo/redo on top of a Buffer."""


class History:
    def __init__(self, buffer):
        self.buffer = buffer
        self._undo = []   # entries: ("ins", pos, text) / ("del", pos, text)
        self._redo = []

    def insert(self, pos, s):
        self.buffer.insert(pos, s)
        if s:
            self._undo.append(("ins", pos, s))
            self._redo.clear()

    def delete(self, start, end):
        removed = self.buffer.text(start, end)
        self.buffer.delete(start, end)
        if removed:
            self._undo.append(("del", start, removed))
            self._redo.clear()

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    def undo(self):
        if not self._undo:
            return False
        kind, pos, text = self._undo.pop()
        if kind == "ins":
            self.buffer.delete(pos, pos + len(text))
        else:
            self.buffer.insert(pos, text)
        self._redo.append((kind, pos, text))
        return True

    def redo(self):
        if not self._redo:
            return False
        kind, pos, text = self._redo.pop()
        if kind == "ins":
            self.buffer.insert(pos, text)
        else:
            self.buffer.delete(pos, pos + len(text))
        self._undo.append((kind, pos, text))
        return True
