#!/usr/bin/env python3
"""Check datasheet rows on one local page, then stamp them and open the PR with one button. Run by the PERSON who checks.

Usage (library repo root):
  python3 tools/review.py --block <Block> [--blocks-repo DIR]   the rows a circuit block reads
  python3 tools/review.py <Value> [<Value> ...]                 every row of these parts
--block reads <blocks repo>/benches/<Block>/docs/design-analysis/library-inputs.json (written by the block's
analysis.py). Default blocks repo: ../ina229 if it exists, else ../circuit-blocks.

Each row is checked (a current human stamp), needs check, or reference (not used by the block): docs/spec/review.md
"Human view". The page (127.0.0.1, random port, random token in the URL) shows per part "<Value>: k of n used rows
checked" and only the rows to check, easiest first, with the evidence crops from .review-cache/ (tools/ds_review.py
runs first when a part has no cache; it needs the local PDF). Tick the rows that match the datasheet image and press
"Stamp N rows and open PR". With the library tree clean (untracked files allowed) it runs, showing each command:
git fetch origin; git switch -c review/<parts>-<login>-<YYYYMMDD>[-n] origin/main; tools/stamp.py --from <list>
(a refusal switches back and deletes the new branch); tools/verify.py --regen <parts> (a FAIL leaves the branch,
uncommitted, for you); git commit of those parts' component.toml, review/review.toml and README.md; git push -u origin
<branch>; gh pr create. Then the server exits. --dry-run is for a person trying the page; agents don't run review.py
(.claude/settings.json denies it; the CLAUDECODE refusal lets only --dry-run through, so the tests can drive it).
Exit 0 = PR opened (or Done pressed), 1 = refused or a step failed.
"""

import argparse
import base64
import datetime
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
from lib.readme import shown  # noqa: E402  (min/typ/max as the README prints them)

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


def classify(root, d, key, ledger, params):
    """(tier, why, images) of one row that needs a check; images = [(cache-relative path, caption)]."""
    if key not in params:
        return "none", ("variant row: variants.toml rows are not reviewed" if key.startswith("variant.")
                        else "catalog row (catalog.csv): not reviewed"), []
    _, _, why = S.check_row(root, d.name, key)
    if why:
        return "fix", why, []
    row = ledger["row"][key]
    if row.get("crop") == "auto":
        imgs = [(row.get("header_image"), "table header"), (row.get("image"), "row"), (row.get("foot_image"), "footnotes")]
        tier = "tier 1" if row.get("status") == "AGREE_TEXT_CHECK" else "tier 2"
        return tier, row.get("reason", ""), [(p, c) for p, c in imgs if p]
    cache = cache_dir(root, d)
    imgs = [(row["image"], "table or page")] if row.get("image") and (cache / row["image"]).is_file() else []
    page = f"evidence/page_p{row.get('pdf_page')}.png"
    if row.get("pdf_page") and page != row.get("image") and (cache / page).is_file():
        imgs.append((page, "full page"))
    return ("tier 3" if imgs else "page"), row.get("reason", ""), imgs


def page_link(ledger, part, row):
    """(text, url or None): local file, PDF page and printed page; url#page=N when the URL is a direct PDF link."""
    inp = ledger.get("inputs", {})
    main = Path(inp.get("datasheet_file") or part.get("datasheet_file") or "").name
    sheet = (row or {}).get("sheet") or main
    pdf_page, printed = (row or {}).get("pdf_page"), (row or {}).get("printed_page")
    text = f"docs/datasheets/{sheet or 'n/a'}, PDF page {pdf_page or 'n/a'}" + (f" (printed page {printed})" if printed else "")
    url = inp.get("datasheet_url") or part.get("datasheet_url")
    if not url or sheet != main:
        return text, None
    direct = url.lower().split("?")[0].endswith(".pdf") or "/lit/" in url
    return text, f"{url}#page={pdf_page}" if direct and pdf_page else url


def check_line(t):
    """'Check: max 0.1 W (Rated power at 70 degC); <cite>': the committed numbers in plain form."""
    vals = ", ".join(f"{f} {shown(t, f)}" for f in ("min", "typ", "max") if shown(t, f))
    name = f" ({t['name']})" if t.get("name") else ""
    return f"Check: {vals or 'no number'} {t.get('unit', '')}".rstrip() + f"{name}; {t.get('cite', 'no cite')}"


