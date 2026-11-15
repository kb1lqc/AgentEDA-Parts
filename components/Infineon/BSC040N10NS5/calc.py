"""BSC040N10NS5 datasheet equations. DS: Infineon Final Data Sheet BSC040N10NS5, Rev.2.4, 2020-05-15, PG-TDSON-8.

Arguments and return values are plain floats in SI units (A, ohm, W, s, degC); temperatures in degC. Only math is imported.
The DS prints no conduction-loss, junction-temperature or gate-drive equation: those functions start with "Not a DS
equation". Hot RDS(on): Diagram 9 (DS p.8) prints absolute RDS(on) lines (typ and max) at Tj = 100 and 150 degC, not a
normalized factor, so there is no rds_on_at_tj_typ for this part. For hot conduction loss use the printed max line as a
bound-like curve value: conduction_loss(i, rds_on=<rds_on_150c_max, read off the figure>); the table row
rds_on_10v is 25 degC only.
"""

import math


def conduction_loss(i, rds_on):
    """Not a DS equation: conduction loss P = I^2 x RDS(on). Use rds_on at the temperature of interest: 25 degC from the
    table (rds_on_10v.max) or a hot curve value (the BSC curve rows rds_on_*c_max below).
    i: drain current, A (either sign; squared). rds_on: ohm. Returns: W."""
    return i * i * rds_on


def tj_from_case(tc, p, rth_jc):
    """Not a DS equation: TJ = TC + P x RthJC, the case-referenced junction temperature (DS RthJC row, Table 3).
    tc: case temperature, degC. p: dissipation, W, >= 0. rth_jc: degC/W, use the max row for a bound. Returns: degC."""
    return tc + p * rth_jc


def tj_from_ambient(ta, p, rth_ja):
    """Not a DS equation: TJ = TA + P x RthJA (DS p.3-4 Table 3, device on the DS PCB, 6 cm2 drain copper, footnote).
    Valid only for that PCB. ta: ambient temperature, degC. p: dissipation, W, >= 0. rth_ja: degC/W, use the max row.
    Returns: degC."""
    return ta + p * rth_ja


def gate_drive_time(qg, ig):
    """Not a DS equation: time to charge the gate, t = |Qg| / Ig, with Qg from the DS gate-charge table (Table 6) and Ig
    the gate drive current (design choice). abs() is applied because a P-channel Qg is printed negative.
    qg: C. ig: A, > 0. Returns: s."""
    return abs(qg) / ig


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). Tolerance is relative (1e-9 = arithmetic only).
    ("conduction_loss", {"i": 50.0, "rds_on": 4.0e-3}, 10.0, 1e-9,
     "DS p.4 Table 4, RDS(on) max 4.0 mohm at ID = 50 A (arithmetic only)"),
    ("tj_from_ambient", {"ta": 25.0, "p": 2.5, "rth_ja": 50.0}, 150.0, 1e-9,
     "DS p.3 Table 2 Ptot = 2.5 W at TA = 25 degC with RthJA = 50 K/W gives Tj = 150 degC, the printed Tj max"),
    ("tj_from_case", {"tc": 25.0, "p": 10.0, "rth_jc": 0.9}, 34.0, 1e-9,
     "DS p.3 Table 3 RthJC max 0.9 K/W (arithmetic only)"),
    ("gate_drive_time", {"qg": 72e-9, "ig": 1.0}, 72e-9, 1e-9,
     "DS p.4 Table 6 Qg max 72 nC with Ig = 1 A (arithmetic only)"),
]

INPUTS = {
    # function: {argument: component.toml param key, with .max / .typ / .min to pass one number}
    "conduction_loss": {"rds_on": "rds_on_10v.max"},
    "tj_from_case": {"rth_jc": "rth_jc_bottom.max"},
    "tj_from_ambient": {"rth_ja": "rth_ja.max"},
    "gate_drive_time": {"qg": "qg.max"},
}
