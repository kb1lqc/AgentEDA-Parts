#!/usr/bin/env python3
"""Check datasheet rows on one local page, then stamp them and open the PR with one button. Run by the PERSON who checks.

Usage (library repo root):
  python3 tools/review.py                                       every part
  python3 tools/review.py <Value> [<Value> ...]                 these parts
  python3 tools/review.py --block <Block> [--blocks-repo DIR]   the rows a circuit block reads
  python3 tools/review.py --list-blocks [--blocks-repo DIR]     the blocks --block can read
--block reads <blocks repo>/benches/<Block>/docs/design-analysis/library-inputs.json (written by the block's
analysis.py). Default blocks repo: ../ina229 if it exists, else ../circuit-blocks.

Each row is checked (a current human stamp), needs check, or reference: docs/spec/review.md "Human view" (the rows
that matter; --block only narrows the page, never a part's status; the pinout is a row, stamped `<Value>:pinout`). The
page (127.0.0.1, random port, random token in the URL) shows a status line per part ("<Value>: k of n rows that matter
checked"), then per part (fewest rows to check first, released parts folded) the rows to check in three sections (Limits,
Used by equations, Pins & package): the statement card (title, value, conditions, temperature, used by; the note
folded under "How we read it"), the crops or the located full page from .review-cache/ (each image file is served
once, by token URL; tools/ds_review.py runs first when a part has no cache, it needs the local PDF) and one tick box, none when
stamp.py would refuse the row. Tick the rows whose statement matches the datasheet image and press
"Stamp N rows and open PR". With the library tree clean (untracked files allowed) it runs, showing each command:
git fetch origin; git switch -c review/<parts>-<login>-<YYYYMMDD>[-n] origin/main; tools/stamp.py --from <list>
(a refusal switches back and deletes the new branch); tools/verify.py --regen <parts> (a FAIL leaves the branch,
uncommitted, for you); git commit of those parts' component.toml, review/review.toml and README.md, plus the top-level README.md status table; git push -u origin
<branch>; gh pr create. Then the server exits. --dry-run is for a person trying the page; agents don't run review.py
(.claude/settings.json denies it; the CLAUDECODE refusal lets only --dry-run through, so the tests can drive it).
Exit 0 = PR opened (or Done pressed), 1 = refused or a step failed.
"""

import argparse
import csv
import datetime
import hashlib
import html
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
import tempfile
import threading
import tomllib
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stamp as S  # noqa: E402  (check_row: the exact rule stamp.py applies, so a tickable row is a stampable row)
from lib import review_status as RS  # noqa: E402
from lib import catalog as CAT  # noqa: E402  (export check of capacitor-series catalogs: docs/spec/capacitor.md)

ROOT = Path(__file__).resolve().parent.parent
AGENT = ("refused: running inside Claude Code (CLAUDECODE is set); a person must run review.py in their own shell "
         "(agents don't run review.py)")
TIERS = (("tier 1", "Easiest: row image, and the datasheet text agrees with the TOML"),
         ("tier 2", "Row image; the text check could not confirm it"),
         ("tier 3", "Table or page image: find the row yourself"),
         ("page", "No image: open the datasheet page"),
         ("fix", "Fix first (cannot be ticked)"),
         ("none", "Not in the review record (cannot be ticked here)"))
TICKABLE = ("tier 1", "tier 2", "tier 3", "page")
MAX_BODY = 1 << 20


def read_toml(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def toml_block(path, header):
    """Source lines of one TOML table, header to the next header, without the `verified` line ('' when absent)."""
    try:
        lines = Path(path).read_text().split("\n")
    except OSError:
        return ""
    start = next((i for i, ln in enumerate(lines) if ln.strip() == header), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return "\n".join(ln for ln in lines[start:end] if not re.match(r"\s*verified\s*=", ln))


def cache_dir(root, d):
    return Path(root) / ".review-cache" / Path(d).parent.name / Path(d).name


def default_blocks_repo(root):
    for name in ("ina229", "circuit-blocks"):
        if (Path(root).parent / name).is_dir():
            return Path(root).parent / name
    return Path(root).parent / "circuit-blocks"


def block_inputs(blocks_repo, block):
    """The entries of a block's library-inputs.json (dicts with value, key, input, dir)."""
    f = Path(blocks_repo) / "benches" / block / "docs" / "design-analysis" / "library-inputs.json"
    if not f.is_file():
        raise SystemExit(f"refused: {f} not found (run python3 blocks/{block}/analysis.py in the blocks repo)")
    return json.loads(f.read_text())


def list_blocks(blocks_repo):
    """Names of the blocks whose library-inputs.json exists (sorted); [] when the blocks repo has no benches/."""
    benches = Path(blocks_repo) / "benches"
    if not benches.is_dir():
        return []
    return sorted(p.name for p in benches.iterdir()
                  if (p / "docs" / "design-analysis" / "library-inputs.json").is_file())


def classify(root, d, key, ledger, params):
    """(tier, why, images) of one row that needs a check; images = [(cache-relative path, caption)]."""
    if key == "pinout":
        _, _, why = S.check_row(root, d.name, "pinout")
        if why:
            return "fix", why, []
        pages = [pg for pg in ledger["pinout"].get("page", []) if pg.get("image")]  # every page a pin cites
        return "tier 3", "", [(pg["image"], f"pin table page {pg['pdf_page']}") for pg in pages]
    if key not in params:
        return "none", ("variant row: variants.toml rows are not reviewed" if key.startswith("variant.")
                        else "catalog row (catalog.csv): not reviewed"), []
    if not RS.values_text(params[key]):
        return "fix", RS.statement(d, key), []  # a row with no min, typ or max: nothing to compare, no tick box
    _, _, why = S.check_row(root, d.name, key)
    if why:
        return "fix", why, []
    row = ledger["row"][key]
    if row.get("crop") == "auto":
        imgs = [(row.get("header_image"), "table header"), (row.get("image"), "row"), (row.get("foot_image"), "footnotes")]
        tier = "tier 1" if row.get("status") == "AGREE_TEXT_CHECK" else "tier 2"
        return tier, row.get("reason", ""), [(p, c) for p, c in imgs if p]
    loc = locate_entry(root, d, key)
    if loc:  # the full page of the cited sheet with boxes (item["locate"]); the ledger image stamp hashes goes below it
        ev = row.get("image")
        same = ev and Path(ev).as_posix() == Path(loc["image"]).as_posix()
        shown = [(ev, "evidence the stamp records")] if ev and not same and (cache_dir(root, d) / ev).is_file() else []
        return "tier 3", row.get("reason", ""), shown
    cache = cache_dir(root, d)
    imgs = [(row["image"], "table or page")] if row.get("image") and (cache / row["image"]).is_file() else []
    pre = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(row["sheet"]).stem) + "_" if row.get("sheet") else ""
    page = f"evidence/{pre}page_p{row.get('pdf_page')}.png"  # the cited sheet's page, never the main file's
    if row.get("pdf_page") and page != row.get("image") and (cache / page).is_file():
        imgs.append((page, "full page"))
    return ("tier 3" if imgs else "page"), row.get("reason", ""), imgs


def locate_entry(root, d, key):
    """The cached Locate data of a row (.review-cache/<Mfr>/<Value>/locate.json: image, boxes in percent of the page;
    docs/spec/review-view.md "Page"): at most 5 well-formed boxes, or None when there is none or its image is gone."""
    cache = cache_dir(root, d)
    try:
        e = json.loads((cache / "locate.json").read_text())["rows"][key]
        ok = isinstance(e, dict) and isinstance(e.get("image"), str) and (cache / e["image"]).is_file()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if not ok:
        return None
    boxes = [b for b in e.get("boxes") or [] if isinstance(b, dict) and isinstance(b.get("box"), list) and len(b["box"]) == 4
             and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in b["box"])]
    return {**e, "boxes": boxes[:5]}


