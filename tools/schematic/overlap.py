#!/usr/bin/env python3
"""Text-overlap and dangling-connection checks for KiCad 10 schematics (.kicad_sch). Plain stdlib.

    python3 tools/schematic/overlap.py [--overlap] [--dangling] sheet.kicad_sch [more.kicad_sch ...]

Exit 0 when nothing is found, 1 when any finding is printed, 2 on a usage or parse error. With neither flag both
checks run. One line per finding: `file | check | kind | x y | detail`.

overlap: the estimated bounding box of every visible text (local, global and hierarchical labels, sheet pins,
shown symbol fields, sheet name/file fields, text notes) is tested against every wire, every symbol pin line, every
symbol body box (union of the unit's graphics) and every other text box. Boxes are shrunk by 0.1 mm. Not checked:
pin number/name text, rectangle (group box) edges, junction dots. Text size is an estimate calibrated against
KiCad 10 renders (per-character advances from a measured table, 1.2 x font size per line, 1.6 x font size line pitch,
hierarchical-label flag 2 x font size); a hit within about 0.3 mm of the limit may be a false positive.

dangling: every wire end, library pin end (hidden pins and `no_connect` pin types excepted), label anchor,
hierarchical label anchor and sheet pin must meet another connecting item: a wire end or the inside of a wire, a
pin, a label, a sheet pin, a junction or a no-connect marker. Agrees with KiCad ERC `wire_dangling`,
`pin_not_connected` and `label_dangling` on the INA229 reference sheets.
"""
import math
import sys

import place
from kicad_sexpr import Node

SHRINK = 0.1
# Advance per character in units of font size, measured on KiCad 10 renders of the default stroke font (10 repeats of
# each glyph at 600 dpi). Caps and digits are exact; lowercase is a rounded estimate (about 0.87 typical).
_W = {"I": 0.44, "J": 0.73, "T": 0.75, "M": 1.12, "W": 1.13, "i": 0.45, "j": 0.46, "l": 0.45, "t": 0.56, "m": 1.3,
      "w": 1.1, ".": 0.44, ",": 0.45, ":": 0.44, ";": 0.45, "_": 0.77, "-": 1.0, "+": 1.0, "/": 1.04, "(": 0.64,
      ")": 0.64, " ": 0.6, "'": 0.4, "|": 0.4, "!": 0.45}


def text_width(line, size):
    return size * sum(_W.get(c, 0.93 if c.isdigit() else 0.95 if c.isupper() else 0.87) for c in line) + 0.3


def text_box(txt, x, y, angle, justify, size, flag=0.0, gap=0.0, label=False):
    """Axis-aligned box (x1, y1, x2, y2) of a text. angle 0/180 reads left to right, 90/270 reads upward (KiCad never
    draws upside-down text); `justify` says which end of the text sits on the anchor. `flag`: extra length between
    the anchor and the text (hierarchical-label / sheet-pin flag). `gap`: clearance above (bottom) or below (top)."""
    lines = txt.split("\n")
    w = max(text_width(l, size) for l in lines)
    h = size * (1.1 if label else 1.2) + (len(lines) - 1) * size * 1.6
    j = justify.split()
    hj = "right" if "right" in j else "left" if "left" in j else "center"
    vj = "top" if "top" in j else "bottom" if "bottom" in j else "center"
    if hj == "left":
        t0, t1 = 0.0, flag + w
    elif hj == "right":
        t0, t1 = -(flag + w), 0.0
    else:
        t0, t1 = -w / 2, w / 2
    if vj == "bottom":
        u0, u1 = gap, gap + h
    elif vj == "top":
        u0, u1 = -(gap + h), -gap
    else:
        u0, u1 = -h / 2, h / 2
    if int(round(angle)) % 180 == 90:
        return (x - u1, y - t1, x - u0, y - t0)
    return (x + t0, y - u1, x + t1, y - u0)


def _eff(node):
    """(font size, justify string, hidden) from a node's (effects ...) child."""
    e = node.get("effects")
    size, just, hide = 1.27, "", node.get("hide") is not None and node.get("hide").args()[:1] == ["yes"]
    if e:
        f = e.get("font")
        if f and f.get("size"):
            size = f.get("size").nums()[0]
        j = e.get("justify")
        if j:
            just = " ".join(j.args())
        h = e.get("hide")
        if h is not None and h.args()[:1] == ["yes"]:
            hide = True
    return size, just, hide


def _at(node):
    n = node.get("at").nums()
    return n[0], n[1], (n[2] if len(n) > 2 else 0.0)


