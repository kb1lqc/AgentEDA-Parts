"""Murata GCM319 series (3216M 1206, thickness code 9 = 0.85 mm) capacitance calculations, C0G.

DS: docs/datasheets/GCM3195C1H273FA16-01A-EN.pdf (C0G reference sheet, product specifications as of Apr.10,2026); X7R rows of the shared 1206 sheet docs/datasheets/GCM31CR71E475KA55-01A-EN.pdf (not used by this directory's catalog).
Units: F, 1 (fractions), 1/degC, temperatures in degC. Parameters are arguments so the worst-case engine can sweep them.
INPUTS maps each function's arguments to a param key; the keys capacitance, tolerance, rated_v and tc come from the
catalog part selection (Part.select), see docs/SPEC.md "Capacitor series". The DS prints no equation for capacitance;
capacitance_worst_pct and capacitance_worst_ppm are combinations of printed rows, marked as not a DS equation.
"""


def capacitance_worst_pct(c0, tol, tc):
    """Not a DS equation: C = C0 * (1 + tol) * (1 + tc).  For percent-change dielectrics (X7R): tc is the capacitance
    change over the whole range as a FRACTION (DS p.2 of the X7R sheet, Rated Value, Temp. coeff. or Cap. Change,
    -15 to 15 % over -55 to 125 degC, ref 25 degC), so with the row's min/max the corners give the full-range worst case.
    For C0G use capacitance_worst_ppm: passing its 1/degC coefficient here would treat 3e-5 as a fraction and badly
    understate the spread, so |tc| below 1e-3 (other than 0) raises ValueError.
    EXCLUDES DC-bias and aging capacitance loss, which the reference sheet does not quantify (DS p.14 section 5 example
    figure; aging text not stored). For X7R these can dominate. A worst-case stack of printed rows, not a guaranteed
    capacitance.
    c0: nominal capacitance, F (catalog, 'capacitance.typ'). tol: capacitance tolerance, fraction (catalog letter).
    tc: capacitance change over temperature, fraction (the dielectric's row, 'tc'). Returns: C, F."""
    if tc != 0 and abs(tc) < 1e-3:
        raise ValueError(f"tc = {tc:g} looks like a ppm/degC coefficient: use capacitance_worst_ppm")
    return c0 * (1 + tol) * (1 + tc)


def capacitance_worst_ppm(c0, tol, tc, dt):
    """Not a DS equation: C = C0 * (1 + tol) * (1 + tc * dt).  For ppm/degC dielectrics (C0G): tc is the coefficient in
    1/degC (0 +/-30 ppm/degC, the 'tc' row) and dt = T - 25 degC in degC, REQUIRED (no default). The coefficient is
    printed only for 25 to 125 degC (tc_c0g, scope partial), so dt is valid from 0 to 100 and ValueError is raised
    outside it. Below 25 degC the coefficient is not printed: use the Table A capacitance-drift rows (capdrift_m55_c0g,
    capdrift_m30_c0g, capdrift_m10_c0g) for -55 to -10 degC; the -10 to 25 degC segment has no printed number.
    For a percent-change dielectric (X7R) use capacitance_worst_pct: a fraction passed here (|tc| above 1e-3) raises
    ValueError. EXCLUDES DC-bias and aging loss. A worst-case stack of printed rows, not a guaranteed capacitance.
    c0: nominal capacitance, F. tol: capacitance tolerance, fraction. tc: coefficient, 1/degC.
    dt: temperature minus 25 degC, degC, 0 to 100 (wca: dt=Param(min=0, max=100)). Returns: C, F."""
    if not 0 <= dt <= 100:
        raise ValueError(f"dt = {dt:g} degC is outside 0 to 100: the C0G coefficient is printed for 25 to 125 degC only")
    if abs(tc) > 1e-3:
        raise ValueError(f"tc = {tc:g} looks like a fraction: use capacitance_worst_pct")
    return c0 * (1 + tol) * (1 + tc * dt)


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). 27000 pF x 0.99 x (1 - 30e-6 x 100) = 26649.81 pF = 2.664981e-8 F.
    ("capacitance_worst_ppm", {"c0": 2.7e-8, "tol": -0.01, "tc": -30e-6, "dt": 100}, 2.664981e-8, 1e-9, "DS p.2, Rated Value"),
    # The X7R example below is the 4.7 uF reference part of the 1206 X7R sheet (DS p.2); this directory has no X7R catalog rows.
    ("capacitance_worst_pct", {"c0": 4.7e-6, "tol": -0.10, "tc": -0.15}, 3.5955e-6, 1e-9, "DS p.2, Rated Value (X7R sheet)"),
]

INPUTS = {
    # function: {argument: param key}. The pct function is for the X7R tc row, the ppm one for the C0G tc row; dt is a
    # design choice (the temperature), not listed.
    "capacitance_worst_pct": {"c0": "capacitance.typ", "tol": "tolerance", "tc": "tc"},
    "capacitance_worst_ppm": {"c0": "capacitance.typ", "tol": "tolerance", "tc": "tc"},
}
