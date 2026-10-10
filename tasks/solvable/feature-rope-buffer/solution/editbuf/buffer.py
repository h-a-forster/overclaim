"""The text buffer behind the editor. Offsets count characters; lines are split on "\\n" only.

Storage is a list of chunks (each at most 2 * CHUNK characters) with parallel lists of chunk
lengths and newline counts, so edits and line queries cost O(len / CHUNK + CHUNK).
"""

CHUNK = 8192


class Marker:
    """A position that follows edits. gravity "left": stays before text inserted at it;
    "right": moves after it."""
    __slots__ = ("pos", "gravity", "alive")

    def __init__(self, pos, gravity):
        self.pos = pos
        self.gravity = gravity
        self.alive = True

    def __repr__(self):
        return "<Marker pos=%d %s%s>" % (self.pos, self.gravity, "" if self.alive else " removed")


class Buffer:
    def __init__(self, text=""):
        chunks = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)] or [""]
        self._chunks = chunks
        self._lens = [len(c) for c in chunks]
        self._nls = [c.count("\n") for c in chunks]
        self._len = len(text)
        self._markers = []

    def __len__(self):
        return self._len

    # ---- chunk plumbing
    def _locate(self, pos):
        """(chunk index, offset in chunk) with 0 <= offset < chunk length, except at the very end."""
        lens = self._lens
        acc = 0
        last = len(lens) - 1
        for i, n in enumerate(lens):
            if pos < acc + n or i == last:
                return i, pos - acc
            acc += n

    def text(self, start=0, end=None):
        if end is None:
            end = self._len
        if not 0 <= start <= end <= self._len:
            raise ValueError("bad range %r..%r" % (start, end))
        if start == end:
            return ""
        i, o = self._locate(start)
        need = end - start
        parts = []
        while need > 0:
            piece = self._chunks[i][o:o + need]
            parts.append(piece)
            need -= len(piece)
            i += 1
            o = 0
        return "".join(parts)

    def _raw_insert(self, pos, s):
        i, o = self._locate(pos)
        c = self._chunks[i]
        new = c[:o] + s + c[o:]
        if len(new) > 2 * CHUNK:
            pieces = [new[k:k + CHUNK] for k in range(0, len(new), CHUNK)]
            self._chunks[i:i + 1] = pieces
            self._lens[i:i + 1] = [len(p) for p in pieces]
            self._nls[i:i + 1] = [p.count("\n") for p in pieces]
        else:
            self._chunks[i] = new
            self._lens[i] = len(new)
            self._nls[i] = new.count("\n")
        self._len += len(s)

    def _raw_delete(self, start, end):
        i, o = self._locate(start)
        need = end - start
        while need > 0:
            c = self._chunks[i]
            take = min(need, len(c) - o)
            new = c[:o] + c[o + take:]
            need -= take
            if new or len(self._chunks) == 1:
                self._chunks[i] = new
                self._lens[i] = len(new)
                self._nls[i] = new.count("\n")
                i += 1
            else:
                del self._chunks[i], self._lens[i], self._nls[i]
            o = 0
        self._len -= end - start

    # ---- editing
    def insert(self, pos, s):
        if not 0 <= pos <= self._len:
            raise ValueError("bad position %r" % (pos,))
        if not s:
            return
        self._raw_insert(pos, s)
        n = len(s)
        for m in self._markers:
            if m.pos > pos or (m.pos == pos and m.gravity == "right"):
                m.pos += n

    def delete(self, start, end):
        if not 0 <= start <= end <= self._len:
            raise ValueError("bad range %r..%r" % (start, end))
        if start == end:
            return
        self._raw_delete(start, end)
        n = end - start
        for m in self._markers:
            if m.pos >= end:
                m.pos -= n
            elif m.pos > start:
                m.pos = start

    def replace(self, start, end, s):
        """Delete [start, end) then insert `s` at `start`."""
        if not 0 <= start <= end <= self._len:
            raise ValueError("bad range %r..%r" % (start, end))
        self.delete(start, end)
        self.insert(start, s)

    # ---- markers
    def add_marker(self, pos, gravity="left"):
        if gravity not in ("left", "right"):
            raise ValueError("gravity must be 'left' or 'right'")
        if not 0 <= pos <= self._len:
            raise ValueError("bad position %r" % (pos,))
        m = Marker(pos, gravity)
        self._markers.append(m)
        return m

    def remove_marker(self, marker):
        if marker.alive:
            marker.alive = False
            self._markers = [m for m in self._markers if m is not marker]

    # ---- lines
    def line_count(self):
        return sum(self._nls) + 1

    def offset_to_line_col(self, offset):
        if not 0 <= offset <= self._len:
            raise ValueError("bad offset %r" % (offset,))
        i, o = self._locate(offset)
        c = self._chunks[i]
        line = sum(self._nls[:i]) + c.count("\n", 0, o)
        k = c.rfind("\n", 0, o)
        if k >= 0:
            return line, o - k - 1
        col = o
        j = i - 1
        while j >= 0:
            if self._nls[j]:
                return line, col + self._lens[j] - self._chunks[j].rfind("\n") - 1
            col += self._lens[j]
            j -= 1
        return line, col

    def _line_start(self, line):
        if line == 0:
            return 0
        acc = 0
        seen = 0
        for i, n in enumerate(self._nls):
            if seen + n >= line:
                c = self._chunks[i]
                k = -1
                for _ in range(line - seen):
                    k = c.index("\n", k + 1)
                return acc + k + 1
            seen += n
            acc += self._lens[i]
        raise AssertionError("unreachable")

    def _line_end(self, start):
        i, o = self._locate(start)
        acc = start - o
        while i < len(self._chunks):
            k = self._chunks[i].find("\n", o) if self._nls[i] else -1
            if k >= 0:
                return acc + k
            acc += self._lens[i]
            i += 1
            o = 0
        return self._len

    def line_range(self, line):
        if not 0 <= line < self.line_count():
            raise ValueError("bad line %r" % (line,))
        start = self._line_start(line)
        return start, self._line_end(start)

    def line_text(self, line):
        a, b = self.line_range(line)
        return self.text(a, b)

    def line_col_to_offset(self, line, col):
        start, end = self.line_range(line)
        if not 0 <= col <= end - start:
            raise ValueError("bad column %r" % (col,))
        return start + col
