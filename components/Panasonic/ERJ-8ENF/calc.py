"""ERJ-8ENF (1206, +/-1 %) datasheet equations. DS: Panasonic "Fixed Resistors" products catalog, 2026.5,
"Precision Thick Film Chip Resistors" (printed pp.9-11; page footers 29-May-25). Arguments and return values are floats in
SI units (ohm, W, V, degC) and fractions for tolerance and TCR (1/degC). Only math is imported.

ERJ8EN is marked NRFND (Not recommended for new design) in the catalog. The equations are the printed ones.
Rated power and voltage are printed for 70 degC ambient and the limiting element voltage (DS p.10, Ratings <+/-1 %>).
The DS has no Absolute Maximum Ratings table.
"""

import math


def rated_voltage(r, p70, v_limit):
    """RCWV = min(sqrt(P x R), limiting element voltage). DS p.10, Ratings <+/-1 %>, footnote *2 (printed formula).
    r: ohm. p70: W (rated power at 70 degC). v_limit: V. Returns: V."""
    return min(math.sqrt(p70 * r), v_limit)


def rated_power(ta_c, p70, knee_c, zero_c):
    """Rated power in W at AMBIENT temperature ta_c (degC).
    p70 is the printed 70 degC rating (DS p.10, Ratings <+/-1 %>). knee_c = 70 degC is printed in the derating text
    (DS p.10). zero_c = 155 degC is read off the DS p.10 derating figure (155 degC line, curve = true).
    Result: p70 up to knee_c, then a linear fall to 0 W at zero_c. Above knee_c the result is a CURVE-BASED ESTIMATE,
    not a datasheet bound. ta_c at or above zero_c gives 0 W.
    ta_c, knee_c, zero_c: degC. p70: W. Returns: W."""
    if ta_c <= knee_c:
        return p70
    if ta_c >= zero_c:
        return 0.0
    return p70 * (zero_c - ta_c) / (zero_c - knee_c)


def resistance_worst(r0, tol, tcr, t_c, t_ref_c):
    """Not a DS equation: combines tolerance (DS p.10) and TCR (DS p.10) per the SPEC temperature recipe.
    r0 is the plain nominal value (a float, e.g. from part.values()), NOT part.series_value(), which already carries
    the tolerance: passing both would count the tolerance twice. The DS
    states no reference temperature for either; the caller supplies t_ref_c (25 degC is the usual assumption; the DS
    T.C.R. test runs from +25 degC).
    R = R0 x (1 + tol) x (1 + tcr x (T - Tref)). Call with tol = -0.01 and +0.01 for the two worst corners.
    The TCR term is valid only over the span the DS covers, which the DS does not state (open item).
    r0: ohm. tol: fraction (0.01 = 1 %). tcr: 1/degC (100e-6 = 100 ppm/degC). t_c, t_ref_c: degC. Returns: ohm."""
    return r0 * (1.0 + tol) * (1.0 + tcr * (t_c - t_ref_c))


def mpn(r_ohm):
    """Not a DS equation: part-number string from the DS decode rule (DS p.9, Explanation of part numbers, +/-1 %
    block): ERJ8EN + F (tolerance) + 4-digit code + V (packaging). Code = three significant digits then the number of
    zeros: 1002 = 10 kohm. The DS prints the hyphen-less form (ERJ8EN), so the prefix is written without the hyphen.
    Below 100 ohm the code is three significant digits with the decimal point written as "R" (DS p.9: "Decimal
    point is expressed by 'R'"), e.g. 49.9 ohm -> 49R9, 10 ohm -> 10R0. Series range 10 ohm to 2.2 Mohm (DS p.10).
    Returns: str."""
    lo, hi = 10.0, 2.2e6
    if not lo <= r_ohm <= hi:
        raise ValueError(f"ERJ8ENF: {r_ohm} ohm outside the printed range 10 ohm to 2.2 Mohm")
    if r_ohm < 100.0:  # 10.0 to 99.9 ohm: two digits, "R", one digit
        n = round(r_ohm * 10)
        if abs(r_ohm * 10 - n) > 1e-9 * r_ohm * 10:
            raise ValueError(f"ERJ8ENF: {r_ohm} ohm is not representable with three significant digits")
        return f"ERJ8ENF{n // 10:02d}R{n % 10}V"
    for zeros in range(10):
        m = r_ohm / 10.0 ** zeros
        n = round(m)
        if 100 <= n <= 999 and abs(m - n) <= 1e-9 * max(1.0, m):
            return f"ERJ8ENF{n:03d}{zeros}V"
    raise ValueError(f"ERJ8ENF: {r_ohm} ohm is not representable with the three-significant-digit code (open item)")


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). Tolerance is relative, absolute when expected == 0 (1e-9).
    (
        "rated_voltage",
        {"r": 2.2e6, "p70": 0.25, "v_limit": 200.0},
        200.0,
        1e-9,
        "DS p.10, Ratings <+/-1 %>, ERJ8EN limiting element voltage 200 V (sqrt(0.25 x 2.2 Mohm) = 742 V, so the limit applies)",
    ),
    (
        "rated_power",
        {"ta_c": 70.0, "p70": 0.25, "knee_c": 70.0, "zero_c": 155.0},
        0.25,
        1e-9,
        "DS p.10, Ratings <+/-1 %>, Power rating (70 degC) 0.25 W",
    ),
    (
        "rated_power",
        {"ta_c": 25.0, "p70": 0.25, "knee_c": 70.0, "zero_c": 155.0},
        0.25,
        1e-9,
        "DS p.10, Power derating curve: full rated power below 70 degC",
    ),
    (
        "rated_power",
        {"ta_c": 155.0, "p70": 0.25, "knee_c": 70.0, "zero_c": 155.0},
        0.0,
        1e-9,
        "DS p.10, Power derating curve: 0 % at 155 degC (curve reading)",
    ),
]

INPUTS = {
    # function: {argument: component.toml param key}. Design choices (resistance, ambient, temperature reference) are
    # not mapped. rated_voltage takes the printed limit (max) of each row.
    "rated_voltage": {"p70": "p70.max", "v_limit": "v_limit.max"},
    "rated_power": {"p70": "p70.max", "knee_c": "derate_knee.typ", "zero_c": "derate_zero.typ"},
    # tcr uses the 10 ohm to 2.2 Mohm key: this part's only TCR range. Use the same key for any value in that range.
    "resistance_worst": {"tol": "tol", "tcr": "tcr_10r_2m2"},
    # mpn takes only the design choice resistance; no DS parameter feeds it.
    "mpn": {},
}
