"""Human view of the review record (docs/spec/review.md "Human view"). Stdlib only.

Each row is `checked` (a current human stamp, bound to the row and the PDF as lib.component decides, ledger
HUMAN_VERIFIED), `needs check` (a row that matters, not checked) or `reference`. A part is released when every row
that matters is checked (k == n > 0). Rules: docs/spec/review.md "Human view".
"""

import ast
import csv
import re
from pathlib import Path

from . import capacitor as _cap
from .component import _read_toml, _review, override_rows, variants_of

CHECKED, NEEDS, REFERENCE = "checked", "needs check", "reference"
WHO_DATE = re.compile(r"^human:(\S+) (\d{4}-\d{2}-\d{2}) ")


def checked_rows(path, local_pdf=True):
    """{key: (login, date)} for each [param] row of component.toml that is checked, plus `pinout` (its [pinout] stamp).
    local_pdf=False: ledger only."""
    path = Path(path)
    data = _read_toml(path / "component.toml") or {}
    params = data.get("param") or {}
    ledger = _read_toml(path / "review" / "review.toml") or {}
    out = {}
    for key, t in params.items():
        stamp = t.get("verified") if isinstance(t, dict) else None
        state, reason = _review(path, key, stamp, local_pdf=local_pdf, ledger=ledger, params=params)
        if reason is None and state == "HUMAN_VERIFIED":
            m = WHO_DATE.match(stamp)
            out[key] = (m[1], m[2])
    for rk, (_merged, own) in override_rows(path, params).items():  # variant.<V>.<key>, stamped in variants.toml
        stamp = own.get("verified")
        state, reason = _review(path, rk, stamp, local_pdf=local_pdf, ledger=ledger, params=params)
        if reason is None and state == "HUMAN_VERIFIED":
            m = WHO_DATE.match(stamp)
            out[rk] = (m[1], m[2])
    stamp = (data.get("pinout") or {}).get("verified")
    if stamp and data.get("pin"):  # the pinout stamp, like a row's
        state, reason = _review(path, "pinout", stamp, local_pdf=local_pdf, ledger=ledger)
        if reason is None and state == "HUMAN_VERIFIED":
            m = WHO_DATE.match(stamp)
            out["pinout"] = (m[1], m[2])
    return out


STR_RE = re.compile(r"""["']([A-Za-z0-9_.:]+)["']""")  # risk_rank's text match
SUFFIXES = (".min", ".typ", ".max")


def calc_inputs(path):
    """{function: {arg: key}} from calc.py INPUTS via ast.literal_eval; {} when absent, unparsable or not a literal."""
    calc = Path(path) / "calc.py"
    if not calc.is_file():
        return {}
    try:
        tree = ast.parse(calc.read_text())
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "INPUTS" for t in node.targets):
                return ast.literal_eval(node.value)
    except (SyntaxError, ValueError):
        pass
    return {}


def row_key(value):
    """An INPUTS value as a param key: a trailing .min/.typ/.max is dropped."""
    value = str(value)
    return value[:-4] if value.endswith(SUFFIXES) else value


def example_files(root):
    """{relative file name: set of quoted strings} for examples/*.py under root."""
    return {f"examples/{f.name}": set(STR_RE.findall(f.read_text(errors="replace")))
            for f in sorted((Path(root) / "examples").glob("*.py"))}


def _root(path, root):
    return Path(root) if root is not None else Path(path).resolve().parents[2]


def _thermal_matters(t):
    sym = t.get("symbol", "")
    return t.get("kind") == "thermal" and ("JC" in sym.upper() or re.sub(r"[^A-Z0-9]", "", sym.upper()) == "TJMAX")


