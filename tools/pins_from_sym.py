#!/usr/bin/env python3
"""Pin table skeleton for component.toml [[pin]] rows from a KiCad .kicad_sym.

usage: tools/pins_from_sym.py <file.kicad_sym> [--datasheet-index index.json] [--symbol NAME] [--out FILE]

Emits number, name and the vendor's electrical type in the TOML form docs/spec/extract.md wants, one status per pin.
It does NOT write `function` or `cite` (those are model work: DS function text decides the final type too).

Pin status:
  OK      number and name parse cleanly, both unique, the name has no marker/alternate/NC/pad/number-as-name
          pattern, the pin is visible and not stacked, AND (with --datasheet-index) a text line of the DS Pin Functions
          table holds both the exact name and the exact number.
  UNSURE  duplicate names (same-name pins may be separate nodes), hidden or stacked pins, alternate functions
          ("/", "," or (alternate ...)), overbar/active-low markers (~{}, leading "*", "#", "\\"), NC/EPAD names, a
          name equal to the pin number, unusual characters, an unknown pin type, a name/number pair not found in the
          DS Pin Functions table region, or no --datasheet-index at all (the vendor name is then unchecked).
  FAIL    zero pins, duplicate pin numbers, empty number or name, more than one symbol in the file (without
          --symbol), unreadable/truncated file.
Exit code 1 on any FAIL. Summary line counts OK/UNSURE/FAIL.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds_index as D  # noqa: E402

TYPES = {"input", "output", "bidirectional", "tri_state", "passive", "free", "unspecified", "power_in", "power_out",
         "open_collector", "open_emitter", "no_connect"}
NC_NAMES = re.compile(r"^(?:N\.?/?C\.?\d*|DNC|NC\d*|EP|EPAD|PAD|TAB|THERMAL(?:_?PAD)?|GND_?PAD|PGND_?PAD)$", re.I)
CLEAN_NAME = re.compile(r"^[A-Za-z0-9_+\-]+$")
CLEAN_NUM = re.compile(r"^[A-Za-z]{0,2}[0-9]{1,3}$")


def tokenize(text):
    return re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+', text)


def parse(text):
    """-> nested lists; strings unquoted. Raises ValueError on unbalanced input (truncated file)."""
    stack, cur = [], []
    for t in tokenize(text):
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            if not stack:
                raise ValueError("unbalanced ')'")
            node = cur
            cur = stack.pop()
            cur.append(node)
        elif t.startswith('"'):
            cur.append(("S", re.sub(r"\\(.)", r"\1", t[1:-1])))
        else:
            cur.append(t)
    if stack:
        raise ValueError("unbalanced '(' (truncated file?)")
    return cur


def sval(x):
    return x[1] if isinstance(x, tuple) else x


def find(node, head):
    return [c for c in node if isinstance(c, list) and c and c[0] == head]


def collect_pins(sym, unit=None, out=None):
    out = [] if out is None else out
    for c in sym:
        if isinstance(c, list) and c:
            if c[0] == "pin":
                out.append((unit or sval(sym[1]), c))
            elif c[0] == "symbol":
                collect_pins(c, sval(c[1]), out)
    return out


def read_symbol(path, symbol=None):
    """-> (symbol_name, [raw pin dicts], note) or raises ValueError."""
    if not os.path.isfile(path):
        raise ValueError("file missing: %s" % path)
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    if not text.strip():
        raise ValueError("file empty")
    root = parse(text)
    if not root or not isinstance(root[0], list) or not root[0] or root[0][0] != "kicad_symbol_lib":
        raise ValueError("not a kicad_symbol_lib file")
    syms = find(root[0], "symbol")
    if symbol:
        syms = [s for s in syms if sval(s[1]) == symbol]
    if len(syms) != 1:
        raise ValueError("expected exactly one symbol, found %d%s" % (
            len(syms), "" if symbol else " (use --symbol NAME)"))
    sym = syms[0]
    pins = []
    for unit, p in collect_pins(sym):
        typ = p[1] if len(p) > 1 else ""
        at = find(p, "at")
        name = find(p, "name")
        num = find(p, "number")
        hidden = "hide" in p or any(h[:2] == ["hide", "yes"] for h in find(p, "hide"))
        pins.append({"unit": unit, "type": typ, "at": tuple(at[0][1:3]) if at else None,
                     "name": sval(name[0][1]) if name and len(name[0]) > 1 else "",
                     "number": sval(num[0][1]) if num and len(num[0]) > 1 else "",
                     "hidden": hidden, "alt": bool(find(p, "alternate"))})
    return sval(sym[1]), pins


def natural(n):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.findall(r"\d+|\D+", n)]


NUMBERED = re.compile(r"^\d+(?:\.\d+)+\s+[A-Z][A-Za-z]")


def _boundary(line):
    """A known title, a Table/Figure caption or a numbered heading ends the pin table (all-caps text rows do not)."""
    return bool(D.classify(line["text"]) or D.caption(line) or NUMBERED.match(line["text"]))


def ds_lines(index_path, pdf_override=None):
    """-> (list of token lists, note) for the DS pin TABLE region(s) named in the index; (None, why) if unavailable.
    Region = from each pin_functions title down to the next title; when it runs to the page bottom, the top of the
    next page down to its first title. The pin diagram (same page, above the table) is deliberately excluded."""
    with open(index_path, encoding="utf-8") as f:
        idx = json.load(f)
    pdf = pdf_override or idx.get("pdf_abspath")
    if not pdf or not os.path.isfile(pdf):
        return None, "datasheet PDF not found (%s)" % pdf
    hits = [h for it in idx.get("items", []) if it["key"] == "pin_functions" for h in it["hits"]]
    if not hits:
        return None, "index has no Pin Functions table title"
    lines, used = [], []
    cache = {}

    def page(n):
        if n not in cache:
            rc, x, _ = D.run(["pdftotext", "-f", str(n), "-l", str(n), "-bbox-layout", pdf, "-"])
            cache[n] = D.parse_bbox(x)[0] if rc == 0 and "<page" in x else None
        return cache[n]

    for h in sorted(hits, key=lambda h: h["pdf_page"]):
        pg = page(h["pdf_page"])
        if pg is None:
            continue
        sel = []
        started = False
        for ln in sorted(pg["lines"], key=lambda l: (l["y0"], l["x0"])):
            if ln["y0"] < h["title_bbox"][1] - 2:
                continue
            if ln["y0"] > pg["h"] * 0.93:
                break
            if started and ln["y0"] > h["title_bbox"][3] + 2 and _boundary(ln):
                break
            started = True
            sel.append(ln)
        lines += sel
        used.append(h["pdf_page"])
        if h["end"] == "page_bottom":
            nxt = page(h["pdf_page"] + 1)
            if nxt:
                for ln in sorted(nxt["lines"], key=lambda l: (l["y0"], l["x0"])):
                    if ln["y0"] < nxt["h"] * 0.08:
                        continue
                    if ln["y0"] > nxt["h"] * 0.93 or _boundary(ln):
                        break
                    lines.append(ln)
                used.append(h["pdf_page"] + 1)
    toks = [[D.norm_dash(w[4]).strip(",;:") for w in r["words"]] for r in D.y_rows(lines)]
    return toks, "pin table regions on pdf pages %s" % ",".join(str(u) for u in sorted(set(used)))


def classify(raw, ds):
    """raw pin dicts -> pin dicts with status/reason."""
    pins = []
    nums, names, pos = {}, {}, {}
    for p in raw:
        nums[p["number"]] = nums.get(p["number"], 0) + 1
        names[p["name"]] = names.get(p["name"], 0) + 1
        pos[(p["unit"], p["at"])] = pos.get((p["unit"], p["at"]), 0) + 1
    for p in raw:
        q = dict(p)
        num, name = p["number"], p["name"]
        why = []
        st = "OK"
        if num == "" or name == "":
            st, why = "FAIL", ["empty pin number or name"]
        elif nums[num] > 1:
            st, why = "FAIL", ["duplicate pin number %s" % num]
        else:
            if names[name] > 1:
                why.append("name %s used by %d pins (separate nodes?)" % (name, names[name]))
            if p["hidden"]:
                why.append("hidden pin")
            if p["at"] is not None and pos[(p["unit"], p["at"])] > 1:
                why.append("stacked pin (same position as another pin)")
            if p["alt"] or re.search(r"[/,]", name):
                why.append("alternate function in name")
            if re.search(r"~|\\|\{|\}|^\*|^/|#$|\*$", name):
                why.append("overbar/active-low marker in name")
            if NC_NAMES.match(name):
                why.append("NC/exposed-pad name: DS wording needed")
            if name == num:
                why.append("name is just the pin number")
            if not re.search(r"[~\\{}*/#,]", name) and not CLEAN_NAME.match(name) and not NC_NAMES.match(name):
                why.append("unusual characters in name")
            if not CLEAN_NUM.match(num):
                why.append("unusual pin number")
            if p["type"] not in TYPES:
                why.append("unknown pin type %r" % p["type"])
            if not why:
                if ds is None:
                    why.append("name not checked against the DS (no usable --datasheet-index)")
                else:
                    lines, _ = ds
                    if not any(name in toks and num in toks for toks in lines):
                        why.append("no DS pin-table line holds both name %s and number %s" % (name, num))
            st = "UNSURE" if why else "OK"
            if not why:
                why = ["parsed cleanly, unique, and matched on a DS pin-table line"]
        q["status"], q["reason"] = st, "; ".join(why)
        pins.append(q)
    pins.sort(key=lambda p: (natural(p["number"]), p["name"]))
    return pins


def tq(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def run(path, index=None, symbol=None, pdf=None):
    """-> (pins, header lines, fatal reason or None)"""
    head = ["# pins_from_sym: skeleton of [[pin]] rows. `function` and `cite` are NOT generated (model work from the",
            "# datasheet pin table); `type` is the vendor symbol's, the DS function text decides the final type.",
            "# source: %s" % os.path.basename(path)]
    try:
        sname, raw = read_symbol(path, symbol)
    except (ValueError, OSError) as e:
        return [], head, str(e)
    head.append("# symbol: %s" % sname)
    ds = None
    if index:
        try:
            ds = ds_lines(index, pdf)
        except (OSError, ValueError) as e:
            ds = (None, "bad index: %s" % e)
        head.append("# datasheet check: %s" % ds[1])
        ds = ds if ds[0] else None
    else:
        head.append("# datasheet check: none (no --datasheet-index); vendor names unchecked, no pin can be OK")
    if not raw:
        return [], head, "symbol has zero pins"
    return classify(raw, ds), head, None


def render(pins, head, fatal):
    out = list(head)
    c = {"OK": 0, "UNSURE": 0, "FAIL": 0}
    for p in pins:
        c[p["status"]] += 1
        out += ["", "# status: %s %s" % (p["status"], p["reason"]), "[[pin]]", "number   = %s" % tq(p["number"]),
                "name     = %s" % tq(p["name"]), "type     = %s" % tq(p["type"])]
    if fatal:
        c["FAIL"] += 1
        out += ["", "# FAIL: %s" % fatal]
    out += ["", "# summary: pins=%d OK=%d UNSURE=%d FAIL=%d" % (len(pins), c["OK"], c["UNSURE"], c["FAIL"])]
    return "\n".join(out) + "\n", c


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pin table skeleton for component.toml from a KiCad symbol.")
    ap.add_argument("sym")
    ap.add_argument("--datasheet-index", help="index.json from tools/ds_index.py (enables the DS name/number check)")
    ap.add_argument("--pdf", help="override the datasheet PDF path stored in the index")
    ap.add_argument("--symbol", help="symbol name when the file holds several")
    ap.add_argument("--out", help="write the skeleton here instead of stdout")
    a = ap.parse_args(argv)
    pins, head, fatal = run(a.sym, a.datasheet_index, a.symbol, a.pdf)
    text, c = render(pins, head, fatal)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    if a.out:
        print(text.strip().splitlines()[-1])
    return 1 if c["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
