#!/usr/bin/env python3
"""Write the GitHub job summary (Markdown on stdout) for a verify run.
Usage: summary.py library <verify log>          (zener-library)
       summary.py blocks <verify log> [<schematic log>...]   (circuit-blocks)
The verify logs are the captured stdout of tools/verify.py; the first line is PASS: ... or FAIL: ... ."""
import re
import sys
import tomllib
from pathlib import Path


def first_line(path):
    p = Path(path)
    lines = p.read_text(errors="replace").splitlines() if p.is_file() else []
    return (lines[0] if lines else "FAIL: no output (the step did not run)"), lines


def head(ok, title):
    return [f"## {'✅' if ok else '❌'} {title}", ""]


def failure_block(lines):
    return ["", "<details open><summary>First failures</summary>", "", "```", *lines[:12], "```", "", "</details>"]


def library(log):
    line, lines = first_line(log)
    ok = line.startswith("PASS")
    tomls = sorted(Path("components").glob("*/*/component.toml"))
    rows = stamped = 0
    for t in tomls:
        params = tomllib.loads(t.read_text()).get("param", {})
        rows += len(params)
        stamped += sum(1 for p in params.values() if "verified" in p)
    families = len(list(Path("components").glob("*/*/variants.toml")))
    series = len(list(Path("components").glob("*/*/catalog.csv")))
    equations = sum(len(re.findall(r"^def [a-z]", c.read_text(), re.M)) for c in Path("components").glob("*/*/calc.py"))
    tests = re.search(r"tests (\d+)", line)
    out = head(ok, "zener-library: every part checked against its datasheet data")
    out += ["| | |", "|---|---|",
            f"| Gate | `tools/verify.py --all`: **{line}** |",
            f"| Components | {len(tomls)} ({families} families, {series} catalog series) |",
            f"| Datasheet rows (each with a page cite) | {rows:,} |",
            f"| Rows with a `verified` stamp | {stamped:,} ({100 * stamped / max(rows, 1):.1f} %) |",
            f"| Datasheet equations (`calc.py`) | {equations} |",
            f"| Unit tests | {tests[1] if tests else '?'} |"]
    return out + ([] if ok else failure_block(lines)), ok


def blocks(log, schem):
    line, lines = first_line(log)
    ok = line.startswith("PASS")
    out = head(ok, "circuit-blocks: blocks build, analyses reproduce, schematics in sync")
    out += ["| | |", "|---|---|", f"| Gate | `tools/verify.py`: **{line}** |"]
    for s in schem:
        sl, _ = first_line(s)
        ok = ok and sl.startswith("PASS")
        out.append(f"| Schematic `{Path(s).stem}` | {sl[:160]} |")
    out += ["", "| Block | Judged PASS | FAIL (reported) | Input verification |", "|---|---|---|---|"]
    for md in sorted(Path("benches").glob("*/docs/design-analysis.md")):
        text = md.read_text()
        unv = len(re.findall(r"PASS \(UNVERIFIED INPUTS\)", text))
        passes = len(re.findall(r"\bPASS\b", text)) - unv
        fails = len(re.findall(r"\bFAIL\b", text))
        m = re.search(r"^(\d+) library rows read; (.*?)[.:]", text, re.M)
        inputs = (f"{m[1]} rows, all verified ✅" if m and "every one" in m[2] else f"{m[1]} rows, {m[2]} ⚠️") if m else "?"
        out.append(f"| {md.parent.parent.name} | {passes + unv}{f' ({unv} unverified)' if unv else ''} | {fails} | {inputs} |")
    return out + ([] if ok else failure_block(lines)), ok


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("library", "blocks"):
        print(__doc__)
        sys.exit(2)
    text, ok = library(sys.argv[2]) if sys.argv[1] == "library" else blocks(sys.argv[2], sys.argv[3:])
    print("\n".join(text))
