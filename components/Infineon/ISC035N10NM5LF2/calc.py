"""ISC035N10NM5LF2 datasheet equations. DS: Infineon Final datasheet ISC035N10NM5LF2, Revision 2.3, 2025-11-07, PG-TDSON-8-59.

Arguments and return values are plain floats in SI units (A, ohm, W, s, degC); temperatures in degC. Only math is imported.
The DS prints no conduction-loss, junction-temperature or gate-drive equation: those functions start with "Not a DS
equation". Hot RDS(on): Diagram 10 (DS p.9) is a normalized curve (RDS(on) / RDS(on) at 25 degC), unlabelled (one line,
read as typical). rds_on_at_tj_typ is therefore a curve-based typical estimate, NOT a bound. The DS prints no
guaranteed RDS(on) above 25 degC (open item).
"""

import math


def conduction_loss(i, rds_on):
    """Not a DS equation: conduction loss P = I^2 x RDS(on). Use the 25 degC max row (rds_on_10v.max) for a bound at
    25 degC; above 25 degC use rds_on_at_tj_typ, a typical estimate.
    i: drain current, A (either sign; squared). rds_on: ohm. Returns: W."""
    return i * i * rds_on


def rds_on_at_tj_typ(rds_on_25, factor):
    """Curve-based estimate, not a bound: RDS(on) at Tj = rds_on_25 x factor. factor = RDS(on)/RDS(on)@25 degC read off
    DS p.9 Diagram 10 (normalized, ID = 50 A, VGS = 10 V). The curve is unlabelled, read as typical.
    rds_on_25: ohm (the 25 degC max row). factor: fraction, 1.0 at 25 degC. Returns: ohm."""
    return rds_on_25 * factor


def tj_from_case(tc, p, rth_jc):
    """Not a DS equation: TJ = TC + P x RthJC, the case-referenced junction temperature (DS p.4 Table 3 RthJC).
    The bottom RthJC (drain tab to case) is used. tc: case temperature, degC. p: dissipation, W, >= 0.
    rth_jc: degC/W, use the max row for a bound. Returns: degC."""
    return tc + p * rth_jc


def tj_from_ambient(ta, p, rth_ja):
    """Not a DS equation: TJ = TA + P x RthJA (DS p.4 Table 3, 6 cm2 cooling area, footnote 5).
    Valid only for that PCB. ta: ambient temperature, degC. p: dissipation, W, >= 0. rth_ja: degC/W, use the max row.
    Returns: degC."""
    return ta + p * rth_ja


def gate_drive_time(qg, ig):
    """Not a DS equation: time to charge the gate, t = |Qg| / Ig, Qg from DS p.6 Table 6 (Qg, VGS = 0 to 10 V) and Ig
    the gate drive current (design choice). abs() is applied so a printed negative charge gives a time.
    qg: C. ig: A, > 0. Returns: s."""
    return abs(qg) / ig


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). Tolerance is relative (1e-9 = arithmetic only).
    (
        "conduction_loss",
        {"i": 50.0, "rds_on": 3.5e-3},
        8.75,
        1e-9,
        "DS p.5 Table 4 and p.1 Table 1, RDS(on) max 3.5 mohm at ID = 50 A (arithmetic only)",
    ),
    (
        "rds_on_at_tj_typ",
        {"rds_on_25": 3.5e-3, "factor": 1.0},
        3.5e-3,
        1e-9,
        "DS p.9 Diagram 10 is normalized to 25 degC: factor 1.0 at 25 degC by definition (arithmetic only)",
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
        {"tc": 25.0, "p": 10.0, "rth_jc": 0.7},
        32.0,
        1e-9,
        "DS p.4 Table 3 RthJC max 0.7 degC/W (arithmetic only)",
    ),
    (
        "gate_drive_time",
        {"qg": 88e-9, "ig": 1.0},
        88e-9,
        1e-9,
        "DS p.6 Table 6 Qg max 88 nC with Ig = 1 A (arithmetic only)",
    ),
]

INPUTS = {
    # function: {argument: component.toml param key, with .max / .typ / .min to pass one number}
    "conduction_loss": {"rds_on": "rds_on_10v.max"},
    "rds_on_at_tj_typ": {"rds_on_25": "rds_on_10v.max", "factor": "norm_rds_150c.typ"},
    "tj_from_case": {"rth_jc": "rth_jc_bottom.max"},
    "tj_from_ambient": {"rth_ja": "rth_ja.max"},
    "gate_drive_time": {"qg": "qg.max"},
}