def page_link(ledger, part, row, pages=None):
    """(text, url or None): local file, PDF page and printed page; url#page=N when the URL is a direct PDF link. pages:
    every PDF page a pinout cites (listed in the text; the link goes to the first)."""
    inp = ledger.get("inputs", {})
    main = Path(inp.get("datasheet_file") or part.get("datasheet_file") or "").name
    sheet = (row or {}).get("sheet") or main
    pdf_page, printed = (row or {}).get("pdf_page"), (row or {}).get("printed_page")
    shown_pages = ", ".join(str(n) for n in pages) if pages and len(pages) > 1 else None  # a pinout citing several pages
    text = (f"docs/datasheets/{sheet or 'n/a'}, PDF " + (f"pages {shown_pages}" if shown_pages else f"page {pdf_page or 'n/a'}")
            + (f" (printed page {printed})" if printed and not shown_pages else ""))
    url = inp.get("datasheet_url") or part.get("datasheet_url")
    if not url or sheet != main:
        return text, None
    direct = url.lower().split("?")[0].endswith(".pdf") or "/lit/" in url
    return text, f"{url}#page={pdf_page}" if direct and pdf_page else url


SECTIONS = ("Limits", "Used by equations", "Pins & package")


def section_of(why):
    """The page section of a row from RS.matters reasons (docs/spec/review-view.md "Page"); a row outside the part's
    [param] rows (variant, catalog) is a used value."""
    why = why or []
    if "pinout" in why or "mechanical" in why:
        return SECTIONS[2]
    return SECTIONS[0] if "abs_max" in why or "thermal" in why else SECTIONS[1]


def all_parts(root):
    """Every component directory (a family is one directory), sorted by path."""
    return sorted(p.parent for p in (Path(root) / "components").glob("*/*/component.toml"))


def build_model(root, used_by_dir):
    """Per part (sorted by name): dict with dir, value, status line, released, items (rows to check), checked
    [(key, login, date)] and reference keys. used_by_dir: {dir: set of rows a block reads, or None = no narrowing}.
    Counts and `released` never depend on the block; it only narrows items (a block row outside the part's [param]
    rows is listed as not reviewable)."""
    parts = []
    for d in sorted(used_by_dir, key=lambda p: Path(p).name):
        d = Path(d)
        used = used_by_dir[d]
        rev = RS.review(d, root)
        status = rev["status"]
        line, released = RS.summary(d.name, rev)
        ledger, comp = read_toml(d / "review" / "review.toml"), read_toml(d / "component.toml")
        params, done = comp.get("param", {}), RS.checked_rows(d)
        items = []
        shown_keys = [k for k, s in status.items() if s == RS.NEEDS and (used is None or k in used)]
        shown_keys += sorted(k for k in (used or ()) if k not in status)
        for key in shown_keys:
            tier, why, imgs = classify(root, d, key, ledger, params)
            pin_pages = [pg for pg in ledger.get("pinout", {}).get("page", []) if isinstance(pg, dict)] if key == "pinout" else []
            row = (pin_pages[0] if pin_pages else None) if key == "pinout" else ledger.get("row", {}).get(key)
            items.append({"ref": f"{d.name}:{key}", "key": key, "tier": tier, "why": why, "images": imgs,
                          "name": params.get(key, {}).get("name", ""), "part": d.name,
                          "locate": None if key == "pinout" or tier not in TICKABLE or (row or {}).get("crop") == "auto"
                          else locate_entry(root, d, key),
                          "statement": RS.statement(d, key, root) if key == "pinout" or key in params else "",
                          "card": RS.statement_card(d, key, root) if key == "pinout" or key in params else None,
                          "section": section_of(rev["matters"].get(key)),
                          "toml": toml_block(d / "component.toml", f"[param.{key}]") if key in params else "",
                          "page": page_link(ledger, comp.get("part", {}), row if isinstance(row, dict) else None,
                                            [pg["pdf_page"] for pg in pin_pages])})
        order = {t: n for n, (t, _) in enumerate(TIERS)}
        items.sort(key=lambda i: (SECTIONS.index(i["section"]), order[i["tier"]], i["key"]))
        # Rows with a value and a citation but no table or figure location: not compared, not stamped, not counted.
        # Listed apart with no tick box, so no image comparison or NOT_FOUND state is shown for them.
        unlocated = [unlocated_item(d, key, params, root, rev) for key in rev["unlocated"] if used is None or key in used]
        parts.append({"dir": d, "value": d.name, "line": line, "released": released, "items": items,
                      "unlocated": unlocated,
                      "k": rev["k"], "n": rev["n"], "used_known": used is not None,
                      "checked": [(k, *done[k]) for k, s in status.items() if s == RS.CHECKED],
                      "reference": [k for k, s in status.items() if s == RS.REFERENCE and k not in rev["unlocated"]]})
    return parts


