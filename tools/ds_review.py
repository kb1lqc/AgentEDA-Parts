#!/usr/bin/env python3
"""Datasheet review record per part: TOML lines | page crop | text-layer line, per Param. A CHECK, never a source.

Contract: docs/spec/review.md. Writes components/<Mfr>/<Value>/review/review.toml (the only committed file) and the
git-ignored local cache .review-cache/<Mfr>/<Value>/ (README.md index, DELTA.md, github-issue.md, unmapped.md,
params/<key>.md, evidence/*.png); never component data or `verified`. [[pin]] parts also get review.toml `[pinout]` (pins hash,
stamp, state) and a `[[pinout.page]]` per page the pins cite (evidence/pinout_p<n>.png) per docs/spec/review-view.md.
usage: python3 tools/ds_review.py [--all | DIR ...] [--dpi N] [--root R]
  no DIR and no --all: the component dirs changed in `git status` plus every part with no review/ (backfill).
Per Param: check status AGREE_TEXT_CHECK | DISAGREE | UNSURE | NOT_FOUND (text layer only) and ledger state
HUMAN_VERIFIED | MACHINE_CHECKED | STALE | PDF_CHANGED | NEW | UNVERIFIED | NOT_COVERED (stamp and review.toml pins).
Renders (pdftoppm -gray, 4-bit PNG) a cache image whose render key changed or that is missing; a re-render with an
unchanged key is compared with the ledger SHA. Prints one mode line: evidence mode (PDF present) or ledger-only mode (no
local PDF: hashes and states only; render = "NOT_RENDERED" when a render is pending). Same inputs, same bytes.
Exit 0: records written (findings live in them). 1: bad input or missing tool; one FAIL line names the fix.
"""
import argparse
import concurrent.futures
import difflib
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import zlib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ds_index as D  # noqa: E402
from lib.review_status import matters  # noqa: E402
import table_xcheck as T  # noqa: E402
from lib.component import LEDGER_STATES as STATES, ledger_state_of, override_rows, pinout_hash  # noqa: E402  (one state rule, shared with lib.check)

TOOL_VERSION = "11"
DEFAULT_DPI, SMALL_DPI, SMALL_PT = 150, 200, 7.0
BUDGET = 80_000  # bytes per image; over budget is listed, never a FAIL
PAD = 6.0  # points around a crop
STATUSES = ("AGREE_TEXT_CHECK", "DISAGREE", "UNSURE", "NOT_FOUND")
CACHE = ".review-cache"  # git-ignored local evidence: <CACHE>/<Mfr>/<Value>/evidence/*.png, params/<key>.md
ISSUE_STATUSES = ("DISAGREE", "UNSURE", "NOT_FOUND")
CITE_RE = re.compile(r"^DS (PDF )?p\.(\d+)(?:-(\d+))?(?: \(([^)]+)\))?,")
PARAM_HDR = re.compile(r"^\[param\.([A-Za-z0-9_\-]+)\]\s*(?:#.*)?$")
TABLE_HDR = re.compile(r"^\s*\[")
SUP = "¹²³⁰⁴-⁹⁾"
MARKER = re.compile(r"\(\d+\)|\d\)$|[%s]" % SUP)  # (1), Max(1), time1), superscripts
FOOT = re.compile(r"^(?:\(\d+\)|\d+\)|\d+\.|[%s]+)$|^\(\d+\)\S" % SUP)  # first word of a footnote line
FIX = {"poppler": "install poppler (macOS: brew install poppler; Debian/Ubuntu: apt install poppler-utils)"}


class InputError(Exception):
    """Bad input or a missing tool: the run stops with one FAIL line naming the fix."""


# ---------------------------------------------------------------- helpers

def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    return sha256_bytes(Path(p).read_bytes())


def row_hash(table):
    t = {k: v for k, v in table.items() if k != "verified"}
    return sha256_bytes(json.dumps(t, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True)
    except OSError as e:
        return 127, "", str(e)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def poppler_version():
    rc, out, err = run(["pdftoppm", "-v"])
    m = re.search(r"version\s+([\d.]+)", out + err)
    if rc == 127 or not m:
        raise InputError("poppler not found (pdftoppm): " + FIX["poppler"])
    for tool in ("pdftotext", "pdfinfo"):
        if run([tool, "-v"])[0] == 127:
            raise InputError("poppler not found (%s): %s" % (tool, FIX["poppler"]))
    return m.group(1)


def write_if_changed(path, data):
    """Write bytes or text only when they differ. Returns True when the file changed."""
    path = Path(path)
    b = data.encode() if isinstance(data, str) else data
    if path.is_file() and path.read_bytes() == b:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b)
    return True


def param_spans(text):
    """{key: (first line, last line)} 1-based, inclusive, of each [param.<key>] table in component.toml source."""
    lines = text.split("\n")
    heads = [(i, PARAM_HDR.match(ln)) for i, ln in enumerate(lines) if TABLE_HDR.match(ln)]
    spans = {}
    for n, (i, m) in enumerate(heads):
        if not m:
            continue
        end = heads[n + 1][0] - 1 if n + 1 < len(heads) else len(lines) - 1
        while end > i and (not lines[end].strip() or lines[end].lstrip().startswith("#")):
            end -= 1
        spans[m.group(1)] = (i + 1, end + 1)
    return spans


OVERRIDE_HDR = re.compile(r'^\[variant\.(?:"([^"]+)"|([A-Za-z0-9_\-]+))\.param\.([A-Za-z0-9_\-]+)\]\s*(?:#.*)?$')


def override_spans(text):
    """{"variant.<V>.<key>": (first line, last line)} of each [variant."V".param.K] table in variants.toml source."""
    lines = text.split("\n")
    heads = [(i, OVERRIDE_HDR.match(ln)) for i, ln in enumerate(lines) if TABLE_HDR.match(ln)]
    spans = {}
    for n, (i, m) in enumerate(heads):
        if not m:
            continue
        end = heads[n + 1][0] - 1 if n + 1 < len(heads) else len(lines) - 1
        while end > i and (not lines[end].strip() or lines[end].lstrip().startswith("#")):
            end -= 1
        spans["variant.%s.%s" % (m.group(1) or m.group(2), m.group(3))] = (i + 1, end + 1)
    return spans


def snippet(text, span):
    lines = text.split("\n")
    return "\n".join(lines[span[0] - 1:span[1]])


def parse_cite(cite):
    m = CITE_RE.match(cite or "")
    if not m:
        return None
    return {"kind": "pdf" if m.group(1) else "printed", "page": int(m.group(2)),
            "page_end": int(m.group(3)) if m.group(3) else None, "sheet": m.group(4)}


def safe(key):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", key)


