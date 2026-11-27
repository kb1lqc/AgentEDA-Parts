"""Is a part safe to use? Ledger only (no PDFs, no catalog export needed), the same numbers as the part README.

  python3 tools/status.py INA229AIDGS [more Values ...] [--json]
  python3 tools/status.py --all [--json]

Exit 0 when every named part is released, 1 when any is not, 2 on an unknown part. Never stamps or changes a file.
JSON (one object per part) is for a blocks repo to read: value, dir, released, checked (k), matters (n), rows,
needs_check (row keys), not_covered (file -> keys), derived (catalog rows covered by the export record).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lib import review_status  # noqa: E402


def part_dirs(root):
    return sorted(p.parent for p in Path(root).glob("components/*/*/component.toml"))


def status(d, root=ROOT):
    r = review_status.review(d, root, local_pdf=False)
    needs = sorted(k for k, v in r["status"].items() if v == review_status.NEEDS)
    return {"value": d.name, "dir": str(d.relative_to(root)), "released": r["released"], "checked": r["k"],
            "matters": r["n"], "rows": r["M"], "needs_check": needs,
            "not_covered": {f: sorted(v) for f, v in r["not_covered"].items()}, "derived": r["derived"]}


def text(s):
    head = "RELEASED" if s["released"] else "NOT RELEASED"
    out = [f"{s['value']}: {head}, {s['checked']} of {s['matters']} rows that matter checked ({s['rows']} rows in all)"]
    if s["needs_check"]:
        out.append("  needs a check: " + ", ".join(s["needs_check"]))
    for f, keys in s["not_covered"].items():
        out.append(f"  used but not covered ({f}): " + ", ".join(keys))
    if s["derived"]:
        out.append(f"  {s['derived']} catalog rows derived (export-check record)")
    if not s["released"]:
        out.append(f"  review: python3 tools/review.py {s['value']}")
    return "\n".join(out)


def main(argv=None, root=ROOT):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("values", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    dirs = part_dirs(root)
    if not a.all:
        if not a.values:
            ap.error("name a part or use --all")
        by = {}
        for d in dirs:
            by.setdefault(d.name, []).append(d)
        missing = [v for v in a.values if v not in by]
        if missing:
            print("unknown part: " + ", ".join(missing), file=sys.stderr)
            return 2
        dirs = [d for v in a.values for d in by[v]]
    res = [status(d, root) for d in dirs]
    print(json.dumps(res, indent=2) if a.json else "\n".join(text(s) for s in res))
    return 0 if all(s["released"] for s in res) else 1


if __name__ == "__main__":
    sys.exit(main())
