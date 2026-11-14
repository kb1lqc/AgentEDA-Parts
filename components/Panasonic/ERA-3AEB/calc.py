"""ERA-3AEB (0603 (1608 metric), +/-0.1 %, +/-25 ppm/degC) datasheet equations. Source: Panasonic Fixed Resistors catalog 2026.5
(docs/datasheets/panasonic-fixed-resistors-catalog-2026-05.pdf), Metal Film (Thin Film) Chip Resistors, High Reliability Type,
ERA A type: DS p.19 (part numbers), p.20 (ratings and derating), p.21 (performance). Arguments and return values are floats
in SI units (ohm, W, V, degC) and fractions for tolerance and TCR (1/degC). Only math is imported.
"""

import math

# E-series mantissas (IEC 60063) as integers: E24 two-digit codes (10 .. 91) and E96 three-digit codes (100 .. 976).
# Copied from lib/series.py (E24, E96) at generation time.
E24_2DIGIT = (10, 11, 12, 13, 15, 16, 18, 20, 22, 24, 27, 30, 33, 36, 39, 43, 47, 51, 56, 62, 68, 75, 82, 91)
E96_3DIGIT = (100, 102, 105, 107, 110, 113, 115, 118, 121, 124, 127, 130, 133, 137, 140, 143, 147, 150, 154, 158, 162, 165, 169, 174, 178, 182, 187, 191, 196, 200, 205, 210, 215, 221, 226, 232, 237, 243, 249, 255, 261, 267, 274, 280, 287, 294, 301, 309, 316, 324, 332, 340, 348, 357, 365, 374, 383, 392, 402, 412, 422, 432, 442, 453, 464, 475, 487, 499, 511, 523, 536, 549, 562, 576, 590, 604, 619, 634, 649, 665, 681, 698, 715, 732, 750, 768, 787, 806, 825, 845, 866, 887, 909, 931, 953, 976)


def rated_voltage(r, p85, v_limit):
    """RCWV = min(sqrt(P x R), limiting element voltage). DS p.20, Ratings, footnote *2 (printed formula).
    r: ohm. p85: W (power rating at 85 degC). v_limit: V. Returns: V."""
    return min(math.sqrt(p85 * r), v_limit)


def rated_power(ta_c, p85, knee_c, zero_c):
    """Rated power in W at AMBIENT temperature ta_c (degC).
    p85 is the printed 85 degC rating (DS p.20, Ratings). knee_c = 85 degC is printed in the derating text (DS p.20).
    zero_c = 155 degC is read off the DS p.20 derating figure (curve = true).
    Result: p85 up to knee_c, then a linear fall to 0 W at zero_c. Above knee_c the result is a CURVE-BASED ESTIMATE,
    not a datasheet bound. ta_c at or above zero_c gives 0 W.
    ta_c, knee_c, zero_c: degC. p85: W. Returns: W."""
    if ta_c <= knee_c:
        return p85
    if ta_c >= zero_c:
        return 0.0
    return p85 * (zero_c - ta_c) / (zero_c - knee_c)


def resistance_worst(r0, tol, tcr, t_c, t_ref_c):
    """Not a DS equation: combines tolerance (DS p.20) and T.C.R. (DS p.20) per the SPEC temperature recipe.
    r0 is the plain nominal value (a float, e.g. from part.values()), NOT part.series_value(), which already carries
    the tolerance: passing both would count the tolerance twice. The DS does not state a reference temperature for the
    T.C.R.; the caller supplies t_ref_c (25 degC: the T.C.R. test starts at +25 degC, DS p.21).
    R = R0 x (1 + tol) x (1 + tcr x (T - Tref)). Call with tol = -0.001 and +0.001 for the two worst corners.
    The TCR term is valid only over the span the DS covers, which the DS does not state (open item).
    r0: ohm. tol: fraction (0.001 = 0.1 %). tcr: 1/degC (25e-6 = 25 ppm/degC). t_c, t_ref_c: degC. Returns: ohm."""
    return r0 * (1.0 + tol) * (1.0 + tcr * (t_c - t_ref_c))


