"""Validate component.toml files: python3 -m lib.check [component paths...]"""

import ast
import inspect
import re
import sys
import tomllib
from pathlib import Path

from . import kicad, series
from .component import ROOT, load_calc, merge_variant, run_example, variants_of
from .units import to_si

PART_FIELDS = ["value", "mpn", "manufacturer", "description", "category", "package", "datasheet_url",
               "datasheet_rev", "datasheet_date", "kicad_symbol", "kicad_footprint", "step"]
PIN_FIELDS = ["number", "name", "type", "function", "cite"]
PARAM_FIELDS = ["name", "kind", "scope", "unit", "conditions", "cite"]
PIN_TYPES = {"input", "output", "bidirectional", "tri_state", "passive", "free", "unspecified", "power_in",
             "power_out", "open_collector", "open_emitter", "no_connect"}
KINDS = {"abs_max", "rec_op", "electrical", "thermal", "mechanical"}
SCOPES = {"25C", "full", "partial", "na"}
CITE_STARTS = ("DS p.", "DS PDF p.")


SERIES_FIELDS = ["value_param", "e_series", "series_power", "series_vlimit", "series_tol"]


def check_part(part, folder, family=False):
    """[part] table: required fields, value == directory name, KiCad/STEP files exist.
    A family's shared [part] has no mpn (each variant sets its own, checked in check_variant); a series has none
    either (calc.mpn gives it, checked in check_series_part)."""
    out = []
    for f in PART_FIELDS:
        if (family or part.get("series")) and f == "mpn":
            continue
        if f not in part:
            out.append(("ERROR", f"[part] missing field '{f}'"))
    if part.get("value", folder.name) != folder.name:
        out.append(("ERROR", f"[part] value '{part['value']}' differs from directory '{folder.name}'"))
    for f in ("kicad_symbol", "kicad_footprint"):
        if f in part and not (folder / part[f]).exists():
            out.append(("ERROR", f"{f} file not found: {part[f]}"))
    if part.get("datasheet_file") and not (ROOT / part["datasheet_file"]).exists():
        out.append(("WARN", f"datasheet_file not found: {part['datasheet_file']} (PDFs are not committed)"))
    step = part.get("step", "none")
    if step not in ("embedded", "none") and not (folder / step).exists():
        out.append(("ERROR", f"step file not found: {step}"))
    return out


def check_pins(pins):
    """[[pin]] entries: required fields and a known type."""
    out = []
    numbers = [str(p.get("number")) for p in pins]
    for num in sorted({n for n in numbers if numbers.count(n) > 1}):
        out.append(("ERROR", f"pin {num}: number appears more than once in [[pin]]"))
    for i, pin in enumerate(pins):
        label = f"pin {pin.get('number', f'#{i + 1}')}"
        if pin.get("cite") and not pin["cite"].startswith(CITE_STARTS):
            out.append(("WARN", f"{label}: cite should start with 'DS p.' or 'DS PDF p.'"))
        for f in PIN_FIELDS:
            if not pin.get(f):
                out.append(("ERROR", f"{label}: missing '{f}'" + (" (cite)" if f == "cite" else "")))
        if pin.get("type") and pin["type"] not in PIN_TYPES:
            out.append(("ERROR", f"{label}: unknown type '{pin['type']}'"))
    return out


def has_field(t, field):
    """True if the TOML row gives min/typ/max (a tol_pct row gives min and max through its typ)."""
    return field in t or ("tol_pct" in t and field in ("min", "max"))


def check_tol_pct(label, t):
    """tol_pct = [lo, hi] (printed percent): needs typ, no min/max, lo <= hi."""
    if "tol_pct" not in t:
        return []
    tol = t["tol_pct"]
    if not (isinstance(tol, list) and len(tol) == 2 and all(isinstance(x, (int, float)) for x in tol)):
        return [("ERROR", f"{label}: tol_pct must be [lo, hi] numbers")]
    out = []
    if "typ" not in t or "min" in t or "max" in t:
        out.append(("ERROR", f"{label}: tol_pct needs typ and no min/max"))
    if tol[0] > tol[1]:
        out.append(("ERROR", f"{label}: tol_pct lo {tol[0]} > hi {tol[1]}"))
    return out


def check_series(label, key, t):
    """Key and symbol both ending in _<digits>: the numbers must agree (vovc_thr_10 with symbol ..._16 is a typo)."""
    k, s = re.search(r"_(\d+)$", key), re.search(r"_(\d+)$", t.get("symbol", ""))
    if k and s and int(k.group(1)) != int(s.group(1)):
        return [("ERROR", f"{label}: key suffix {int(k.group(1))} != symbol suffix {int(s.group(1))}")]
    return []