UNLOCATED_WHY = ("Reference, not checked: the value has a citation but no table or figure location in the datasheet "
                 "(a features bullet, design or application text). It is not compared with an image and is not stamped. "
                 "Add a page locator or a crop to its review record to make it a check.")


def unlocated_item(d, key, params, root, rev):
    """A reference row of the block view: its statement and citation, no tick box and no image."""
    return {"ref": f"{d.name}:{key}", "key": key, "part": d.name, "tier": "reference", "why": UNLOCATED_WHY,
            "card": RS.statement_card(d, key, root),
            "toml": toml_block(d / "component.toml", f"[param.{key}]")}


def cited_export(root, catalog_path):
    """The export file the catalog's source cite names ("... export <file>, row <part>"), looked up in docs/datasheets/
    then docs/vendor/; None when the cite or the file is missing."""
    try:
        with open(catalog_path, newline="", encoding="utf-8") as f:
            first = next(csv.DictReader(f), None)
    except OSError:
        return None
    m = re.search(r"export (\S+), row", (first or {}).get("source", ""))
    for sub in ("docs/datasheets", "docs/vendor"):
        if m and (Path(root) / sub / m[1]).is_file():
            return Path(root) / sub / m[1]
    return None


def build_groups(root, dirs):
    """The capacitor-series groups of the page (docs/spec/capacitor.md "Export check"): one entry per dielectric of each
    murata-gcm catalog among dirs, with the export check result, the distinct combinations, the group's current human
    stamp (its `verified` line, or None) and ref "<Value>:group:<dielectric>". tickable: MATCH and not yet stamped."""
    out = []
    for d in dirs:
        d = Path(d)
        part = read_toml(d / "component.toml").get("part", {})
        if part.get("catalog_decoder") != "murata-gcm":
            continue
        export = cited_export(root, d / part.get("catalog", "catalog.csv"))
        if export is None:
            out.append({"part": d.name, "dielectric": "all", "dir": d, "export": None, "rows": 0, "result": "NO EXPORT",
                        "differences": [], "combos": [], "stamp": None, "ref": None, "tickable": False,
                        "group_sha256": None})
            continue
        res = CAT.export_check(d, export)
        with open(export, newline="", encoding="utf-8-sig") as f:
            expected, _, _ = CAT.build_rows(list(csv.DictReader(f)), d.name[3:], set(part.get("tc_param", {})), export.name)
        record = read_toml(d / "review" / CAT.EXPORT_RECORD)
        current = record.get("catalog", {}).get("sha256") == res["catalog_sha256"]
        for diel, g in res["groups"].items():
            prior = record.get("group", {}).get(diel, {})
            stamp = prior.get("verified") if current and prior.get("group_sha256") == g["sha256"] else None
            out.append({"part": d.name, "dielectric": diel, "dir": d, "export": export, "rows": g["rows"],
                        "result": res["result"], "differences": res["differences"],
                        "rows_expected": sorted((r for r in expected if r["dielectric"] == diel), key=lambda r: r["value"]),
                        "stamp": stamp, "ref": f"{d.name}:group:{diel}", "tickable": res["result"] == "MATCH" and stamp is None,
                        "group_sha256": g["sha256"]})
    return out


def legend_html(rows):
    """The legend of one group: every code the group's part numbers use, with its meaning (the decode tables of
    lib/catalog.py), and how to read the table. The decode is a cross-check, not a datasheet rule (docs/spec/capacitor.md)."""
    esc = html.escape
    seen = {}
    for r in rows:
        for label, code, meaning in CAT.fields_of(r["value"]) or []:
            seen.setdefault((label, code), meaning)
    order = {f: i for i, f in enumerate(CAT.FIELDS)}
    items = "".join(f"<li><b>{esc(label)}</b> {esc(code)} = {esc(meaning)}</li>"
                    for (label, code), meaning in sorted(seen.items(), key=lambda kv: (order[kv[0][0]], kv[0][1])))
    return ('<details open><summary>Legend: how to read the part numbers</summary>'
            '<p class="small">A part number is the catalog value plus a package letter (the export prints it with #). '
            'Each row below splits it into fields; the last column is what the export prints for the same part. '
            'The machine check already compared every field. Your tick confirms the decoded fields and the printed '
            'values agree. The decode tables are a cross-check, not datasheet rules (docs/spec/capacitor.md).</p>'
            f'<ul class="small">{items}</ul></details>')


