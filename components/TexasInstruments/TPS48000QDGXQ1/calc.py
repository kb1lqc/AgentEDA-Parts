"""TPS48000-Q1 (TPS4800-Q1 datasheet, SLUSEZ1B Rev. B) application equations, DGX package.

DS: docs/datasheets/tps4800-q1.pdf. Printed page numbers are cited per function (PDF page = printed page).
Units: V, A, ohm, F, s, Hz, W; temperatures in degC. Arguments are plain SI floats so the worst-case engine can sweep
them. Stored negative currents are not used by this part (all currents in component.toml are magnitudes).
INPUTS maps each function's datasheet argument to the component.toml param key that supplies it. Design choices
(resistors, capacitors, load, targets) are not mapped; a function with no mapped argument has no INPUTS entry.
Equation text in this file is transcribed from the DS equation images (eq. 1-8 on DS p.14-19, design eq. 9-13 on
DS p.23-24). The DS prints several constants inside its equations (19 mV, 2 uA, 1.1, 0.63, 10, 22.7e6); they are
kept as printed and named in each docstring.
"""

import math


def t_drv_en(cbst, vbst_uvlor, i_bst):
    """TDRV_EN = CBST x V(BST_UVLOR) / 345 uA. Initial gate driver enable delay, eq. (1).
    DS p.14, 7.3.2 Charge pump, Equation 1 (the DS quotes 345 uA as the charge-pump current; the table value is
    I(BST) typ 345 uA, DS p.6). The text under eq. 1 gives V(BST_UVLOR) = 10.81 V (max).
    cbst: F (design choice, BST to SRC). vbst_uvlor: V, rising UVLO threshold (DS p.6). i_bst: A, charge-pump
    current (DS p.6, I(BST); min 100 uA gives the longest delay). Returns: s.
    INPUTS: vbst_uvlor -> v_bst_uvlor (max 10.81 V is the worst case), i_bst -> i_bst (min 100 uA is the worst case)."""
    return cbst * vbst_uvlor / i_bst


def i_inrush(c_load, vbatt, t_charge):
    """IINRUSH = CLOAD x VBATT / Tcharge. Inrush current during turn-on, eq. (2). DS p.15, 7.3.1 Inrush Current
    Limiting, Equation 2. c_load: F (design choice). vbatt: V (design choice). t_charge: s (design choice).
    Returns: A. INPUTS: none (all design choices)."""
    return c_load * vbatt / t_charge


def c1_for_inrush(c_load, vbst_src, r1, i_inrush_target):
    """C1 = 0.63 x V(BST-SRC) x CLOAD / (R1 x IINRUSH). Gate-ramp capacitor for a target inrush, eq. (3). DS p.16,
    7.3.1 Inrush Current Limiting, Equation 3. The 0.63 is printed in the equation. vbst_src: charge-pump voltage, V
    (the DS text under eq. 3 gives 11 V; design choice). c_load: F. r1: ohm (the DS suggests 100 kohm as a start).
    i_inrush_target: A (design choice). Returns: F. INPUTS: none."""
    return 0.63 * vbst_src * c_load / (r1 * i_inrush_target)


def cbst_min(qg_total, dv_bst, c1=0.0):
    """CBST = Qg(total) / dVBST + 10 x C1. Minimum bootstrap capacitor, eq. (4). DS p.16, 7.3.1 Inrush Current
    Limiting, Equation 4. The 10 x C1 term is printed in the equation; with C1 = 0 this is the DS design eq. (9)
    (DS p.23, CBST = Qg(total) / 1 V). qg_total: C (gate charge, design choice, e.g. 85 nC for the DS design FET).
    dv_bst: V, the BST ripple (DS p.16 text: dVBST 1 V typical; design choice). c1: F (from c1_for_inrush).
    Returns: F. INPUTS: none."""
    return qg_total / dv_bst + 10.0 * c1


