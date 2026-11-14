"""Minimal KiCad S-expression reader, plus symbol-pin and footprint-pad helpers."""

import re

# A token is: "(", ")", a quoted string, or any run of other non-space characters.
TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text):
    """Parse S-expression text into nested lists of strings (quotes removed)."""
    stack = [[]]
    for tok in TOKEN.findall(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        elif tok.startswith('"'):
            stack[-1].append(tok[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        else:
            stack[-1].append(tok)
    return stack[0][0]


def find_all(node, head):
    """Every nested list whose first item is `head`, in file order."""
    found = []
    if isinstance(node, list):
        if node and node[0] == head:
            found.append(node)
        for child in node:
            found.extend(find_all(child, head))
    return found


def _field(node, key):
    """Text of the first (key "value" ...) child of node, or ''."""
    for child in node:
        if isinstance(child, list) and child and child[0] == key and len(child) > 1:
            return child[1]
    return ""


def read(path):
    """Parse a KiCad file."""
    with open(path, encoding="utf-8") as f:
        return parse(f.read())


def symbol_pins(path):
    """List of (number, name, electrical_type) for every pin in a .kicad_sym file."""
    pins = []
    for pin in find_all(read(path), "pin"):
        if len(pin) > 2 and isinstance(pin[1], str):  # (pin <type> <style> ...)
            pins.append((_field(pin, "number"), _field(pin, "name"), pin[1]))
    return pins


def footprint_pads(path):
    """Set of pad numbers in a .kicad_mod file (pads with no number are ignored)."""
    numbers = set()
    for pad in find_all(read(path), "pad"):
        if len(pad) > 1 and pad[1] != "":
            numbers.add(pad[1])
    return numbers