def group_html(g):
    """One capacitor-series group on the page: heading, status, the distinct combinations with an export row each, and one
    tick box when the group can be stamped (the box's value is the group ref; publish stamps it with lib.catalog)."""
    esc = html.escape
    head = f"<h2>{esc(g['part'])} {esc(g['dielectric'])}: {g['rows']} rows</h2>"
    if g["export"] is None:
        return (f'<div class="item">{head}<p class="warn">no export file: the catalog cites a file that is not in '
                "docs/datasheets/ or docs/vendor/</p></div>")
    parts = [head, f'<p class="mute small">Export: {esc(g["export"].name)}; group sha256 {esc(g["group_sha256"][:12])}</p>']
    if g["result"] != "MATCH":
        parts.append('<p class="warn">MISMATCH: ' + esc("; ".join(g["differences"][:3])) + "</p>")
    if g["stamp"]:
        m = re.match(r"human:(\S+) (\S+) ", g["stamp"])
        parts.append(f'<p class="small">Ticked by {esc(m[1] if m else "?")} on {esc(m[2] if m else "?")}</p>')
    rows = g["rows_expected"]
    parts.append(legend_html(rows))
    cells = []
    for r in rows:
        fields = CAT.fields_of(r["value"]) or []
        decoded = "".join(f"<td>{esc(code)} = {esc(meaning)}</td>" for _, code, meaning in fields)
        cells.append(f"<tr><td>{esc(r['value'])}</td>{decoded}"
                     f"<td>{esc(r['capacitance'])}, {esc(r['tolerance'])}, {esc(r['rated_voltage'])}, {esc(r['thickness'])}</td></tr>")
    head_cells = "".join(f"<th>{esc(f)}</th>" for f in ("Part", *CAT.FIELDS, "Export prints"))
    parts.append(f'<details><summary>All {len(rows)} parts, decoded</summary>'
                 f'<table class="stmt"><tr>{head_cells}</tr>{"".join(cells)}</table></details>')
    if g["tickable"]:
        parts.append(f'<label class="pick"><input type="checkbox" class="ok" value="{esc(g["ref"])}">'
                     "matches the export: every combination above is the export's row</label>")
    return f'<div class="item" id="group-{esc(g["ref"])}">' + "".join(parts) + "</div>"


def ensure_cache(root, dirs, run=subprocess.run, dry_run=False):
    """Run tools/ds_review.py on the parts with no .review-cache/ (needs the local PDF). Returns the lines printed.
    dry_run: spawn nothing, return the command as "would run"."""
    missing = [str(Path(d).relative_to(root)) for d in dirs if not cache_dir(root, d).is_dir()]
    if not missing:
        return []
    cmd = [sys.executable, "tools/ds_review.py", *missing]
    if dry_run:
        return [f"would run (dry run): {shlex.join(cmd)}"]
    r = run(cmd, cwd=root, capture_output=True, text=True)
    return [f"$ {shlex.join(cmd)}"] + (r.stdout + r.stderr).strip().splitlines()[-3:]


CSS = """
:root{--bg:#fff;--fg:#1b1b1b;--mute:#5d5d5d;--line:#d9d9d9;--card:#f6f6f4;--code:#efefec;--warn:#9a3b00;--ok:#1f6b3a;
--link:#0b57d0;--visited:#6a3db8}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#e6e6e6;--mute:#a3a3a3;--line:#3a3a3a;--card:#1f1f1f;
--code:#262626;--warn:#ffb27a;--ok:#7fd29b;--link:#8ab4f8;--visited:#c58af9}}
a{color:var(--link)}a:visited{color:var(--visited)}
#summary{background:var(--card);border:2px solid var(--ok);border-radius:6px;padding:10px 14px;margin:12px 0}
#summary p{margin:4px 0}.small{font-size:13px}
img.big{max-height:70vh;width:auto;object-fit:contain;cursor:zoom-in}img.big.full{max-height:none;cursor:zoom-out}
body{background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1000px;padding:0 16px}
h2{border-bottom:2px solid var(--line);padding-bottom:4px;margin-top:2em}h3{font-size:1em;margin:1.4em 0 .4em}
.item{background:var(--card);border:1px solid var(--line);border-radius:6px;margin:12px 0;padding:10px 14px}
.item.done{border-color:var(--ok);border-width:2px}.mute{color:var(--mute)}.warn{color:var(--warn)}
table.stmt{border-collapse:collapse;margin:4px 0}.stmt th{text-align:left;color:var(--mute);font-weight:normal;padding:1px 14px 1px 0}
.stmt td{padding:1px 14px 1px 0}.card summary{cursor:pointer}
pre{background:var(--code);padding:8px;overflow-x:auto;font-size:13px;white-space:pre-wrap}
img{max-width:100%;display:block;margin:4px 0;background:#fff;border:1px solid var(--line)}
.loc{overflow:auto;max-height:60vh;border:1px solid var(--line);cursor:zoom-out}.loc.full{overflow:visible;max-height:none}
.pg{position:relative}.loc.full .pg{width:100%!important}.pg img{max-width:none;width:100%;margin:0;border:0}
.box{position:absolute;box-sizing:border-box;border:2px solid #e5251d;background:rgba(229,37,29,.14);pointer-events:none}
label.pick{display:inline-block;margin:4px 0;padding:4px 10px;border:1px solid var(--ok);border-radius:4px;cursor:pointer}
label.pick input{transform:scale(1.3);margin-right:8px}
#bar{position:sticky;bottom:0;background:var(--bg);border-top:2px solid var(--ok);padding:8px 0}
#bar button{font:inherit;padding:6px 14px;margin-right:8px;cursor:pointer}#log{max-height:14em;overflow-y:auto}
"""

JS = r"""
(function(){
var T=document.body.dataset.token, boxes=[].slice.call(document.querySelectorAll('input.ok'));
var go=document.getElementById('go'), log=document.getElementById('log'), done=document.getElementById('done');
function refs(){return boxes.filter(function(b){return b.checked}).map(function(b){return b.value})}
function update(){var n=refs().length; go.disabled=n===0; go.textContent='Stamp '+n+' row'+(n===1?'':'s')+' and open PR';
  boxes.forEach(function(b){b.closest('.item').classList.toggle('done',b.checked)})}
boxes.forEach(function(b){b.addEventListener('change',update)});
function say(t){log.hidden=false; log.textContent+=t; log.scrollTop=log.scrollHeight}
go.addEventListener('click',async function(){
  var r=refs(); if(!r.length||!confirm('Stamp '+r.length+' rows as checked by you on the datasheet image, and open a PR?'))return;
  go.disabled=true; done.disabled=true; boxes.forEach(function(b){b.disabled=true});
  try{var res=await fetch('/stamp?t='+T,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refs:r})});
    var rd=res.body.getReader(), dec=new TextDecoder();
    for(;;){var c=await rd.read(); if(c.done)break; say(dec.decode(c.value,{stream:true}))}
  }catch(e){say('\n'+e+'\n')}
  var m=/^PR: (https:\/\/\S+)/m.exec(log.textContent);
  if(m){var a=document.createElement('a'); a.href=m[1]; a.textContent='Open the pull request: '+m[1];
    log.parentNode.insertBefore(a,log)}
  say('\n(the review server has stopped; run tools/review.py again for more rows)\n');
});
[].forEach.call(document.querySelectorAll('img.big'),function(i){i.addEventListener('click',function(){i.classList.toggle('full')})});
[].forEach.call(document.querySelectorAll('.loc'),function(l){
  function aim(){if(l.classList.contains('full'))return; var p=l.firstChild;
    l.scrollLeft=l.dataset.cx/100*p.offsetWidth-l.clientWidth/2; l.scrollTop=l.dataset.cy/100*p.offsetHeight-l.clientHeight/2}
  l.addEventListener('click',function(){l.classList.toggle('full'); aim()});
  l.querySelector('img').addEventListener('load',aim); aim()});
done.addEventListener('click',function(){fetch('/done?t='+T,{method:'POST'}).then(function(){say('closed\n')})});
update();
})();
"""