def matters(path, root=None):
    """{row: [reasons]} for the rows that matter (docs/spec/review.md "Human view", rules 1-4), in TOML order, the
    pinout last. root: the library root (examples/ lives there); default two levels above components/<Mfr>/<Value>."""
    path = Path(path)
    data = _read_toml(path / "component.toml") or {}
    params = data.get("param") or {}
    used = {row_key(v) for m in calc_inputs(path).values() for v in m.values()}
    examples = example_files(_root(path, root))
    out = {}
    for key, t in params.items():
        why = []
        if t.get("kind") in ("abs_max", "mechanical"):
            why.append(t["kind"])
        if _thermal_matters(t):
            why.append("thermal")
        if key in used:
            why.append("calc.py INPUTS")
        if any(key in s for s in examples.values()):
            why.append("examples")
        if t.get("check_pins") or t.get("check_ambient"):
            why.append("zener check")
        if why:
            out[key] = why
    for rk, (_merged, own) in override_rows(path, params).items():  # an override: its base row matters, or its key is used
        key = rk.rsplit(".", 1)[-1]  # keys hold no dot, a variant name may
        why = list(out.get(key, [])) if key in params else (["calc.py INPUTS"] if key in used else [])
        if why:
            out[rk] = why
    if data.get("pin"):
        out["pinout"] = ["pinout"]
    return out


def catalog_columns(path):
    """The header columns of catalog.csv (empty when there is none)."""
    f = Path(path) / "catalog.csv"
    try:
        with open(f, newline="") as fh:
            return set(next(csv.reader(fh), []))
    except OSError:
        return set()


DERIVED_COLUMNS = ("capacitance", "tolerance", "rated_voltage")  # catalog columns a current export-check group covers


def derived_rows(path):
    """Catalog rows of a capacitor series covered by a current export-check record, machine or legacy human (docs/spec/
    capacitor.md "Export check"): derived, checked. 0 without a catalog or a current record. Not part of k or n."""
    path = Path(path)
    part = (_read_toml(path / "component.toml") or {}).get("part") or {}
    if part.get("series") != "capacitor" or not part.get("catalog"):
        return 0
    return sum(g["rows"] for g in _cap.current_groups(path, path / part["catalog"]).values())


def not_covered(path, mat=None):
    """{file: [keys]} the ledger cannot stamp, by where they live: used values (calc.py INPUTS) that are no [param] row
    of component.toml (catalog.csv only for a real catalog column; else series, else "unknown"). A used key that is a
    variants.toml override is a ledger row (`variant.<V>.<key>`), not listed. mat: unused, kept for callers."""
    path = Path(path)
    data = _read_toml(path / "component.toml") or {}
    params = data.get("param") or {}
    variants = variants_of(path)
    own = {k for v in variants.values() for k in v.get("param", {})}
    cols = catalog_columns(path)
    out = {}
    for key in sorted({row_key(v) for m in calc_inputs(path).values() for v in m.values()} - set(params)):
        if key in own:
            continue  # an override row of the ledger (counted in k and n when it matters)
        elif key in cols:
            if key in DERIVED_COLUMNS and derived_rows(path):  # covered by a current group: derived, checked
                continue
            where = "catalog.csv"
        elif (data.get("part") or {}).get("series"):
            where = "series"
        else:
            where = "unknown"
        out.setdefault(where, []).append(key)
    return out


def located(row):
    """True when a ledger row points at a datasheet table or figure: an evidence image (ds_review.py), the same
    condition stamp.py needs before it stamps a row. A row without one (a value from a features bullet, design or
    application text) cannot be compared with an image, so it is a reference row, not a check."""
    return isinstance(row, dict) and bool(row.get("image"))


