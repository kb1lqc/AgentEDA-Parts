"""Human view of the review record (docs/spec/review.md "Human view"). Stdlib only.

Each row is `checked` (a current human stamp, bound to the row and the PDF as lib.component decides, ledger
HUMAN_VERIFIED), `needs check` (any other row a block uses; every other row when use is unknown) or `reference` (not
used by any block in scope). A part is released for a block when every row the block uses is checked.
"""

import re
from pathlib import Path

from .component import _read_toml, _review, variants_of

CHECKED, NEEDS, REFERENCE = "checked", "needs check", "reference"
WHO_DATE = re.compile(r"^human:(\S+) (\d{4}-\d{2}-\d{2}) ")


def checked_rows(path, local_pdf=True):
    """{key: (login, date)} for each [param] row of component.toml that is checked. local_pdf=False: ledger only."""
    path = Path(path)
    params = (_read_toml(path / "component.toml") or {}).get("param") or {}
    ledger = _read_toml(path / "review" / "review.toml") or {}
    out = {}
    for key, t in params.items():
        stamp = t.get("verified") if isinstance(t, dict) else None
        state, reason = _review(path, key, stamp, local_pdf=local_pdf, ledger=ledger, params=params)
        if reason is None and state == "HUMAN_VERIFIED":
            m = WHO_DATE.match(stamp)
            out[key] = (m[1], m[2])
    return out


def statuses(path, used=None, local_pdf=True):
    """{row: status} for every [param] key of the part plus every used row (a used `variant.<V>.<key>` or catalog key
    is never checked). used: set of rows a block reads; None = unknown (no row is reference)."""
    path = Path(path)
    params = (_read_toml(path / "component.toml") or {}).get("param") or {}
    done = checked_rows(path, local_pdf)
    rows = list(params) + sorted(set(used or ()) - set(params))
    return {k: REFERENCE if used is not None and k not in used else CHECKED if k in done else NEEDS for k in rows}


def summary(value, status, used_known=True):
    """("<Value>: <k> of <n> used rows checked", released) over the rows that are not reference."""
    rows = [s for s in status.values() if s != REFERENCE]
    k, n = rows.count(CHECKED), len(rows)
    return f"{value}: {k} of {n} {'used rows' if used_known else 'rows'} checked", k == n and n > 0


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