def check_param(key, t, pin_names=(), used_by_series=False):
    """One [param.key] table (used_by_series: the series check reads this row, so it needs no Zener disposition)."""
    out = []
    label = f"param {key}"
    for f in PARAM_FIELDS:
        if f not in t or (f == "cite" and not t[f]):
            out.append(("ERROR", f"{label}: missing '{f}'"))
    if t.get("cite") and not t["cite"].startswith(CITE_STARTS):
        out.append(("WARN", f"{label}: cite should start with 'DS p.' or 'DS PDF p.'"))
    if t.get("kind") not in KINDS and "kind" in t:
        out.append(("ERROR", f"{label}: kind '{t['kind']}' not one of {sorted(KINDS)}"))
    if t.get("scope") not in SCOPES and "scope" in t:
        out.append(("ERROR", f"{label}: scope '{t['scope']}' not one of {sorted(SCOPES)}"))
    out.extend(check_tol_pct(label, t) + check_series(label, key, t))
    has_number = any(f in t for f in ("min", "typ", "max"))
    if has_number == ("text" in t):  # both or neither
        out.append(("ERROR", f"{label}: needs either min/typ/max or text, not both and not neither"))
    if t.get("sym") and ("max" not in t or "min" in t):
        out.append(("ERROR", f"{label}: sym = true needs max and no min"))
    if t.get("curve") and not any(w in t.get("cite", "").lower() for w in ("fig", "graph")):
        out.append(("WARN", f"{label}: curve value but cite does not name a figure or graph"))
    out.extend(check_zen_fields(label, t, pin_names, used_by_series))
    for f in ("min_ref", "max_ref", "typ_ref"):
        if f in t and t[f] not in pin_names:
            out.append(("ERROR", f"{label}: {f} '{t[f]}' is not a [[pin]] name"))
    if "typ_ref" in t and "typ" not in t:
        out.append(("ERROR", f"{label}: typ_ref needs typ"))
    out.extend(check_order(label, t))
    return out


def check_zen_fields(label, t, pin_names, used_by_series=False):
    """check_pins / check_ambient / unchecked (docs/SPEC.md, Zener wrapper)."""
    out = []
    pins = t.get("check_pins", [])
    if pins and (t.get("unit", "").lstrip("munpkMG") != "V" or "text" in t or t.get("curve")):
        out.append(("ERROR", f"{label}: check_pins needs a numeric voltage param (not text, not curve)"))
    for pin in pins:
        if pin not in pin_names:
            out.append(("ERROR", f"{label}: check_pins '{pin}' is not a [[pin]] name"))
    if pins and not any(has_field(t, f) for f in ("min", "max")):
        out.append(("ERROR", f"{label}: check_pins needs a min or max"))
    if t.get("check_ambient") and (t.get("unit") != "degC" or not has_field(t, "min") or not has_field(t, "max") or t.get("curve")):
        out.append(("ERROR", f"{label}: check_ambient needs a degC param with min and max (not curve)"))
    if "unchecked" in t and not str(t["unchecked"]).strip():
        out.append(("ERROR", f"{label}: unchecked needs a reason"))
    if t.get("kind") in ("abs_max", "rec_op") and not (pins or t.get("check_ambient") or t.get("unchecked") or used_by_series):
        out.append(("WARN", f"{label}: {t['kind']} row has no check_pins, check_ambient or unchecked reason"))
    return out


def check_order(label, t):
    """Units known, values numeric, min <= typ <= max compared in SI."""
    try:
        v = {f: to_si(t[f], t.get("unit", ""))[0] for f in ("min", "typ", "max") if f in t}
        if not v:
            to_si(0, t.get("unit", ""))  # still validate the unit
    except ValueError as e:
        return [("ERROR", f"{label}: {e}")]
    if "tol_pct" in t:
        return []  # min/max come from typ and the percentages (check_tol_pct)
    if "min_ref" in t or "max_ref" in t or "typ_ref" in t:
        return []  # offsets from different pins (2 from -VS, -2 from +VS) cannot be ordered
    if t.get("sym") and "max" in v:
        v["min"] = -v["max"]
    if t.get("typ_pm") and "typ" in v:
        v["typ"] = 0.0
    vals = [v[f] for f in ("min", "typ", "max") if f in v]
    if vals != sorted(vals):
        return [("ERROR", f"{label}: min <= typ <= max violated ({vals} in SI)")]
    return []


