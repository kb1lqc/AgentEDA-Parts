#!/usr/bin/env python3
"""Check KiCad symbol geometry that pinmap.py does not look at, per unit.

Usage: python3 -I scripts/symgeom.py <file.kicad_sym>
Prints BODY and PINPOS rows per unit and flags: pin off the 2.54 grid, pin inside its unit's body outline (e.g. a pin
left at (0 0) by a shift script), unit body centre more than 1.27 from the origin (-Wstyle centring), pin_names offset
outside 0.508..1.27. Body = rectangle, polyline, circle and arc points of the unit plus unit 0 (shared by all units).
Exit 0 ok, 1 flagged, 2 usage. A unit with no body graphics still gets its pin and grid checks.
"""
import re
import sys

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(2)


def _tree(text):
    st = [[]]
    for tok in re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text):
        if tok == "(":
            st.append([])
        elif tok == ")":
            n = st.pop()
            st[-1].append(n)
        else:
            st[-1].append(tok.strip('"'))
    return st[0][0]


def _find(n, key):
    if isinstance(n, list):
        if n and n[0] == key:
            yield n
        for c in n:
            yield from _find(c, key)


def _xy(n, key):
    c = next(_find(n, key))
    return float(c[1]), float(c[2])


def _body_points(node):
    pts = []
    for r in _find(node, "rectangle"):
        pts += [_xy(r, "start"), _xy(r, "end")]
    for pl in _find(node, "polyline"):
        pts += [(float(p[1]), float(p[2])) for p in _find(pl, "xy")]
    for a in _find(node, "arc"):
        pts += [_xy(a, k) for k in ("start", "mid", "end")]
    for c in _find(node, "circle"):
        (x, y), r = _xy(c, "center"), float(next(_find(c, "radius"))[1])
        pts += [(x - r, y - r), (x + r, y + r)]
    return pts


root = _tree(open(sys.argv[1]).read())
flags = []
units = {}  # unit number -> (body points, pins); sub-symbols are named <name>_<unit>_<style>
for sub in _find(root, "symbol"):
    m = re.search(r"_(\d+)_\d+$", sub[1]) if len(sub) > 1 else None
    if not m:
        continue
    pts, pins = units.setdefault(int(m.group(1)), ([], []))
    pts += _body_points(sub)
    pins += [(next(_find(p, "number"))[1], *_xy(p, "at")) for p in _find(sub, "pin")]
shared_pts, shared_pins = units.pop(0, ([], []))
if not units:  # single-unit symbol drawn entirely in unit 0
    units = {1: ([], [])}
for u, (pts, pins) in sorted(units.items()):
    pts, pins = pts + shared_pts, pins + shared_pins
    if pts:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        print(f"BODY unit={u} x={x0:+.2f}..{x1:+.2f} y={y0:+.2f}..{y1:+.2f} centre=({(x0 + x1) / 2:+.2f},{(y0 + y1) / 2:+.2f})")
        if abs((x0 + x1) / 2) > 1.3 or abs((y0 + y1) / 2) > 1.3:
            flags.append(f"unit {u}: body centre is more than 1.27 from origin (-Wstyle centring)")
    else:
        print(f"BODY unit={u} none (no rectangle/polyline/arc/circle)")
    for n, x, y in sorted(pins, key=lambda p: (not p[0].isdigit(), int(p[0]) if p[0].isdigit() else 0, p[0])):
        off = any(abs(v / 2.54 - round(v / 2.54)) > 0.004 for v in (x, y))
        inside = bool(pts) and x0 + 0.01 < x < x1 - 0.01 and y0 + 0.01 < y < y1 - 0.01
        print(f"PINPOS unit={u} num={n} x={x:+.2f} y={y:+.2f}" + ("  OFFGRID" if off else "") + ("  INSIDE_BODY" if inside else ""))
        if off:
            flags.append(f"pin {n} off the 2.54 grid")
        if inside:
            flags.append(f"pin {n} inside the unit {u} body outline (unshifted (0 0) pin?)")
for o in _find(root, "pin_names"):
    v = [float(c[1]) for c in o[1:] if isinstance(c, list) and c[0] == "offset"]
    if v and not 0.508 <= v[0] <= 1.27:
        flags.append(f"pin_names offset {v[0]} outside 0.508..1.27")
for f in flags:
    print("FLAG:", f)
print("symbol geometry:", "FLAGGED" if flags else "OK")
sys.exit(1 if flags else 0)