class Geometry:
    """Everything the checks need, in sheet coordinates (mm)."""

    def __init__(self, sh):
        self.sh = sh
        self.wires, self.pins, self.bodies, self.texts = [], [], [], []
        self.labels, self.junctions, self.ncs, self.sheet_pins = [], [], [], []
        root = sh.root
        for w in root.nodes("wire"):
            p = w.get("pts").nodes("xy")
            a, b = p[0].nums(), p[-1].nums()
            self.wires.append((a[0], a[1], b[0], b[1]))
        for j in root.nodes("junction"):
            self.junctions.append(tuple(j.get("at").nums()[:2]))
        for n in root.nodes("no_connect"):
            self.ncs.append(tuple(n.get("at").nums()[:2]))
        for kind in ("label", "global_label", "hierarchical_label"):
            for n in root.nodes(kind):
                x, y, a = _at(n)
                name = n.atoms()[1].value
                size, just, _ = _eff(n)
                self.labels.append((kind, name, x, y))
                if kind == "label":
                    box = text_box(name, x, y, a, just, size, 0.0, 0.55 * size, True)
                else:
                    box = text_box(name, x, y, a, just, size, 2.0 * size)
                self.texts.append((kind + " " + name, box))
        for n in root.nodes("text"):
            x, y, a = _at(n)
            size, just, _ = _eff(n)
            t = n.atoms()[1].value
            self.texts.append(("text " + repr(t[:24]), text_box(t, x, y, a, just or "left", size)))
        for s in sh.symbols():
            self._symbol(s)
        for sn in root.nodes("sheet"):
            self._sheet(sn)

    def _field(self, owner, p, rot=0):
        a = p.atoms()
        size, just, hide = _eff(p)
        val = a[2].value if len(a) > 2 else ""
        if hide or not val:
            return
        x, y, ang = _at(p)
        ang = (ang + rot) % 360  # a symbol field's stored angle is relative to the symbol's rotation
        self.texts.append(("field %s.%s" % (owner, a[1].value), text_box(val, x, y, ang, just, size)))

    def _symbol(self, s):
        sh = self.sh
        ref = s.ref
        for p in s.node.nodes("property"):
            self._field(ref, p, s.rot)
        ls = sh.lib_symbol(s.lib_id)
        pts = []
        for sub in ls.nodes("symbol"):
            import re
            m = re.match(r".*_(\d+)_(\d+)$", sub.atoms()[1].value)
            u, b = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
            if u not in (0, s.unit) or b not in (0, 1):
                continue
            for g in sub.nodes():
                h = g.head
                if h == "rectangle":
                    pts += [tuple(g.get("start").nums()[:2]), tuple(g.get("end").nums()[:2])]
                elif h in ("polyline", "bezier"):
                    pts += [tuple(q.nums()[:2]) for q in g.get("pts").nodes("xy")]
                elif h == "circle":
                    cx, cy = g.get("center").nums()[:2]
                    r = g.get("radius").nums()[0]
                    pts += [(cx - r, cy - r), (cx + r, cy + r)]
                elif h == "arc":
                    pts += [tuple(g.get(k).nums()[:2]) for k in ("start", "mid", "end")]
            for p in sub.nodes("pin"):
                at = p.get("at").nums()
                length = p.get("length").nums()[0] if p.get("length") else 0
                typ = p.atoms()[1].value if len(p.atoms()) > 1 else ""
                hid = p.get("hide") is not None and p.get("hide").args()[:1] == ["yes"] or "hide" in [
                    a.raw for a in p.atoms()]
                ex, ey = place.pin_endpoint((at[0], at[1]), s.at, s.rot, s.mirror)
                d = place.pin_direction(at[2] if len(at) > 2 else 0, s.rot, s.mirror)
                vx, vy = place._dir_vec(d)
                self.pins.append(dict(ref=ref, num=p.get("number").args()[0], type=typ, hidden=hid, x=ex, y=ey,
                                      seg=(ex, ey, ex + vx * length, ey + vy * length)))
        if pts:
            P = [place.pin_endpoint(q, s.at, s.rot, s.mirror) for q in pts]
            xs, ys = [p[0] for p in P], [p[1] for p in P]
            self.bodies.append((ref, (min(xs), min(ys), max(xs), max(ys))))

    def _sheet(self, sn):
        x, y = sn.get("at").nums()[:2]
        w, h = sn.get("size").nums()[:2]
        self.bodies.append(("sheet", (x, y, x + w, y + h)))
        for p in sn.nodes("property"):
            self._field("sheet", p)
        for p in sn.nodes("pin"):
            px, py, a = _at(p)
            size, just, _ = _eff(p)
            name = p.atoms()[1].value
            self.sheet_pins.append((name, px, py))
            self.texts.append(("sheet pin " + name, text_box(name, px, py, a, just, size, 2.0 * size)))


def _seg_hits_box(seg, box):
    """Liang-Barsky: does the segment touch the box?"""
    x1, y1, x2, y2 = seg
    t0, t1 = 0.0, 1.0
    for p, q in ((-(x2 - x1), x1 - box[0]), (x2 - x1, box[2] - x1), (-(y2 - y1), y1 - box[1]), (y2 - y1, box[3] - y1)):
        if p == 0:
            if q < 0:
                return False
        else:
            r = q / p
            if p < 0:
                t0 = max(t0, r)
            else:
                t1 = min(t1, r)
            if t0 > t1:
                return False
    return True


