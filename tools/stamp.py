#!/usr/bin/env python3
"""Write a person's human stamp into checked rows. Run by the PERSON who checked the evidence; by convention agents
never run it on real data (docs/spec/review.md "Runs").

Usage (repo root):
  python3 tools/stamp.py [--who <github-login>] <Value>:<key> [...] [--from FILE] [--root R]
--who defaults to your GitHub login (`gh api user --jq .login`); library CI requires it to equal the PR author.
<Value> is the component directory name (components/<Mfr>/<Value>/), <key> the [param.<key>] row; FILE holds one
<Value>:<key> per line (blank lines and # comments ignored).

Each row gets `verified = "human:<github-login> <YYYY-MM-DD> page-image ds_review <pdf-sha256[:12]> row <row-hash[:12]>"`
(replacing any stamp; row hash as review.toml's). All or nothing; refused: unknown component or key, unreadable TOML,
no review/review.toml row, ledger `hash` != the row's hash (re-run tools/verify.py), status DISAGREE or NOT_FOUND, a
missing or changed local cache image (.review-cache/, image_sha256), a local PDF missing or not the ledger's `sheets`
SHA-256, or CLAUDECODE set (an agent's shell). Line endings and a comment on a replaced verified line are kept.
Exit 0 = written, 1 = refused. Then run tools/verify.py on the part.
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ds_review import row_hash, sha256_file  # noqa: E402  (the ledger's own hash, so the comparison is exact)
from lib.component import GITHUB_LOGIN  # noqa: E402  (the stamp's name part, as lib checks it)

WHO_RE = re.compile(f"^{GITHUB_LOGIN}\\Z")
AGENT = "refused: running inside Claude Code (CLAUDECODE is set); a person must run stamp.py in their own shell"
GH_FIX = "run `gh auth login`, or pass --who <github-login>"


def github_login(timeout=20):
    """(login, None) from `gh api user --jq .login`, else (None, why)."""
    try:
        r = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, f"gh is not installed: {GH_FIX}"
    except subprocess.TimeoutExpired:
        return None, f"gh api user timed out: {GH_FIX}"
    login = r.stdout.strip()
    if r.returncode or not login:
        detail = (r.stderr.strip().splitlines() or ["no login printed"])[-1]
        return None, f"gh api user failed ({detail}): {GH_FIX}"
    return login, None
REFUSE_STATUS = ("DISAGREE", "NOT_FOUND")
VERIFIED_LINE = re.compile(r'^(\s*verified\s*=\s*)("[^"\\]*"|\'[^\']*\')(.*)$', re.S)


def component_dir(root, value):
    found = sorted(p.parent for p in (Path(root) / "components").glob(f"*/{value}/component.toml"))
    return found[0] if len(found) == 1 else None


def check_row(root, value, key):
    """(component dir, stamp suffix "<pdf12> row <row12>", None) for a row that may be stamped, else (None, None, reason)."""
    d = component_dir(root, value)
    if d is None:
        return None, None, f"no component directory components/*/{value}/ (use the directory name, not a variant)"
    try:
        table = tomllib.loads((d / "component.toml").read_bytes().decode()).get("param", {}).get(key)
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        return None, None, f"{d.name}/component.toml is not valid TOML ({e})"
    if table is None:
        return None, None, f"no [param.{key}] in {d.name}/component.toml"
    try:
        with open(d / "review" / "review.toml", "rb") as f:
            ledger = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return None, None, "no readable review/review.toml (no review record)"
    row = ledger.get("row", {}).get(key)
    if not isinstance(row, dict) or not row.get("hash"):
        return None, None, "no review record for this row"
    h = row_hash(table)
    if row["hash"] != h:
        return None, None, "review record is older than the committed row: run tools/verify.py and check again"
    if row.get("status") in REFUSE_STATUS:
        return None, None, f"status {row['status']}: fix the row before stamping"
    cache = Path(root) / ".review-cache" / d.relative_to(Path(root) / "components")
    img = cache / row["image"] if row.get("image") else None
    if img is None or not img.is_file():
        return None, None, f"no local evidence image for this row: run python3 tools/ds_review.py {d.relative_to(root)}"
    if sha256_file(img) != row.get("image_sha256"):
        return None, None, "evidence image differs from the ledger's image_sha256: run tools/verify.py"
    inp = ledger.get("inputs", {})
    sheet = row.get("sheet") or Path(inp.get("datasheet_file", "")).name
    want = inp.get("sheets", {}).get(sheet)
    dsf = inp.get("datasheet_file", "")
    pdf = Path(root) / (dsf if dsf and sheet == Path(dsf).name else f"docs/datasheets/{sheet}")
    if not sheet or not want:
        return None, None, "ledger names no PDF SHA-256 for this row's sheet"
    if not pdf.is_file():
        return None, None, f"local PDF {pdf.relative_to(root)} missing"
    if sha256_file(pdf) != want:
        return None, None, f"{pdf.relative_to(root)} differs from the PDF the evidence was rendered from (SHA-256)"
    return d, f"{want[:12]} row {h[:12]}", None


def set_stamp(text, key, stamp):
    """component.toml text with `verified = "<stamp>"` in [param.<key>] (replaced keeping any trailing comment and the
    line ending, else inserted after `cite`). ValueError when the edit is not exactly that."""
    lines = text.split("\n")  # a "\r" stays at the end of its line
    start = next((i for i, ln in enumerate(lines) if ln.strip() == f"[param.{key}]"), None)
    if start is None:
        raise ValueError(f"[param.{key}] header not found")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    span = range(start + 1, end)
    old = next((i for i in span if re.match(r"\s*verified\s*=", lines[i])), None)
    if old is not None:
        m = VERIFIED_LINE.match(lines[old])
        if not m:
            raise ValueError(f"[param.{key}]: verified line is not a one-line string")
        lines[old] = f'{m.group(1)}"{stamp}"{m.group(3)}'
    else:
        cite = next((i for i in span if re.match(r"\s*cite\s*=", lines[i])), None)
        if cite is None:
            raise ValueError(f"[param.{key}] has no cite line")
        eq = lines[cite].index("=")
        cr = "\r" if lines[cite].endswith("\r") else ""
        lines.insert(cite + 1, ("verified".ljust(eq) if eq > len("verified") else "verified ") + f'= "{stamp}"{cr}')
    out = "\n".join(lines)
    try:
        before, after = tomllib.loads(text), tomllib.loads(out)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"not valid TOML ({e})")
    before["param"][key]["verified"] = stamp
    if before != after:
        raise ValueError(f"[param.{key}]: edit would change more than the stamp")
    return out


def read_refs(args_refs, from_file):
    refs = list(args_refs)
    if from_file:
        for ln in Path(from_file).read_text().splitlines():
            ln = ln.split("#", 1)[0].strip()
            if ln:
                refs.append(ln)
    return refs


def stamp(root, who, refs, today=None):
    """(exit code, printed lines). Writes only when every ref passes check_row; files replaced atomically."""
    if os.environ.get("CLAUDECODE"):
        return 1, [AGENT]
    if not WHO_RE.match(who or ""):
        return 1, [f"refused: --who '{who}' is not a GitHub login (1-39 letters, digits or single inner hyphens)"]
    if not refs:
        return 1, ["refused: no <Value>:<key> given"]
    date = (today or datetime.date.today()).isoformat()
    plan, bad = {}, []
    for ref in dict.fromkeys(refs):
        value, sep, key = ref.partition(":")
        if not sep or not value or not key:
            bad.append(f"refused {ref}: expected <Value>:<key>")
            continue
        d, suffix, why = check_row(root, value, key)
        if why:
            bad.append(f"refused {ref}: {why}")
        else:
            plan.setdefault(d, []).append((key, f"human:{who} {date} page-image ds_review {suffix}"))
    if bad:
        return 1, bad + ["nothing written"]
    out, new = [], {}
    for d, rows in plan.items():
        text = (d / "component.toml").read_bytes().decode()
        old = tomllib.loads(text)["param"]
        for key, s in rows:
            try:
                text = set_stamp(text, key, s)
            except ValueError as e:
                return 1, [f"refused {d.name}:{key}: {e}", "nothing written"]
            out.append(f"{d.name}:{key}: {old[key].get('verified') or '(no stamp)'} -> {s}")
        new[d] = text
    temps = {}
    try:
        for d, text in new.items():
            fd, tmp = tempfile.mkstemp(dir=d, prefix=".component.toml.")
            with os.fdopen(fd, "wb") as f:
                f.write(text.encode())
            temps[d] = tmp
            os.chmod(tmp, (d / "component.toml").stat().st_mode & 0o7777)
        for d, tmp in temps.items():
            os.replace(tmp, d / "component.toml")
    finally:
        for tmp in temps.values():
            if os.path.exists(tmp):
                os.unlink(tmp)
    out.append("next: python3 tools/verify.py " + " ".join(str(d.relative_to(root)) for d in plan))
    return 0, out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tools/stamp.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("refs", nargs="*", metavar="Value:key", help="row to stamp: component directory name and param key")
    ap.add_argument("--who", metavar="GITHUB_LOGIN", help="your GitHub login (default: gh api user --jq .login)")
    ap.add_argument("--from", dest="from_file", metavar="FILE", help="file with one Value:key per line (# comments ok)")
    ap.add_argument("--root", default=Path(__file__).resolve().parent.parent, help="library repo root (default: this repo)")
    a = ap.parse_args(argv)
    who = a.who
    if os.environ.get("CLAUDECODE"):
        print(AGENT)
        return 1
    if who is None:
        who, why = github_login()
        if why:
            print(f"refused: no --who and {why}")
            return 1
    rc, lines = stamp(Path(a.root).resolve(), who, read_refs(a.refs, a.from_file))
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main())
