"""Agent-review record of a part (docs/spec/review.md "Agent review record"). Stdlib only.

review/agent_review.toml holds one entry per role (verifier, adversarial), written only by tools/agent_review.py (a thin
CLI over `record`). It is an accountability record, not proof: it binds a review report to the exact inputs of the part
(hashes the tool computes), it does not show the review was right. Scope is what was offered to the reviewer, not read.
"""

import ast
import hashlib
import json
import re
import tomllib
from datetime import date
from pathlib import Path

from . import catalog, review_status
from .component import _read_toml, override_rows, variants_of

ROLES = ("verifier", "adversarial")
FILE = "agent_review.toml"
CURRENT, STALE, MISSING, MALFORMED = "CURRENT", "STALE", "MISSING", "MALFORMED"
FIELDS = {"date": str, "model": str, "findings": int, "applied": int, "logged": int, "clean": bool,
          "report_sha256": str, "report_lines": int, "inputs_sha256": str, "calc_ast_sha256": str,
          "matters": list, "functions": list, "reference_rows": list,
          "reference_overrides": list, "input_sha256": dict}
OPTIONAL = {"datasheet_pdf_sha256": str, "rows_checked": int, "rows_total": int}  # absent in older records
ALL_FIELDS = {**FIELDS, **OPTIONAL}


def _sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def _strip_verified(x):
    """A parsed TOML value without any `verified` key (a human stamp must never stale the record)."""
    if isinstance(x, dict):
        return {k: _strip_verified(v) for k, v in x.items() if k != "verified"}
    if isinstance(x, list):
        return [_strip_verified(v) for v in x]
    return x