def review(path, root=None, local_pdf=True):
    """The human view of one component directory: status {row: status} for every [param] row (+ `pinout`), matters
    (every row that matters, with reasons), unlocated (rows that matter but have no datasheet table or figure location:
    reference, not checked, not counted), k (checked rows among n), n (checkable rows that matter), M (all rows),
    released, not_covered. A checked row stays checked whatever its location."""
    path = Path(path)
    data = _read_toml(path / "component.toml") or {}
    params = data.get("param") or {}
    mat = matters(path, root)
    done = checked_rows(path, local_pdf)
    rows = (_read_toml(path / "review" / "review.toml") or {}).get("row", {})
    # A value with a citation (a features bullet, design or application text) but no table or figure location is
    # reference, not a check. A row with no min, typ or max, or with no citation, is a defect to fix in the TOML, so it
    # stays checkable (the page shows it as "fix first").
    over = {rk: own for rk, (_m, own) in override_rows(path, params).items()}
    tables = {**params, **over}  # an override shows its own cite and values
    unlocated = sorted(k for k in mat if k != "pinout" and k not in done and not located(rows.get(k))
                       and values_text(tables.get(k, {})) and tables.get(k, {}).get("cite"))
    checkable = [k for k in mat if k not in unlocated]
    status = {k: CHECKED if k in done else NEEDS if k in checkable else REFERENCE for k in tables}
    if "pinout" in mat:
        status["pinout"] = CHECKED if "pinout" in done else NEEDS
    k = sum(status[r] == CHECKED for r in checkable)
    from . import agent_review  # here, not at the top: agent_review imports this module
    return {"agent": agent_review.status(path, root), "status": status, "matters": mat, "unlocated": unlocated, "k": k, "n": len(checkable), "M": len(status),
            "released": k == len(checkable) > 0, "not_covered": not_covered(path, mat), "derived": derived_rows(path)}


def statuses(path, local_pdf=True, root=None):
    """{row: status} (see review)."""
    return review(path, root, local_pdf)["status"]


def summary(value, r):
    """("<Value>: <k> of <n> rows that matter checked", released); rows without a table location are named apart."""
    text = f"{value}: {r['k']} of {r['n']} rows that matter checked"
    if r.get("unlocated"):
        text += f" ({len(r['unlocated'])} reference: no table or figure location)"
    return text + derived_text(r), r["released"]


def derived_text(r):
    """"; N catalog rows derived, checked (machine export-check)" when a current export-check record covers catalog rows."""
    return f"; {r['derived']} catalog rows derived, checked (export-check record)" if r.get("derived") else ""


def not_covered_text(r):
    c = sum(len(v) for v in r["not_covered"].values())
    return f"; {c} used values not covered ({', '.join(sorted(r['not_covered']))})" if c else ""


def readme_line(value, r):
    """Line 5 of a part README (docs/spec/review.md "Human view")."""
    from . import agent_review
    extra = derived_text(r) + not_covered_text(r) + (agent_review.clause(r["agent"]) if r.get("agent") else "")
    if r["released"]:
        return f"Released: all {r['n']} rows that matter checked ({r['M']} rows in all){extra}" + "."
    return (f"Checked by a person: {r['k']} of {r['n']} rows that matter ({r['M']} rows in all). "
            f"Review: python3 tools/review.py {value}{extra}")


def row_table(path, key):
    """The table of a row: [param.<key>], or for `variant.<V>.<key>` the override's own table (its own cite and values)."""
    path = Path(path)
    params = (_read_toml(path / "component.toml") or {}).get("param") or {}
    if key.startswith("variant."):
        return override_rows(path, params)[key][1]
    return params[key]


def used_by(path, key, root=None):
    """The places the library uses a row: calc.py function(argument), Zener check, examples file. An override is used
    wherever its base key is."""
    path = Path(path)
    key = key.rsplit(".", 1)[-1] if key.startswith("variant.") else key
    t = ((_read_toml(path / "component.toml") or {}).get("param") or {}).get(key, {})
    out = [f"{fn}({arg})" for fn, m in calc_inputs(path).items() for arg, v in m.items() if row_key(v) == key]
    if t.get("check_pins"):
        out.append("Zener check on pins " + ", ".join(t["check_pins"]))
    if t.get("check_ambient"):
        out.append("Zener check on board ambient")
    out += [f for f, s in example_files(_root(path, root)).items() if key in s]
    return out


def values_text(t):
    """"min 1, typ 2, max 3" as the README prints them ("" when the row has no min, typ or max)."""
    from .readme import shown
    return ", ".join(f"{f} {shown(t, f)}" for f in ("min", "typ", "max") if shown(t, f))