WARN = "⚠ "


def card_html(card):
    """The statement card (RS.statement_card): bold title, a small label/value table (the pinout: its pin table), the note
    folded under "How we read it" (open, with a warning sign, when card["note_open"]). All text is html-escaped."""
    esc = html.escape
    out = [f'<div class="card"><p><b>{esc(card["title"])}</b></p>']
    if card.get("fix"):
        out.append(f'<p class="warn">{esc(card["fix"])}</p>')
    if card.get("pins") is not None:
        out.append('<table class="stmt"><tr><th>Pin</th><th>Name</th><th>Type</th><th>Function</th></tr>'
                   + "".join("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in pin) + "</tr>" for pin in card["pins"])
                   + "</table>")
    elif card.get("lines"):
        out.append('<table class="stmt">' + "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in card["lines"])
                   + "</table>")
    if card.get("note"):
        opened = bool(card.get("note_open"))
        out.append(f'<details{" open" if opened else ""}><summary>{WARN if opened else ""}'
                   f'How we read it</summary><p>{esc(card["note"])}</p></details>')
    return "".join(out) + "</div>"


def render(title, parts, token, root, notes=(), block=None, images=None, groups=()):
    """The page: a status line per part, then per part (fewest rows to check first; released parts folded) three
    sections (Limits, Used by equations, Pins & package) of rows: statement, crops, one tick box. Images are served
    by token-protected URL (/img/<id>); each distinct file is one entry of `images` ({id: Path}), however many rows
    show it."""
    esc = html.escape
    images = {} if images is None else images

    def register(d, rel, caption):
        """(image id, None), or (None, warning html). One id per file: every row showing it uses the same URL."""
        cache = cache_dir(root, d).resolve()
        p = (cache / rel).resolve()
        if not p.is_relative_to(cache):  # never register or serve a file outside .review-cache/<Mfr>/<Value>/
            return None, f'<p class="warn">no image ({esc(caption)}): its path is outside the review cache, not shown</p>'
        if not p.is_file():
            return None, f'<p class="warn">no image ({esc(caption)}): run python3 tools/ds_review.py {esc(str(Path(d).relative_to(root)))}</p>'
        iid = hashlib.sha256(str(p).encode()).hexdigest()[:16]
        images[iid] = p
        return iid, None

    def img(d, rel, caption, big):
        iid, warn = register(d, rel, caption)
        if warn:
            return warn
        hint = " (click to enlarge)" if big else ""
        return (f'<p class="mute small">{esc(caption)}{hint}</p><img{" class=big" if big else ""} '
                f'src="/img/{iid}?t={esc(token)}" alt="{esc(caption)}">')

    def page_view(d, loc):
        """The full page of the cited sheet; the browser draws the boxes over it (percent of the page, no pixel edits),
        opened zoomed and scrolled to them; a click shows the whole page. No box: say so, plain page."""
        boxes = loc["boxes"]
        if not boxes:
            return '<p class="warn">row not located, find it on the page</p>' + img(d, loc["image"], "datasheet page", True)
        iid, warn = register(d, loc["image"], "datasheet page")
        if warn:
            return warn
        xs0, ys0 = min(b["box"][0] for b in boxes), min(b["box"][1] for b in boxes)
        xs1, ys1 = max(b["box"][2] for b in boxes), max(b["box"][3] for b in boxes)
        zoom = round(min(3.0, max(1.5, 95 / (xs1 - xs0 + 4))), 2)
        marks = "".join(
            f'<div class="box" style="left:{b["box"][0]}%;top:{b["box"][1]}%;width:{round(b["box"][2] - b["box"][0], 2)}%;'
            f'height:{round(b["box"][3] - b["box"][1], 2)}%" title="{esc(str(b.get("text", "")))}"></div>' for b in boxes)
        return (f'<p class="mute small">Datasheet page: {len(boxes)} box{"" if len(boxes) == 1 else "es"} mark where the row prints '
                "(click to show the whole page)</p>"
                f'<div class="loc" data-cx="{round((xs0 + xs1) / 2, 2)}" data-cy="{round((ys0 + ys1) / 2, 2)}">'
                f'<div class="pg" style="width:{round(zoom * 100)}%"><img src="/img/{iid}?t={esc(token)}" alt="datasheet page">'
                f"{marks}</div></div>")

    k, n = sum(p["k"] for p in parts), sum(p["n"] for p in parts)
    summary = [f"<p><b>{k} of {n} rows that matter checked</b></p>"]
    for p in parts:
        text = f"{p['line']}. Released for {block or 'these rows'}." if p["released"] else p["line"]
        summary.append(f'<p><a href="#part-{esc(p["value"])}">{esc(text)}</a></p>')
    body = [f"<h1>{esc(title)}</h1>", '<div id="summary">' + "\n".join(summary) + "</div>",
            "<p>For each row, compare the statement with the datasheet image: values and sign, the right column "
            "(table header), conditions, temperature scope, unit, and whether the library uses the row that way. Tick "
            "only rows whose statement matches the image; leave wrong or unclear rows unticked. Then press the button "
            "at the bottom.</p>"]
    body += [f'<p class="mute small">{esc(x)}</p>' for x in notes]
    if groups:  # capacitor-series catalogs: one group per dielectric, stamped as a group (docs/spec/capacitor.md)
        body.append("<h2>Catalog groups (capacitor series)</h2>")
        body += [group_html(g) for g in groups]
    shown_parts = sorted((p for p in parts if p["items"] and not p["released"]), key=lambda p: (p["n"] - p["k"], p["value"]))  # the whole part's needs-check count
    folded = [p for p in parts if p not in shown_parts]
    for p in shown_parts:
        body.append(f'<h2 id="part-{esc(p["value"])}">{esc(p["line"])}</h2>')
        for section in SECTIONS:
            group = [i for i in p["items"] if i["section"] == section]
            if not group:
                continue
            body.append(f"<h3>{esc(section)} ({len(group)})</h3>")
            for i in group:
                out = [f'<div class="item" id="row-{esc(i["ref"])}"><b>{esc(i["part"])}</b> · {esc(i["key"])}<br>']
                if i["tier"] in TICKABLE:
                    out.append(f'<label class="pick"><input type="checkbox" class="ok" value="{esc(i["ref"])}">'
                               "matches the datasheet</label>")
                if i.get("card"):
                    out.append(card_html(i["card"]))
                text, url = i["page"]
                out.append(f'<p class="small">Datasheet: {esc(text)}'
                           + (f'; <a href="{esc(url)}" target="_blank" rel="noreferrer noopener">open the page</a>' if url else "")
                           + "</p>")
                if i["why"]:
                    out.append(f'<p class="{"warn" if i["tier"] in ("fix", "none") else "mute small"}">{esc(i["why"])}</p>')
                if i.get("locate"):
                    out.append(page_view(p["dir"], i["locate"]))
                out += [img(p["dir"], rel, cap, cap in ("table or page", "full page", "evidence the stamp records") or cap.startswith("pin table page"))
                        for rel, cap in i["images"]]
                if i["toml"]:
                    out.append(f"<details><summary>Full TOML</summary><pre>{esc(i['toml'])}</pre></details>")
                out.append("</div>")
                body.append("\n".join(out))
        if p["unlocated"]:
            body.append(f'<details><summary>Reference, not checked: {len(p["unlocated"])} row(s) without a table or figure '
                        'location</summary>')
            for i in p["unlocated"]:
                body.append(f'<div class="item" id="row-{esc(i["ref"])}"><b>{esc(i["part"])}</b> · {esc(i["key"])}<br>'
                            + (card_html(i["card"]) if i.get("card") else "")
                            + f'<p class="mute small">{esc(i["why"])}</p>'
                            + (f"<details><summary>Full TOML</summary><pre>{esc(i['toml'])}</pre></details>" if i["toml"] else "")
                            + "</div>")
            body.append("</details>")
        ck, ref = p["checked"], p["reference"]
        if ck or ref:
            body.append(f"<details><summary>Already checked: {len(ck)} rows; other rows (reference): {len(ref)} rows</summary>"
                        + (f"<p>Checked: {esc(', '.join(f'{k} ({w}, {d})' for k, w, d in ck))}</p>" if ck else "")
                        + (f"<p>Reference: {esc(', '.join(ref))}</p>" if ref else "") + "</details>")
    if folded:
        body.append(f"<details><summary>Released parts or parts with nothing to check ({len(folded)})</summary>"
                    + "".join(f'<p id="part-{esc(p["value"])}">{esc(p["line"])}</p>' for p in folded) + "</details>")
    body.append('<div id="bar"><button id="go" disabled>Stamp 0 rows and open PR</button>'
                '<button id="done">Done (stop the server)</button><pre id="log" hidden></pre></div>')
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>Review rows</title><style>{CSS}</style></head><body data-token=\"{esc(token)}\">\n"
            + "\n".join(body) + f"\n<script>{JS}</script>\n</body></html>\n")


