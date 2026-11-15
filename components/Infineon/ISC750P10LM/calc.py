"""ISC750P10LM datasheet equations. DS: Infineon Final Data Sheet ISC750P10LM, Rev.2.0, 2022-10-13, PG-TDSON-8 (SuperSO8).

P-channel: the DS stores drain current and drain-source voltage signed (ID, VDS negative). The functions take magnitudes
where the physics needs them: conduction_loss squares the current and gate_drive_time takes abs() of the charge.
Arguments and return values are plain floats in SI units (A, ohm, W, s, degC); temperatures in degC. Only math is imported.
The DS prints no conduction-loss, junction-temperature or gate-drive equation: those functions start with
"Not a DS equation". Hot RDS(on): Diagram 9 (DS p.8) is a normalized curve (RDS(on) / RDS(on) at 25 degC), unlabelled
(one line, read as typical). rds_on_at_tj_typ is therefore a curve-based typical estimate, NOT a bound. The DS prints
no guaranteed RDS(on) above 25 degC (open item).
"""

import math


def conduction_loss(i, rds_on):
    """Not a DS equation: conduction loss P = I^2 x RDS(on). Use the 25 degC max row (rds_on_10v.max at VGS = -10 V) for a
    bound at 25 degC; above 25 degC use rds_on_at_tj_typ, a typical estimate. i: drain current, A (sign ignored, squared).
    rds_on: ohm. Returns: W."""
    return i * i * rds_on


def rds_on_at_tj_typ(rds_on_25, factor):
    """Curve-based estimate, not a bound: RDS(on) at Tj = rds_on_25 x factor. factor = RDS(on)/RDS(on)@25 degC read off
    DS p.8 Diagram 9 (normalized, ID = -25 A, VGS = -10 V). The curve is unlabelled, read as typical.
    rds_on_25: ohm (the 25 degC max row). factor: fraction, 1.0 at 25 degC. Returns: ohm."""
    return rds_on_25 * factor


def tj_from_case(tc, p, rth_jc):
    """Not a DS equation: TJ = TC + P x RthJC, the case-referenced junction temperature (DS p.3 Table 3 RthJC, no
    bottom or top qualifier in the DS). tc: case temperature, degC. p: dissipation, W, >= 0. rth_jc: degC/W, use the max
    row for a bound. Returns: degC."""
    return tc + p * rth_jc


def tj_from_ambient(ta, p, rth_ja):
    """Not a DS equation: TJ = TA + P x RthJA (DS p.3 Table 3, device on PCB, 6 cm2 cooling area, footnote 2).
    Valid only for that PCB. ta: ambient temperature, degC. p: dissipation, W, >= 0. rth_ja: degC/W, use the max row.
    Returns: degC."""
    return ta + p * rth_ja


def gate_drive_time(qg, ig):
    """Not a DS equation: time to charge the gate, t = |Qg| / Ig, Qg from DS p.4 Table 6 (Qg, VGS = 0 to -10 V, the
    printed magnitude 122 nC) and Ig the gate drive current (design choice). abs() is applied to the printed negative
    charge. qg: C. ig: A, > 0. Returns: s."""
    return abs(qg) / ig


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). Tolerance is relative (1e-9 = arithmetic only).
    (
        "conduction_loss",
        {"i": -25.0, "rds_on": 75e-3},
        46.875,
        1e-9,
        "DS p.4 Table 4 and p.1 Table 1, RDS(on) max 75 mohm at VGS = -10 V, ID = -25 A (arithmetic only; sign ignored)",
    ),
    (
        "rds_on_at_tj_typ",
        {"rds_on_25": 75e-3, "factor": 1.0},
        75e-3,
        1e-9,
        "DS p.8 Diagram 9 is normalized to 25 degC: factor 1.0 at 25 degC by definition (arithmetic only)",
    ),
    (
        "tj_from_ambient",
        {"ta": 25.0, "p": 3.0, "rth_ja": 50.0},
        175.0,
        1e-9,
        "DS p.3 Table 2 Ptot = 3 W at TA = 25 degC with RthJA = 50 degC/W gives Tj = 175 degC, the printed Tj max",
    ),
    (
        "tj_from_case",
        {"tc": 25.0, "p": 10.0, "rth_jc": 0.8},
        33.0,
        1e-9,
        "DS p.3 Table 3 RthJC max 0.8 degC/W (arithmetic only)",
    ),
    (
        "gate_drive_time",
        {"qg": -122e-9, "ig": 1.0},
        122e-9,
        1e-9,
        "DS p.4 Table 6 Qg VGS = -10 V, printed magnitude 122 nC, Ig = 1 A (arithmetic only; abs applied)",
    ),
]

INPUTS = {
    # function: {argument: component.toml param key, with .max / .typ / .min to pass one number}
    "conduction_loss": {"rds_on": "rds_on_10v.max"},
    "rds_on_at_tj_typ": {"rds_on_25": "rds_on_10v.max", "factor": "norm_rds_150c.typ"},
    "tj_from_case": {"rth_jc": "rth_jc.max"},
    "tj_from_ambient": {"rth_ja": "rth_ja.max"},
    "gate_drive_time": {"qg": "qg_10v.min"},
}