def statement(path, key, root=None):
    """The text a person compares with the datasheet (docs/spec/review-view.md "Statement"); committed fields only. A row
    with no min, typ or max gives "Fix first: <why>"; no unit prints `unitless`."""
    path = Path(path)
    data = _read_toml(path / "component.toml") or {}
    if key == "pinout":
        pins = "; ".join(f"{p.get('number', '')} {p.get('name', '')} ({p.get('type', '')}): {p.get('function', '')}"
                         for p in data.get("pin", []))
        return f"Pinout of {path.name}: {pins}"
    t = row_table(path, key)
    vals = values_text(t)
    if not vals:
        return "Fix first: the row has no min, typ or max"
    text = (f"{t.get('name', '')} ({t.get('symbol', '')}): {vals} {t.get('unit') or 'unitless'}; "
            f"{t.get('conditions') or 'no conditions printed'}; scope {t.get('scope', '')}.")
    if t.get("note"):
        text += f" Note: {t['note']}" + ("" if str(t["note"]).endswith(".") else ".")
    use = used_by(path, key, root)
    if use:
        text += " Used by: " + ", ".join(use)
    return text


PRETTY_UNIT = re.compile(r"(?<![A-Za-z_])u(Vpp|Vrms|Arms|Hz|V|A|F|H|W|C|J)(?![A-Za-z])")  # "3uV" yes, "x_uA" no
PRETTY_UNIT_AFTER_NUMBER = re.compile(r"(\d\s?)u(s|m|g)(?![A-Za-z])")
PRETTY_OHM = re.compile(r"(?<![A-Za-z_])([kM]?)ohm(?![A-Za-z])")
PRETTY_DEGC = re.compile(r"(?<![A-Za-z_])(m?)degC(?![A-Za-z])")  # "125degC", "mdegC"
SCOPE_TEXT = {"25C": "at 25 \u00b0C only", "full": "over the full temperature range",
              "partial": "over part of the range: see conditions"}
READ_AS = re.compile(r"read as|applied as|inferred", re.I)
MAGNITUDE_ORDER = re.compile(r"magnitude[ -]order", re.I)  # the DS prints a negative pair in magnitude order
PRINTED_COLUMN = re.compile(r"\b(MIN|TYP|MAX)\b(?: column)?(?: printed)? ([-−]?\d[\d.]*)", re.I)  # "MAX column -10"
STORED_FOR = {"MIN": "max", "TYP": "typ", "MAX": "min"}  # numeric order: printed MIN is the stored max, printed MAX the min


def printed_columns(note):
    """[(column, printed value, stored field)] for the columns a magnitude-order note quotes, in MIN, TYP, MAX order;
    [] for any other note (INA241's rail-relative "MAX VS - 0.2 V" quotes no column number, so it gets none)."""
    if not MAGNITUDE_ORDER.search(note):
        return []
    seen = {}
    for col, val in PRINTED_COLUMN.findall(note):
        seen.setdefault(col.upper(), val.replace("−", "-"))
    return [(c, seen[c], STORED_FOR[c]) for c in ("MIN", "TYP", "MAX") if c in seen]


def pretty(text):
    """Display-only unit and sign prettifying (docs/spec/review-view.md "Statement card"); never written to the TOML:
    degC -> \u00b0C, ohm/kohm/Mohm -> \u03a9/k\u03a9/M\u03a9, u-prefixed units -> \u00b5, +/- -> \u00b1."""
    text = PRETTY_DEGC.sub("\\1\u00b0C", str(text))
    text = PRETTY_OHM.sub(lambda m: m[1] + "\u03a9", text)
    text = PRETTY_UNIT.sub("\u00b5\\1", text)
    text = PRETTY_UNIT_AFTER_NUMBER.sub("\\1\u00b5\\2", text)
    return text.replace("+/-", "\u00b1")


def card_value(t):
    """The Value line: values_text, except a `sym` row or min = -max prints "\u00b1<max>"; no unit prints `unitless`."""
    from .readme import shown
    both = isinstance(t.get("min"), (int, float)) and isinstance(t.get("max"), (int, float)) and t["min"] == -t["max"]
    if (t.get("sym") or both) and "max" in t and "tol_pct" not in t and not t.get("min_ref") and not t.get("max_ref"):
        parts = ([f"typ {shown(t, 'typ')}"] if shown(t, "typ") else []) + [f"\u00b1{t['max']}"]
    else:
        parts = [f"{f} {shown(t, f)}" for f in ("min", "typ", "max") if shown(t, f)]
    return ", ".join(parts) + f" {t.get('unit') or 'unitless'}"