def mpn(r_ohm):
    """Not a DS equation: orderable part number from the catalog part-number rule (DS p.19, Explanation of part numbers,
    E24 and E96 blocks): ERA3AEB + size/T.C.R./tolerance letters + resistance code + packaging code V.
    E24 value (two significant figures): code = two figures + number of zeros, e.g. 47 ohm -> ERA3AEB470V, 1 kohm -> ERA3AEB102V.
    A value that is also an E24 value follows the E24 number (DS note *5). Other E96 values use four figures
    (three significant + zeros), e.g. 1.05 kohm -> ERA3AEB1051V.
    An E96 value below 100 ohm that is not an E24 value has no printed code (the catalog has no decimal-point code):
    raises ValueError (open item). Values outside 47 to 330 k ohm raise ValueError.
    Returns: str."""
    lo, hi = 47.0, 330000.0
    if not lo * (1 - 1e-9) <= r_ohm <= hi * (1 + 1e-9):
        raise ValueError(f"ERA3AEB: {r_ohm} ohm outside the printed range 47 to 330 k ohm")
    decade = math.floor(math.log10(r_ohm) + 1e-9)
    m = r_ohm / 10.0 ** decade  # mantissa, 1 <= m < 10
    n2 = round(m * 10)
    if abs(m * 10 - n2) <= 1e-6 and n2 in E24_2DIGIT:
        return f"ERA3AEB{n2:02d}{decade - 1}V"
    n3 = round(m * 100)
    if abs(m * 100 - n3) <= 1e-6 and n3 in E96_3DIGIT:
        if decade < 2:
            raise ValueError(f"ERA3AEB: {r_ohm} ohm is an E96 value below 100 ohm with no printed part-number code (open item)")
        return f"ERA3AEB{n3:03d}{decade - 2}V"
    raise ValueError(f"ERA3AEB: {r_ohm} ohm is not an E24 or E96 value")


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). Tolerance is relative, absolute when expected == 0 (1e-9).
    (
        "rated_voltage",
        {"r": 1.0e3, "p85": 0.1, "v_limit": 75.0},
        math.sqrt(0.1 * 1.0e3),
        1e-9,
        "DS p.20, Ratings, footnote *2: RCWV = sqrt(Power rating x R) (arithmetic on the printed formula; 1 kohm is below the limit)",
    ),
    (
        "rated_voltage",
        {"r": 330000.0, "p85": 0.1, "v_limit": 75.0},
        75.0,
        1e-9,
        "DS p.20, Ratings, Limiting element voltage 75 V: the limit applies at the top of the range",
    ),
    (
        "rated_power",
        {"ta_c": 85.0, "p85": 0.1, "knee_c": 85.0, "zero_c": 155.0},
        0.1,
        1e-9,
        "DS p.20, Ratings, Power rating (85 degC) 0.1 W",
    ),
    (
        "rated_power",
        {"ta_c": 25.0, "p85": 0.1, "knee_c": 85.0, "zero_c": 155.0},
        0.1,
        1e-9,
        "DS p.20, Power derating curve: full rated power below 85 degC",
    ),
    (
        "rated_power",
        {"ta_c": 155.0, "p85": 0.1, "knee_c": 85.0, "zero_c": 155.0},
        0.0,
        1e-9,
        "DS p.20, Power derating curve: 0 % at 155 degC (curve reading)",
    ),
    (
        "resistance_worst",
        {"r0": 1000.0, "tol": 0.001, "tcr": 25e-6, "t_c": 125.0, "t_ref_c": 25.0},
        1003.5025,
        1e-9,
        "Arithmetic check of the formula: 1 kohm x 1.001 x (1 + 25e-6 x 100); tol +/-0.1 % (DS p.20), TCR +/-25 ppm/degC (DS p.20)",
    ),
]

INPUTS = {
    # function: {argument: component.toml param key}. Design choices (resistance, ambient, temperature reference) are
    # not mapped. rated_voltage takes the printed limit (max) of each row.
    "rated_voltage": {"p85": "p85.max", "v_limit": "v_limit.max"},
    "rated_power": {"p85": "p85.max", "knee_c": "derate_knee.typ", "zero_c": "derate_zero.typ"},
    "resistance_worst": {"tol": "tol", "tcr": "tcr_25"},
    # mpn takes only the design choice resistance; no DS parameter feeds it.
    "mpn": {},
}
