#!/usr/bin/env python3
"""Bounding box of a STEP model from its VERTEX_POINT coordinates (mm), plus the footprint pad extents.

Usage: python3 -I scripts/stepbox.py <model.step|stp> [<footprint.kicad_mod>]
Checks a STEP is the right package without 3D tools. Exit 0 printed, 2 usage or unknown length unit (Stop).
Read the result against the DS package drawing, and say which dimension matched:
- One solid (most Ultra Librarian/SnapEDA/KiCad models): the box is body + leads, so X/Y match the overall lead span
  (E, D) and Z (or Y) the max height A.
- Assembly (TI models: body and instanced leads): NO assembly transforms are applied, so the box is usually the body only
  (D1/E1 x A minus standoff); lead span, pitch and seating are NOT verified.
- The height axis is the one matching DS A max; Y-up models are common. Round bodies (cans, domes) have only seam
  vertices, so their box is a lower bound.
- Pin-1 orientation is never verified here: confirm it once in the KiCad 3D viewer (open item until done).
"""
import re
import sys

if len(sys.argv) < 2:
    print(__doc__)
    sys.exit(2)
NUM = r"[-+\d.eE]+"
t = open(sys.argv[1], errors="ignore").read().replace("\n", "")
pts = {m.group(1): tuple(float(v) for v in m.group(2).split(","))
       for m in re.finditer(r"#(\d+)\s*=\s*CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(([^)]*)\)\s*\)", t)}
vids = [m.group(1) for m in re.finditer(r"VERTEX_POINT\s*\(\s*'[^']*'\s*,\s*#(\d+)\s*\)", t)]
v = [pts[i] for i in vids if i in pts] or list(pts.values())
if re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'INCH'", t):
    unit, k = "inch (scaled to mm)", 25.4
elif re.search(r"\.MILLI\.\s*,\s*\.METRE\.", t):
    unit, k = "mm", 1.0
elif re.search(r"SI_UNIT\s*\(\s*\$\s*,\s*\.METRE\.", t):
    unit, k = "metre (scaled to mm)", 1000.0
else:
    print("unknown length unit: Stop (CLAUDE.md step 5)")
    sys.exit(2)
v = [tuple(c * k for c in p) for p in v]
lo = [min(p[i] for p in v) for i in range(3)]
hi = [max(p[i] for p in v) for i in range(3)]
print(f"unit={unit} vertices={len(v)}")
for a, l, h in zip("XYZ", lo, hi):
    print(f"{a}: {l:+.3f} .. {h:+.3f}  size {h - l:.3f}  centre {(l + h) / 2:+.3f}")
if len(sys.argv) > 2:
    f = open(sys.argv[2]).read()
    pad_re = rf"\(pad \"[^\"]*\" \w+ \w+\s*\(at ({NUM}) ({NUM})(?: ({NUM}))?\)\s*\(size ({NUM}) ({NUM})\)"
    ext = []
    for m in re.finditer(pad_re, f):
        x, y, w, h = float(m.group(1)), float(m.group(2)), float(m.group(4)), float(m.group(5))
        if m.group(3) and round(float(m.group(3))) % 180 == 90:
            w, h = h, w
        ext.append((x - w / 2, x + w / 2, y - h / 2, y + h / 2))
    print(f"pads parsed: {len(ext)} of {f.count('(pad ')}")
    if ext:
        print(f"pad extents X {min(e[0] for e in ext):+.3f}..{max(e[1] for e in ext):+.3f}  "
              f"Y {min(e[2] for e in ext):+.3f}..{max(e[3] for e in ext):+.3f}")
