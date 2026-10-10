"""Backtracking matcher: the AST is compiled to a small program run by an explicit-stack VM,
so long subject strings do not hit Python's recursion limit."""
from .nodes import Alt, Any, Assertion, Backref, CharClass, Concat, Group, Literal, Repeat

CHAR, ANY, CLASS, SPLIT, JMP, SAVE, BOL, EOL, BACKREF, MATCH, SETPOS, CHKPOS = range(12)


def nullable(node):
    if isinstance(node, (Literal, Any, CharClass)):
        return False
    if isinstance(node, Concat):
        return all(nullable(x) for x in node.items)
    if isinstance(node, Alt):
        return any(nullable(x) for x in node.options)
    if isinstance(node, Group):
        return nullable(node.node)
    if isinstance(node, Repeat):
        return node.lo == 0 or nullable(node.node)
    return True


class Program:
    def __init__(self, node, ngroups):
        self.code = []
        self.nregs = 0
        self.ngroups = ngroups
        self.emit_node(node)
        self.code.append((MATCH,))
        self.nslots = 2 * (ngroups + 1) + self.nregs

    def here(self):
        return len(self.code)

    def emit_node(self, node):
        code = self.code
        if isinstance(node, Literal):
            code.append((CHAR, node.ch))
        elif isinstance(node, Any):
            code.append((ANY,))
        elif isinstance(node, CharClass):
            code.append((CLASS, node))
        elif isinstance(node, Concat):
            for x in node.items:
                self.emit_node(x)
        elif isinstance(node, Alt):
            jumps = []
            for n, opt in enumerate(node.options):
                if n < len(node.options) - 1:
                    sp = self.here()
                    code.append(None)
                    self.emit_node(opt)
                    jumps.append(self.here())
                    code.append(None)
                    code[sp] = (SPLIT, sp + 1, self.here())
                else:
                    self.emit_node(opt)
            for j in jumps:
                code[j] = (JMP, self.here())
        elif isinstance(node, Group):
            code.append((SAVE, 2 * node.index))
            self.emit_node(node.node)
            code.append((SAVE, 2 * node.index + 1))
        elif isinstance(node, Assertion):
            code.append((BOL,) if node.kind == "bol" else (EOL,))
        elif isinstance(node, Backref):
            code.append((BACKREF, node.index))
        elif isinstance(node, Repeat):
            self.emit_repeat(node)
        else:
            raise TypeError(node)

    def split(self, greedy, body, exit_):
        return (SPLIT, body, exit_) if greedy else (SPLIT, exit_, body)

    def emit_repeat(self, node):
        code = self.code
        for _ in range(node.lo):
            self.emit_node(node.node)
        if node.hi is None:
            guard = nullable(node.node)
            loop = self.here()
            code.append(None)
            reg = None
            if guard:
                reg = 2 * (self.ngroups + 1) + self.nregs
                self.nregs += 1
                code.append((SETPOS, reg))
            self.emit_node(node.node)
            if guard:
                code.append((CHKPOS, reg))
            code.append((JMP, loop))
            code[loop] = self.split(node.greedy, loop + 1, self.here())
        else:
            splits = []
            for _ in range(node.hi - node.lo):
                splits.append(self.here())
                code.append(None)
                self.emit_node(node.node)
            end = self.here()
            for sp in splits:
                code[sp] = self.split(node.greedy, sp + 1, end)


def run(prog, s, start, full=False, noempty=False):
    """Return the capture-slot list of the first match starting at `start`, or None."""
    code = prog.code
    n = len(s)
    slots = [-1] * prog.nslots
    stack = []
    pc = 0
    i = start
    while True:
        ins = code[pc]
        op = ins[0]
        ok = True
        if op == CHAR:
            if i < n and s[i] == ins[1]:
                i += 1
                pc += 1
            else:
                ok = False
        elif op == ANY:
            if i < n and s[i] != "\n":
                i += 1
                pc += 1
            else:
                ok = False
        elif op == CLASS:
            if i < n and ins[1].matches(s[i]):
                i += 1
                pc += 1
            else:
                ok = False
        elif op == SPLIT:
            stack.append((ins[2], i))
            pc = ins[1]
        elif op == JMP:
            pc = ins[1]
        elif op == SAVE or op == SETPOS:
            slot = ins[1]
            stack.append((slot, slots[slot], 0))
            slots[slot] = i
            pc += 1
        elif op == CHKPOS:
            if slots[ins[1]] == i:
                ok = False
            else:
                pc += 1
        elif op == BOL:
            if i == 0:
                pc += 1
            else:
                ok = False
        elif op == EOL:
            if i == n:
                pc += 1
            else:
                ok = False
        elif op == BACKREF:
            a = slots[2 * ins[1]]
            b = slots[2 * ins[1] + 1]
            if a < 0 or b < 0:
                ok = False
            else:
                length = b - a
                if s.startswith(s[a:b], i):
                    i += length
                    pc += 1
                else:
                    ok = False
        else:  # MATCH
            if (full and i != n) or (noempty and i == start):
                ok = False
            else:
                slots[0] = start
                slots[1] = i
                return slots
        if not ok:
            while stack:
                e = stack.pop()
                if len(e) == 3:
                    slots[e[0]] = e[1]
                else:
                    pc, i = e
                    break
            else:
                return None
