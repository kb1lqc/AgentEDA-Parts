#!/usr/bin/env python3
"""Print symbol pins and footprint pads for mechanical diffing against the datasheet pin table.

Usage: python3 -I scripts/pinmap.py <file.kicad_sym> <file.kicad_mod> [EP pad numbers...]
Output: one PIN row per symbol pin (unit, number, name, electrical type), one PAD row per pad
(number, x, y in mm, KiCad Y-down, top view), the set differences, and a pad-numbering
winding check (pin 1 onward must run counter-clockwise in top view).
Exit 0 ok; 1 set mismatch or clockwise (mirrored) numbering; 2 usage, or winding not checkable on a part with more
than 2 pads (alphanumeric BGA/LGA names, collinear numeric pads): then compare pad 1 / A1 position and row/column
direction with the DS top-view diagram by hand and log it. Pass every numeric EP/tab pad number (QFN EP, SOT-223 tab)
as an extra argument, or it pollutes the winding polygon. Zig-zag connector numbering is not JEDEC CCW: hand check.
It cannot tell whether pad 1 is in the right corner: check that by hand.
"""
import re
import sys

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(2)


def parse(text):
    tokens = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    stack = [[]]
    for tok in tokens:
        if tok == "(":
            stack.append([])
        elif tok == ")":
            node = stack.pop()
            stack[-1].append(node)
        else:
            stack[-1].append(tok[1:-1] if tok.startswith('"') else tok)
    return stack[0][0]


def walk(node, unit=None):
    if not isinstance(node, list) or not node:
        return
    if node[0] == "symbol" and len(node) > 1:
        m = re.search(r"_(\d+)_\d+$", node[1])
        unit = m.group(1) if m else unit
    if node[0] == "pin":
        fields = {c[0]: c[1] for c in node if isinstance(c, list) and len(c) > 1}
        yield ("PIN", unit or "1", fields.get("number", "?"), fields.get("name", "?"), node[1])
        return
    for child in node:
        yield from walk(child, unit)


def pads(node):
    for child in node:
        if isinstance(child, list) and child and child[0] == "pad":
            at = next(c for c in child if isinstance(c, list) and c[0] == "at")
            yield ("PAD", child[1], float(at[1]), float(at[2]), child[2])


sym = sorted(set(walk(parse(open(sys.argv[1]).read()))), key=lambda r: (r[1], not r[2].isdigit(), int(r[2]) if r[2].isdigit() else 0, r[2]))
fp = sorted(pads(parse(open(sys.argv[2]).read())), key=lambda r: (not r[1].isdigit(), int(r[1]) if r[1].isdigit() else 0, r[1]))
for unit, num, name, etype in [r[1:] for r in sym]:
    print(f"PIN unit={unit} num={num} name={name} type={etype}")
for num, x, y, kind in [r[1:] for r in fp]:
    print(f"PAD num={num or '(unnumbered)'} x={x:+.3f} y={y:+.3f} {kind}")
pin_nums = {r[2] for r in sym}
pad_nums = {r[1] for r in fp if r[1]}
print("pins_without_pad:", sorted(pin_nums - pad_nums))
print("pads_without_pin:", sorted(pad_nums - pin_nums))
ep = set(sys.argv[3:])  # EP/thermal pad numbers, excluded from the winding check
ring = sorted({(int(n), x, y) for _, n, x, y, _ in fp if n.isdigit() and n not in ep})
area = sum(a[1] * b[2] - b[1] * a[2] for a, b in zip(ring, ring[1:] + ring[:1]))
alpha = any(not n.isdigit() for n in pad_nums - ep)  # BGA/LGA ball names are never winding-checked
unchecked = alpha or len(ring) < 3 or abs(area) < 1e-9
if unchecked and not alpha and len(pad_nums) <= 2:
    print("pad numbering: 2-pad part, winding not applicable")
elif unchecked:
    print("pad numbering: WINDING NOT CHECKED (alphanumeric or collinear pads): hand-check against the DS top view")
else:
    print("pad numbering:", "CCW top view OK" if area < 0 else "CW: MIRRORED")
if pin_nums != pad_nums or (not alpha and area > 1e-9):
    sys.exit(1)
sys.exit(2 if unchecked and (alpha or len(pad_nums) > 2) else 0)
