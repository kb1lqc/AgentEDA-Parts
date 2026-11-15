"""Series components: a passive whose value is a design input (docs/SPEC.md, "Series components")."""

import math

# IEC 60063 preferred-number mantissas for one decade [1.0, 10.0). Literal lists, not computed, so a human can
# compare them with the standard.
E24 = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0, 3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5,
       8.2, 9.1]
E96 = [1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30, 1.33, 1.37, 1.40, 1.43, 1.47, 1.50,
       1.54, 1.58, 1.62, 1.65, 1.69, 1.74, 1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32,
       2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09, 3.16, 3.24, 3.32, 3.40, 3.48, 3.57,
       3.65, 3.74, 3.83, 3.92, 4.02, 4.12, 4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49,
       5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65, 6.81, 6.98, 7.15, 7.32, 7.50, 7.68, 7.87, 8.06, 8.25, 8.45,
       8.66, 8.87, 9.09, 9.31, 9.53, 9.76]
# Vishay Dale "Standard resistance decade values" (document 30117, rev 04-Oct-06, titled "WSL Type Resistors"): every
# two-significant-digit value 10..99 in each decade. Mantissas 1.0 ... 9.9: n / 10 is the float nearest to the printed
# decimal (the same rule allowed_values uses for the E-series).
DECADE = [n / 10 for n in range(10, 100)]
E_SERIES = {"E24": E24, "E96": E96, "VISHAY-DECADE": DECADE}


def _table(value):
    """(key, item) pairs of a [part] table value that may be malformed (lib.check reports that)."""
    return value.items() if isinstance(value, dict) else []


def options(info):
    """[(code, tolerance param key, range param key)] of a series with tolerance options, [] for a plain series."""
    return [(code, o["tol"], o["range"]) for code, o in _table(info.get("series_tolerances", {}))
            if isinstance(o, dict) and "tol" in o and "range" in o]


def tcr_rows(info):
    """[(tcr param key, range param key)] of a series whose TCR depends on the value, [] otherwise."""
    return [(o["tcr"], o["range"]) for o in info.get("series_tcr", []) if isinstance(o, dict) and "tcr" in o and "range" in o]


def series_keys(part):
    """Param keys a series reads (value range, power, voltage limit, tolerance, tolerance options, TCR rows)."""
    keys = {part[f] for f in ("value_param", "series_power", "series_vlimit", "series_tol") if f in part}
    for _, tol, rng in options(part):
        keys |= {tol, rng}
    for tcr, rng in tcr_rows(part):
        keys |= {tcr, rng}
    return keys


def pairs(info, bounds):
    """Sorted [(value, code)] a series allows: every (value, tolerance code) with the value inside the directory range
    (`value_param`) and inside that code's own range, clipped to the directory range. A plain series (no
    `series_tolerances`) gives [(value, None)].

    bounds(key) -> (low, high) in ohm of a range row.
    """
    low, high = bounds(info["value_param"])
    mins = info.get("series_eseries_min")
    if not info.get("series_tolerances"):
        return [(v, None) for v in allowed_values(info["e_series"], low, high, mins)]
    found = []
    for code, _, key in options(info):
        lo, hi = bounds(key)
        lo, hi = max(lo, low), min(hi, high)
        if lo <= hi:
            found += [(v, code) for v in allowed_values(info["e_series"], lo, hi, mins)]
    return sorted(found, key=lambda p: (p[0], p[1]))


def allowed_values(e_series, low, high, eseries_min=None):
    """Sorted unique values (ohm) of the named E-series with low <= value <= high (a 1e-9 relative slack on the ends).

    eseries_min ({"E96": 100}, optional) raises the lower end for one E-series only: its values below that are
    left out, but the same value stays allowed when another listed series (E24) contains it.

    Each value is the float nearest to its printed decimal (2.61 x 10^3 -> 2610.0, the same float 2.61e3 gives).
    """
    found = set()
    eseries_min = eseries_min or {}
    for name in e_series:
        lo = max(low, eseries_min.get(name, low))
        for exponent in range(math.floor(math.log10(low)) - 1, math.ceil(math.log10(high)) + 2):
            for mantissa in E_SERIES[name]:
                value = float(f"{mantissa}e{exponent}")
                if lo * (1 - 1e-9) <= value <= high * (1 + 1e-9):
                    found.add(value)
    return sorted(found)


def rated_voltage(r_ohm, p70_w, vlimit_v=None):
    """Rated voltage in V: min(sqrt(P70 x R), Vlimit); sqrt(P70 x R) when the datasheet prints no Vlimit (None)."""
    rated = math.sqrt(p70_w * r_ohm)
    return rated if vlimit_v is None else min(rated, vlimit_v)


def mpn_table(calc, pair_list):
    """([(value, code, mpn)], [problem text]) from calc.mpn over every (value, code) pair (code None: calc.mpn(value),
    else calc.mpn(value, code)): an exception or a repeated MPN is a problem."""
    rows, problems, seen = [], [], {}
    for value, code in pair_list:
        args = (value,) if code is None else (value, code)
        shown = f"{value:g}" + ("" if code is None else f", '{code}'")
        try:
            mpn = calc.mpn(*args)
        except Exception as e:
            problems.append(f"calc.mpn({shown}) raised {type(e).__name__}: {e}")
            continue
        if mpn in seen:
            problems.append(f"calc.mpn gives '{mpn}' for both {seen[mpn]} and {shown} ohm")
        seen[mpn] = shown
        rows.append((value, code, mpn))
    return rows, problems