def vscp_from_riscp(riscp):
    """V(SCP) = 2 uA x RISCP + 19 mV. Short-circuit threshold set by the ISCP resistor, the inverse of eq. (5).
    DS p.17, 7.3.3 Short-Circuit Protection, Equation 5: RISCP = (ISC x RSNS - 19 mV) / 2 uA, where ISC x RSNS is
    V(SCP). The 19 mV and 2 uA are printed in eq. 5; they reproduce the DS table rows (R(ISCP) = 140.5 kohm gives
    300 mV, 28 kohm gives 75 mV, DS p.7). riscp: ohm. Returns: V (threshold across CS+ and CS-).
    INPUTS: none (riscp is a design choice; the table row bounds are in the v_scp_* params)."""
    return 2e-6 * riscp + 19e-3


def riscp_for_isc(isc, rsns):
    """RISCP = (ISC x RSNS - 19 mV) / 2 uA. Short-circuit ISCP resistor for a desired short-circuit current, eq. (5).
    DS p.17, 7.3.3 Short-Circuit Protection, Equation 5. isc: A (design choice). rsns: ohm, the high or low side sense
    resistor or the FET RDS(ON) (design choice). Returns: ohm. INPUTS: none.
    Note: the DS design example (DS p.23, eq. 10) prints 50.5 kohm for ISC = 60 A with RDS(ON) = 2.3 mohm; eq. 5 with
    those numbers gives 59.5 kohm. The printed result implies RSNS = 2.0 mohm. See the open items."""
    return (isc * rsns - 19e-3) / 2e-6


def i_sc_from_vscp(vscp, rsns):
    """ISC = V(SCP) / RSNS. Short-circuit current trip level from a V(SCP) threshold row and the sense resistor
    (eq. 5 solved for ISC: ISC x RSNS = V(SCP)). The V(SCP) row must be the one for the chosen ISCP resistor
    (v_scp_r140k5 for 140.5 kohm, v_scp_r28k for 28 kohm, and so on, DS p.7). Using the row min and max gives a
    worst-case trip range; the RSNS tolerance is a separate input. vscp: V. rsns: ohm. Returns: A.
    INPUTS: vscp -> v_scp_r140k5 (example row; use the row for the chosen R(ISCP))."""
    return vscp / rsns


def v_iscp_bias_for_vscp(vscp):
    """V(SCP_BIAS) = 5 x ISC x RSNS - 95 mV, with ISC x RSNS = V(SCP). External bias voltage on the ISCP pin that sets
    the threshold without RISCP. DS p.17, 7.3.3 Short-Circuit Protection, text equation ('V(SCP_BIAS) in mV = ISC x
    RSNS x 5 - 95 mV'). The DS limits the bias to 3 V. vscp: V (threshold, ISC x RSNS). Returns: V.
    INPUTS: none (vscp is a design choice; the table rows V(ISCP) = 3 V, 1.405 V, 280 mV, 105 mV are the DS checks)."""
    return 5.0 * vscp - 95e-3


def ctmr_for_tsc(tsc, i_tmr=80e-6, v_tmr=1.1):
    """CTMR = ITMR x tSC / 1.1. Fault-timer capacitor for a desired short-circuit response time, eq. (6). DS p.18,
    7.3.3.1 Short-Circuit Protection With Auto-Retry, Equation 6. The DS text under eq. 6 gives ITMR = 80 uA internal
    pull-up current; eq. 11 (DS p.24, design example) uses I(TMR_SRC_CB) = 87 uA. The 1.1 is printed; it is the
    TMR clamp (V(TMR_SC) typ 1.1 V, DS p.7).
    tsc: s (design choice). i_tmr: A, default 80 uA as printed in the eq. 6 text. v_tmr: V, default 1.1 as printed.
    Returns: F. INPUTS: i_tmr -> i_tmr_src_cb (table row 65/87/106 uA, DS p.7; eq. 11 uses its typ) and
    v_tmr -> v_tmr_sc (0.87/1.1/1.26 V, DS p.7), so wca gives bounds. The 80 uA text value is a DS inconsistency
    (open item), kept only as the default and as i_tmr_pullup_text."""
    return i_tmr * tsc / v_tmr


