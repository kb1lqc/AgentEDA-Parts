"""Generate a Zener wrapper (<Value>.zen + pcb.toml) for each component, from component.toml.

    python3 -m lib.zen [component dirs...]      (default: every components/*/*/component.toml)

A family directory (variants.toml) gets one wrapper per variant, <Variant>.zen, and one pcb.toml.

component.toml stays the single source of truth. The wrapper only adds what Zener is for: pins as typed nets for
circuit capture, the KiCad symbol/footprint, part info, and DC checks on the voltages the instance declares.
Which rows become checks is stated in component.toml with `check_pins` / `check_ambient` (docs/SPEC.md, Zener).
Every other abs_max / rec_op row is listed in the wrapper as UNCHECKED with its reason.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import series
from .component import ROOT, load_calc, merge_variant, to_param, variants_of

GROUND_NAMES = {"GND", "AGND", "DGND", "PGND", "SGND", "VSS", "VSSA"}

# Verbatim template core: unset input -> UNVERIFIED warning (advice when the part is built alone); a waiver drops a
# warning-level check to advice; errors cannot be waived.
TEMPLATE_CORE = '''_ROOT = len(builtin.current_module_path()) == 0  # built standalone, not instantiated
check(derate > 0 and derate <= 1.0, "derate must be in (0, 1]; >1 would loosen abs max")


def _limit(name, fn, inputs, severity, waiver=""):
    # Unset input: UNVERIFIED warning, never a silent pass. Waiver drops a warning to advice.
    if waiver and severity != "warning":
        error("only warning-level checks can be waived: " + name)
    unset = [k for k, v in inputs.items() if v == None]
    if unset:

        def _unverified(_m):
            error("UNVERIFIED " + name + ": no value for " + ", ".join(unset))

        builtin.add_electrical_check(name=name, check_fn=_unverified, severity="advice" if _ROOT else "warning")
    else:
        builtin.add_electrical_check(name=name, check_fn=fn, inputs=inputs, severity="advice" if waiver else severity)


def _range(_m, v, what, lo=None, hi=None, lo_ref=None, hi_ref=None):
    # Worst case: v.min >= lo + lo_ref.max and v.max <= hi + hi_ref.min (narrowest window). No ref = absolute.
    lo_b = None if lo == None else lo + (0.0 if lo_ref == None else lo_ref.max)
    hi_b = None if hi == None else hi + (0.0 if hi_ref == None else hi_ref.min)
    ok = (lo_b == None or v.min >= lo_b) and (hi_b == None or v.max <= hi_b)
    lo_t = "no limit" if lo_b == None else "%s V" % lo_b
    hi_t = "no limit" if hi_b == None else "%s V" % hi_b
    check(ok, "%s: %s to %s V outside %s to %s" % (what, v.min, v.max, lo_t, hi_t))


def _temp(_m, v, what, lo, hi):
    # Temperatures are kelvin floats in Zener; messages in degC.
    ok = v.min >= lo and v.max <= hi
    msg = "%s: %s to %s degC outside %s to %s degC"
    check(ok, msg % (what, v.min - 273.15, v.max - 273.15, lo - 273.15, hi - 273.15))
'''


def io_name(pin_name):
    """'+IN' -> 'IN_P', '-VS' -> 'VS_N', 'NC3' -> 'NC3', 'V+' -> 'V_P'."""
    name = pin_name.strip()
    suffix = ""
    if name.startswith("+"):
        name, suffix = name[1:], "_P"
    elif name.startswith("-"):
        name, suffix = name[1:], "_N"
    elif name.endswith("+"):
        name, suffix = name[:-1], "_P"
    elif name.endswith("-"):
        name, suffix = name[:-1], "_N"
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper() + suffix
    return name if not name[:1].isdigit() else "P" + name


def num(x):
    """Float literal for Zener, rounded to 9 decimals so 273.15-offset temperatures print cleanly."""
    return repr(round(float(x), 9))


def limit_args(t, p, key, nets, derate):
    """Zener argument text for one voltage limit: lo/hi (derated if abs_max) and lo_ref/hi_ref."""
    args = []
    for end, field, ref_field in (("lo", "min", "min_ref"), ("hi", "max", "max_ref")):
        value = getattr(p, field)
        if value is None:
            continue
        text = num(value)
        away_from_zero = (end == "lo" and value < 0) or (end == "hi" and value > 0)
        if derate and away_from_zero:
            text += " * derate"
        args.append(f'"{end}": {text}')
        ref = t.get(ref_field)
        if ref:
            args.append(f'"{end}_ref": {nets[ref]}.voltage')
    return args


def comment_block(key, t, p, what, severity, why):
    """Comment above each check: what, DS row, printed limit, conditions, severity and why."""
    printed = " / ".join(f"{f} {t[f]}" for f in ("min", "typ", "max") if f in t)
    if "tol_pct" in t:
        printed += f" (tol_pct {t['tol_pct'][0]:+g} % / {t['tol_pct'][1]:+g} %; min/max follow from typ)"
    refs = " ".join(f"({f} rel. {t[f]})" for f in ("min_ref", "max_ref") if t.get(f))
    lines = [
        f"# {key}: {what}",
        f"#   {t.get('name', '')}: {printed} {t.get('unit', '')} {refs}".rstrip(),
        f"#   {t.get('cite', '')}",
    ]
    if t.get("conditions"):
        lines.append(f"#   Conditions: {t['conditions']}")
    if t.get("sym"):
        lines.append("#   sym = true: DS prints an unsigned magnitude, checked as +/- that value.")
    lines.append(f"#   Severity {severity}: {why}")
    return lines


def severity_of(t):
    """(severity, why, waivable). abs_max / rec_op over the grade = error; 25 degC-only or partial = warning."""
    if t.get("scope") in ("25C", "partial"):
        return "warning", f"limit holds only at {t['scope']} (waivable with waive_<check>)", True
    return "error", f"{t['kind']} violated", False


def micro_ohm(value):
    """Integer micro-ohms: the dict key for a resistance (float text differs between Python and Zener, ints do not)."""
    return int(round(value * 1e6))


def series_code(info, params, part_dir):
    """(lookup lines, check lines, problems) for a series component: MPN lookup by value and the voltage-across check.

    The MPN dict is generated from calc.mpn over every allowed value, so calc.py stays the single source.
    """
    problems = []
    rng, power, vlim = (to_param(params[info[f]]) for f in ("value_param", "series_power", "series_vlimit"))
    values = series.allowed_values(info["e_series"], rng.min, rng.max)
    rows, mpn_problems = series.mpn_table(load_calc(part_dir / "calc.py"), values)
    problems += mpn_problems
    if power.max is None or vlim.max is None or power.unit != "W" or vlim.unit != "V":
        return [], [], problems + ["series_power needs a W row with max and series_vlimit a V row with max"]
    if any(abs(micro_ohm(v) / 1e6 - v) > 1e-9 * v for v in values):
        problems.append("a series value is not a whole number of micro-ohm")
    if not rows:
        return [], [], problems + ["no allowed values"]
    t = params[info["series_power"]]
    tv = params[info["series_vlimit"]]
    allowed = f"{'/'.join(info['e_series'])} values from {rng.min:g} to {rng.max:g} ohm"
    lines = [
        "# Orderable part number per value, generated from calc.mpn() over every allowed value (calc.py is the single",
        "# source). Keys are integer micro-ohms: float text differs between Python and Zener, integers do not.",
        "_MPN = {",
        *[f'    {micro_ohm(v)}: "{m}",  # {v:g} ohm' for v, m in rows],
        "}",
        "_KEY = int(value.value * 1e6 + 0.5)",
        "# Part number for an allowed value; any other value takes the first entry and fails value_allowed below.",
        f"_MPN_STR = _MPN.get(_KEY, _MPN[{micro_ohm(rows[0][0])}])",
        "",
        "",
        "def _allowed(_m, r, what):",
        f'    check(_KEY in _MPN, "%s: %s ohm is not an allowed value ({allowed})" % (what, r))',
        "",
        "",
        # A required config reads 0 while the module file is first loaded, so this is a check, not an error() call.
        '_ALLOWED_SEVERITY = "advice" if _ROOT else "error"  # standalone build: value is unset',
        'builtin.add_electrical_check(name="value_allowed", check_fn=_allowed, inputs={"r": value.value, '
        '"what": "value_allowed"}, severity=_ALLOWED_SEVERITY)',
        "",
        "",
        "def _rated_voltage(_m, v1, v2, what, r, p, vlim, derate):",
        "    # Worst case |V(P1) - V(P2)| over both nets' ranges. Zener has no sqrt, so compare squares:",
        "    # vmax <= derate x min(sqrt(P x R), vlim)  <=>  vmax^2 <= derate^2 x min(P x R, vlim^2).",
        "    vmax = max(v1.max - v2.min, v2.max - v1.min)",
        "    limit2 = min(p * r, vlim * vlim) * derate * derate",
        '    msg = "%s: up to %s V across the part, (V across)^2 = %s V^2 > %s V^2 = derate^2 x min(P x R, Vlimit^2) '
        'with R = %s ohm, P = %s W, Vlimit = %s V"',
        "    check(vmax * vmax <= limit2, msg % (what, vmax, vmax * vmax, limit2, r, p, vlim))",
    ]
    name = "rated_voltage"
    checks = [
        f"# {name}: voltage across the part within min(sqrt(P x R), Vlimit), x derate",
        f"#   Power rating {info['series_power']}: {t.get('name', '')}: max {t.get('max')} {t.get('unit', '')} "
        f"({t.get('cite', '')})",
        f"#   Voltage limit {info['series_vlimit']}: {tv.get('name', '')}: max {tv.get('max')} {tv.get('unit', '')} "
        f"({tv.get('cite', '')})",
        "#   Evaluated for the configured value. Error: a rated part voltage is exceeded.",
        "#   Not checked here: power derating above 70 degC (curve) is the module's job, calc.rated_power;",
        "#   above 70 degC ambient this check is optimistic.",
        f'_limit("{name}", _rated_voltage, {{"v1": P1.voltage, "v2": P2.voltage, "what": "{name}", "r": value.value, '
        f'"p": {num(power.max)}, "vlim": {num(vlim.max)}, "derate": derate}}, "error")',
        "",
    ]
    return lines, checks, problems


def generate(part_dir, variant=None):
    """Return (zen_text, problems). problems is a list of strings; empty means the wrapper is complete.

    For a family directory pass variant=<Value>: the wrapper uses that variant's merged [part] and params.
    """
    import tomllib

    part_dir = Path(part_dir)
    data = tomllib.loads((part_dir / "component.toml").read_text())
    if variant is not None:
        data = merge_variant(data, variants_of(part_dir), variant)
    info, pins, params = data["part"], data.get("pin", []), data.get("param", {})
    value = info["value"]
    problems = []

    connected = [p for p in pins if p["type"] != "no_connect"]
    by_name = {}  # same-name pins are one node (two GND pins): one io, one pins={} entry
    for p in connected:
        by_name.setdefault(p["name"], []).append(p)
    nets = {p["name"]: io_name(p["name"]) for p in connected}
    if len(set(nets.values())) != len(nets):
        problems.append("two pins map to the same io name")
    grounds = [p["name"] for p in connected if p["name"].upper() in GROUND_NAMES]

    out = [
        f'"""{value}: {info.get("description", "")}.',
        f"GENERATED from component.toml by `python3 -m lib.zen`; do not edit. Source of truth: component.toml and",
        f"calc.py (numbers, cites, equations). DS: {info.get('datasheet_url', '')}, {info.get('datasheet_rev', '')}"
        f" ({info.get('datasheet_date', '')}).",
        "Checks are DC steady-state on the voltages each instance declares. They do not cover transients, overshoot,",
        "hot-plug ringing or load dump. A checked net with no declared voltage reports UNVERIFIED (a warning).",
        'Analysis (worst case, tables, plots) is done in Python: see README.md and calc.py."""',
        "",
    ]
    checks, unchecked, configs, uses_ambient = [], [], [], False
    is_series = bool(info.get("series"))
    series_rows = series.series_keys(info)

    for key, t in params.items():
        if is_series and key in series_rows and not (t.get("check_pins") or t.get("check_ambient")):
            continue  # read by the series check below, not an unchecked rating
        if t.get("kind") not in ("abs_max", "rec_op") and not (t.get("check_pins") or t.get("check_ambient")):
            continue
        if not (t.get("check_pins") or t.get("check_ambient")):
            reason = t.get("unchecked", "no check_pins / check_ambient in component.toml")
            unchecked.append(f"# UNCHECKED: {key}: {t.get('name', '')} ({t.get('cite', '')}); {reason}")
            continue
        if t.get("curve") or "text" in t:
            problems.append(f"{key}: curve or text rows cannot be checks")
            continue
        try:
            p = to_param(t)
        except ValueError as e:
            problems.append(f"{key}: {e}")
            continue
        severity, why, waivable = severity_of(t)
        waiver = ""
        if waivable:
            waiver = f"waive_{key}"
            configs.append(f'{waiver} = config(str, default="", help="Rationale with a cite for violating {key}")')
        derate = t["kind"] == "abs_max"
        for pin in t.get("check_pins", []):
            if p.unit != "V":
                problems.append(f"{key}: check_pins needs a voltage param, unit is {p.unit!r}")
                break
            if pin not in nets:
                problems.append(f"{key}: check_pins names unknown or NC pin {pin!r}")
                continue
            if any(t.get(f) and t[f] not in nets for f in ("min_ref", "max_ref")):
                problems.append(f"{key}: min_ref/max_ref is not a connected pin")
                break
            name = f"{key}_{nets[pin]}"
            what = f"pin {pin} ({nets[pin]}) within the limit" + (", x derate" if derate else "")
            checks += comment_block(name, t, p, what, severity, why)
            args = [f'"v": {nets[pin]}.voltage', f'"what": "{name}"'] + limit_args(t, p, key, nets, derate)
            tail = f", {waiver}" if waiver else ""
            checks.append(f'_limit("{name}", _range, {{{", ".join(args)}}}, "{severity}"{tail})')
            checks.append("")
        if t.get("check_ambient"):
            if p.unit != "degC" or p.min is None or p.max is None:
                problems.append(f"{key}: check_ambient needs a degC param with min and max")
                continue
            uses_ambient = True
            name = f"{key}_ambient"
            checks += comment_block(name, t, p, "board ambient range inside this range", severity, why)
            tail = f", {waiver}" if waiver else ""
            checks.append(f'_limit("{name}", _temp, {{"v": ambient, "what": "{name}", "lo": {num(p.min + 273.15)}, '
                          f'"hi": {num(p.max + 273.15)}}}, "{severity}"{tail})')
            checks.append("")

    lookup = []
    if is_series:
        lookup, series_checks, series_problems = series_code(info, params, part_dir)
        problems += series_problems
        checks += series_checks
        unchecked.append("# UNCHECKED: power derating above 70 degC: curve-based, depends on the dissipation; "
                         "owner: module (calc.rated_power). rated_voltage below uses the 70 degC power rating at")
        unchecked.append("#   every ambient, so above 70 degC ambient it is OPTIMISTIC (0 W at the derating zero).")
    units = (["Resistance"] if is_series else []) + (["Temperature"] if uses_ambient else [])
    if units:
        out += [f'load("@stdlib/units.zen", {", ".join('"' + u + '"' for u in units)})', ""]
    out += unchecked + ([""] if unchecked else [])
    out.append("# Pins: component.toml [[pin]]. power_in/power_out pins are Net io cast to Power at the pin, so a negative rail or")
    out.append("# GND can drive them; ground-named pins are Ground.")
    for name, group in by_name.items():
        kind = "Ground" if name in grounds else "Net"
        for p in group:
            out.append(f"# pin {p['number']} {p['name']}, {p['type']}: {p['function']}")
        out.append(f"{nets[name]} = io({kind})")
    nc = [f"{p['number']} {p['name']}" for p in pins if p["type"] == "no_connect"]
    if nc:
        out.append(f"# No-connect pins omitted (auto NotConnected): {', '.join(nc)}.")
    out.append("")
    if is_series:
        out.append('value = config(Resistance, help="Resistance, an allowed E-series value (see the _MPN table)")')
    if uses_ambient:
        out.append('ambient = config(Temperature, optional=True, help="Board ambient temperature range")')
    out.append('derate = config(float, default=1.0, help="Project derating factor in (0, 1]; shrinks abs-max only")')
    out += configs
    out += ["", TEMPLATE_CORE, ""] + lookup
    out += checks

    pin_map = []
    for name, group in by_name.items():
        net = nets[name]
        if any(p["type"] in ("power_in", "power_out") for p in group) and name not in grounds:
            net = f"Power({net}, voltage={net}.voltage)"
        pin_map.append(f'        "{name}": {net},')
    alts = info.get("alternates", [])
    out += [
        "Component(",
        f'    name="{value}",',
        f'    symbol=Symbol(library="./{info["kicad_symbol"]}"),',
        f'    part=Part(mpn={"_MPN_STR" if is_series else chr(34) + info["mpn"] + chr(34)}, manufacturer="{info["manufacturer"]}"'
        + (f', datasheet="{info["datasheet_url"]}"),' if info.get("datasheet_url") else "),"),  # Part() rejects an empty URL
        "    pins={",
        *pin_map,
        "    },",
    ]
    if alts:
        out.append(f"    properties={{\"alternatives\": {alts!r}}},".replace("'", '"'))
    out += [")", ""]
    return "\n".join(out), problems


def wrappers(args):
    """[(directory, variant or None)]: one entry per wrapper to write (a family gives one per variant)."""
    dirs = [Path(a) for a in args] or sorted(p.parent for p in (ROOT / "components").glob("*/*/component.toml"))
    return [(d, v) for d in dirs for v in (sorted(variants_of(d)) or [None])]


def main(argv):
    bad = 0
    for d, variant in wrappers(argv):
        text, problems = generate(d, variant)
        value = variant or d.name
        for msg in problems:
            print(f"{value}: ERROR: {msg}")
        bad += len(problems)
        (d / f"{value}.zen").write_text(text)
        toml = d / "pcb.toml"
        if not toml.exists():
            toml.write_text("")
        print(f"wrote {d / (value + '.zen')}")
    if shutil.which("pcb"):  # the committed wrapper is exactly what the toolchain's formatter produces
        for d in dict.fromkeys(d for d, _ in wrappers(argv)):
            subprocess.run(["pcb", "fmt", str(d)], check=True, capture_output=True)
    else:
        print("pcb not found: wrappers written but not formatted (run `pcb fmt` before committing)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
