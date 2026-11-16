"""Minimal lossless S-expression reader/writer for KiCad 10 files (.kicad_sch).

Every token keeps the whitespace in front of it, so `dumps(loads(text)) == text` byte for byte. Edit by changing
atom values or by adding/removing nodes; untouched text is never reformatted. New nodes are written in KiCad's
own layout (tabs, one property per line) by the emitters in `place.py` and parsed back with `parse_snippet`.
Plain Python stdlib.
"""
import re

_TOK = re.compile(r'(\s*)(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))')
_TAIL = re.compile(r"\s*\Z")


class Atom:
    """A string (quoted) or bare token (number, keyword). `raw` is the exact source text."""

    __slots__ = ("ws", "raw")

    def __init__(self, raw, ws=" "):
        self.raw, self.ws = raw, ws

    @property
    def quoted(self):
        return self.raw.startswith('"')

    @property
    def value(self):
        if not self.quoted:
            return self.raw
        s = self.raw[1:-1]
        return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) == "n" else m.group(1), s)

    def set(self, value, quoted=None):
        """Set the value. Numbers are written bare via fmt(); strings quoted."""
        if quoted is None:
            quoted = self.quoted
        self.raw = qstr(value) if quoted else str(value)

    def num(self):
        return float(self.raw)


class Node:
    """A parenthesised list. items holds Atom and Node children in source order."""

    __slots__ = ("ws", "items", "close_ws", "post")

    def __init__(self, items=None, ws="\n", close_ws=""):
        self.items, self.ws, self.close_ws = items if items is not None else [], ws, close_ws
        self.post = "\n"  # text after the closing paren (root only)

    @property
    def head(self):
        i = self.items
        return i[0].raw if i and isinstance(i[0], Atom) and not i[0].quoted else None

    def nodes(self, head=None):
        return [c for c in self.items if isinstance(c, Node) and (head is None or c.head == head)]

    def get(self, head):
        """First child node with this head, or None."""
        for c in self.items:
            if isinstance(c, Node) and c.head == head:
                return c
        return None

    def atoms(self):
        return [c for c in self.items if isinstance(c, Atom)]

    def args(self):
        """Atom values after the head."""
        return [a.value for a in self.atoms()[1:]]

    def nums(self):
        """Floats of the bare numeric atoms after the head, e.g. (at x y a) -> [x, y, a]."""
        out = []
        for a in self.atoms()[1:]:
            try:
                out.append(float(a.raw))
            except ValueError:
                pass
        return out

    def set_nums(self, *vals):
        """Rewrite the leading numeric atoms (e.g. an `(at ...)` node), keeping their count if more are given."""
        a = [x for x in self.atoms()[1:] if not x.quoted]
        for x, v in zip(a, vals):
            x.raw = fmt(v)
        for v in vals[len(a):]:
            self.items.append(Atom(fmt(v)))

    def remove(self, child):
        self.items = [c for c in self.items if c is not child]

    def append(self, node, indent=1):
        """Append a child node on its own line at tab depth `indent`; fixes the closing paren indentation."""
        node.ws = "\n" + "\t" * indent
        self.items.append(node)
        self.close_ws = "\n" + "\t" * (indent - 1)

    def walk(self):
        yield self
        for c in self.items:
            if isinstance(c, Node):
                yield from c.walk()


def fmt(v):
    """Number as KiCad writes it: up to 4 decimals, trailing zeros stripped, no '-0'."""
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def qstr(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def loads(text):
    """Parse one top-level expression. Returns the root Node; trailing whitespace is kept in `root.post`."""
    stack, root, pos = [], None, 0
    while True:
        m = _TOK.match(text, pos)
        if not m:
            break
        ws, op, cl, qs, bare = m.groups()
        if op:
            n = Node(ws=ws)
            if stack:
                stack[-1].items.append(n)
            elif root is None:
                root = n
            else:
                raise ValueError("more than one top-level expression")
            stack.append(n)
        elif cl:
            if not stack:
                raise ValueError("unbalanced ')' at offset %d" % pos)
            stack[-1].close_ws = ws
            stack.pop()
            if not stack:
                pos = m.end()
                break
        else:
            if not stack:
                raise ValueError("atom outside list at offset %d" % pos)
            stack[-1].items.append(Atom(qs if qs is not None else bare, ws))
        pos = m.end()
    if root is None or stack:
        raise ValueError("unbalanced '('")
    if not _TAIL.match(text, pos):
        raise ValueError("trailing text after the top-level expression at offset %d" % pos)
    root.post = text[pos:]
    return root


def load(path):
    with open(path, encoding="utf-8", newline="") as f:
        return loads(f.read())


def dumps(node):
    out = []

    def w(n):
        out.append(n.ws + "(")
        for c in n.items:
            if isinstance(c, Atom):
                out.append(c.ws + c.raw)
            else:
                w(c)
        out.append(n.close_ws + ")")

    w(node)
    return "".join(out) + node.post


def save(path, node):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(dumps(node))


def parse_snippet(text):
    """Parse a text snippet (one expression, KiCad layout) into a detached Node."""
    n = loads(text.strip("\n"))
    n.ws = "\n"
    return n