def t_retry(ctmr):
    """tRETRY = 22.7 x 10^6 x CTMR. Auto-retry time after the first cycle, eq. (7). DS p.18, 7.3.3.1, Equation 7.
    The 22.7e6 s/F is printed in the equation. ctmr: F. Returns: s. INPUTS: none."""
    return 22.7e6 * ctmr


def ctmr_latch(tsc, rtmr, i_tmr_src_cb):
    """CTMR = tSC / (RTMR x ln(1 / (1 - 1.1 / (RTMR x I(TMR_SRC_CB))))). Fault-timer capacitor for latch-off with a
    parallel RTMR, eq. (8). DS p.19, 7.3.3.2 Short-Circuit Protection With Latch-Off, Equation 8. The 1.1 is printed
    (the TMR clamp). tsc: s (design choice). rtmr: ohm (the DS uses 100 kohm). i_tmr_src_cb: A, positive
    charge current, abs() applied. Returns: F. INPUTS: i_tmr_src_cb -> i_tmr_src_cb. C increases with I: max 106 uA
    gives the largest C for a target tSC; for a fixed C, min 65 uA gives the longest tSC. The printed 1.1 V is kept
    as printed (eq. 8); it is V(TMR_SC) typ (0.87-1.26 V, DS p.7), not swept here."""
    i = abs(i_tmr_src_cb)
    return tsc / (rtmr * math.log(1.0 / (1.0 - 1.1 / (rtmr * i))))


def vin_ovp_from_divider(r1, r2, r3, vovr):
    """VINOVP = V(OVR) x (R1 + R2 + R3) / R3. Overvoltage trip from the resistor divider VIN-R1-EN/UVLO-R2-OV-R3-GND (DS Fig 7-5, p.16; EN/UVLO is the upper tap, OV the lower).
    Inverse of eq. (12), DS p.24, 8.2.2 Detailed Design Procedure, Equation 12: V(OVR) = R3/(R1+R2+R3) x VINOVP.
    r1, r2, r3: ohm (design choices). vovr: V, OV rising threshold (DS p.6 typ 1.23 V; DS text p.24 uses 1.225 V).
    Returns: V. INPUTS: vovr -> v_ovr (rising OV threshold; min 1.17, max 1.28 V gives the trip range)."""
    return vovr * (r1 + r2 + r3) / r3


def vin_uvlo_from_divider(r1, r2, r3, vuvlo):
    """VINUVLO = V(UVLOR) x (R1 + R2 + R3) / (R2 + R3). Undervoltage (UVLO) rising trip from the same divider.
    Inverse of eq. (13), DS p.24, 8.2.2 Detailed Design Procedure, Equation 13: V(UVLOR) = (R2+R3)/(R1+R2+R3) x
    VINUVLO. r1, r2, r3: ohm (design choices). vuvlo: V, UVLO rising threshold (DS p.6). Returns: V.
    INPUTS: vuvlo -> v_uvlor (rising UVLO threshold; min 1.17, max 1.29 V gives the trip range).
    For the falling (shutdown) trip pass v_uvlof (DS p.6) instead."""
    return vuvlo * (r1 + r2 + r3) / (r2 + r3)


# INPUTS: {function name: {datasheet argument: component.toml param key}}. Every key must exist in component.toml.
INPUTS = {
    "t_drv_en": {"vbst_uvlor": "v_bst_uvlor", "i_bst": "i_bst"},
    "i_inrush": {},
    "c1_for_inrush": {},
    "cbst_min": {},
    "vscp_from_riscp": {},
    "riscp_for_isc": {},
    "i_sc_from_vscp": {"vscp": "v_scp_r140k5"},
    "v_iscp_bias_for_vscp": {},
    "ctmr_for_tsc": {"i_tmr": "i_tmr_src_cb", "v_tmr": "v_tmr_sc"},
    "t_retry": {},
    "ctmr_latch": {"i_tmr_src_cb": "i_tmr_src_cb"},
    "vin_ovp_from_divider": {"vovr": "v_ovr"},
    "vin_uvlo_from_divider": {"vuvlo": "v_uvlor"},
}


