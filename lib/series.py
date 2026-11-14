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
E_SERIES = {"E24": E24, "E96": E96}


def series_keys(part):
    """Param keys a series reads (value range, power, voltage limit, tolerance), as named in its [part] table."""
    return {part[f] for f in ("value_param", "series_power", "series_vlimit", "series_tol") if f in part}


def allowed_values(e_series, low, high):
    """Sorted unique values (ohm) of the named E-series with low <= value <= high (a 1e-9 relative slack on the ends).

    Each value is the float nearest to its printed decimal (2.61 x 10^3 -> 2610.0, the same float 2.61e3 gives).
    """
    found = set()
    for name in e_series:
        for exponent in range(math.floor(math.log10(low)) - 1, math.ceil(math.log10(high)) + 2):
            for mantissa in E_SERIES[name]:
                value = float(f"{mantissa}e{exponent}")
                if low * (1 - 1e-9) <= value <= high * (1 + 1e-9):
                    found.add(value)
    return sorted(found)


def rated_voltage(r_ohm, p70_w, vlimit_v):
    """Rated voltage in V: min(sqrt(P70 x R), Vlimit)."""
    return min(math.sqrt(p70_w * r_ohm), vlimit_v)


def mpn_table(calc, values):
    """([(value, mpn)], [problem text]) from calc.mpn over every value: an exception or a repeated MPN is a problem."""
    rows, problems, seen = [], [], {}
    for value in values:
        try:
            mpn = calc.mpn(value)
        except Exception as e:
            problems.append(f"calc.mpn({value:g}) raised {type(e).__name__}: {e}")
            continue
        if mpn in seen:
            problems.append(f"calc.mpn gives '{mpn}' for both {seen[mpn]:g} and {value:g} ohm")
        seen[mpn] = value
        rows.append((value, mpn))
    return rows, problems
