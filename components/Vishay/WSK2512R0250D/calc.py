"""WSK2512R0250D datasheet equations. DS: Vishay Document 30108, Revision 11-Dec-2023 (https://www.vishay.com/doc?30108).

Arguments and return values are plain floats in SI units (ohm, A, W, V) and fractions (tol = 0.005 for ±0.5 %,
tcr in 1/degC = 35e-6 for 35 ppm/degC). Temperatures are in degC. Parameters come in as arguments; this file stores
no numbers except the EXAMPLES, which cite the DS. Only math is imported.
The DS has no Absolute Maximum Ratings table and gives no thermal resistance or element temperature, so nothing here
models self-heating: ambient temperature is the only temperature input.
"""

import math


def resistance_worst(r0, tol, tcr, t_c, t_ref_c):
    """Not a DS equation: combines tolerance (DS p.1) and TCR (DS p.2) per the SPEC temperature recipe; DS states no
    reference temperature, caller supplies t_ref_c (25 degC is the usual assumption).
    R = R0 * (1 + tol) * (1 + tcr * (T - Tref)). Call with tol = -0.005 and +0.005 for the two worst corners.
    The TCR term is only valid over the span the DS covers, which the DS does not state (open item).
    r0: ohm. tol: fraction (0.005 = 0.5 %). tcr: 1/degC (35e-6 = 35 ppm/degC). t_c, t_ref_c: degC. Returns: ohm."""
    return r0 * (1.0 + tol) * (1.0 + tcr * (t_c - t_ref_c))


def sense_voltage(i, r):
    """Not a DS equation: Ohm's law, V = I x R, for the E1-to-E2 sense voltage (DS p.3 Notes: E1, E2 sense the
    voltage of the current path). i: A (signed). r: ohm. Returns: V."""
    return i * r


def dissipation(i, r):
    """Not a DS equation: P = I^2 x R, the power in the resistor (DS p.1 and p.3 rate power only). Physical relation.
    i: A (either sign). r: ohm. Returns: W."""
    return i * i * r


def rated_power(ta_c, p70, knee_c, zero_c):
    """Rated power in W at AMBIENT temperature ta_c (degC).
    Only p70 is a printed rating: DS p.1, Standard Electrical Specifications, P70 degC = 1.0 W (a maximum).
    The 70 degC knee (knee_c) and the 170 degC zero (zero_c) are read off the DS p.3 DERATING graph (curve = true).
    Result: p70 up to knee_c, then a linear fall to 0 W at zero_c. Above knee_c the result is a CURVE-BASED ESTIMATE,
    not a datasheet bound. ta_c at or above zero_c gives 0 W.
    ta_c, knee_c, zero_c: degC. p70: W. Returns: W."""
    if ta_c <= knee_c:
        return p70
    if ta_c >= zero_c:
        return 0.0
    return p70 * (zero_c - ta_c) / (zero_c - knee_c)


def max_current(p_w, r):
    """Not a DS equation: largest continuous current magnitude I = sqrt(P / R), derived from P = I^2 R. The DS gives no
    current figure. p_w: W, from rated_power (above 70 degC this is a CURVE-BASED ESTIMATE, see rated_power). r: ohm,
    pass the largest resistance (resistance_worst) for a conservative bound. Returns: A (magnitude)."""
    return math.sqrt(p_w / r)


def max_working_voltage(p_w, r):
    """Maximum working voltage across the resistor in V: V = (P x R)^1/2.
    DS p.2, Technical Specifications, Maximum working voltage, (P x R)^1/2 (printed formula).
    p_w: W, from rated_power (above 70 degC a CURVE-BASED ESTIMATE). r: ohm. Returns: V."""
    return math.sqrt(p_w * r)


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). The tolerance is relative, except when expected == 0, where it is
    # absolute (1e-9).
    (
        "rated_power",
        {"ta_c": 70.0, "p70": 1.0, "knee_c": 70.0, "zero_c": 170.0},
        1.0,
        1e-9,
        "DS p.1, Standard Electrical Specifications, P70 degC = 1.0 W (100 % at 70 degC, DS p.3 DERATING)",
    ),
    (
        "rated_power",
        {"ta_c": 25.0, "p70": 1.0, "knee_c": 70.0, "zero_c": 170.0},
        1.0,
        1e-9,
        "DS p.3, DERATING graph: 100 % flat below 70 degC (curve reading)",
    ),
    (
        "rated_power",
        {"ta_c": 170.0, "p70": 1.0, "knee_c": 70.0, "zero_c": 170.0},
        0.0,
        1e-9,
        "DS p.3, DERATING graph: 0 % at 170 degC (curve reading)",
    ),
]

INPUTS = {
    # function: {argument: component.toml param key}. Design choices (current, ambient temperature, t_ref_c, p_w) are
    # not mapped.
    "resistance_worst": {"r0": "r_nom.typ", "tol": "tol", "tcr": "tcr"},
    "sense_voltage": {"r": "r_nom.typ"},
    "dissipation": {"r": "r_nom.typ"},
    "rated_power": {"p70": "p70.max", "knee_c": "derate_knee.typ", "zero_c": "derate_zero.typ"},
    "max_current": {"r": "r_nom.typ"},
    "max_working_voltage": {"r": "r_nom.typ"},
}
