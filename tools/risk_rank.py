#!/usr/bin/env python3
"""Rank component rows by the risk of a wrong value. JSON on stdout, one summary line on stderr. Exit 0 = ok, 1 = FAIL.

Usage (repo root): python3 tools/risk_rank.py [--blocks DIR] [--root R]

For every component (components/*/*/component.toml, plus the rows of variants.toml) the rows are ranked:
  rank 0  every [[pin]] (key "pin:<number>") and every kind = "mechanical" row (land-pattern and package dimensions)
  rank 1  a row that is used: its key appears as a quoted string in any <blocks>/blocks/*/analysis.py or examples/*.py
          (`.param("key")`, INPUTS mapped through `.inputs("fn")`, any literal), or a Zener check selects it
          (check_pins or check_ambient on the row)
  rank 2  all other rows
"used" is a text match on quoted strings, not an AST of the call: a key string used for another part also marks a row
in this part (over-marking is the safe direction; the reasons list says why). Keys built at run time (f-strings) are
not seen. --blocks: the circuit-blocks worktree; default $CIRCUIT_BLOCKS, else ../circuit-blocks next to this repo;
the chosen path is printed in the JSON ("blocks_dir"). Missing blocks dir, no analysis.py in it, or zero components =
FAIL (nothing is ranked without them). A calc.py whose INPUTS is not a literal makes that component UNSURE (its INPUTS
uses are not counted); the ranking is still printed. Output is sorted and deterministic.
"""
import argparse
import ast
import json
import os
import re
import sys
import tomllib
from pathlib import Path

STR_RE = re.compile(r"""["']([A-Za-z0-9_.:]+)["']""")


def literals(files):
    out = set()
    for f in files:
        out.update(STR_RE.findall(f.read_text(errors="replace")))
    return out


def read_inputs(calc):
    """INPUTS of a calc.py as {function: {arg: key}} via ast.literal_eval; (None, reason) when it cannot be read."""
    if not calc.is_file():
        return {}, None
    try:
        tree = ast.parse(calc.read_text())
    except SyntaxError as e:
        return None, f"calc.py does not parse ({e.msg})"
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "INPUTS" for t in node.targets):
            try:
                return ast.literal_eval(node.value), None
            except ValueError:
                return None, "INPUTS is not a literal"
    return {}, None


def component_rows(folder):
    """{key: (kind, check selected)} for [param.*] rows of component.toml and variants.toml, plus pin numbers."""
    data = tomllib.loads((folder / "component.toml").read_text())
    rows = {k: v for k, v in data.get("param", {}).items()}
    var = folder / "variants.toml"
    if var.is_file():
        for v in tomllib.loads(var.read_text()).get("variant", {}).values():
            for k, p in v.get("param", {}).items():
                rows.setdefault(k, p)
    pins = [str(p.get("number", "")) for p in data.get("pin", [])]
    return rows, pins


def rank_component(folder, used_literals):
    rows, pins = component_rows(folder)
    inputs, why_unsure = read_inputs(folder / "calc.py")
    from_inputs = set()
    for fn, mapping in (inputs or {}).items():
        if fn in used_literals:
            from_inputs.update(str(v).split(".")[0] for v in mapping.values())
    out = [{"key": f"pin:{n}", "rank": 0, "reasons": ["pin"], "status": "OK"} for n in pins]
    for key, row in rows.items():
        reasons = []
        if row.get("kind") == "mechanical":
            reasons.append("mechanical")
        if key in used_literals:
            reasons.append("analysis-or-example")
        if key in from_inputs:
            reasons.append("inputs-of-used-function")
        if row.get("check_pins") or row.get("check_ambient"):
            reasons.append("zener-check")
        rank = 0 if "mechanical" in reasons else 1 if reasons else 2
        out.append({"key": key, "rank": rank, "reasons": sorted(reasons), "status": "OK"})
    out.sort(key=lambda r: (r["rank"], r["key"]))
    return out, why_unsure


def rank_all(root, blocks):
    """(result dict, problems). problems non-empty = FAIL."""
    root, blocks = Path(root), Path(blocks)
    problems = []
    if not blocks.is_dir():
        return None, [f"blocks dir not found: {blocks}"]
    sources = sorted(blocks.glob("blocks/*/analysis.py")) + sorted((root / "examples").glob("*.py"))
    if not sorted(blocks.glob("blocks/*/analysis.py")):
        return None, [f"no blocks/*/analysis.py under {blocks}"]
    folders = sorted(root.glob("components/*/*/component.toml"))
    if not folders:
        return None, ["no components/*/*/component.toml found"]
    used = literals(sources)
    comps = []
    for toml in folders:
        folder = toml.parent
        name = f"{folder.parent.name}/{folder.name}"
        try:
            rows, unsure = rank_component(folder, used)
        except (tomllib.TOMLDecodeError, OSError) as e:
            comps.append({"part": name, "status": "FAIL", "reason": f"cannot read component.toml: {e}", "rows": []})
            problems.append(f"{name}: cannot read component.toml: {e}")
            continue
        comps.append({"part": name, "status": "UNSURE" if unsure else "OK", "reason": unsure or "", "rows": rows})
    return {"blocks_dir": str(blocks), "sources": [str(p.relative_to(p.parents[2]) if p.name == "analysis.py" else p.name)
                                                  for p in sources], "components": comps}, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--blocks")
    ap.add_argument("--root", default=Path(__file__).resolve().parent.parent)
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    blocks = Path(a.blocks or os.environ.get("CIRCUIT_BLOCKS") or root.parent / "circuit-blocks").resolve()
    res, problems = rank_all(root, blocks)
    if res is None:
        print(f"risk_rank: FAIL: {problems[0]}", file=sys.stderr)
        return 1
    n = [sum(1 for c in res["components"] for r in c["rows"] if r["rank"] == k) for k in (0, 1, 2)]
    unsure = sum(c["status"] == "UNSURE" for c in res["components"])
    fail = sum(c["status"] == "FAIL" for c in res["components"])
    print(json.dumps(res, indent=1, sort_keys=True))
    print(f"risk_rank: {len(res['components']) - unsure - fail} OK, {unsure} UNSURE, {fail} FAIL components; "
          f"rows rank0 {n[0]}, rank1 {n[1]}, rank2 {n[2]}; blocks {blocks}", file=sys.stderr)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