def check_series_part(part, pins, params, folder):
    """[part] series fields, the rows they name, and calc.mpn over every allowed value (docs/SPEC.md, Series components)."""
    if part.get("series") != "resistor":
        return [("ERROR", f"[part] series = '{part.get('series')}': only 'resistor' is supported")]
    out = [("ERROR", f"[part] series needs '{f}'") for f in SERIES_FIELDS if f not in part]
    if "mpn" in part:
        out.append(("ERROR", "[part] mpn must be absent for a series: calc.mpn(value) is the single source"))
    if len(pins) != 2:
        out.append(("ERROR", f"a series resistor needs exactly 2 pins, found {len(pins)}"))
    for f in ("value_param", "series_power", "series_vlimit", "series_tol"):
        if f in part and part[f] not in params:
            out.append(("ERROR", f"[part] {f} = '{part[f]}' is not a param key"))
    names = part.get("e_series", [])
    unknown = [n for n in names if n not in series.E_SERIES]
    if unknown or not names:
        out.append(("ERROR", f"[part] e_series must list names from {sorted(series.E_SERIES)}, got {names}"))
    rng = params.get(part.get("value_param"), {})
    if rng and not (rng.get("unit", "").endswith("ohm") and "min" in rng and "max" in rng):
        out.append(("ERROR", f"param {part['value_param']}: the series value range needs min, max and an ohm unit"))
    tol = params.get(part.get("series_tol"), {})
    if tol and not (tol.get("unit") in ("%", "ppm") and "min" in tol and "max" in tol):
        out.append(("ERROR", f"param {part['series_tol']}: the series tolerance needs min, max and unit %"))
    if out:
        return out
    if not (folder / "calc.py").exists():
        return [("ERROR", "a series needs calc.py with mpn(value)")]
    try:
        calc = load_calc(folder / "calc.py")
    except Exception:
        return []  # check_calc reports the import failure
    if not callable(getattr(calc, "mpn", None)):
        return [("ERROR", "calc.py of a series must define mpn(value)")]
    values = series.allowed_values(names, *(to_si(rng[f], rng["unit"])[0] for f in ("min", "max")))
    return [("ERROR", msg) for msg in series.mpn_table(calc, values)[1]]


def check_kicad(pins, part, folder):
    """TOML pins vs symbol pins (exact), and footprint pads cover every pin number."""
    out = []
    sym, fp = folder / part.get("kicad_symbol", ""), folder / part.get("kicad_footprint", "")
    if part.get("kicad_symbol") and sym.exists():
        symbol = {num: (name, typ) for num, name, typ in kicad.symbol_pins(sym)}
        toml = {str(p.get("number")): (p.get("name"), p.get("type")) for p in pins}
        for num in sorted(toml.keys() - symbol.keys()):
            out.append(("ERROR", f"pin {num}: in TOML but not in symbol"))
        for num in sorted(symbol.keys() - toml.keys()):
            out.append(("ERROR", f"pin {num}: in symbol ({symbol[num][0]}) but not in TOML"))
        for num in sorted(toml.keys() & symbol.keys()):
            if toml[num][0] != symbol[num][0]:
                out.append(("ERROR", f"pin {num}: name mismatch, TOML '{toml[num][0]}' vs symbol '{symbol[num][0]}'"))
            if toml[num][1] != symbol[num][1]:
                out.append(("ERROR", f"pin {num}: type mismatch, TOML '{toml[num][1]}' vs symbol '{symbol[num][1]}'"))
    if part.get("kicad_footprint") and fp.exists():
        for num in sorted({str(p.get("number")) for p in pins} - kicad.footprint_pads(fp)):
            out.append(("ERROR", f"pin {num}: no footprint pad with that number"))
    return out