# EXAMPLES: datasheet printed numbers the functions must reproduce.
# (function name, kwargs, expected, relative tolerance, cite). Tolerances above 1e-3 are commented on the row above.
EXAMPLES = [
    # Eq. 9 (DS p.23): CBST = 85 nC / 1 V = 85 nF, with C1 = 0 (eq. 4 reduces to eq. 9).
    ("cbst_min", {"qg_total": 85e-9, "dv_bst": 1.0, "c1": 0.0}, 85e-9, 1e-3, "DS p.23, 8.2.2 Selection of Bootstrap Capacitor, eq. 9, CBST = 85 nF"),
    # Table rows: R(ISCP) = 140.5 kohm gives V(SCP) 300 mV typ, 28 kohm 75 mV, 10.5 kohm 40 mV, 500 ohm 20 mV (DS p.7).
    ("vscp_from_riscp", {"riscp": 140.5e3}, 300e-3, 1e-3, "DS p.7, 5.5 V(SCP) R(ISCP) = 140.5 kohm typ 300 mV; eq. 5 inverse"),
    ("vscp_from_riscp", {"riscp": 28e3}, 75e-3, 1e-3, "DS p.7, 5.5 V(SCP) R(ISCP) = 28 kohm typ 75 mV; eq. 5 inverse"),
    ("vscp_from_riscp", {"riscp": 10.5e3}, 40e-3, 1e-3, "DS p.7, 5.5 V(SCP) R(ISCP) = 10.5 kohm typ 40 mV; eq. 5 inverse"),
    ("vscp_from_riscp", {"riscp": 500.0}, 20e-3, 1e-3, "DS p.7, 5.5 V(SCP) R(ISCP) = 500 ohm typ 20 mV; eq. 5 inverse"),
    # Bias rows: V(ISCP) = 1.405 V gives 300 mV, 280 mV gives 75 mV, 105 mV gives 40 mV (DS p.7, DS p.17 text).
    ("v_iscp_bias_for_vscp", {"vscp": 300e-3}, 1.405, 1e-3, "DS p.17 text and DS p.7, V(ISCP) = 1.405 V for V(SCP) 300 mV"),
    ("v_iscp_bias_for_vscp", {"vscp": 75e-3}, 280e-3, 1e-3, "DS p.17 text and DS p.7, V(ISCP) = 280 mV for V(SCP) 75 mV"),
    ("v_iscp_bias_for_vscp", {"vscp": 40e-3}, 105e-3, 1e-3, "DS p.17 text and DS p.7, V(ISCP) = 105 mV for V(SCP) 40 mV"),
    # Eq. 12 inverse with the DS-solved divider (DS p.24): R1 = 470 k, R2 = 28.7 k, R3 = 10.4 k gives 60 V with V(OVR) 1.225 V.
    # Eq. 11 (DS p.24): CTMR = 87 uA x 50 us / 1.1 V = 3.955 nF (the DS then picks the closest standard 3.3 nF).
    ("ctmr_for_tsc", {"tsc": 50e-6, "i_tmr": 87e-6, "v_tmr": 1.1}, 3.955e-9, 1e-3, "DS p.24, 8.2.2 Selection of CTMR, eq. 11, 3.95 nF before the standard-value choice"),
    ("vin_ovp_from_divider", {"r1": 470e3, "r2": 28.7e3, "r3": 10.4e3, "vovr": 1.225}, 60.0, 1e-3, "DS p.24, 8.2.2 Setting the UVLO and OV, eq. 12 with V(OVR) 1.225 V, VINOVP 60 V"),
    # Eq. 13 inverse with the same divider: 16 V with V(UVLOR) 1.23 V. DS solves R2 = 28.7 k from 16 V, so the exact
    # result is 16.016 V (0.1 % from the printed 16 V). Tolerance 0.002 because the DS rounds R2 to 28.7 k.
    ("vin_uvlo_from_divider", {"r1": 470e3, "r2": 28.7e3, "r3": 10.4e3, "vuvlo": 1.23}, 16.0, 0.002, "DS p.24, 8.2.2 Setting the UVLO, eq. 13 with V(UVLOR) 1.23 V, VINUVLO 16 V; tolerance 0.2 % for the DS rounding of R2"),
]