def branch_name(values, login, day, taken):
    base = f"review/{'-'.join(v.lower() for v in values)}-{login.lower()}-{day.strftime('%Y%m%d')}"
    base = re.sub(r"[^a-z0-9._/-]", "-", base)
    n, name = 1, base
    while name in taken:
        n += 1
        name = f"{base}-{n}"
    return name


def publish(root, dirs, refs, run, emit, today=None, python=sys.executable, groups=None):
    """Stamp `refs` on a new branch from origin/main and open the PR. run(cmd) -> (rc, output), in the library root;
    emit(line) shows progress. Returns 0 = PR opened, 1 = stopped (the last lines say what was left)."""
    def sh(*cmd):
        emit("$ " + shlex.join(cmd))
        return run(list(cmd))

    def stop(msg, out=""):
        emit(*[ln for ln in out.splitlines() if ln.strip()][:8])
        emit(f"stopped: {msg}")
        return 1

    rc, out = sh("git", "status", "--porcelain")
    if rc:
        return stop("git status failed", out)
    dirty = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("??")]
    if dirty:
        return stop("the library has uncommitted changes (" + ", ".join(ln[3:] for ln in dirty[:5]) + "). Commit or "
                    "stash them, then run tools/review.py again. Nothing was changed.")
    rc, prev = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    prev = prev.strip()
    if rc or not prev:
        return stop("cannot read the current branch. Nothing was changed.", prev)
    if prev == "HEAD":
        rc, prev = sh("git", "rev-parse", "HEAD")
        prev = prev.strip()
    rc, login = sh("gh", "api", "user", "--jq", ".login")
    login = login.strip()
    if rc or not S.WHO_RE.match(login):
        return stop(f"no GitHub login from gh ({S.GH_FIX.split(',')[0]}). Nothing was changed.", login)
    rc, out = sh("git", "fetch", "origin")
    if rc:
        return stop("git fetch origin failed. Nothing was changed.", out)
    rc, out = sh("git", "for-each-ref", "--format=%(refname)", "refs/heads/review/", "refs/remotes/origin/review/")
    taken = {re.sub(r"^refs/(heads|remotes/origin)/", "", ln.strip()) for ln in out.splitlines() if ln.strip()}
    values = sorted({Path(d).name for d in dirs if any(r.startswith(Path(d).name + ":") for r in refs)})
    branch = branch_name(values, login, today or datetime.date.today(), taken)
    rc, out = sh("git", "switch", "-c", branch, "origin/main")
    if rc:
        return stop(f"could not create branch {branch}. Nothing was changed.", out)
    row_refs = [r for r in refs if ":group:" not in r]
    group_refs = [r for r in refs if ":group:" in r]
    rc, out = 0, ""
    if row_refs:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", prefix="review-rows-", delete=False) as f:
            f.write("\n".join(row_refs) + "\n")
        try:
            rc, out = sh(python, "tools/stamp.py", "--who", login, "--from", f.name)
        finally:
            os.unlink(f.name)
        emit(*out.strip().splitlines())
    for ref in ([] if rc else group_refs):  # a catalog group: the export check stamps exactly the ticked dielectric
        info = (groups or {}).get(ref)
        if info is None or info["export"] is None:
            emit(f"{ref}: no export file for this group")
            rc = 1
            break
        diel = ref.partition(":group:")[2]
        rc, out = sh(python, "-m", "lib.catalog", "export-check", str(info["export"]), str(info["dir"]), "--stamp", login,
                     "--groups", diel)
        emit(*out.strip().splitlines())
        if rc:
            break
    if rc:
        r1, o1 = sh("git", "switch", prev)
        r2, o2 = sh("git", "branch", "-D", branch)
        if r1 or r2:
            return stop(f"stamping refused, and the cleanup failed ({(o1 + o2).strip()}): you are on "
                        f"{'?' if r1 else prev}; delete branch {branch} yourself. Nothing was stamped.")
        return stop(f"stamping refused (above). Back on {prev}, branch {branch} deleted. Nothing was stamped.")
    rel = [str(Path(d).relative_to(root)) for d in dirs if Path(d).name in values]
    rc, out = sh(python, "tools/verify.py", "--regen", *rel)
    if rc:
        return stop(f"verify failed (above). The stamps are on branch {branch}, not committed: fix and commit them, "
                    f"or discard them with git restore . && git switch {prev}.", out)
    rc, out = sh("git", "status", "--porcelain")
    allowed = {f"{r}/{n}" for r in rel for n in ("component.toml", "review/review.toml", "review/export_check.toml", "README.md")}
    allowed.add("README.md")  # the top-level status table, rewritten by verify.py --regen (lib.readme.update_top)
    changed = [ln[3:] for ln in out.splitlines() if ln.strip() and not ln.startswith("??")]
    extra = [p for p in changed if p not in allowed]
    if rc or extra or not changed:
        return stop(f"unexpected changes ({', '.join(extra) or 'none'}): nothing committed, branch {branch} left for you.", out)
    title = f"{', '.join(values)}: human check of {len(refs)} rows"
    rows = "\n".join(f"- {r}" for r in refs)
    rc, out = sh("git", "add", "--", *sorted(changed))
    if not rc:
        rc, out = sh("git", "commit", "-m", f"{title}\n\nRows checked on the datasheet page image (tools/review.py):\n{rows}")
    if rc:
        return stop(f"commit failed: the stamps are on branch {branch}, not committed.", out)
    rc, out = sh("git", "push", "-u", "origin", branch)
    if rc:
        return stop(f"push failed: committed on {branch}; run git push -u origin {branch}, then gh pr create.", out)
    body = f"Rows checked on the datasheet page image with tools/review.py:\n\n{rows}\n"
    rc, out = sh("gh", "pr", "create", "--base", "main", "--head", branch, "--title", title, "--body", body)
    url = next((ln.strip() for ln in reversed(out.splitlines()) if ln.strip().startswith("https://")), None)
    if rc or not url:
        return stop(f"gh pr create failed: {branch} is pushed; open the PR on GitHub.", out)
    emit(f"PR: {url}")
    return 0