def fmtv(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        return repr(v)
    return str(v)


def md_cell(x):
    return str(x).replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------- TOML out (deterministic)

def tq(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(tq(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join("%s = %s" % (tk(k), tq(v[k])) for k in sorted(v)) + " }"
    return json.dumps(str(v), ensure_ascii=True)


def tk(k):
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k, ensure_ascii=True)


ROW_FIELDS = ("state", "status", "reason", "hash", "stamp", "stamp_hash", "pdf_sha256", "baseline", "sheet",
              "printed_page", "pdf_page", "toml_lines", "image", "image_sha256", "image_bytes", "crop", "crop_box", "dpi",
              "render_key", "header_image", "header_sha256", "header_box", "header_key", "foot_image", "foot_sha256", "foot_box",
              "foot_key", "text_snippet", "text_cells", "stamped_toml")
KEPT = ("status", "reason", "sheet", "printed_page", "pdf_page", "crop", "crop_box", "dpi", "text_snippet",
        "text_cells", "image", "image_sha256", "image_bytes", "render_key", "header_image", "header_sha256", "header_box",
        "foot_image", "foot_sha256", "foot_box", "header_key", "foot_key")  # what a run without the PDF keeps from the last one
PIN_FIELDS = ("state", "hash", "stamp", "stamp_hash", "pdf_sha256")  # [pinout] (docs/spec/review-view.md "Pinout stamp")
PAGE_FIELDS = ("sheet", "pdf_page", "image", "image_sha256", "image_bytes", "dpi", "render_key")  # one [[pinout.page]]
INPUT_FIELDS = ("tool", "poppler", "python", "dpi", "datasheet_url", "datasheet_file", "datasheet_rev", "pdf_sha256",
                "pages", "text_layer", "component_sha256", "render", "backfill", "sheets")


def ledger_text(inputs, rows, pinout=None):
    out = ["# GENERATED by tools/ds_review.py (docs/spec/review.md). Do not edit; stamps live in component.toml.", "",
           "[inputs]"]
    out += ["%s = %s" % (k, tq(inputs[k])) for k in INPUT_FIELDS if k in inputs]
    if pinout:
        out += ["", "[pinout]"] + ["%s = %s" % (f, tq(pinout[f])) for f in PIN_FIELDS if pinout.get(f) not in (None, "")]
        for pg in pinout.get("page", []):
            out += ["", "[[pinout.page]]"] + ["%s = %s" % (f, tq(pg[f])) for f in PAGE_FIELDS if pg.get(f) not in (None, "")]
    for key in rows:
        out += ["", "[row.%s]" % tk(key)]
        out += ["%s = %s" % (f, tq(rows[key][f])) for f in ROW_FIELDS if rows[key].get(f) not in (None, "")]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- PDF documents

class Doc:
    """One local PDF: text layer (bbox words), printed-page map, rotation; lazily: headers, lines, layout, index."""

    def __init__(self, path, label):
        self.path, self.label, self.name = Path(path), label, Path(path).name
        self.missing = not self.path.is_file()
        self._lay, self._yl, self._hd, self._index = {}, {}, {}, None
        if self.missing:
            return
        err = D.check_file(str(self.path))
        if err:
            raise InputError("%s: %s; replace it with a complete copy of the datasheet" % (label, err))
        self.sha = sha256_file(self.path)
        rc, info, se = run(["pdfinfo", str(self.path)])
        m = re.search(r"^Pages:\s+(\d+)", info, re.M)
        if rc != 0 or not m:
            raise InputError("%s: poppler cannot open it (%s); supply an unencrypted, undamaged copy"
                             % (label, (se.strip().splitlines() or ["encrypted or damaged"])[-1][:100]))
        self.count = int(m.group(1))
        rc, xhtml, se = run(["pdftotext", "-bbox-layout", str(self.path), "-"])
        if rc != 0 or "<page" not in xhtml:
            raise InputError("%s: pdftotext failed (%s); supply an undamaged copy" % (label, se.strip()[:100]))
        self.pages = D.parse_bbox(xhtml)
        if len(self.pages) != self.count:
            raise InputError("%s: page count mismatch (truncated?); supply a complete copy" % label)
        nwords = sum(len(ln["words"]) for p in self.pages for ln in p["lines"])
        textpages = sum(1 for p in self.pages if sum(len(ln["words"]) for ln in p["lines"]) >= 5)
        self.text_layer = nwords >= 50 and textpages * 2 >= len(self.pages)
        self.printed, self.offset = D.printed_pages(self.pages) if self.text_layer else ({}, None)
        self.inv = {}
        for pdfp, pr in self.printed.items():
            self.inv.setdefault(pr, []).append(pdfp)
        self.rot = D.page_rotations(str(self.path), self.count)

    def heads(self, pn):
        if pn not in self._hd:
            self._hd[pn] = T.find_headers(self.pages[pn - 1])
        return self._hd[pn]

    def ylines(self, pn):
        if pn not in self._yl:
            self._yl[pn] = T.y_lines(self.pages[pn - 1])
        return self._yl[pn]

    def layout(self, pn):
        if pn not in self._lay:
            rc, out, _ = run(["pdftotext", "-layout", "-f", str(pn), "-l", str(pn), str(self.path), "-"])
            self._lay[pn] = out.replace("\f", "").split("\n") if rc == 0 else []
        return self._lay[pn]

    def page_gray(self, pn, dpi=100):
        """(w, h, bytes) of a gray render of page pn, read only to find ruled lines (never written or shown)."""
        if (pn, dpi) not in self._lay:
            with tempfile.TemporaryDirectory(prefix="ds_review-") as td:
                rc, _, _ = run(["pdftoppm", "-gray", "-r", str(dpi), "-f", str(pn), "-l", str(pn), "-singlefile",
                                str(self.path), os.path.join(td, "g")])
                pgm = Path(td, "g.pgm").read_bytes() if rc == 0 and Path(td, "g.pgm").is_file() else b""
            m = re.match(rb"P5\s+(?:#[^\n]*\n\s*)*(\d+)\s+(\d+)\s+255\s", pgm)
            self._lay[(pn, dpi)] = (int(m.group(1)), int(m.group(2)), pgm[m.end():]) if m else None
        return self._lay[(pn, dpi)]

    def index_hits(self, pn):
        """ds_index title hits on PDF page pn (with table_bbox), or [] when the index cannot be built."""
        if self._index is None:
            try:
                doc, _ = D.build(str(self.path), None, False, False)
                self._index = [h for it in doc.get("items", []) for h in it.get("hits", [])]
            except Exception:  # an index failure only removes the table-box fallback; the full page remains
                self._index = []
        return [h for h in self._index if h["pdf_page"] == pn]


# ---------------------------------------------------------------- one Param

def text_check(row, vendor, doc, pn):
    """table_xcheck's gating and verdict for one row on PDF page pn -> (status, reason). Mirrors T.check_rows."""
    if not any(k in row for k in ("min", "typ", "max")):
        return "UNSURE", "row has no min/typ/max number"
    why = T.row_conventions(row)
    if why:
        return "UNSURE", why
    if not vendor.startswith(T.TESTED_VENDORS):
        return "UNSURE", "vendor %r not in the text-check tested set" % vendor
    if doc.rot.get(pn, 0):
        return "UNSURE", "rotated page"
    sym = row.get("symbol", "")
    if not sym:
        return "UNSURE", "row has no symbol to locate it"
    if not doc.heads(pn):
        return "UNSURE", "no MIN/TYP/MAX header on the cited page"
    st, why = T.one_row(row, sym, doc.ylines(pn), doc.heads(pn))
    return ("AGREE_TEXT_CHECK" if st == "AGREE" else st), why


def resolve_page(c, doc):
    """-> (pdf page or None, printed page or None, problem or None, ambiguity note or None)."""
    if c["kind"] == "pdf":
        if not 1 <= c["page"] <= doc.count:
            return None, None, "PDF p.%d is out of range (%d pages)" % (c["page"], doc.count), None
        return c["page"], doc.printed.get(c["page"]), None, None
    hits = doc.inv.get(c["page"], [])
    if len(hits) == 1:
        note = ("cite spans printed pages %d-%d; showing p.%d" % (c["page"], c["page_end"], c["page"])
                if c["page_end"] else None)
        return hits[0], c["page"], None, note
    if len(hits) > 1:
        return None, None, "printed p.%d appears on %d PDF pages" % (c["page"], len(hits)), None
    cand = c["page"] - doc.offset if doc.offset is not None else None
    if cand and 1 <= cand <= doc.count and printed_on(doc, cand, c["page"]):
        # ds_index maps only numbers in its 9 %/10 % bands; this page prints the number just outside them
        note = ("cite spans printed pages %d-%d; showing p.%d" % (c["page"], c["page_end"], c["page"])
                if c["page_end"] else None)
        return cand, c["page"], None, note
    if doc.offset is None and 1 <= c["page"] <= doc.count:
        return c["page"], None, None, "no printed page numbers in the text layer; assumed PDF p.%d" % c["page"]
    return None, None, "printed p.%d not found in the PDF" % c["page"], None


def printed_on(doc, pn, number):
    """True when PDF page pn prints `number` (or `number/N`) as a word in its top or bottom 15 %."""
    pg = doc.pages[pn - 1]
    return any(re.fullmatch(r"%d(?:/\d{1,4})?" % number, w[4]) and (w[1] < pg["h"] * 0.15 or w[1] > pg["h"] * 0.85)
               for ln in pg["lines"] for w in ln["words"])


HEAD_WORD = re.compile(r"(?i)^(?:min|minimum|typ|typical|nom|nominal|max|maximum|units?|symbols?|parameters?|"
                       r"conditions|values)\.?(?:\(\d+\)|\d\))?$")
MAX_GROUP = 16  # lines in one row group; more is not a row


def has_num(ln):
    return any(T.NUM.match(T.norm_minus(w[4]).lstrip("±")) for w in ln["words"])


def region_for(doc, pn, y):
    """(top, bottom, title) of the table holding y: the nearest ds_index title above y to the next title below."""
    pg = doc.pages[pn - 1]
    hits = sorted(doc.index_hits(pn), key=lambda h: h["title_bbox"][1])
    above = [h for h in hits if h["title_bbox"][1] <= y]
    below = [h["title_bbox"][1] for h in hits if h["title_bbox"][1] > y]
    top = above[-1]["title_bbox"][1] if above else pg["h"] * 0.09
    return top, (below[0] if below else pg["h"] * 0.93), (above[-1]["title"] if above else None)


def label_words(ln):
    """Words left of the line's first plain number (the row's label cells)."""
    out = []
    for w in ln["words"]:
        if T.NUM.match(T.norm_minus(w[4]).lstrip("±")):
            break
        out.append(w)
    return out


def find_row(doc, pn, row, cite):
    """-> (line index, how) of the one table line that is this row, or (None, why). By symbol, then by the cite's
    'row <label>' words; table_xcheck's own match wins when it has one, so the image and the check agree."""
    lines, sym = doc.ylines(pn), row.get("symbol", "")
    if sym and doc.heads(pn):
        c = T.locate(sym, lines, doc.heads(pn))
        if len(c) == 1:
            return c[0][0], "symbol (table_xcheck match)"
    want = re.sub(r"\s+", "", T.norm_minus(sym))
    by_sym = [i for i, ln in enumerate(lines) if want and
              any(T.sym_at(label_words(ln), k) == want for k in range(len(label_words(ln))))]
    if len(by_sym) == 1:
        return by_sym[0], "symbol"
    m = re.search(r"\brow\s+([^,]+)", cite or "")
    toks = [t for t in re.findall(r"[A-Za-z0-9][\w.+/-]*", m.group(1)) if re.search(r"[A-Z0-9]", t)] if m else []
    pool = by_sym or range(len(lines))
    top = [i for i in pool if toks and all(t in {w[4] for w in lines[i]["words"]} for t in toks)]  # every word
    best = len(top)
    if len(top) == 1:
        return top[0], "cite row label (%s)" % " ".join(toks)
    if len(by_sym) > 1:
        return None, "symbol %r on %d lines and the cite's row label does not pick one" % (sym, len(by_sym))
    return None, ("symbol %r not found as a table row" % sym if sym else "row has no symbol") + (
        "; cite row label matches %d lines" % len(top) if best else "")


def hrules(doc, pn, x, y0, y1, dpi=100):
    """y (pt) of horizontal rules crossing the strip x-2..x+12 pt (the table's first column) between y0 and y1."""
    g = doc.page_gray(pn, dpi)
    if not g:
        return []
    w, h, px = g
    s = dpi / 72.0
    xa, xb = max(0, int((x - 2) * s)), min(w, int((x + 12) * s))
    out = []
    for yy in range(max(0, int(y0 * s)), min(h, int(y1 * s) + 1)):
        row = px[yy * w + xa:yy * w + xb]
        if row and sum(1 for v in row if v < 230) >= 0.8 * len(row):  # ST draws light gray rules (193)
            if not out or yy - out[-1][1] > 1:
                out.append([yy, yy])
            else:
                out[-1][1] = yy
    return [round((a + b) / 2 / s, 1) for a, b in out]


def values_missing(row, lns):
    """Committed min/typ/max numbers that no word of the given lines prints (signs and +/- kept as printed)."""
    printed = set()
    for ln in lns:
        for w in ln["words"]:
            t = T.norm_minus(w[4]).lstrip("\u00b1")
            if T.NUM.match(t):
                printed.add(float(t))
    # magnitudes: a printed +/-X is stored min = -X, a printed MAX -2 / MIN -6 is swapped; a *_ref row prints a pin name
    miss = [f for f in ("min", "typ", "max") if isinstance(row.get(f), (int, float)) and f + "_ref" not in row
            and not any(abs(abs(v) - abs(row[f])) <= 1e-9 * max(1.0, abs(v)) for v in printed)]
    return ", ".join(miss)


def table_model(doc, pn, i):
    """Header band, row group, footnotes and the shared width/dpi of the table holding line i -> dict or (None, why)."""
    lines, pg = doc.ylines(pn), doc.pages[pn - 1]
    ln = lines[i]
    top, bot, title = region_for(doc, pn, ln["y0"])
    reg = [j for j, l2 in enumerate(lines) if top - 0.5 <= l2["y0"] < bot]
    if i not in reg:
        return None, "row is outside its table region"
    lab = label_words(ln) or ln["words"][:1]
    left = min(lines[j]["words"][0][0] for j in reg)
    starts = {round(lab[0][0]), round(left)} | ({round(lab[1][0])} if len(lab) > 1 and lab[1][0] > lab[0][0] + 15 else set())

    def row_start(j):
        return any(abs(lines[j]["words"][0][0] - x) <= 6 for x in starts) and any(
            re.search(r"\d", w[4]) for w in lines[j]["words"])
    kw = [j for j in reg if j < i and any(HEAD_WORD.match(w[4]) for w in lines[j]["words"])]
    body = kw[-1] + 1 if kw else reg[0]  # the first line below the column headings
    sym_x = {round(lab[0][0]), round(left)}  # a line starting here is a row or a section label (INPUT)
    at_label = lambda j: any(abs(lines[j]["words"][0][0] - x) <= 6 for x in sym_x) or row_start(j)
    pitch = lambda j: 1.8 * max(1.0, lines[j]["y1"] - lines[j]["y0"])
    near = lambda j, k: lines[k]["y0"] - lines[j]["y1"] < pitch(j)  # j directly above k
    # Top-aligned tables (label on the row's first line): the label line and the lines below it up to the next label.
    # Centred tables (TI: the symbol sits mid-cell, so data begins with unlabelled sub-lines): every sub-line belongs to
    # the nearest labelled row line; a section label (INPUT, no digits) is a boundary that claims no lines.
    rows_j = [j for j in reg if j >= body and row_start(j)] + ([i] if not row_start(i) else [])
    walls = [j for j in reg if j >= body and at_label(j) and j not in rows_j]
    after = [j for j in reg if j >= body and j not in walls]  # section labels say nothing about the layout
    centred = bool(after) and not at_label(after[0])
    g0 = g1 = i
    cell = None
    rl = hrules(doc, pn, left, top, bot)  # from the table top: the rule under the header bounds the first row
    above = [y for y in rl if y < ln["ymid"]]
    below = [y for y in rl if y > ln["ymid"]]
    if above and below:  # ruled table: the row is exactly the cell between the rules around its label line
        group = [j for j in reg if above[-1] < lines[j]["ymid"] < below[0]]
        g0, g1 = group[0], group[-1]
        cell = (above[-1] - 1.0, below[0] + 1.0)
    elif centred:
        def owner(j):
            lo = max([k for k in walls + rows_j if k < j], default=None)
            hi = min([k for k in walls + rows_j if k > j], default=None)
            cands = [k for k in (lo, hi) if k is not None and k in rows_j]
            return min(cands, key=lambda k: (abs(lines[k]["ymid"] - lines[j]["ymid"]), -k)) if cands else None
        while g0 - 1 >= body and not at_label(g0 - 1) and near(g0 - 1, g0) and owner(g0 - 1) == i:
            g0 -= 1
        while g1 + 1 in reg and not at_label(g1 + 1) and near(g1, g1 + 1) and owner(g1 + 1) == i:
            g1 += 1
    else:
        while g1 + 1 in reg and not at_label(g1 + 1) and near(g1, g1 + 1):
            g1 += 1
    vals = [w[0] for j in kw for w in lines[j]["words"] if re.match(r"(?i)^(?:min|typ|nom|max)", w[4])]
    valx = min(vals) - 2 if vals else None  # data starts left of the value columns; headings (TJ = 25 degC) inside
    first = next((j for j in reg if body <= j < g0 and (row_start(j) or valx is not None and lines[j]["words"][0][0] < valx
                  and any(re.search(r"\d", w[4]) for w in lines[j]["words"]))), g0)
    head = [j for j in reg if j < first]
    if first - body > (3 if kw else 6):
        return None, "header band not found (more than %d lines before the first data row)" % (3 if kw else 6)
    if g1 - g0 + 1 > MAX_GROUP:
        return None, "row group longer than %d lines" % MAX_GROUP
    group = list(range(g0, g1 + 1))
    foot, fnote = [], "no footnote marker on the row or header"
    if any(MARKER.search(w[4]) for j in group + head for w in lines[j]["words"]):
        fs = [j for j in range(g1 + 1, len(lines)) if FOOT.match(lines[j]["words"][0][4]) and lines[j]["y0"] < pg["h"] * 0.93]
        if fs:
            foot = [fs[0]]
            for j in range(fs[0] + 1, len(lines)):
                if lines[j]["y0"] - lines[foot[-1]]["y1"] > pitch(foot[-1]) or lines[j]["y0"] >= pg["h"] * 0.93:
                    break
                foot.append(j)
            fnote = "footnotes shown"
        else:
            fnote = "a footnote marker is present; its note is not on this page"
    ws = [w for j in reg for w in lines[j]["words"]]  # the table alone sets width and dpi (shared images agree)
    x0, x1 = max(0.0, min(w[0] for w in ws) - PAD), min(pg["w"], max(w[2] for w in ws) + PAD)
    hs = [w[3] - w[1] for w in ws if re.search(r"[A-Za-z0-9]", w[4])]

    def box(js):
        a, b = js[0], js[-1]
        y0 = (lines[a - 1]["y1"] + lines[a]["y0"]) / 2 if a > 0 else lines[a]["y0"] - PAD
        y1 = (lines[b]["y1"] + lines[b + 1]["y0"]) / 2 if b + 1 < len(lines) else lines[b]["y1"] + PAD
        y0, y1 = max(y0, lines[a]["y0"] - PAD), min(y1, lines[b]["y1"] + PAD)
        return [round(x0, 1), round(max(0.0, y0), 1), round(x1, 1), round(min(pg["h"], y1), 1)]
    return {"title": title, "head": head, "group": group, "foot": foot, "fnote": fnote,
            "head_box": box(head) if head else None,
            "row_box": ([round(x0, 1), round(cell[0], 1), round(x1, 1), round(cell[1], 1)] if cell else box(group)), "foot_box": box(foot) if foot else None,
            "small": min(hs) if hs else None}, None


def small_glyph(doc, pn, box):
    """Smallest word glyph height (pt) inside a box, or None."""
    hs = [w[3] - w[1] for ln in doc.pages[pn - 1]["lines"] for w in ln["words"]
          if re.search(r"[A-Za-z0-9]", w[4]) and (box is None or (w[1] >= box[1] and w[3] <= box[3]))]
    return min(hs) if hs else None


def table_box(doc, pn, cite):
    """ds_index box of the cited table on the page (exactly one title match in the cite), or None."""
    want = re.sub(r"\s+", " ", (cite or "").lower())
    m = [h for h in doc.index_hits(pn) if re.sub(r"\s+", " ", h["title"].lower()) in want]
    if len(m) != 1:
        return None, None
    return [round(v, 1) for v in m[0]["table_bbox"]], m[0]["title"]


def layout_lines(doc, pn, lns):
    """`pdftotext -layout` lines of page pn whose tokens contain each given y-line's tokens in order."""
    lay = doc.layout(pn)
    out = []
    for ln in lns:
        want = [w[4] for w in ln["words"] if re.search(r"[A-Za-z0-9]", w[4])]  # bullets and glyphs may differ
        hit = None
        for span in (1, 2, 3):  # -layout may put a row's label on the line above its values
            for i in range(len(lay) - span + 1):
                flat, pos = re.sub(r"\s+", "", "".join(lay[i:i + span])), 0
                for w in want:  # every word, in order, without spaces (split subscripts: V + UV(HYST))
                    pos = flat.find(re.sub(r"\s+", "", w), pos)
                    if pos < 0:
                        break
                    pos += len(w)
                else:
                    hit = "\n".join(s.rstrip() for s in lay[i:i + span]) if want else None
                    break
            if hit:
                break
        if hit and hit not in out:
            out.append(hit)
        elif not hit:
            out.append("(row line not matched in the -layout text)" if ln is lns[-1] else "(header line not matched)")
    return out


def examine(key, row, ctx):
    """-> dict: status, reason, sheet, doc, pdf_page, printed_page, crop, crop_box, dpi, text_snippet, cells."""
    r = {"status": "NOT_FOUND", "reason": "", "sheet": "", "doc": None, "pdf_page": None, "printed_page": None,
         "crop": "", "crop_box": None, "dpi": None, "text_snippet": "", "cells": None, "header_box": None,
         "foot_box": None}
    c = parse_cite(row.get("cite"))
    if c is None:
        r["reason"] = "cite missing or unparseable (want 'DS p.<n>, ...' or 'DS PDF p.<n>, ...')"
        return r
    doc = ctx["main"]
    if c["sheet"] and c["sheet"] != ctx["main"].name:
        r["sheet"] = c["sheet"]
        doc = ctx["sheet"](c["sheet"])
    r["doc"] = doc
    if doc.missing:
        r["reason"] = "PDF not on this machine (%s); not rendered" % doc.label
        return r
    pn, printed, problem, note = resolve_page(c, doc)
    if problem:
        r["reason"] = problem
        return r
    r["pdf_page"], r["printed_page"] = pn, printed
    why_fb = []
    if note:
        why_fb.append(note)
    if not doc.text_layer:
        why_fb.append("no text layer (scanned PDF?)")
    if doc.rot.get(pn, 0):
        why_fb.append("rotated page")
    status, reason = ("UNSURE", "no text layer") if not doc.text_layer else text_check(row, ctx["vendor"], doc, pn)
    model = None
    if not why_fb:
        i, how = find_row(doc, pn, row, row.get("cite"))
        if i is None:
            why_fb.append(how)
        else:
            model, why = table_model(doc, pn, i)
            lines = doc.ylines(pn)
            h = T.head_for(doc.heads(pn), lines[i]["ymid"]) if doc.heads(pn) else None
            if why:
                why_fb.append(why)
            else:
                # a line the text check did not validate must show the committed numbers (AGREE and DISAGREE lines
                # were validated: one clean line, same unit)
                missing = "" if status in ("AGREE_TEXT_CHECK", "DISAGREE") else values_missing(
                    row, [lines[j] for j in model["group"]])
                if missing:
                    why_fb.append("committed %s not printed in the matched row group (wrong row?)" % missing)
                elif h and not any(T.split_line(lines[j], h)[2] for j in model["group"]):
                    why_fb.append("no unit cell in the row group (merged with other rows)")
            if why_fb:
                model = None
    if model:
        lines = doc.ylines(pn)
        r.update(crop="auto", crop_box=model["row_box"], header_box=model["head_box"], foot_box=model["foot_box"])
        n = len(model["group"])
        r["status"], r["reason"] = status, "%s; row found by %s%s; %s" % (
            reason, how, ", row group of %d lines" % n if n > 1 else "", model["fnote"])
        hdr = [lines[j] for j in model["head"] if lines[j]["y0"] >= region_for(doc, pn, lines[i]["y0"])[0] + 0.5]
        r["text_snippet"] = "\n".join(layout_lines(doc, pn, hdr[-3:] + [lines[j] for j in model["group"]]))
        if h and n == 1:
            lab, cells, unit, _bad = T.split_line(lines[i], h)
            r["cells"] = {k: " ".join(w[4] for w in v) for k, v in cells.items()}
            r["cells"]["unit"] = " ".join(w[4] for w in unit[:1])
        g = model["small"]
        r["dpi"] = max(ctx["dpi"], SMALL_DPI) if g is not None and g < SMALL_PT else ctx["dpi"]
        return r
    else:
        box, title = (None, None) if not doc.text_layer else table_box(doc, pn, row.get("cite"))
        r["crop_box"] = box or "full_page"
        r["crop"] = "fallback"
        shown = ("table '%s'" % title) if box else "full page"
        r["status"] = "UNSURE"
        r["reason"] = "fallback (%s): %s; text check: %s %s" % (shown, "; ".join(why_fb), status, reason)
        if doc.text_layer and row.get("symbol"):
            sym = row["symbol"]
            hits = [s.rstrip() for s in doc.layout(pn) if sym in s.split()][:5]
            r["text_snippet"] = "\n".join(hits)
        r["text_snippet"] = r["text_snippet"] or "(no text-layer line located)"
    g = small_glyph(doc, pn, None if r["crop_box"] == "full_page" else r["crop_box"])
    r["dpi"] = max(ctx["dpi"], SMALL_DPI) if g is not None and g < SMALL_PT else ctx["dpi"]
    return r


# ---------------------------------------------------------------- locate (display only)

LOCATE_MAX = 5  # boxes per row
NUMBER_RE = re.compile(r"(?<![\w.])([±+-]?)(\d+\.?\d*|\.\d+)")  # "0.9-1.4": 0.9 and 1.4, not -1.4


def printed_numbers(ln):
    """[(value, printed with +/-)] of every number the words of one y-line print (footnote markers dropped)."""
    out = []
    for w in ln["words"]:
        for m in NUMBER_RE.finditer(MARKER.sub("", T.norm_minus(w[4]))):
            v = float(m.group(2))
            out.append((-v if m.group(1) == "-" else v, m.group(1) == "±"))
    return out


def line_holds(ln, want, sym):
    """True when the y-line prints every number in `want` (compared by value: 0.90 = 0.9; a +/- printed or `sym` row
    also matches the unsigned magnitude)."""
    nums = printed_numbers(ln)
    return all(any(abs(v - x) <= 1e-9 * max(1.0, abs(x)) or ((sym or pm) and abs(abs(v) - abs(x)) <= 1e-9 * max(1.0, abs(x)))
                   for v, pm in nums) for x in want)


def printed_in_order(ln, want, sym):
    """True when the line prints `want` adjacent and in order: consecutive numbers with nothing numeric between (a +/-
    printed or `sym` number covers a -x, +x pair, so "±100" is "-100 to 100")."""
    nums = printed_numbers(ln)

    def same(v, x, loose):
        return abs(v - x) <= 1e-9 * max(1.0, abs(x)) or (loose and abs(abs(v) - abs(x)) <= 1e-9 * max(1.0, abs(x)))
    for start in range(len(nums)):
        i, ok = start - 1, True
        for x in want:
            if i >= start and (sym or nums[i][1]) and same(nums[i][0], x, True):
                continue  # the same ± number covers this one too
            if i + 1 < len(nums) and same(nums[i + 1][0], x, sym or nums[i + 1][1]):
                i += 1
            else:
                ok = False
                break
        if ok:
            return True
    return False


def row_label_words(cite):
    """Lower-case words of the cite's 'row <label>' (else its third comma part) for the symbol fallback."""
    m = re.search(r"\brow\s+([^,]+)", cite or "")
    if m:
        label = m.group(1)
    else:
        parts = (cite or "").split(",")
        label = parts[-1] if len(parts) > 2 else ""
    return {t.lower() for t in re.findall(r"[A-Za-z0-9][\w.+/-]*", label)}


def locate_boxes(row, doc, pn):
    """-> (how, boxes): boxes are {"box": [x0, y0, x1, y1] in percent of the page, "text": line text}, at most LOCATE_MAX.
    how: "numbers" (lines printing every min/typ/max of the row; only those printing them adjacent and in order when
    there are any), "symbol" (lines with the symbol and a word of the
    cite's row label) or "none". Text layer of the cited page only; a rotated page or one without text: none."""
    if not doc.text_layer or doc.rot.get(pn, 0):
        return "none", []
    pg, lines = doc.pages[pn - 1], doc.ylines(pn)
    want = [row[f] for f in ("min", "typ", "max") if isinstance(row.get(f), (int, float)) and not isinstance(row[f], bool)
            and f + "_ref" not in row]
    sym = re.sub(r"\s+", "", T.norm_minus(row.get("symbol", "")))
    labels = row_label_words(row.get("cite"))

    def has_symbol(ln):
        ws = [(w[0], w[1], w[2], w[3], w[4]) for w in ln["words"]]
        return bool(sym) and any(T.sym_at(ws, k) == sym for k in range(len(ws)))

    def has_label(ln):
        return bool(labels & {w[4].lower() for w in ln["words"]})
    how, hits = "none", []
    if want:
        hits = [i for i, ln in enumerate(lines) if line_holds(ln, want, bool(row.get("sym")))]
        ordered = [i for i in hits if printed_in_order(lines[i], want, bool(row.get("sym")))]
        hits = ordered or hits  # the row's numbers printed side by side beat lines that merely hold them
        if len(hits) > LOCATE_MAX:  # ambiguity: lines that also name the row first
            hits = sorted(sorted(hits, key=lambda i: not (has_symbol(lines[i]) or has_label(lines[i])))[:LOCATE_MAX])
        how = "numbers" if hits else "none"
    if not hits and sym and labels:
        hits = [i for i, ln in enumerate(lines) if has_symbol(ln) and has_label(ln)][:LOCATE_MAX]
        how = "symbol" if hits else "none"
    boxes = []
    for i in hits:
        ws = lines[i]["words"]
        boxes.append({"box": [round(100 * min(w[0] for w in ws) / pg["w"], 2), round(100 * min(w[1] for w in ws) / pg["h"], 2),
                              round(100 * max(w[2] for w in ws) / pg["w"], 2), round(100 * max(w[3] for w in ws) / pg["h"], 2)],
                      "text": " ".join(w[4] for w in ws)[:160]})
    return how, boxes


# ---------------------------------------------------------------- images

def png_bytes(w, h, rows4, meta):
    """4-bit grayscale PNG (color type 0) from packed rows; tEXt chunks in the given order; no time chunk."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows4)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 4, 0, 0, 0, 0))
    for k, v in meta:
        out += chunk(b"tEXt", k.encode("latin-1") + b"\x00" + v.encode("latin-1", "replace"))
    return out + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


HI = bytes(((v * 15 + 127) // 255) << 4 for v in range(256))
LO = bytes((v * 15 + 127) // 255 for v in range(256))


def pgm_to_png(pgm, meta):
    m = re.match(rb"P5\s+(?:#[^\n]*\n\s*)*(\d+)\s+(\d+)\s+(\d+)\s", pgm)
    if not m or m.group(3) != b"255":
        raise InputError("pdftoppm wrote an unexpected PGM header; check the poppler install")
    w, h = int(m.group(1)), int(m.group(2))
    data = pgm[m.end():m.end() + w * h]
    rows = []
    n = (w + 1) // 2
    for y in range(h):
        r = data[y * w:(y + 1) * w] + (b"\xff" if w % 2 else b"")
        a = int.from_bytes(r[0::2].translate(HI), "big") | int.from_bytes(r[1::2].translate(LO), "big")
        rows.append(a.to_bytes(n, "big"))
    return png_bytes(w, h, rows, meta)


def render(job):
    """job: (pdf, page, box or 'full_page', dpi, meta, out path) -> (out path, sha256, size)."""
    pdf, pn, box, dpi, meta, out = job
    with tempfile.TemporaryDirectory(prefix="ds_review-") as td:
        cmd = ["pdftoppm", "-gray", "-r", str(dpi), "-f", str(pn), "-l", str(pn)]
        if box != "full_page":
            s = dpi / 72.0
            cmd += ["-x", str(int(box[0] * s)), "-y", str(int(box[1] * s)),
                    "-W", str(int((box[2] - box[0]) * s) + 1), "-H", str(int((box[3] - box[1]) * s) + 1)]
        rc, _, err = run(cmd + ["-singlefile", str(pdf), os.path.join(td, "p")])
        if rc != 0 or not os.path.isfile(os.path.join(td, "p.pgm")):
            raise InputError("pdftoppm failed on %s page %d: %s" % (pdf, pn, err.strip()[:100]))
        png = pgm_to_png(Path(td, "p.pgm").read_bytes(), meta)
    return out, sha256_bytes(png), write_if_changed(out, png)


def png_info(path):
    """{'ihdr': (w, h, depth, color), 'text': {k: v}} from a PNG file (stdlib parse)."""
    b = Path(path).read_bytes()
    i, info = 8, {"text": {}}
    while i < len(b):
        n = struct.unpack(">I", b[i:i + 4])[0]
        t, d = b[i + 4:i + 8], b[i + 8:i + 8 + n]
        if t == b"IHDR":
            info["ihdr"] = struct.unpack(">IIBB", d[:10])
        elif t == b"tEXt":
            k, _, v = d.partition(b"\x00")
            info["text"][k.decode("latin-1")] = v.decode("latin-1")
        elif t == b"tIME":
            info["time"] = True
        i += 12 + n
    return info


# ---------------------------------------------------------------- git backfill

def git_blame(root, rel):
    """{line number: commit} for the working-tree file, or None when git cannot answer."""
    rc, out, _ = run(["git", "-C", str(root), "blame", "--porcelain", "--", rel])
    if rc != 0:
        return None
    res, cur = {}, None
    for ln in out.split("\n"):
        m = re.match(r"^([0-9a-f]{40}) \d+ (\d+)", ln)
        if m:
            cur = m.group(1)
            res[int(m.group(2))] = cur
    return res


def table_at(root, commit, rel, key):
    """(row hash, source snippet) of [param.<key>] at a commit, or (None, None)."""
    rc, out, _ = run(["git", "-C", str(root), "show", "%s:%s" % (commit, rel)])
    if rc != 0:
        return None, None
    try:
        t = tomllib.loads(out).get("param", {}).get(key)
    except tomllib.TOMLDecodeError:
        return None, None
    sp = param_spans(out).get(key)
    return (row_hash(t), snippet(out, sp)) if t is not None and sp else (None, None)


# ---------------------------------------------------------------- ledger states

def ledger_state(h, stamp, P, pr, backfill, pinout=False):
    """-> dict of pins and state. pr: previous ledger row or None. backfill: callable -> (stamp_hash, snippet, base)."""
    pr = pr or {}
    o = {"stamp": stamp or "", "stamp_hash": pr.get("stamp_hash", ""), "pdf_sha256": pr.get("pdf_sha256", ""),
         "baseline": pr.get("baseline", False), "stamped_toml": pr.get("stamped_toml", "")}
    if stamp and stamp != pr.get("stamp"):
        o["stamp_hash"], o["stamped_toml"], o["baseline"] = backfill()
        o["pdf_sha256"] = P or o["pdf_sha256"]
    elif not o["pdf_sha256"]:
        o["pdf_sha256"] = P or ""
    o["state"] = ledger_state_of(h, stamp, o["stamp_hash"], o["pdf_sha256"], P, pinout)
    return o


# ---------------------------------------------------------------- markdown

LEGEND = """## Legend
Check status (text layer only; never a verification): `AGREE_TEXT_CHECK` printed min/typ/max/unit equal the TOML ·
`DISAGREE` they differ (adjudicate on the image) · `UNSURE` not comparable or row not isolated · `NOT_FOUND` cite or page
not located. Ledger state: `HUMAN_VERIFIED` a `human:` stamp bound to this row and PDF · `MACHINE_CHECKED` any other
stamp (not a human check) · `STALE` row changed since its stamp · `PDF_CHANGED` PDF differs from the stamped one · `NEW`
never stamped · `UNVERIFIED` stamp removed or malformed · `NOT_COVERED` not reviewed by this tool. `AGREE_TEXT_CHECK` is not verified."""

WORKFLOW = """## Human workflow
1. `python3 tools/verify.py` renders the evidence into the git-ignored local cache (needs the PDF; never committed).
2. Open `DELTA.md` (human-stamped rows that changed), then the rows table below; per row, open `params/<key>.md` and
   compare the TOML with the image; open the page link if the crop is a fallback or looks cut off.
3. Decide: correct: `python3 tools/stamp.py <Value>:<key>` in your own shell; wrong: fix the TOML with a cite;
   unclear: leave it, log an open item.
4. `verify.py` re-pins the stamp. Audit: review.toml keeps each image's crop box, dpi, render key and SHA-256."""


def page_link(ctx, row):
    if row.get("sheet") or not ctx["url"]:
        return "no URL recorded for %s (local PDF p.%s)" % (row.get("sheet") or ctx["main_name"], row.get("pdf_page"))
    return "[%s#page=%d](%s#page=%d)" % (ctx["url"], row["pdf_page"], ctx["url"], row["pdf_page"])


def caption(ctx, row):
    sheet = row.get("sheet") or ctx["main_name"]
    rev = ctx["rev"] if not row.get("sheet") else "rev not recorded"
    pr = "p.%s" % row["printed_page"] if row.get("printed_page") else "no printed page"
    url = ctx["url"] if not row.get("sheet") and ctx["url"] else "no URL recorded"
    return "Source: %s, %s datasheet (%s) %s, %s (PDF p.%s), %s" % (ctx["mfr"], ctx["value"], sheet, rev, pr,
                                                                      row.get("pdf_page"), url)


def param_md(key, t, row, ctx, src):
    sym = t.get("symbol", "")
    out = ["# %s: %s%s" % (key, t.get("name", ""), " (%s)" % sym if sym else ""), "",
           "Local only (git-ignored cache; rebuild: `python3 tools/ds_review.py %s`)." % ctx["rel"], "",
           "Check: **%s**: %s  " % (row["status"], row["reason"]),
           "Ledger: **%s**. Stamp: %s. [Legend](%s#legend)" % (
               row["state"], "`%s`" % row["stamp"] if row.get("stamp") else "none", ctx["legend"]), "",
           "## Committed (`component.toml` lines %s)" % row["toml_lines"], "", "```toml", src, "```", "", "## Evidence", ""]
    if row.get("image"):
        out += (["![header](../%s)" % row["header_image"]] if row.get("header_image") else []) + [
            "![%s](../%s)" % (key, row["image"])] + (["![footnotes](../%s)" % row["foot_image"]] if row.get("foot_image") else []) + [
            "", "Header and footnotes: shared crops of the same table, same width and dpi as the row." if row.get("crop") == "auto"
            and row.get("header_image") else "Full table or page (fallback)." if row.get("crop") != "auto" else "", "",
                caption(ctx, row) + "  ",
                ("Crop: auto" if row.get("crop") == "auto" else "Crop: fallback: %s" % row["reason"]) + "  ",
                "Full page: " + page_link(ctx, row)]
    else:
        out += ["No image: %s" % row["reason"]]
    out += ["", "## Text layer", "", "```text", "# text layer, unverified, not a source",
            row.get("text_snippet") or "(none)", "```", "", "## Side by side (text layer is a check, not a source)", "",
            "| | min | typ | max | unit | conditions | scope |", "|---|---|---|---|---|---|---|"]
    com = [fmtv(t.get(k)) for k in ("min", "typ", "max")] + [t.get("unit", ""), t.get("conditions", ""), t.get("scope", "")]
    cells = row.get("text_cells")
    if cells:
        txt = [cells.get(k, "") for k in ("min", "typ", "max", "unit")] + ["(see image)", "(see image)"]
        match = []
        for k, cv in zip(("min", "typ", "max"), txt[:3]):
            match.append(num_match(t.get(k), cv))
        match.append("" if not t.get("unit") and not txt[3] else
                     ("yes" if T.norm_unit(t.get("unit", "")) == T.norm_unit(txt[3]) else "no"))
        match += ["not compared", "not compared"]
    else:
        txt = ["(row not isolated)"] + [""] * 5
        match = ["not compared"] * 6
    out += ["| committed | " + " | ".join(md_cell(x) for x in com) + " |",
            "| text layer | " + " | ".join(md_cell(x) for x in txt) + " |",
            "| match | " + " | ".join(match) + " |", "", "## Checklist", "",
            "- [ ] value/sign/unit - [ ] column - [ ] conditions/scope - [ ] package - [ ] footnotes - [ ] cite page", "",
            "After checking the image, in your own shell (not an agent): `python3 tools/stamp.py %s:%s`" % (ctx["dirname"], key),
            ""]
    return "\n".join(out)


def num_match(committed, printed):
    if committed is None and not printed:
        return ""
    if committed is None or not printed:
        return "no"
    try:
        return "yes" if abs(float(T.norm_minus(printed)) - float(committed)) <= 1e-9 * max(1.0, abs(float(committed))) else "no"
    except ValueError:
        return "?"


def readme_md(ctx, rows, params, over, pinout=None):
    pr = {k: r for k, r in rows.items() if k in params}
    cs = {s: sum(1 for r in pr.values() if r["status"] == s) for s in STATUSES}
    ss = {s: sum(1 for r in list(rows.values()) + ([pinout] if pinout else []) if r["state"] == s) for s in STATES}
    fb = sum(1 for r in pr.values() if r.get("crop") == "fallback")
    out = ["# Datasheet review: %s" % ctx["value"], "",
           "GENERATED by `tools/ds_review.py` v%s ([docs/spec/review.md](../../../docs/spec/review.md)); local only, "
           "not committed (the ledger is `%s/review/review.toml`)." % (TOOL_VERSION, ctx["rel"]),
           "PDF `%s` SHA-256 `%s`, %s, URL %s. Render: %s." % (
               ctx["main_name"], ctx["P"] or "unknown (PDF not on this machine)", ctx["rev"] or "rev not recorded",
               ctx["url"] or "not recorded", ctx["render"]), "",
           LEGEND, "",
           "Counts: " + ", ".join("%s %d" % kv for kv in cs.items()) + " · " + ", ".join("%s %d" % kv for kv in ss.items())
           + " · fallback images %d · over %d KB: %s" % (fb, BUDGET // 1000, ", ".join(over) or "none"), "",
           WORKFLOW, "",
           "Limits: page images are vendor excerpts (copyright %s), kept in the local cache only. Text checks never "
           "verify. Coverage is partial (NOT_COVERED rows, `unmapped.md`). Local PDF == URL document: not checked."
           % ctx["mfr"], "",
           "## Rows to review", "", "| Param | check | state |", "|---|---|---|"]
    for k, r in pr.items():
        if r["state"] != "HUMAN_VERIFIED":
            out.append("| [%s](params/%s.md) | %s | %s |" % (k, safe(k), r["status"], r["state"]))
    if pinout and pinout["state"] != "HUMAN_VERIFIED":
        out.append("| pinout ([[pin]] list) | not checked | %s |" % pinout["state"])
    return "\n".join(out) + "\n"


def delta_rows(rows, params, pinout=None):
    """Human-stamped rows (and the pinout, listed as `pinout`) whose row or pins (STALE) or PDF (PDF_CHANGED) changed
    since the stamp. NEW and machine-stamped rows are not a delta: they are in the README index and params/."""
    return [k for k in params if (rows[k].get("stamp") or "").startswith("human:")
            and rows[k]["state"] in ("STALE", "PDF_CHANGED")] + (
        ["pinout"] if pinout and (pinout.get("stamp") or "").startswith("human:")
        and pinout["state"] in ("STALE", "PDF_CHANGED") else [])


def delta_md(ctx, rows, params, src, pinout=None):
    todo = delta_rows(rows, params, pinout)
    if not todo:
        return "no human-stamped row changed since its stamp\n"
    out = ["# Review delta: %s" % ctx["value"], "",
           "%d row(s) need review: human-stamped rows whose row (STALE) or PDF (PDF_CHANGED) changed since the stamp "
           "([legend](README.md#legend)). Unstamped rows: README.md." % len(todo)]
    for k in todo:
        if k == "pinout":
            out += ["", "## pinout: %s" % pinout["state"], "",
                    "The `[[pin]]` list or the PDF changed since the human pinout stamp (`%s`). Check the pin table on "
                    "every page in `evidence/pinout_p*.png` against the committed pins (README.md pin table)." % pinout["stamp"]]
            continue
        r = rows[k]
        old = r.get("stamped_toml") or ""
        diff = list(difflib.unified_diff(old.split("\n") if old else [], src[k].split("\n"), "stamped", "committed",
                                         lineterm="", n=99))[2:]
        out += ["", "## [%s](params/%s.md): %s, %s" % (k, safe(k), r["state"], r["status"]), "", "```diff"] + diff + ["```"]
    return "\n".join(out) + "\n"


QUESTION = {"DISAGREE": "Does the printed row on the page match the committed values, column and unit?",
            "UNSURE": "Is the committed row what the page prints (value, column, unit, conditions, package)?",
            "NOT_FOUND": "Which page and table does this row come from, and is the cite right?",
            "STALE": "Does the changed row still match the page?"}


def issue_md(ctx, rows, params, pinout=None):
    keys = [k for k in params if rows[k]["status"] in ISSUE_STATUSES or rows[k]["state"] == "STALE"]
    pin = "pinout" in delta_rows({}, {}, pinout)
    if not keys and not pin:
        return None
    out = ["# Datasheet review questions: %s" % ctx["value"], "",
           "Draft issue (not filed). Text checks are not verification; adjudicate on the page image."]
    if pin:
        out += ["", "### pinout: %s" % pinout["state"],
                "Committed: the `[[pin]]` list (hash `%s`); stamp `%s`" % (pinout["hash"][:12], pinout["stamp"]),
                "Page: " + ", ".join("PDF p.%d" % pg["pdf_page"] for pg in pinout.get("page", [])),
                "Question: Does the pin table still match the pin drawing or table on every cited page?",
                "- [ ] matches: stamp it - [ ] wrong: TOML fix with cite - [ ] unclear: open item"]
    for k in keys:
        r, t = rows[k], params[k]
        q = QUESTION["STALE"] if r["state"] == "STALE" else QUESTION[r["status"]]
        vals = " / ".join("%s %s" % (f, fmtv(t[f])) for f in ("min", "typ", "max") if f in t) or ("text %r" % t.get("text", ""))
        out += ["", "### %s: %s / %s" % (k, r["status"], r["state"]),
                "Committed: %s %s; cite `%s`" % (vals, t.get("unit", ""), t.get("cite", "")),
                "Page: " + (page_link(ctx, r) if r.get("pdf_page") else "not located"),
                "Question: " + q,
                "- [ ] matches: stamp it - [ ] wrong: TOML fix with cite - [ ] unclear: open item"]
    return "\n".join(out) + "\n"


def unmapped_md(ctx, doc, params, not_covered):
    out = ["# Unmapped: %s" % ctx["value"], "",
           "Text-layer heuristic, incomplete: a starting point, not coverage. Main PDF `%s` only." % doc.name, "",
           "## Table rows with no Param (pages with a MIN/TYP/MAX header)", "",
           "| PDF page | printed | first word | text |", "|---|---|---|---|"]
    cited = {}
    for k, t in params.items():
        c = parse_cite(t.get("cite"))
        if c and (not c["sheet"] or c["sheet"] == doc.name):
            pn = resolve_page(c, doc)[0]
            if pn:
                cited.setdefault(pn, set()).add(re.sub(r"\s+", "", T.norm_minus(t.get("symbol", ""))))
    n = 0
    for pn in range(1, doc.count + 1):
        if not doc.text_layer or not doc.heads(pn):
            continue
        for ln in doc.ylines(pn):
            h = T.head_for(doc.heads(pn), ln["ymid"])
            if h is None:
                continue
            lab, cells, unit, _ = T.split_line(ln, h)
            if not lab or not any(cells.values()):
                continue
            first = T.sym_at(lab, 0)
            if first in cited.get(pn, set()) or any(T.sym_at(lab, k) in cited.get(pn, set())
                                                     for k, _x in T.line_symbol_x(lab, h)):
                continue
            text = " ".join(w[4] for w in ln["words"])[:80]
            out.append("| %d | %s | %s | %s |" % (pn, doc.printed.get(pn, ""), md_cell(first), md_cell(text)))
            n += 1
    if not n:
        out.append("| | | | none found |")
    seen = set(cited)
    out += ["", "## Pages no Param cites (not inspected)", "",
            ", ".join(str(p) for p in range(1, doc.count + 1) if p not in seen) or "none", "",
            "## NOT_COVERED", ""] + ["- `%s`: %s" % (k, r) for k, r in not_covered] + [""]
    return "\n".join(out)


# ---------------------------------------------------------------- one component

def not_covered_rows(comp, data):
    out = []
    if (comp / "catalog.csv").is_file():
        n = max(0, len((comp / "catalog.csv").read_text().strip().split("\n")) - 1)
        out.append(("catalog", "catalog.csv (%d rows): catalog values are not reviewed by ds_review" % n))
    if data.get("part", {}).get("series"):
        out.append(("series", "%s-series values and MPN rule (calc.py) are not reviewed by ds_review" % data["part"]["series"]))
    out.append(("calc", "calc.py equations are not reviewed by ds_review"))
    return out


def pinout_pages(pins, ctx):
    """[(sheet, pdf page, Doc)] for every distinct page any [[pin]] cites, main file first, in page order; `sheet` is
    "" for the main file. A cite that does not resolve to one page adds none. Docs may be missing (caller checks)."""
    main, found = ctx["main"], {}
    for pin in pins:
        c = parse_cite(pin.get("cite"))
        if not c:
            continue
        sheet = c["sheet"] if c["sheet"] and c["sheet"] != main.name else ""
        doc = ctx["sheet"](sheet) if sheet else main
        if doc.missing:
            found[(sheet, 0)] = doc  # a marker: this sheet is cited but cannot be read here
            continue
        for n in range(c["page"], (c["page_end"] or c["page"]) + 1):
            pn = resolve_page(dict(c, page=n, page_end=None), doc)[0]
            if pn:
                found[(sheet, pn)] = doc
    return sorted(((s, pn, d) for (s, pn), d in found.items()), key=lambda x: (x[0] != "", x[0], x[1]))


def pinout_record(data, ctx, pr, prev_inp, prev_imgs, cache, sched, pending, first):
    """The [pinout] record (docs/spec/review-view.md "Pinout stamp"), or None without [[pin]]: hash of the pin list, its
    stamp and state like a row's (the stamp binds the main PDF), and a `page` list: the full-page render of every page
    any pin cites. `sched` queues each render."""
    pins = data.get("pin")
    if not pins:
        return None
    main = ctx["main"]
    h, stamp, pr = pinout_hash(pins), (data.get("pinout") or {}).get("verified", ""), pr or {}
    P = main.sha if not main.missing else (prev_inp.get("sheets") or {}).get(main.name, "")
    st = ledger_state(h, stamp, P, pr, lambda: (h, "", True), pinout=True)
    rec = {"state": st["state"], "hash": h, "stamp": st["stamp"], "stamp_hash": st["stamp_hash"], "pdf_sha256": st["pdf_sha256"], "page": []}
    cited = pinout_pages(pins, ctx)
    if any(d.missing for _, _, d in cited):  # a PDF is absent: keep what was found with it
        if pr.get("hash") == h and pr.get("page"):
            rec["page"] = [dict(pg) for pg in pr["page"]]
        else:
            pending.append("pinout")
        return rec
    old = {pg.get("image"): pg for pg in pr.get("page", []) if isinstance(pg, dict)}
    for sheet, pn, doc in cited:
        g = small_glyph(doc, pn, None)
        dpi = max(ctx["dpi"], SMALL_DPI) if g is not None and g < SMALL_PT else ctx["dpi"]
        img = "evidence/%spinout_p%d.png" % (safe(Path(sheet).stem) + "_" if sheet else "", pn)
        meta = [("Source", ctx["url"] if not sheet and ctx["url"] else "no URL recorded (%s)" % doc.name),
                ("Title", "%s datasheet (%s)" % (ctx["value"], doc.name)),
                ("Revision", ctx["rev"] if not sheet else "not recorded"), ("Page", "%s (PDF %d)" % (
                    doc.printed.get(pn) or "none", pn)), ("Copyright", ctx["mfr"]), ("SHA256", doc.sha)]
        prev_imgs.setdefault(img, (old.get(img, {}).get("render_key", ""), old.get(img, {}).get("image_sha256", "")))
        rec["page"].append({"sheet": sheet, "pdf_page": pn, "image": img, "dpi": dpi,
                            "render_key": sched(img, doc, pn, "full_page", dpi, meta)})
    return rec


def review_component(root, comp, dpi, poppler):
    """Write one part's review/. Returns a summary dict."""
    rel = comp.relative_to(root)
    ctoml = comp / "component.toml"
    if not ctoml.is_file():
        raise InputError("%s: not a component dir (no component.toml)" % rel)
    text = ctoml.read_bytes().decode("utf-8")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise InputError("%s/component.toml: unreadable TOML (%s); run python3 -m lib.check" % (rel, e))
    part, params = data.get("part", {}), data.get("param", {})
    spans = param_spans(text)
    missing_span = [k for k in params if k not in spans]
    if missing_span:
        raise InputError("%s: [param.%s] is not a plain table header line; write it as [param.<key>]" % (rel, missing_span[0]))
    # variants.toml overrides (docs/spec/agent-review.md): one that matters is a full row `variant.<V>.<key>`
    # (examined from its own cite, hashed as base row + override fields), one that does not is a REFERENCE row
    vtext, over, reference = "", {}, {}
    if (comp / "variants.toml").is_file():
        vtext = (comp / "variants.toml").read_bytes().decode("utf-8")
        try:
            tomllib.loads(vtext)
            found = override_rows(comp, params)
        except tomllib.TOMLDecodeError as e:
            raise InputError("%s: variants.toml unreadable (%s); fix the TOML" % (rel, e))
        vspans = override_spans(vtext)
        bad = [k for k in found if k not in vspans]
        if bad:
            raise InputError('%s: %s is not a plain table header line; write it as [variant."<V>".param.<key>]' % (rel, bad[0]))
        mat = matters(comp, root)
        for rk, (merged, own) in found.items():
            if rk in mat:
                over[rk] = (merged, own)
                spans[rk] = vspans[rk]
                params = {**params, rk: own}
            else:
                reference[rk] = "variants.toml override of a row that does not matter: covered by the agent-review scope, not a stamp"
    rdir = comp / "review"
    cache = root / CACHE / comp.relative_to(root / "components")  # git-ignored: images and params/<key>.md
    prev, prev_rows, prev_inp = {}, {}, {}
    if (rdir / "review.toml").is_file():
        try:
            prev = tomllib.loads((rdir / "review.toml").read_text())
        except tomllib.TOMLDecodeError as e:
            raise InputError("%s/review/review.toml: unreadable (%s); delete it to rebuild the ledger" % (rel, e))
        prev_rows, prev_inp = prev.get("row", {}), prev.get("inputs", {})
    first = not prev
    dsf = part.get("datasheet_file", "")
    if not dsf:
        raise InputError("%s: [part] datasheet_file is empty; set it (docs/spec/extract.md)" % rel)
    docs = {}

    def get_doc(path, label):
        if path not in docs:
            docs[path] = Doc(path, label)
        return docs[path]

    main = get_doc(root / dsf, dsf)
    ctx = {"main": main, "vendor": part.get("manufacturer", ""), "dpi": dpi, "value": part.get("value", comp.name),
           "mfr": part.get("manufacturer", ""), "url": part.get("datasheet_url", ""), "rev": part.get("datasheet_rev", ""),
           "main_name": main.name, "rel": str(rel), "dirname": comp.name, "cache_rel": str(cache.relative_to(root)),
           "legend": "../README.md",
           "sheet": lambda name: get_doc(root / "docs" / "datasheets" / name, "docs/datasheets/" + name)}
    sheets_prev = prev_inp.get("sheets", {})
    blame = git_blame(root, str(rel / "component.toml")) if first else None

    rows, src, jobs, changed, pending, done = {}, {}, [], [], [], {}
    rerender = {}  # img -> ledger SHA of a re-render with an unchanged render key (compared after rendering)
    prev_imgs = {}
    locate = {}  # key -> {image, render_key, pdf_page, sheet, how, boxes}: .review-cache/<Mfr>/<Value>/locate.json
    try:
        prev_locate = json.loads((cache / "locate.json").read_text()).get("rows", {})
    except (OSError, ValueError, AttributeError):
        prev_locate = {}
    prev_loc = {e.get("image"): e.get("render_key", "") for e in prev_locate.values() if isinstance(e, dict)}
    for r in prev_rows.values():
        for f, kf, sf in (("image", "render_key", "image_sha256"), ("header_image", "header_key", "header_sha256"),
                          ("foot_image", "foot_key", "foot_sha256")):
            if r.get(f):
                prev_imgs[r[f]] = (r.get(kf, ""), r.get(sf, ""))
    def sched(img, doc, pn, b, dpi, meta, extra=""):
        """Queue a render unless the render key is unchanged; returns the key."""
        rk = sha256_bytes(("%s %d %s %s %s%s" % (doc.sha, pn, b, dpi, TOOL_VERSION, extra)).encode())[:16]
        if img in done:
            pass
        elif prev_imgs.get(img, ("", ""))[0] == rk and (cache / img).is_file():
            done[img] = prev_imgs[img][1]  # unchanged: the ledger's hash, never re-read from disk
        else:
            if prev_imgs.get(img, ("", ""))[0] == rk and prev_imgs[img][1]:
                rerender[img] = prev_imgs[img][1]
            done[img] = None
            jobs.append((img, (str(doc.path), pn, b, dpi, meta, cache / img)))
        return rk

    for key, t in params.items():
        sp = spans[key]
        src[key] = snippet(vtext if key in over else text, sp)
        h = row_hash(over[key][0] if key in over else t)
        pr = prev_rows.get(key)
        stamp = t.get("verified", "")
        ex = examine(key, t, ctx)
        doc = ex["doc"]
        P = (doc.sha if doc and not doc.missing else
             sheets_prev.get(doc.name if doc else "", "")) if doc else ""

        def backfill(key=key, sp=sp, h=h):
            if not first:
                return h, src[key], False
            if key in over:  # an override has no git-blame baseline here: its stamp is pinned as the baseline
                return h, src[key], True
            line = next((n for n in range(sp[0], sp[1] + 1) if text.split("\n")[n - 1].lstrip().startswith("verified")), None)
            c = blame.get(line) if blame and line else None
            if not c or set(c) == {"0"}:
                return h, src[key], True
            hc, snip = table_at(root, c, str(rel / "component.toml"), key)
            return (h, src[key], True) if hc in (None, h) else (hc, snip, False)
        st = ledger_state(h, stamp, P, pr, backfill)
        row = dict(st, hash=h, toml_lines="%d-%d" % sp)
        have_pdf = doc is not None and not doc.missing
        if have_pdf:
            row.update(status=ex["status"], reason=ex["reason"], sheet=ex["sheet"], printed_page=ex["printed_page"],
                       pdf_page=ex["pdf_page"], crop=ex["crop"], crop_box=ex["crop_box"], dpi=ex["dpi"],
                       text_snippet=ex["text_snippet"], text_cells=ex["cells"], header_box=ex["header_box"],
                       foot_box=ex["foot_box"])
        elif not doc:  # cite unparseable: no PDF needed to say so
            row.update(status=ex["status"], reason=ex["reason"])
        elif pr and pr.get("hash") == h:  # PDF absent: keep what was found with the PDF
            row.update({f: pr[f] for f in KEPT if f in pr})
        else:  # PDF absent and the row is new or changed: say so; keep the old image (never blank it)
            row.update({f: pr[f] for f in KEPT if pr and f in pr})
            row.update(status="NOT_FOUND" if not pr else "UNSURE", sheet=ex["sheet"],
                       reason=ex["reason"] if not pr else "row changed; not re-checked: " + ex["reason"])
            pending.append(key)
        if have_pdf and ex["pdf_page"]:
            pn, box = ex["pdf_page"], ex["crop_box"]
            if ex["crop"] == "auto":  # one image per Param
                img = "evidence/%s_p%d.png" % (safe(key), pn)
            else:  # fallbacks are shared by every Param that falls back to the same page or table
                pre = safe(Path(ex["sheet"]).stem) + "_" if ex["sheet"] else ""
                img = ("evidence/%spage_p%d.png" % (pre, pn) if box == "full_page"
                       else "evidence/%stable_p%d_y%d.png" % (pre, pn, int(box[1])))
            meta = [("Source", ctx["url"] if not ex["sheet"] and ctx["url"] else "no URL recorded (%s)" % doc.name),
                    ("Title", "%s datasheet (%s)" % (ctx["value"], doc.name)),
                    ("Revision", ctx["rev"] if not ex["sheet"] else "not recorded"),
                    ("Page", "%s (PDF %d)" % (ex["printed_page"] or "none", pn)),
                    ("Copyright", ctx["mfr"]), ("SHA256", doc.sha)]

            def schedule(img, b, extra=""):
                return sched(img, doc, pn, b, ex["dpi"], meta, extra)
            row["image"] = img
            row["render_key"] = schedule(img, box, " " + h if ex["crop"] == "auto" else "")
            for kind, word in (("header", "head"), ("foot", "foot")):  # shared per table: same width and dpi
                b = ex.get(kind + "_box")
                if b:
                    pre = safe(Path(ex["sheet"]).stem) + "_" if ex["sheet"] else ""
                    row[kind + "_image"] = "evidence/%s%s_p%d_y%d-%d_x%d-%d.png" % (pre, word, pn, int(b[1]), int(b[3]),
                                                                                    int(b[0]), int(b[2]))
                    prev_imgs.setdefault(row[kind + "_image"], ((pr or {}).get(kind + "_key", ""), ""))
                    row[kind + "_key"] = schedule(row[kind + "_image"], b)
            if ex["crop"] != "auto":  # display only: the full page of the cited sheet, boxes drawn by the viewer
                pre = safe(Path(ex["sheet"]).stem) + "_" if ex["sheet"] else ""
                limg = img if box == "full_page" else "evidence/%slocate_p%d.png" % (pre, pn)
                prev_imgs.setdefault(limg, (prev_loc.get(limg, ""), ""))
                how, found = locate_boxes(t, doc, pn)
                locate[key] = {"image": limg, "render_key": row["render_key"] if limg == img else
                               sched(limg, doc, pn, "full_page", ctx["dpi"], meta),
                               "pdf_page": pn, "sheet": ex["sheet"], "how": how, "boxes": found}
        elif not have_pdf and pr and pr.get("hash") == h and key in prev_locate:  # no PDF here: keep what it showed
            locate[key] = prev_locate[key]
        row["sha_for_stamp"] = (P or "")[:12]
        rows[key] = row

    pinout = pinout_record(data, ctx, prev.get("pinout"), prev_inp, prev_imgs, cache, sched, pending, first)
    if jobs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2)) as pool:
            for (img, _job), res in zip(jobs, pool.map(render, [j for _, j in jobs])):
                done[img] = res[1]  # cache files: not part of the committed record, so not listed as changed
    for r in list(rows.values()) + (pinout["page"] if pinout else []):
        for f, sf in (("image", "image_sha256"), ("header_image", "header_sha256"), ("foot_image", "foot_sha256")):
            if r.get(f) in done:
                r[sf] = done[r[f]]
        if r.get("image") in done and (cache / r["image"]).is_file():  # size in the ledger: the README's budget list
            r["image_bytes"] = (cache / r["image"]).stat().st_size  # must not depend on the cache being present
    missing_any = any(d.missing for d in docs.values())
    # derived from the rows, so a second run without the PDF keeps saying so (and stays byte-identical)
    stale = [k for k in params if rows[k].get("reason", "").startswith(("row changed; not re-checked",
                                                                         "PDF not on this machine"))]
    stale += ["pinout"] if pinout and "pinout" in pending else []
    render_state = "NOT_RENDERED" if missing_any and (pending or first or stale) else "complete"

    for key, why in reference.items():
        rows[key] = {"state": "REFERENCE", "status": "UNSURE", "reason": why}
    for key, why in not_covered_rows(comp, data):
        rows[key] = {"state": "NOT_COVERED", "status": "UNSURE", "reason": why}

    # inputs
    inputs = {k: prev_inp[k] for k in INPUT_FIELDS if k in prev_inp}
    if jobs:
        inputs.update(tool=TOOL_VERSION, poppler=poppler, python="%d.%d.%d" % sys.version_info[:3], dpi=dpi)
    inputs.setdefault("tool", TOOL_VERSION)
    inputs.setdefault("dpi", dpi)
    inputs.update(datasheet_url=ctx["url"], datasheet_file=dsf, datasheet_rev=ctx["rev"],
                  component_sha256=sha256_bytes(ctoml.read_bytes()), render=render_state)
    if not main.missing:
        inputs.update(pdf_sha256=main.sha, pages=main.count, text_layer=main.text_layer)
    sheets = dict(sheets_prev)
    sheets.update({d.name: d.sha for d in docs.values() if not d.missing})
    inputs["sheets"] = sheets
    if first:
        inputs["backfill"] = "git blame" if blame is not None else "no git history: stamps pinned as baseline"
    ctx.update(P=inputs.get("pdf_sha256", ""), render=render_state)

    # files
    keep = {r[f] for r in list(rows.values()) + (pinout["page"] if pinout else []) for f in ("image", "header_image", "foot_image")
            if r.get(f)} | {e["image"] for e in locate.values()}
    ev = cache / "evidence"
    if ev.is_dir():
        for f in sorted(ev.iterdir()):
            if "evidence/" + f.name not in keep:
                f.unlink()
    for legacy in ("evidence", "params"):  # records before the cache: images were committed under review/
        if (rdir / legacy).is_dir():
            shutil.rmtree(rdir / legacy)
            changed.append(str(rel / "review" / legacy) + "/")
    over = sorted({r["image"] for r in rows.values() if r.get("image") and (r.get("image_bytes") or 0) > BUDGET})
    ledger_rows = {}
    for k, r in rows.items():
        lr = {f: r.get(f) for f in ROW_FIELDS}
        lr["baseline"] = r.get("baseline") or None
        if lr["stamp"] == "":
            lr["stamped_toml"] = r.get("stamped_toml") if r.get("stamp_hash") else None
        ledger_rows[k] = lr
    files = {"review.toml": ledger_text(inputs, ledger_rows, pinout)}  # the only committed file
    for legacy in ("README.md", "DELTA.md", "github-issue.md", "unmapped.md"):  # earlier records committed these
        if (rdir / legacy).is_file():
            (rdir / legacy).unlink()
            changed.append(str(rel / "review" / legacy))
    local = {"params/%s.md" % safe(k): param_md(k, t, rows[k], ctx, src[k]) for k, t in params.items()}
    local.update({"README.md": readme_md(ctx, rows, params, over, pinout), "DELTA.md": delta_md(ctx, rows, params, src, pinout)})
    if locate or (cache / "locate.json").is_file():  # never committed: the viewer's boxes (docs/spec/review-view.md "Page")
        local["locate.json"] = json.dumps({"rows": locate}, sort_keys=True, indent=1) + "\n"
    issue = issue_md(ctx, rows, params, pinout)
    if issue:
        local["github-issue.md"] = issue
    elif (cache / "github-issue.md").is_file():
        (cache / "github-issue.md").unlink()
    if not main.missing:
        local["unmapped.md"] = unmapped_md(ctx, main, params, not_covered_rows(comp, data))
    elif not (cache / "unmapped.md").is_file():
        local["unmapped.md"] = "# Unmapped: %s\n\nNot built: PDF not on this machine (%s).\n" % (ctx["value"], dsf)
    pdir = cache / "params"
    if pdir.is_dir():
        for f in sorted(pdir.iterdir()):
            if "params/" + f.name not in local:
                f.unlink()
    for name, body in local.items():
        write_if_changed(cache / name, body)
    for name, body in files.items():
        if write_if_changed(rdir / name, body):
            changed.append(str(rel / "review" / name))
    matched = sum(1 for img, old in rerender.items() if done.get(img) == old)
    mode = ("ledger-only" if all(d.missing for d in docs.values()) else
            "partial" if missing_any else "evidence")
    return {"dir": str(rel), "rows": rows, "params": params, "renders": len(jobs), "changed": changed,
            "delta": len(delta_rows(rows, params, pinout)), "pinout": pinout,
            "render": render_state, "over": over, "mode": mode, "rerendered": len(rerender), "matched": matched,
            "differ": sorted(img for img, old in rerender.items() if done.get(img) != old)}


# ---------------------------------------------------------------- scope and CLI

def component_dirs(root):
    return sorted(p.parent for p in Path(root).glob("components/*/*/component.toml"))


def default_scope(root):
    rc, out, _ = run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--", "components"])
    if rc != 0:
        raise InputError("git status failed; give component dirs or --all")
    dirs = set()
    for line in out.splitlines():
        parts = line[3:].split(" -> ")[-1].strip().strip('"').split("/")
        if len(parts) >= 4 and parts[0] == "components" and parts[3] != "review":
            dirs.add(Path(root, *parts[:3]))
    dirs |= {d for d in component_dirs(root) if not (d / "review").is_dir()}
    return sorted(d for d in dirs if (d / "component.toml").is_file())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dirs", nargs="*", help="component dirs (components/<Mfr>/<Value>)")
    ap.add_argument("--all", action="store_true", help="every component")
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="base render resolution (default 150)")
    ap.add_argument("--root", default=Path(__file__).resolve().parent.parent)
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    try:
        if not 50 <= a.dpi <= 600:
            raise InputError("--dpi %d out of range; use 50..600" % a.dpi)
        poppler = poppler_version()
        dirs = (component_dirs(root) if a.all else [(root / d).resolve() if not Path(d).is_absolute() else Path(d)
                                                     for d in a.dirs] or default_scope(root))
        results = [review_component(root, d, a.dpi, poppler) for d in dirs]
    except InputError as e:
        print("FAIL: %s" % e)
        return 1
    tot = {"renders": 0, "changed": 0}
    for r in results:
        rws = [x for k, x in r["rows"].items() if k in r["params"]]
        st = {s: sum(1 for x in rws if x["status"] == s) for s in STATUSES}
        sg = {s: sum(1 for x in list(r["rows"].values()) + ([r["pinout"]] if r["pinout"] else []) if x["state"] == s)
              for s in STATES}
        fb = sum(1 for x in rws if x.get("crop") == "fallback")
        print("%s: %s | %s | fallback %d | renders %d | changed %d%s%s%s" % (
            r["dir"], " ".join("%s=%d" % kv for kv in st.items()), " ".join("%s=%d" % kv for kv in sg.items() if kv[1]),
            fb, r["renders"], len(r["changed"]), " | delta %d" % r["delta"] if r["delta"] else "",
            " | NOT_RENDERED" if r["render"] == "NOT_RENDERED" else "",
            (" | over budget: " + ", ".join(r["over"][:5]) + (" ..." if len(r["over"]) > 5 else "")) if r["over"] else ""))
        tot["renders"] += r["renders"]
        tot["changed"] += len(r["changed"])
    print("summary: %d component(s), %d render(s), %d file(s) changed" % (len(results), tot["renders"], tot["changed"]))
    print(mode_line(results))
    return 0


def mode_line(results):
    """One line naming the mode that ran, so a run without PDFs never reads as an evidence check."""
    ev = [r for r in results if r["mode"] != "ledger-only"]
    lo = [r["dir"].split("/")[-1] for r in results if r["mode"] == "ledger-only"]
    pa = [r["dir"].split("/")[-1] for r in results if r["mode"] == "partial"]
    rr, ok = sum(r["rerendered"] for r in ev), sum(r["matched"] for r in ev)
    new = sum(r["renders"] for r in ev) - rr
    out = []
    if ev:
        out.append("evidence mode (PDF present) in %d part(s): %d image(s) re-rendered with an unchanged key, %d matched "
                   "the ledger, %d differ; %d new or changed render(s)%s" % (
                       len(ev), rr, ok, rr - ok, new, "; partial (a sheet missing): " + ", ".join(pa) if pa else ""))
    if lo:
        out.append("ledger-only mode (no local PDF) in %d part(s): %s" % (len(lo), ", ".join(lo)))
    return "review: " + ("; ".join(out) or "no parts")


if __name__ == "__main__":
    sys.exit(main())