def check_imports(path):
    """ERROR for every import in calc.py other than math."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or "."]
        out += [("ERROR", f"calc.py imports '{n}'; only math is allowed") for n in names if n.split(".")[0] != "math"]
    return out


def check_inputs(calc, params):
    """INPUTS = {function: {argument: "key" or "key.min|typ|max"}}: function, argument, key and field must exist."""
    inputs = getattr(calc, "INPUTS", None)
    if not inputs:
        return [("WARN", "calc.py has no INPUTS")]
    out = []
    for fname, args in inputs.items():
        fn = getattr(calc, fname, None)
        if not callable(fn):
            out.append(("ERROR", f"INPUTS: function '{fname}' does not exist"))
            continue
        for arg, key in args.items():
            if arg not in inspect.signature(fn).parameters:
                out.append(("ERROR", f"INPUTS: {fname} has no argument '{arg}'"))
            name, _, field = key.partition(".")
            if name not in params:
                out.append(("ERROR", f"INPUTS: {fname}.{arg} -> unknown param key '{name}'"))
            elif field and field not in ("min", "typ", "max"):
                out.append(("ERROR", f"INPUTS: {fname}.{arg} -> '{key}': field must be min, typ or max"))
            elif field and not has_field(params[name], field):
                out.append(("ERROR", f"INPUTS: {fname}.{arg} -> '{key}': the DS gives no {field}"))
            elif not field and not (has_field(params[name], "min") and has_field(params[name], "max")) and not params[name].get("sym"):
                out.append(("WARN", f"INPUTS: {fname}.{arg} -> '{key}' has no min/max range; wca cannot sweep "
                                    f"it. Name the field, e.g. '{key}.typ'"))
    return out


def check_examples(calc):
    """EXAMPLES present and reproducing within tolerance."""
    examples = getattr(calc, "EXAMPLES", None)
    if not examples:
        return [("WARN", "calc.py has no EXAMPLES")]
    out = []
    for row in examples:
        if not callable(getattr(calc, row[0], None)):
            out.append(("ERROR", f"example function '{row[0]}' does not exist"))
            continue
        try:
            got, ok = run_example(calc, row)
        except Exception as e:
            out.append(("ERROR", f"example {row[0]}{row[1]}: {type(e).__name__}: {e}"))
            continue
        if not ok:
            out.append(("ERROR", f"example {row[0]}{row[1]}: got {got:.6g}, expected {row[2]:.6g} "
                                 f"(tol {row[3]:g}) [{row[4]}]"))
    return out


def check_calc(folder, params, inputs=True):
    """calc.py present, imports only math, EXAMPLES and INPUTS valid (inputs=False: a family checks them per variant)."""
    if not (folder / "calc.py").exists():
        return [("WARN", "no calc.py")]
    out = check_imports(folder / "calc.py")
    try:
        calc = load_calc(folder / "calc.py")
    except Exception as e:
        return out + [("ERROR", f"calc.py fails to import: {e}")]
    return out + check_examples(calc) + (check_inputs(calc, params) if inputs else [])


def check_component(folder):
    """All checks for one component directory. Returns [(level, message), ...].

    A family (variants.toml present): the shared file is checked once; each variant's merged params get the
    param and INPUTS checks, reported as 'variant <Value>: ...'.
    """
    folder = Path(folder)
    toml_file = folder / "component.toml"
    if not toml_file.exists():
        return [("ERROR", "component.toml not found")]
    try:
        with open(toml_file, "rb") as f:
            data = tomllib.load(f)
        variants = variants_of(folder)
    except tomllib.TOMLDecodeError as e:
        return [("ERROR", f"component.toml or variants.toml is not valid TOML: {e}")]
    part, pins = data.get("part", {}), data.get("pin", [])
    out = check_part(part, folder, family=bool(variants)) + check_pins(pins)
    names = {p.get("name") for p in pins}
    used = series.series_keys(part)
    if part.get("series") and variants:
        out.append(("ERROR", "a series component cannot be a family (variants.toml)"))
    elif part.get("series"):
        out += check_series_part(part, pins, data.get("param", {}), folder)
    for key, table in data.get("param", {}).items():
        out += check_param(key, table, names, used_by_series=key in used)
    out += check_kicad(pins, part, folder)
    if not variants:
        return out + check_calc(folder, data.get("param", {}))
    out += check_calc(folder, data.get("param", {}), inputs=False)
    for key, table in data.get("param", {}).items():
        for v in table.get("variants", []):
            if v not in variants:
                out.append(("ERROR", f"param {key}: variants names unknown variant '{v}'"))
    calc = load_calc(folder / "calc.py") if (folder / "calc.py").exists() else None
    for name in sorted(variants):
        merged = merge_variant(data, variants, name)
        found = [(lvl, f"variant {name}: {msg}") for lvl, msg in check_variant(merged, variants[name], names, calc)]
        out += found
    return out


def check_variant(merged, own, pin_names, calc):
    """Checks for one variant: required [part] fields, its override rows, INPUTS resolving in its merged params."""
    out = [("ERROR", f"[part] missing field '{f}'") for f in PART_FIELDS if f not in merged["part"]]
    for f in ("mpn", "alternates", "temp_grade"):  # inherited values would silently be wrong for some variants
        if f not in own:
            out.append(("ERROR", f"must set its own {f} in variants.toml"))
    for key, table in own.get("param", {}).items():
        out += check_param(key, table, pin_names)
    return out + (check_inputs(calc, merged["param"]) if calc else [])


def find_components(args):
    """Directories from the command line (dir or component.toml path), else all in components/."""
    if not args:
        return sorted(p.parent for p in (ROOT / "components").glob("*/*/component.toml"))
    return [Path(a).parent if a.endswith("component.toml") else Path(a) for a in args]


def main(argv=None):
    """Print problems, a summary, and return the exit code (1 if any ERROR)."""
    folders = find_components(sys.argv[1:] if argv is None else argv)
    errors = warns = 0
    for folder in folders:
        for level, msg in check_component(folder):
            print(f"{folder.parent.name}/{folder.name}: {level}: {msg}")
            errors += level == "ERROR"
            warns += level == "WARN"
    print(f"{len(folders)} components, {errors} errors, {warns} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