def real_runner(root):
    def run(cmd):
        try:
            p = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        except OSError as e:
            return 127, f"cannot start {cmd[0]}: {e}"
        return p.returncode, p.stdout + p.stderr
    return run


def dry_runner():
    """Runs nothing: answers each command as a clean, successful run would (git status is clean, then lists the
    files stamp.py and verify would change in the parts given to verify)."""
    state = {"parts": None}

    def run(cmd):
        out = ""
        if len(cmd) > 2 and cmd[1] == "tools/verify.py":
            state["parts"] = cmd[3:]
        elif cmd[:3] == ["git", "status", "--porcelain"] and state["parts"]:
            out = "".join(f" M {d}/{n}\n" for d in state["parts"] for n in ("component.toml", "review/review.toml", "README.md"))
        elif cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
            out = "main"
        elif cmd[:2] == ["gh", "api"]:
            out = "your-login"
        elif cmd[:3] == ["gh", "pr", "create"]:
            out = "https://github.com/OWNER/AgentEDA-Parts/pull/0"
        return 0, out
    return run


class App:
    """One page, one stamp job. GET /?t=<token> serves the page; POST /stamp?t=<token> (JSON {"refs": [...]}, only
    tickable refs) streams the job's lines; POST /done?t=<token> stops. Wrong token, Host or Origin: 403."""

    def __init__(self, page, tickable, job, images=None):
        self.page, self.tickable, self.job, self.images = page, set(tickable), job, images or {}
        self.token = secrets.token_urlsafe(24)
        self.lock, self.started, self.finished = threading.Lock(), False, threading.Event()
        self.rc = 1
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler())
        self.origin = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.url = f"{self.origin}/?t={self.token}"

    def handler(self):
        app = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, text, ctype="text/plain; charset=utf-8", cache="no-store"):
                b = text if isinstance(text, bytes) else text.encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", cache)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(b)

            def allowed(self, post):
                u = urllib.parse.urlsplit(self.path)
                t = urllib.parse.parse_qs(u.query).get("t", [""])[0]
                ok = secrets.compare_digest(t, app.token) and self.headers.get("Host") == app.origin[7:]
                if post:
                    ok = ok and self.headers.get("Origin", app.origin) == app.origin
                if not ok:
                    self.reply(403, "forbidden")
                return u.path if ok else None

            def do_GET(self):
                path = self.allowed(False)
                if path == "/":
                    self.reply(200, app.page.replace("{TOKEN}", app.token), "text/html; charset=utf-8")
                elif path and path.startswith("/img/") and path[5:] in app.images:
                    try:
                        data = app.images[path[5:]].read_bytes()
                    except OSError:
                        return self.reply(404, "not found")
                    self.reply(200, data, "image/png", "private, max-age=3600")  # one fetch per image file
                elif path:
                    self.reply(404, "not found")

            def do_POST(self):
                path = self.allowed(True)
                if path == "/done":
                    with app.lock:
                        if app.started:
                            return self.reply(409, "a stamp run is in progress or done; the server stops on its own")
                    self.reply(200, "stopped")
                    app.finished.set()
                    return
                if path != "/stamp":
                    if path:
                        self.reply(404, "not found")
                    return
                n = int(self.headers.get("Content-Length") or 0)
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json" or not 0 < n <= MAX_BODY:
                    return self.reply(400, "expected a JSON body")
                try:
                    refs = json.loads(self.rfile.read(n))["refs"]
                except (ValueError, KeyError, TypeError):
                    return self.reply(400, "expected {\"refs\": [...]}")
                if (not isinstance(refs, list) or not refs or len(set(map(str, refs))) != len(refs)
                        or not all(isinstance(r, str) and r in app.tickable for r in refs)):
                    return self.reply(400, "refs must be distinct rows shown with a tick box")
                with app.lock:
                    if app.started:
                        return self.reply(409, "a stamp run already started; run tools/review.py again")
                    app.started = True
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()

                def emit(*lines):
                    for ln in lines:
                        try:
                            self.wfile.write((ln + "\n").encode())
                            self.wfile.flush()
                        except OSError:
                            pass
                        print(ln, flush=True)
                try:
                    app.rc = app.job(refs, emit)
                except Exception as e:  # the page must see why it stopped
                    emit(f"stopped: {type(e).__name__}: {e}")
                    app.rc = 1
                app.finished.set()
        return H

    def serve(self):
        """Serve until the job finishes or Done is pressed; returns the exit code."""
        t = threading.Thread(target=self.server.serve_forever, daemon=True)
        t.start()
        self.finished.wait()
        self.server.shutdown()
        self.server.server_close()
        return 0 if self.rc == 0 or not self.started else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tools/review.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("values", nargs="*", metavar="Value", help="component directory name: show every row of the part")
    ap.add_argument("--block", help="circuit block name: show the rows its analysis reads")
    ap.add_argument("--list-blocks", action="store_true", help="list the blocks --block can read (blocks repo: --blocks-repo) "
                    "and exit; no Value, no --block")
    ap.add_argument("--blocks-repo", help="circuit-blocks checkout (default: ../ina229 if it exists, else ../circuit-blocks)")
    ap.add_argument("--dry-run", action="store_true", help="for a person trying the page: show the git, gh, stamp and "
                    "ds_review commands, run none (agents don't run review.py)")
    ap.add_argument("--no-browser", action="store_true", help="print the page URL instead of opening a browser")
    ap.add_argument("--root", default=ROOT, help="library repo root (default: this repo)")
    a = ap.parse_args(argv)
    if os.environ.get("CLAUDECODE") and not a.dry_run:
        print(AGENT)
        return 1
    if a.block and a.values:
        ap.error("give --block <Block> or <Value> ..., not both (no argument: every part)")
    if a.list_blocks and (a.block or a.values):
        ap.error("--list-blocks takes no --block and no Value")
    root = Path(a.root).resolve()
    if a.list_blocks:
        repo = Path(a.blocks_repo).resolve() if a.blocks_repo else default_blocks_repo(root)
        print(f"blocks repo: {repo}")
        names = list_blocks(repo)
        if not names:
            print(f"no block has docs/design-analysis/library-inputs.json under {repo / 'benches'} "
                  "(run the block's analysis.py first)")
        for name in names:
            print(name)
        return 0
    notes = []
    try:
        if a.block:
            repo = Path(a.blocks_repo).resolve() if a.blocks_repo else default_blocks_repo(root)
            notes.append(f"Block {a.block}, blocks repo {repo}.")
            used = RS.used_rows(root, block_inputs(repo, a.block))
            title = f"Rows to check: {a.block}"
        else:
            used = {}
            for v in a.values:
                d, _ = RS.component_dir(root, v)
                if d is None:
                    raise ValueError(f"no single components/*/{v}/")
                used[d] = None
            if not a.values:
                used = {d: None for d in all_parts(root)}
            title = "Rows to check: " + (", ".join(a.values) or "every part")
    except (ValueError, OSError) as e:
        print(f"refused: {e}")
        return 1
    for ln in ensure_cache(root, list(used), dry_run=a.dry_run):
        print(ln)
    parts = build_model(root, used)
    for p in parts:
        print(p["line"])
    if a.dry_run:
        notes.append("Dry run: the button shows the commands and runs none of them.")
    groups = build_groups(root, list(used))
    tickable = [i["ref"] for p in parts for i in p["items"] if i["tier"] in TICKABLE] + [g["ref"] for g in groups if g["tickable"]]
    dirs = [p["dir"] for p in parts]
    run = dry_runner() if a.dry_run else real_runner(root)
    def job(refs, emit):
        if a.dry_run:
            emit("(dry run: each command is shown, none is run)")
        return publish(root, dirs, refs, run, emit, groups={g["ref"]: g for g in groups if g["ref"]})
    images = {}
    app = App(render(title, parts, "{TOKEN}", root, notes, a.block, images, groups), tickable, job, images)
    print(f"review page: {app.url}\n(stops after the stamp run, or press Done; Ctrl-C to quit)", flush=True)
    if not a.no_browser:
        webbrowser.open(app.url)
    try:
        return app.serve()
    except KeyboardInterrupt:
        return 1


if __name__ == "__main__":
    sys.exit(main())