def _boxes_hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _shrunk(b):
    return (b[0] + SHRINK, b[1] + SHRINK, b[2] - SHRINK, b[3] - SHRINK)


def check_overlap(sh):
    """List of findings (kind, (x, y), detail): text over a wire, a pin line, a symbol body, or another text."""
    g = Geometry(sh)
    out = []
    for name, box in g.texts:
        b = _shrunk(box)
        if b[2] <= b[0] or b[3] <= b[1]:
            continue
        c = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        for w in g.wires:
            if _seg_hits_box(w, b):
                out.append(("text-wire", c, "%s crosses wire (%s,%s)-(%s,%s)" % ((name,) + tuple(map(place.fmt, w)))))
        for p in g.pins:
            if _seg_hits_box(p["seg"], b):
                out.append(("text-pin", c, "%s crosses pin %s.%s" % (name, p["ref"], p["num"])))
        for ref, bb in g.bodies:
            if name.startswith("field %s." % ref) or (ref == "sheet" and name.startswith("sheet pin")):
                if ref != "sheet":
                    pass
            if _boxes_hit(b, bb) and not (ref == "sheet" and (name.startswith("sheet pin") or name.startswith("field sheet"))):
                out.append(("text-body", c, "%s overlaps body of %s" % (name, ref)))
    for i, (n1, b1) in enumerate(g.texts):
        for n2, b2 in g.texts[i + 1:]:
            if _boxes_hit(_shrunk(b1), _shrunk(b2)):
                out.append(("text-text", ((b1[0] + b1[2]) / 2, (b1[1] + b1[3]) / 2), "%s overlaps %s" % (n1, n2)))
    return out


def _on_seg(p, w, tol=0.005):
    x, y = p
    x1, y1, x2, y2 = w
    cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
    if abs(cross) > tol * max(1.0, math.hypot(x2 - x1, y2 - y1)):
        return False
    return min(x1, x2) - tol <= x <= max(x1, x2) + tol and min(y1, y2) - tol <= y <= max(y1, y2) + tol


def _same(a, b, tol=0.005):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def check_dangling(sh):
    """List of findings (kind, (x, y), detail) for wire ends, pins, labels and sheet pins that connect to nothing."""
    g = Geometry(sh)
    others = ([("pin", (p["x"], p["y"])) for p in g.pins] + [("label", (l[2], l[3])) for l in g.labels]
              + [("sheet pin", (s[1], s[2])) for s in g.sheet_pins] + [("junction", j) for j in g.junctions]
              + [("no_connect", n) for n in g.ncs])
    out = []

    def touched(pt, skip_wire=None, skip_item=None):
        for i, w in enumerate(g.wires):
            if i != skip_wire and _on_seg(pt, w):
                return True
        for k, o in enumerate(others):
            if k != skip_item and _same(pt, o[1]):
                return True
        return False

    for i, w in enumerate(g.wires):
        for pt in ((w[0], w[1]), (w[2], w[3])):
            if not touched(pt, skip_wire=i):
                out.append(("wire-end", pt, "wire (%s,%s)-(%s,%s) end connects to nothing" % tuple(map(place.fmt, w))))
    for k, (kind, pt) in enumerate(others):
        if kind in ("junction", "no_connect"):
            continue
        if kind == "pin":
            p = g.pins[k]
            if p["hidden"] or p["type"] == "no_connect":
                continue
            what = "pin %s.%s" % (p["ref"], p["num"])
        elif kind == "label":
            what = "label %s" % g.labels[k - len(g.pins)][1]
        else:
            what = "sheet pin %s" % g.sheet_pins[k - len(g.pins) - len(g.labels)][0]
        if not touched(pt, skip_item=k):
            out.append((kind + "-unconnected", pt, "%s connects to nothing" % what))
    return out


def main(argv):
    flags = [a for a in argv if a.startswith("--")]
    files = [a for a in argv if not a.startswith("--")]
    if not files or any(f not in ("--overlap", "--dangling") for f in flags):
        sys.stderr.write(__doc__)
        return 2
    do_o = "--overlap" in flags or not flags
    do_d = "--dangling" in flags or not flags
    n = 0
    for f in files:
        try:
            sh = place.Sheet.load(f)
        except (OSError, ValueError, KeyError) as e:
            sys.stderr.write("%s: %s\n" % (f, e))
            return 2
        for chk, fn, on in (("overlap", check_overlap, do_o), ("dangling", check_dangling, do_d)):
            if on:
                for kind, (x, y), detail in fn(sh):
                    n += 1
                    print("%s | %s | %s | %s %s | %s" % (f, chk, kind, place.fmt(x), place.fmt(y), detail))
    print("%d finding(s)" % n)
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
