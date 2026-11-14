"""Murata GCM32Q series (3225M 1210, thickness code Q = 1.5 mm) capacitance calculations, X7R.

DS: no reference sheet for an X7R thickness code Q exists in docs/datasheets (open item). The X7R temperature row comes from
docs/datasheets/GCM32ER71C226ME19-01A-EN.pdf (1210 X7R reference sheet of thickness code E, Apr.13,2026); the catalog
tolerance and rated voltage come from the export (catalog.csv). The U2J sheet GCM32Q7U2J682JX01-00B-EN.pdf is not used here.
Units: F, 1 (fractions), temperatures in degC. Parameters are arguments so the worst-case engine can sweep them.
INPUTS maps each function's arguments to a param key; the keys capacitance, tolerance, rated_v and tc come from the
catalog part selection (Part.select), see docs/SPEC.md "Capacitor series". The DS prints no equation for capacitance;
capacitance_worst_pct is a combination of printed rows, marked as not a DS equation.
"""


def capacitance_worst_pct(c0, tol, tc):
    """Not a DS equation: C = C0 * (1 + tol) * (1 + tc).  For percent-change dielectrics (X7R): tc is the capacitance
    change over the whole range as a FRACTION (the 1210 X7R sheet, DS p.2, Rated Value, Temp. coeff. or Cap. Change,
    -15 to 15 % over -55 to 125 degC, ref 25 degC), so with the row's min/max the corners give the full-range worst case.
    |tc| below 1e-3 (other than 0) raises ValueError, because that is a ppm/degC coefficient, not a fraction.
    EXCLUDES DC-bias and aging capacitance loss, which the reference sheet does not quantify (DS p.14 section 5 figure;
    DS p.15 section 6 text). For X7R these can dominate. A worst-case stack of printed rows, not a guaranteed
    capacitance.
    c0: nominal capacitance, F (catalog, 'capacitance.typ'). tol: capacitance tolerance, fraction (catalog letter).
    tc: capacitance change over temperature, fraction (the dielectric's row, 'tc'). Returns: C, F."""
    if tc != 0 and abs(tc) < 1e-3:
        raise ValueError(f"tc = {tc:g} looks like a ppm/degC coefficient: use a C0G function")
    return c0 * (1 + tol) * (1 + tc)


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). GCM32QR72J682KWB1 (catalog): 6800 pF, tolerance K = +/-10 % (export),
    # X7R -15 to 15 % over the range (1210 X7R sheet, DS p.2): 6800 pF x 0.90 x 0.85 = 5202 pF. Used to check the function
    # only; the 1.5 mm X7R parts have no per-part reference sheet.
    ("capacitance_worst_pct", {"c0": 6.8e-9, "tol": -0.10, "tc": -0.15}, 5.202e-9, 1e-12, "DS p.2, Rated Value (X7R 1210 sheet)"),
]

INPUTS = {
    # function: {argument: param key}. The X7R function takes the dielectric's tc row; the others are design choices.
    "capacitance_worst_pct": {"c0": "capacitance.typ", "tol": "tolerance", "tc": "tc"},
}
