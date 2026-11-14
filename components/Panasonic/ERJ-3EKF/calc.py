"""ERJ-3EKF (0603, +/-1 %) datasheet equations. DS: Panasonic AOA0000C304, "Precision Thick Film Chip Resistors, ERJ type"
(footer date 29-May-25). Arguments and return values are floats in SI units (ohm, W, V, degC) and fractions for tolerance
and TCR (1/degC). Only math is imported.

Rated power and voltage are printed for 70 degC ambient and the limiting element voltage (DS PDF p.3, Ratings <+/-1 %>).
The DS has no Absolute Maximum Ratings table.
"""

import math


def rated_voltage(r, p70, v_limit):
    """RCWV = min(sqrt(P x R), limiting element voltage). DS PDF p.3, Ratings <+/-1 %>, footnote *2 (printed formula).
    r: ohm. p70: W (rated power at 70 degC). v_limit: V. Returns: V."""
    return min(math.sqrt(p70 * r), v_limit)


def rated_power(ta_c, p70, knee_c, zero_c):
    """Rated power in W at AMBIENT temperature ta_c (degC).
    p70 is the printed 70 degC rating (DS PDF p.3, Ratings <+/-1 %>). knee_c = 70 degC is printed in the derating text
    (DS PDF p.3). zero_c = 155 degC is read off the DS PDF p.3 derating figure (155 degC line, curve = true).
    Result: p70 up to knee_c, then a linear fall to 0 W at zero_c. Above knee_c the result is a CURVE-BASED ESTIMATE,
    not a datasheet bound. ta_c at or above zero_c gives 0 W.
    ta_c, knee_c, zero_c: degC. p70: W. Returns: W."""
    if ta_c <= knee_c:
        return p70
    if ta_c >= zero_c:
        return 0.0
    return p70 * (zero_c - ta_c) / (zero_c - knee_c)


def resistance_worst(r0, tol, tcr, t_c, t_ref_c):
    """Not a DS equation: combines tolerance (DS PDF p.3) and TCR (DS PDF p.3) per the SPEC temperature recipe.
    r0 is the plain nominal value (a float, e.g. from part.values()), NOT part.series_value(), which already carries
    the tolerance: passing both would count the tolerance twice. The DS
    states no reference temperature for either; the caller supplies t_ref_c (25 degC is the usual assumption; the DS
    T.C.R. test runs from +25 degC).
    R = R0 x (1 + tol) x (1 + tcr x (T - Tref)). Call with tol = -0.01 and +0.01 for the two worst corners.
    The TCR term is valid only over the span the DS covers, which the DS does not state (open item).
    r0: ohm. tol: fraction (0.01 = 1 %). tcr: 1/degC (100e-6 = 100 ppm/degC). t_c, t_ref_c: degC. Returns: ohm."""
    return r0 * (1.0 + tol) * (1.0 + tcr * (t_c - t_ref_c))


def mpn(r_ohm):
    """Not a DS equation: part-number string from the DS decode rule (DS PDF p.2, Explanation of part numbers, +/-1 %
    block): ERJ3EK + F (tolerance) + 4-digit code + V (packaging). Code = three significant digits then the number of
    zeros: 1002 = 10 kohm. The DS prints the hyphen-less form (ERJ3EK), so the prefix is written without the hyphen.
    Below 100 ohm the code is three significant digits with the decimal point written as "R" (DS PDF p.2: "Decimal
    point is expressed by 'R'"), e.g. 49.9 ohm -> 49R9, 10 ohm -> 10R0. Series range 10 ohm to 1 Mohm (DS PDF p.3).
    Returns: str."""
    lo, hi = 10.0, 1.0e6
    if not lo <= r_ohm <= hi:
        raise ValueError(f"ERJ3EKF: {r_ohm} ohm outside the printed range 10 ohm to 1 Mohm")
    if r_ohm < 100.0:  # 10.0 to 99.9 ohm: two digits, "R", one digit
        n = round(r_ohm * 10)
        if abs(r_ohm * 10 - n) > 1e-9 * r_ohm * 10:
            raise ValueError(f"ERJ3EKF: {r_ohm} ohm is not representable with three significant digits")
        return f"ERJ3EKF{n // 10:02d}R{n % 10}V"
    for zeros in range(10):
        m = r_ohm / 10.0 ** zeros
        n = round(m)
        if 100 <= n <= 999 and abs(m - n) <= 1e-9 * max(1.0, m):
            return f"ERJ3EKF{n:03d}{zeros}V"
    raise ValueError(f"ERJ3EKF: {r_ohm} ohm is not representable with the three-significant-digit code (open item)")


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). Tolerance is relative, absolute when expected == 0 (1e-9).
    (
        "rated_voltage",
        {"r": 1.0e6, "p70": 0.1, "v_limit": 75.0},
        75.0,
        1e-9,
        "DS PDF p.3, Ratings <+/-1 %>, ERJ3EK limiting element voltage 75 V (sqrt(0.1 x 1 Mohm) = 316 V, so the limit applies)",
    ),
    (
        "rated_power",
        {"ta_c": 70.0, "p70": 0.1, "knee_c": 70.0, "zero_c": 155.0},
        0.1,
        1e-9,
        "DS PDF p.3, Ratings <+/-1 %>, Power rating (70 degC) 0.1 W",
    ),
    (
        "rated_power",
        {"ta_c": 25.0, "p70": 0.1, "knee_c": 70.0, "zero_c": 155.0},
        0.1,
        1e-9,
        "DS PDF p.3, Power derating curve: full rated power below 70 degC",
    ),
    (
        "rated_power",
        {"ta_c": 155.0, "p70": 0.1, "knee_c": 70.0, "zero_c": 155.0},
        0.0,
        1e-9,
        "DS PDF p.3, Power derating curve: 0 % at 155 degC (curve reading)",
    ),
]

INPUTS = {
    # function: {argument: component.toml param key}. Design choices (resistance, ambient, temperature reference) are
    # not mapped. rated_voltage takes the printed limit (max) of each row.
    "rated_voltage": {"p70": "p70.max", "v_limit": "v_limit.max"},
    "rated_power": {"p70": "p70.max", "knee_c": "derate_knee.typ", "zero_c": "derate_zero.typ"},
    # tcr uses the 10 ohm to 1 Mohm key: this part's only TCR range. Use the same key for any value in that range.
    "resistance_worst": {"tol": "tol", "tcr": "tcr_10r_1m"},
    # mpn takes only the design choice resistance; no DS parameter feeds it.
    "mpn": {},
}