def build_model(root, used_by_dir):
    """Per part (sorted by name): dict with dir, value, status line, released, items (rows to check), checked
    [(key, login, date)] and reference keys. used_by_dir: {dir: set of rows, or None = use unknown}."""
    parts = []
    for d in sorted(used_by_dir, key=lambda p: Path(p).name):
        d = Path(d)
        used = used_by_dir[d]
        status = RS.statuses(d, used)
        line, released = RS.summary(d.name, status, used is not None)
        ledger, comp = read_toml(d / "review" / "review.toml"), read_toml(d / "component.toml")
        params, done = comp.get("param", {}), RS.checked_rows(d)
        items = []
        for key, s in status.items():
            if s != RS.NEEDS:
                continue
            tier, why, imgs = classify(root, d, key, ledger, params)
            row = ledger.get("row", {}).get(key)
            items.append({"ref": f"{d.name}:{key}", "key": key, "tier": tier, "why": why, "images": imgs,
                          "name": params.get(key, {}).get("name", ""), "part": d.name,
                          "check": check_line(params[key]) if key in params else "",
                          "toml": toml_block(d / "component.toml", f"[param.{key}]") if key in params else "",
                          "page": page_link(ledger, comp.get("part", {}), row if isinstance(row, dict) else None)})
        order = {t: n for n, (t, _) in enumerate(TIERS)}
        items.sort(key=lambda i: (order[i["tier"]], i["key"]))
        rows = [s for s in status.values() if s != RS.REFERENCE]
        parts.append({"dir": d, "value": d.name, "line": line, "released": released, "items": items,
                      "k": rows.count(RS.CHECKED), "n": len(rows), "used_known": used is not None,
                      "checked": [(k, *done[k]) for k, s in status.items() if s == RS.CHECKED],
                      "reference": [k for k, s in status.items() if s == RS.REFERENCE]})
    return parts


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
pre{background:var(--code);padding:8px;overflow-x:auto;font-size:13px;white-space:pre-wrap}
img{max-width:100%;display:block;margin:4px 0;background:#fff;border:1px solid var(--line)}
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
done.addEventListener('click',function(){fetch('/done?t='+T,{method:'POST'}).then(function(){say('closed\n')})});
update();
})();
"""


def render(title, parts, token, root, notes=(), block=None):
    """The page: a summary box (one line per part, overall line), then every part's rows to check in one list,
    easiest first across parts, then per part its checked and reference rows collapsed."""
    esc, cache = html.escape, {}

    def img(d, rel, caption, big):
        p = cache_dir(root, d) / rel
        if not p.is_file():
            return f'<p class="warn">no image ({esc(caption)}): run python3 tools/ds_review.py {esc(str(Path(d).relative_to(root)))}</p>'
        if p not in cache:
            cache[p] = base64.b64encode(p.read_bytes()).decode()
        hint = " (click to enlarge)" if big else ""
        return (f'<p class="mute small">{esc(caption)}{hint}</p><img{" class=big" if big else ""} '
                f'src="data:image/png;base64,{cache[p]}" alt="{esc(caption)}">')

    def count(part, tiers):
        return sum(1 for i in part["items"] if i["tier"] in tiers)

    known = all(p["used_known"] for p in parts)
    k, n = sum(p["k"] for p in parts), sum(p["n"] for p in parts)
    summary = [f"<p><b>{k} of {n} {'used rows' if known else 'rows'} checked</b></p>"]
    for p in parts:
        bits = [f"{count(p, ('tier 1', 'tier 2'))} quick (row image)", f"{count(p, ('tier 3', 'page'))} need the page"]
        if count(p, ("fix", "none")):
            bits.append(f"{count(p, ('fix', 'none'))} cannot be ticked yet")
        text = f"{p['line']}; " + ", ".join(bits)
        if p["released"]:
            text = f"{p['line']}. Released for {block or 'these rows'}."
        summary.append(f'<p><a href="#part-{esc(p["value"])}">{esc(text)}</a></p>')
    body = [f"<h1>{esc(title)}</h1>", '<div id="summary">' + "\n".join(summary) + "</div>",
            "<p>Rows are listed easiest first. For each row, compare the <b>Check</b> line with the datasheet image: "
            "value and sign, unit, the right column (table header), conditions, footnotes. Tick only rows you "
            "checked on the image; leave wrong or unclear rows unticked. Then press the button at the bottom.</p>"]
    body += [f'<p class="mute small">{esc(x)}</p>' for x in notes]
    items = [(p, i) for p in parts for i in p["items"]]
    for tier, heading in TIERS:
        group = [(p, i) for p, i in items if i["tier"] == tier]
        if not group:
            continue
        body.append(f"<h2>{esc(heading)} ({len(group)})</h2>")
        for p, i in group:
            out = [f'<div class="item" id="row-{esc(i["ref"])}"><b>{esc(i["part"])}</b> · {esc(i["key"])}<br>']
            if tier in TICKABLE:
                out.append(f'<label class="pick"><input type="checkbox" class="ok" value="{esc(i["ref"])}">'
                           "matches the datasheet</label>")
            if i["check"]:
                out.append(f"<p><b>{esc(i['check'])}</b></p>")
            text, url = i["page"]
            out.append(f'<p class="small">Datasheet: {esc(text)}'
                       + (f'; <a href="{esc(url)}" target="_blank" rel="noreferrer noopener">open the page</a>' if url else "")
                       + "</p>")
            if i["why"]:
                out.append(f'<p class="{"warn" if tier in ("fix", "none") else "mute small"}">{esc(i["why"])}</p>')
            out += [img(p["dir"], rel, cap, cap in ("table or page", "full page")) for rel, cap in i["images"]]
            if i["toml"]:
                out.append(f"<details><summary>Full TOML</summary><pre>{esc(i['toml'])}</pre></details>")
            out.append("</div>")
            body.append("\n".join(out))
    body.append("<h2>Parts</h2>")
    for p in parts:
        ck, ref = p["checked"], p["reference"]
        body.append(f'<h3 id="part-{esc(p["value"])}">{esc(p["line"])}'
                    + (f". Released for {esc(block or 'these rows')}." if p["released"] else "") + "</h3>")
        if p["items"]:
            body.append("<p class=small>To check: " + ", ".join(
                f'<a href="#row-{esc(i["ref"])}">{esc(i["key"])}</a>' for i in p["items"]) + "</p>")
        if ck or ref:
            body.append(f"<details><summary>Already checked: {len(ck)} rows; not used by this block: {len(ref)} rows</summary>"
                        + (f"<p>Checked: {esc(', '.join(f'{k} ({w}, {d})' for k, w, d in ck))}</p>" if ck else "")
                        + (f"<p>Not used: {esc(', '.join(ref))}</p>" if ref else "") + "</details>")
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


def publish(root, dirs, refs, run, emit, today=None, python=sys.executable):
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
    with tempfile.NamedTemporaryFile("w", suffix=".txt", prefix="review-rows-", delete=False) as f:
        f.write("\n".join(refs) + "\n")
    try:
        rc, out = sh(python, "tools/stamp.py", "--who", login, "--from", f.name)
    finally:
        os.unlink(f.name)
    emit(*out.strip().splitlines())
    if rc:
        r1, o1 = sh("git", "switch", prev)
        r2, o2 = sh("git", "branch", "-D", branch)
        if r1 or r2:
            return stop(f"stamp.py refused, and the cleanup failed ({(o1 + o2).strip()}): you are on "
                        f"{'?' if r1 else prev}; delete branch {branch} yourself. Nothing was stamped.")
        return stop(f"stamp.py refused (above). Back on {prev}, branch {branch} deleted. Nothing was stamped.")
    rel = [str(Path(d).relative_to(root)) for d in dirs if Path(d).name in values]
    rc, out = sh(python, "tools/verify.py", "--regen", *rel)
    if rc:
        return stop(f"verify failed (above). The stamps are on branch {branch}, not committed: fix and commit them, "
                    f"or discard them with git restore . && git switch {prev}.", out)
    rc, out = sh("git", "status", "--porcelain")
    allowed = {f"{r}/{n}" for r in rel for n in ("component.toml", "review/review.toml", "README.md")}
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
            out = "https://github.com/OWNER/zener-library/pull/0"
        return 0, out
    return run


class App:
    """One page, one stamp job. GET /?t=<token> serves the page; POST /stamp?t=<token> (JSON {"refs": [...]}, only
    tickable refs) streams the job's lines; POST /done?t=<token> stops. Wrong token, Host or Origin: 403."""

    def __init__(self, page, tickable, job):
        self.page, self.tickable, self.job = page, set(tickable), job
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

            def reply(self, code, text, ctype="text/plain; charset=utf-8"):
                b = text.encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store")
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
    ap.add_argument("--blocks-repo", help="circuit-blocks checkout (default: ../ina229 if it exists, else ../circuit-blocks)")
    ap.add_argument("--dry-run", action="store_true", help="for a person trying the page: show the git, gh, stamp and "
                    "ds_review commands, run none (agents don't run review.py)")
    ap.add_argument("--no-browser", action="store_true", help="print the page URL instead of opening a browser")
    ap.add_argument("--root", default=ROOT, help="library repo root (default: this repo)")
    a = ap.parse_args(argv)
    if os.environ.get("CLAUDECODE") and not a.dry_run:
        print(AGENT)
        return 1
    if bool(a.block) == bool(a.values):
        ap.error("give --block <Block> or one or more <Value>, not both")
    root = Path(a.root).resolve()
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
            title = "Rows to check: " + ", ".join(a.values)
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
    tickable = [i["ref"] for p in parts for i in p["items"] if i["tier"] in TICKABLE]
    dirs = [p["dir"] for p in parts]
    run = dry_runner() if a.dry_run else real_runner(root)
    def job(refs, emit):
        if a.dry_run:
            emit("(dry run: each command is shown, none is run)")
        return publish(root, dirs, refs, run, emit)
    app = App(render(title, parts, "{TOKEN}", root, notes, a.block), tickable, job)
    print(f"review page: {app.url}\n(stops after the stamp run, or press Done; Ctrl-C to quit)", flush=True)
    if not a.no_browser:
        webbrowser.open(app.url)
    try:
        return app.serve()
    except KeyboardInterrupt:
        return 1


if __name__ == "__main__":
    sys.exit(main())