def statement_card(path, key, root=None):
    """The statement a person compares with the datasheet as data (docs/spec/review-view.md "Statement card"); committed
    fields only. A row: {title, lines: [(label, text)], note, note_open, fix: ""}; text is prettified (display only).
    A row with no min, typ or max has fix = "Fix first: <why>". The pinout: {title, pins: [(number, name, type,
    function)]}."""
    path = Path(path)
    data = _read_toml(path / "component.toml") or {}
    if key == "pinout":
        return {"title": f"Pinout of {path.name}", "lines": [], "note": "", "note_open": False, "fix": "",
                "pins": [(str(p.get("number", "")), p.get("name", ""), p.get("type", ""), p.get("function", ""))
                         for p in data.get("pin", [])]}
    t = row_table(path, key)
    title = pretty(f"{t['symbol']} \u2014 {t.get('name', '')}" if t.get("symbol") else t.get("name", ""))
    card = {"title": title, "lines": [], "note": "", "note_open": False, "fix": ""}
    from .readme import shown
    if not values_text(t):
        card["fix"] = "Fix first: the row has no min, typ or max"
        return card
    lines = [("Value", pretty(card_value(t))), ("Conditions", pretty(t.get("conditions") or "none printed"))]
    cols = printed_columns(str(t.get("note") or ""))
    if cols:
        lines.insert(1, ("Datasheet columns", "; ".join(f"printed {c} {v} = stored {f} {shown(t, f) or 'not set'}"
                                                       for c, v, f in cols)))
    if t.get("scope") in SCOPE_TEXT:
        lines.append(("Temperature", SCOPE_TEXT[t["scope"]]))
    use = [re.sub(r"^(\w+)\((.*)\)$", r"\1 (\2)", u) for u in used_by(path, key, root)]
    if use:
        lines.append(("Used by", ", ".join(use)))
    note = str(t.get("note") or "")
    card.update(lines=lines, note=pretty(note), note_open=bool(note and (t.get("unchecked") or READ_AS.search(note))))
    return card


def component_dir(root, label):
    """(component dir, variant) of an input label ("<Value>", "<Value>[<selection>]" or a variant Value of a family);
    (None, None) when no single directory matches."""
    base = label.split("[")[0]
    comps = Path(root) / "components"
    found = sorted(p.parent for p in comps.glob(f"*/{base}/component.toml"))
    if found:
        return (found[0], None) if len(found) == 1 else (None, None)
    fams = [f.parent for f in sorted(comps.glob("*/*/variants.toml")) if base in variants_of(f.parent)]
    return (fams[0], base) if len(fams) == 1 else (None, None)


def used_rows(root, inputs):
    """{component dir: set of rows} from "<label>:<key>" strings (lib.used_inputs()) or a block's library-inputs.json
    entries (their "dir" is used when it holds a component.toml). A variants.toml override is the row
    `variant.<V>.<key>`. An unknown label raises ValueError."""
    out = {}
    for inp in inputs:
        given = Path(root) / inp["dir"] if isinstance(inp, dict) and inp.get("dir") else None
        inp = inp["input"] if isinstance(inp, dict) else inp
        label, _, key = inp.rpartition(":")
        base = label.split("[")[0]
        if given and (given / "component.toml").is_file():
            d, variant = given, (base if base != given.name and base in variants_of(given) else None)
        else:
            d, variant = component_dir(root, label)
        if d is None:
            raise ValueError(f"{inp}: no single components/*/{label.split('[')[0]}/ in {root}")
        own = variants_of(d).get(variant, {}).get("param", {}) if variant else {}
        out.setdefault(d, set()).add(f"variant.{variant}.{key}" if key in own else key)
    return out
