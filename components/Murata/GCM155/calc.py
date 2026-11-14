"""Murata GCM155 family (1005M, X7R R7) capacitance calculations.

DS: docs/datasheets/GCM155R71H104KE02-01A-EN.pdf (reference sheet 01A, product specifications as of Apr.6,2026).
Units: F, 1 (fractions), temperatures in degC. Parameters are arguments so the worst-case engine can sweep them.
INPUTS maps each function's arguments to the component.toml param key that supplies them. The DS prints no equation
for capacitance; capacitance_worst is a combination of printed rows, marked as not a DS equation.
"""

def capacitance_worst(c0, tol, tc):
    """Not a DS equation: C = C0 * (1 + tol) * (1 + tc). Combines capacitance tolerance (DS p.2, Rated Value,
    Capacitance Tolerance +/-10 %) and the temperature characteristic capacitance change (DS p.2, Rated Value,
    Temp. coeff. or Cap. Change -15 to 15 % over -55 to 125 degC, ref 25 degC). EXCLUDES DC-bias and aging capacitance
    loss, which the reference sheet does not quantify (DS p.14 section 5 figure; DS p.15 section 6 figure). For X7R
    these can dominate. This is a worst-case stack of two printed rows, not a guaranteed capacitance.
    c0: nominal capacitance, F (DS p.2, 0.1 uF). tol: capacitance tolerance, fraction (DS p.2, +/-10 %).
    tc: temperature characteristic capacitance change, fraction (DS p.2, -15 to 15 %). Returns: C, F."""
    return c0 * (1 + tol) * (1 + tc)


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). Worst low corner from printed numbers only: 0.1 uF, tolerance K
    # = -10 %, temperature characteristic R7 = -15 % (DS p.2 Rated Value): 0.1 uF x 0.90 x 0.85 = 0.0765 uF.
    ("capacitance_worst", {"c0": 0.1e-6, "tol": -0.10, "tc": -0.15}, 0.0765e-6, 1e-9, "DS p.2, Rated Value"),
]

INPUTS = {
    # function: {argument: param key}
    "capacitance_worst": {"c0": "capacitance.typ", "tol": "tolerance", "tc": "tc_r7"},
}
