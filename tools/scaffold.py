#!/usr/bin/env python3
"""Create a part scaffold: components/<Mfr>/<Value>/ with an empty pcb.toml, a component.toml template and the vendor
KiCad files. Exit 0 = created (items OK, or UNSURE for a missing STEP), 1 = FAIL (nothing is written).

Usage (repo root): python3 tools/scaffold.py <Mfr> <Value> [--root R]

Vendor files come from docs/vendor/<Value>/ (the N density lives there; L and M are moved to <Value>_unused/, which is
never read). Exactly one *.kicad_sym is required. *.kicad_mod: one, or among several exactly one ending -N, or exactly
one not ending -L/-M; otherwise FAIL (ambiguous). STEP (*.step, *.stp): zero = UNSURE, `step = "none"` (open item,
docs/CLAUDE.md "STEP missing"); several = FAIL. Files are copied as <Value>.kicad_sym / .kicad_mod / .step.
The component.toml template lists every field of docs/spec/extract.md with an EMPTY value and one empty [[pin]]:
`python3 -m lib.check` rejects it until the part is filled in, so a scaffold cannot pass as a part. FAIL if the
directory exists, a vendor file is missing or ambiguous, or Mfr/Value is not a plain directory name.
Output (sorted, no timestamps): one `item | status | reason` line each, then a summary line.
"""
import argparse
import shutil
import sys
from pathlib import Path

TEMPLATE = '''# SCAFFOLD for {value}: every value below is EMPTY on purpose. `python3 -m lib.check` fails until all are filled.
# Format contract: docs/spec/extract.md. Fill from the datasheet page images; never guess a number.

[part]
value           = ""   # directory name: {value}
mpn             = ""   # exact orderable number with reel suffix
manufacturer    = ""   # as printed in the datasheet
description     = ""   # one line
category        = ""   # snake_case part kind
package         = ""   # package name and drawing code as printed
datasheet_url   = ""
datasheet_file  = "docs/datasheets/<file>.pdf"   # git-ignored; replace <file>
datasheet_rev   = ""   # document number / revision as printed
datasheet_date  = ""   # YYYY-MM as printed
kicad_symbol    = "{value}.kicad_sym"
kicad_footprint = "{value}.kicad_mod"
step            = "{step}"   # "embedded" | "<file>.step" | "none"

# One [[pin]] per package pin, exactly matching the symbol (names verbatim from the datasheet).
[[pin]]
number   = ""   # pin number as printed
name     = ""   # verbatim; a printed minus or en dash is ASCII "-"
type     = ""   # KiCad electrical type: input output bidirectional tri_state passive free unspecified power_in
                # power_out open_collector open_emitter no_connect
function = ""   # short, from the datasheet pin table
cite     = ""   # DS p.<printed page>, <table or figure title>, <row>

# One [param.<key>] table per datasheet row (snake_case key; _25c / _full when both exist). Required fields:
# name, kind (abs_max|rec_op|electrical|thermal|mechanical), scope (25C|full|partial|na), unit, conditions, cite,
# plus min/typ/max or text. Every abs_max and rec_op row also needs check_pins, check_ambient or unchecked.
'''


def pick_mod(mods):
    """The N-density footprint among candidates, or None when it cannot be decided."""
    if len(mods) == 1:
        return mods[0]
    n = [m for m in mods if m.stem.endswith("-N")]
    if len(n) == 1:
        return n[0]
    plain = [m for m in mods if not m.stem.endswith(("-L", "-M"))]
    return plain[0] if len(plain) == 1 else None


def plan(root, mfr, value):
    """([(item, status, reason)], copies) where copies = [(src, dst name)]; any FAIL means do nothing."""
    items, copies = [], []
    for label, name in (("Mfr", mfr), ("Value", value)):
        if not name or name.startswith(".") or "/" in name or "\\" in name or name in ("..", "."):
            items.append((label, "FAIL", f"not a plain directory name: {name!r}"))
    if items:
        return items, copies
    dest = root / "components" / mfr / value
    if dest.exists():
        items.append(("directory", "FAIL", f"{dest.relative_to(root)} already exists"))
        return items, copies
    vend = root / "docs" / "vendor" / value
    if not vend.is_dir():
        items.append(("vendor", "FAIL", f"missing: docs/vendor/{value}/"))
        return items, copies
    files = sorted(p for p in vend.rglob("*") if p.is_file())
    for kind, suffixes, dst in (("symbol", (".kicad_sym",), f"{value}.kicad_sym"),
                                ("footprint", (".kicad_mod",), f"{value}.kicad_mod"),
                                ("step", (".step", ".stp"), f"{value}.step")):
        found = [p for p in files if p.suffix.lower() in suffixes]
        if kind == "footprint" and len(found) > 1:
            pick = pick_mod(found)
            found = [pick] if pick else found
        rel = lambda p: str(p.relative_to(root))
        if len(found) == 1:
            items.append((kind, "OK", f"{rel(found[0])} -> {dst}"))
            copies.append((found[0], dst))
        elif not found and kind == "step":
            items.append((kind, "UNSURE", f"no STEP in docs/vendor/{value}/: step = \"none\", open item"))
        elif not found:
            items.append((kind, "FAIL", f"missing: no {suffixes[0]} under docs/vendor/{value}/"))
        else:
            items.append((kind, "FAIL", "ambiguous: " + ", ".join(rel(p) for p in found)))
    return items, copies


def scaffold(root, mfr, value):
    """Create the scaffold. Returns (exit code, output lines)."""
    root = Path(root)
    items, copies = plan(root, mfr, value)
    if not any(s == "FAIL" for _, s, _ in items):
        dest = root / "components" / mfr / value
        has_step = any(d.endswith(".step") for _, d in copies)
        try:
            dest.mkdir(parents=True)
            (dest / "pcb.toml").write_text("")
            (dest / "component.toml").write_text(TEMPLATE.format(value=value, step=f"{value}.step" if has_step else "none"))
            for src, name in copies:
                shutil.copyfile(src, dest / name)
        except OSError as e:
            shutil.rmtree(dest, ignore_errors=True)
            items.append(("write", "FAIL", str(e)))
        else:
            items.append(("component.toml", "OK", "template, empty values (rejected by lib.check until filled)"))
            items.append(("pcb.toml", "OK", "empty"))
    counts = {s: sum(1 for _, t, _ in items if t == s) for s in ("OK", "UNSURE", "FAIL")}
    lines = [f"{i} | {s} | {r}" for i, s, r in sorted(items)]
    lines.append(f"scaffold {mfr}/{value}: {counts['OK']} OK, {counts['UNSURE']} UNSURE, {counts['FAIL']} FAIL")
    return (1 if counts["FAIL"] else 0), lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mfr")
    ap.add_argument("value")
    ap.add_argument("--root", default=Path(__file__).resolve().parent.parent)
    a = ap.parse_args(argv)
    rc, lines = scaffold(Path(a.root).resolve(), a.mfr, a.value)
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main())
