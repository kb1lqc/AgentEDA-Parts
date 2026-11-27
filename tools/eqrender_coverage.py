#!/usr/bin/env python3
"""Coverage of lib.eqrender over every public calc.py function: python3 tools/eqrender_coverage.py"""
import importlib.util
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from lib import eqrender as q  # noqa: E402

KINDS = ("ds", "algebra", "engineering", "helper")
STATS = ("math", "cases", "source_only", "failed")


def main():
    counts = {k: dict.fromkeys(STATS, 0) for k in KINDS}
    listed = {"source_only": [], "failed": []}
    for path in sorted(glob.glob(os.path.join(ROOT, "components", "*", "*", "calc.py"))):
        value = os.path.basename(os.path.dirname(path))
        spec = importlib.util.spec_from_file_location("calc_" + value.replace("-", "_"), path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as ex:
            mod = None
            print("cannot import %s: %s" % (value, ex))
        examples = getattr(mod, "EXAMPLES", []) if mod else []
        for x in q.render_part(path):
            if x.status in ("math", "cases") and mod is not None and hasattr(mod, x.name):
                rows = [kw for f, kw, *_ in examples if f == x.name]
                for issue in q.validate(x, getattr(mod, x.name), vars(mod), rows):
                    x.status = "failed"
                    x.warnings.append(issue)
            counts[x.kind][x.status] += 1
            if x.kind in ("ds", "algebra") and x.status in listed:
                why = (x.warnings or [""])[0][:90]
                listed[x.status].append("%s:%s  %s" % (value, x.name, why))
    print("%-12s %5s %5s %12s %7s %6s" % ("kind", "math", "cases", "source_only", "failed", "total"))
    for k in KINDS:
        c = counts[k]
        print("%-12s %5d %5d %12d %7d %6d" % (k, c["math"], c["cases"], c["source_only"], c["failed"], sum(c.values())))
    for s in ("source_only", "failed"):
        print("\nds/algebra %s (%d):" % (s, len(listed[s])))
        for l in listed[s]:
            print("  " + l)
    tot = sum(sum(counts[k].values()) for k in ("ds", "algebra"))
    ok = sum(counts[k]["math"] + counts[k]["cases"] for k in ("ds", "algebra"))
    pct = 100.0 * ok / tot if tot else 0.0
    print("\nds+algebra rendered as math or cases: %d of %d = %.1f%% (gate >= 85%%: %s)"
          % (ok, tot, pct, "PASS" if pct >= 85 else "FAIL"))
    return 0 if pct >= 85 else 1


if __name__ == "__main__":
    sys.exit(main())
