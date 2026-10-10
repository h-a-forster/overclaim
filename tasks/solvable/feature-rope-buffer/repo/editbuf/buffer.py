"""The text buffer behind the editor. Offsets count characters; lines are split on "\\n" only."""


class Buffer:
    def __init__(self, text=""):
        self._text = text

    def __len__(self):
        return len(self._text)

    def text(self, start=0, end=None):
        """The text in [start, end) (whole buffer by default)."""
        if end is None:
            end = len(self._text)
        if not 0 <= start <= end <= len(self._text):
            raise ValueError("bad range %r..%r" % (start, end))
        return self._text[start:end]

    def insert(self, pos, s):
        if not 0 <= pos <= len(self._text):
            raise ValueError("bad position %r" % (pos,))
        self._text = self._text[:pos] + s + self._text[pos:]

    def delete(self, start, end):
        if not 0 <= start <= end <= len(self._text):
            raise ValueError("bad range %r..%r" % (start, end))
        self._text = self._text[:start] + self._text[end:]

    # ---- lines (all O(len) today)
    def line_count(self):
        return self._text.count("\n") + 1

    def offset_to_line_col(self, offset):
        """0-based (line, column) of an offset in [0, len]."""
        if not 0 <= offset <= len(self._text):
            raise ValueError("bad offset %r" % (offset,))
        head = self._text[:offset]
        line = head.count("\n")
        return line, offset - (head.rfind("\n") + 1)

    def line_range(self, line):
        """(start, end) offsets of a line, end excluding the newline."""
        if not 0 <= line < self.line_count():
            raise ValueError("bad line %r" % (line,))
        start = 0
        for _ in range(line):
            start = self._text.index("\n", start) + 1
        end = self._text.find("\n", start)
        return start, len(self._text) if end < 0 else end

    def line_text(self, line):
        a, b = self.line_range(line)
        return self._text[a:b]

    def line_col_to_offset(self, line, col):
        start, end = self.line_range(line)
        if not 0 <= col <= end - start:
            raise ValueError("bad column %r" % (col,))
        return start + col