def _toml_hash(f):
    data = tomllib.loads(f.read_bytes().decode())
    return _sha(json.dumps(_strip_verified(data), sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def calc_ast_hash(f):
    """SHA-256 of ast.dump of calc.py (docstrings kept: a docstring edit stales the record; comments and layout do not)."""
    src = Path(f).read_text()
    return _sha(ast.dump(ast.parse(src), annotate_fields=True, include_attributes=False))


def public_functions(f):
    """Names of the top-level functions of calc.py that do not start with an underscore (display only)."""
    return [n.name for n in ast.parse(Path(f).read_text()).body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]


def example_files_of(path, root=None):
    """examples/*.py (under the library root) that name this part: its Value or a variant Value (examples are repo-level)."""
    path = Path(path)
    root = Path(root) if root is not None else path.resolve().parents[2]
    names = [re.compile(r"\b" + re.escape(n) + r"\b") for n in {path.name, *variants_of(path)}]  # whole word: no over-match
    return [f for f in sorted((root / "examples").glob("**/*.py")) if any(n.search(f.read_text(errors="replace")) for n in names)]


def current(path, root=None):
    """What the part's committed inputs are now: {input_sha256: {name: hash}, inputs_sha256, calc_ast_sha256, matters,
    functions, reference_rows, reference_overrides, datasheet_pdf_sha256}. ValueError when a TOML or calc.py is unreadable."""
    path = Path(path)
    root = Path(root) if root is not None else path.resolve().parents[2]
    parts = {}
    try:
        parts["component.toml"] = _toml_hash(path / "component.toml")
        if (path / "variants.toml").is_file():
            parts["variants.toml"] = _toml_hash(path / "variants.toml")
        calc = path / "calc.py"
        if calc.is_file():
            parts["calc.py"] = calc_ast_hash(calc)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, SyntaxError) as e:
        raise ValueError(f"{path.name}: cannot hash the inputs ({e})")
    if (path / "catalog.csv").is_file():
        parts["catalog.csv"] = _sha((path / "catalog.csv").read_bytes())
    for f in example_files_of(path, root):
        parts[f"examples/{f.relative_to(root / 'examples').as_posix()}"] = _sha(f.read_bytes())
    data = _read_toml(path / "component.toml") or {}
    if (data.get("part") or {}).get("catalog_decoder"):  # a capacitor series: the decode tables are an input
        parts["catalog_tables"] = catalog.tables_sha256()
    params = data.get("param") or {}
    mat = review_status.matters(path, root)
    dsf = (data.get("part") or {}).get("datasheet_file", "")
    pdf = root / dsf if dsf and (root / dsf).is_file() else None
    pdf_sha = _sha(pdf.read_bytes()) if pdf else ((_read_toml(path / "review" / "review.toml") or {}).get("inputs") or {}).get("pdf_sha256", "")
    return {"input_sha256": parts, "inputs_sha256": _sha(json.dumps(parts, sort_keys=True, separators=(",", ":"))),
            "calc_ast_sha256": parts.get("calc.py", ""),
            "matters": sorted(mat),
            "functions": public_functions(path / "calc.py") if (path / "calc.py").is_file() else [],
            "reference_rows": [k for k in params if k not in mat],
            "reference_overrides": [k for k in override_rows(path, params) if k not in mat],
            "datasheet_pdf_sha256": pdf_sha}


def find_part(root, value):
    """The component directory components/<Mfr>/<value>/ under root; ValueError when there is not exactly one."""
    found = sorted(p.parent for p in (Path(root) / "components").glob(f"*/{value}/component.toml"))
    if len(found) != 1:
        raise ValueError(f"no single component directory components/*/{value}/ in {root}")
    return found[0]


def _toml_text(entries):
    out = ["# GENERATED by tools/agent_review.py (docs/spec/review.md \"Agent review record\"). Do not edit.",
           "# An accountability record, not proof: the hashes bind a review report to the inputs it was offered."]
    for role in ROLES:
        e = entries.get(role)
        if not e:
            continue
        out += ["", f"[{role}]"]
        for k in ALL_FIELDS:
            if k == "input_sha256" or k not in e:
                continue
            out.append(f"{k} = {json.dumps(e[k])}")
        out += ["", f"[{role}.input_sha256]"] + [f"{json.dumps(n)} = {json.dumps(h)}" for n, h in sorted(e["input_sha256"].items())]
    return "\n".join(out) + "\n"


def record(root, value, role, model, findings, applied, logged, report, clean=False, today=None, rows_checked=None):
    """Write the role's entry of components/<Mfr>/<value>/review/agent_review.toml (the other role's entry is kept).
    Returns the file. ValueError (nothing written) for an unknown part or role, an unreadable report, counts that do not
    fit (applied + logged > findings), zero findings without `clean`, `clean` with findings, or findings with an empty report."""
    if role not in ROLES:
        raise ValueError(f"unknown role '{role}': use one of {', '.join(ROLES)}")
    if role == "verifier" and rows_checked is None:
        raise ValueError("--rows-checked N is required for the verifier (how many reference rows it checked)")
    if role != "verifier" and rows_checked is not None:
        raise ValueError("--rows-checked is only for the verifier")
    path = find_part(root, value)
    if not model or not str(model).strip():
        raise ValueError("--model is required")
    if min(findings, applied, logged) < 0 or applied + logged > findings:
        raise ValueError("counts: need 0 <= applied + logged <= findings")
    try:
        body = Path(report).read_bytes()
    except OSError as e:
        raise ValueError(f"cannot read the report ({e})")
    empty = not body.strip()
    if clean and findings:
        raise ValueError("--clean means zero findings")
    if clean and empty:
        raise ValueError("--clean needs a report that says what was checked (the report is empty)")
    if not findings and not clean:
        raise ValueError("zero findings needs --clean (and the report that says so)")
    if findings and empty:
        raise ValueError("findings were counted but the report is empty")
    if not clean and empty:
        raise ValueError("the report is empty")
    if not clean and findings > len(body.splitlines()):
        raise ValueError(f"{findings} findings but the report has only {len(body.splitlines())} lines (one finding per line)")
    prior = _read_toml(path / "review" / FILE) or {}
    for other in ROLES:
        if other != role and (prior.get(other) or {}).get("report_sha256") == _sha(body):
            raise ValueError(f"this report is the {other} record's report: each role needs its own reviewer's report")
    now = current(path, root)
    e = {"date": (today or date.today()).isoformat(), "model": str(model), "findings": findings, "applied": applied,
         "logged": logged, "clean": bool(clean), "report_sha256": _sha(body), "report_lines": len(body.splitlines()),
         **{k: now[k] for k in ("inputs_sha256", "calc_ast_sha256", "matters", "functions", "reference_rows",
                                "reference_overrides", "input_sha256")}}
    if rows_checked is not None:
        total = len(now["reference_rows"]) + len(now["reference_overrides"])
        if not 0 <= rows_checked <= total:
            raise ValueError(f"--rows-checked {rows_checked} must be between 0 and {total} (the reference rows in scope)")
        e["rows_checked"], e["rows_total"] = rows_checked, total  # rows_checked == rows_total: the full case
    if now["datasheet_pdf_sha256"]:
        e["datasheet_pdf_sha256"] = now["datasheet_pdf_sha256"]
    f = path / "review" / FILE
    entries = {r: t for r, t in (_read_toml(f) or {}).items() if r in ROLES and isinstance(t, dict)}
    entries[role] = e
    f.parent.mkdir(exist_ok=True)
    f.write_text(_toml_text(entries))
    return f


def malformed(entry):
    """Problems (list of str) in one role entry: a missing or mistyped field."""
    out = []
    for k, typ in ALL_FIELDS.items():
        if k in OPTIONAL and k not in entry:
            continue
        v = entry.get(k)
        if not isinstance(v, typ) or (typ is int and isinstance(v, bool)):
            out.append(f"{k} is missing or not a {typ.__name__}")
    for k in ("matters", "functions", "reference_rows", "reference_overrides"):
        if isinstance(entry.get(k), list) and not all(isinstance(x, str) for x in entry[k]):
            out.append(f"{k} holds a non-string")
    return out


def status(path, root=None):
    """{role: CURRENT | STALE | MISSING | MALFORMED}, plus `date` {role: date}, `problems` [(role, text)] and `functions`
    (the public calc.py names, display only). CURRENT: the role's inputs_sha256 equals the part's now and its
    rows-that-matter keys are the same (a human stamp changes neither)."""
    path = Path(path)
    f = path / "review" / FILE
    out = {"state": {}, "date": {}, "problems": [], "functions": []}
    try:
        recs = tomllib.loads(f.read_text()) if f.is_file() else {}
    except (OSError, tomllib.TOMLDecodeError) as e:
        recs = None
        out["problems"].append((None, f"review/{FILE} is not valid TOML ({e})"))
    try:
        now = current(path, root)
    except ValueError as e:
        now = None
        out["problems"].append((None, str(e)))
    out["functions"] = (now or {}).get("functions", [])
    for role in ROLES:
        e = (recs or {}).get(role)
        if recs is None:
            out["state"][role] = MALFORMED
        elif not e:
            out["state"][role] = MISSING
        elif not isinstance(e, dict) or malformed(e):
            out["state"][role] = MALFORMED
            out["problems"].append((role, "; ".join(malformed(e)) if isinstance(e, dict) else "not a table"))
        elif now is None:
            out["state"][role] = STALE
        else:
            out["date"][role] = e["date"]
            ok = e["inputs_sha256"] == now["inputs_sha256"] and sorted(e["matters"]) == now["matters"]
            pdf = now["datasheet_pdf_sha256"]  # a changed datasheet stales the review (main PDF only)
            ok = ok and not (pdf and e.get("datasheet_pdf_sha256") and e["datasheet_pdf_sha256"] != pdf)
            out["state"][role] = CURRENT if ok else STALE
            if ok:  # scope must name what exists
                bad = [k for k in e["reference_rows"] + e["reference_overrides"] if k not in now["reference_rows"] + now["reference_overrides"]]
                bad += [fn for fn in e["functions"] if fn not in now["functions"]]
                if bad:
                    out["state"][role] = MALFORMED
                    out["problems"].append((role, "scope names something that does not exist: " + ", ".join(bad)))
    for role in recs or {}:
        if role not in ROLES:
            out["problems"].append((role, f"unknown role '{role}'"))
    return out


def clause(st):
    """The README line 5 agent clause (docs/spec/review-view.md): both roles current, stale, or pending."""
    s = st["state"]
    if all(s[r] == CURRENT for r in ROLES):
        return f"; agent review: verifier+adversarial current {min(st['date'][r] for r in ROLES)}"
    if any(s[r] in (STALE, MALFORMED) for r in ROLES):
        return "; agent review: stale"
    return f"; agent review: pending ({', '.join(r for r in ROLES if s[r] == MISSING)})"
