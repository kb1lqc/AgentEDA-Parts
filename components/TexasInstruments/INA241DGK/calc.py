"""INA241 datasheet equations (TI INA241A/INA241B, SBOSA30D Rev. D, Dec 2024). Plain floats, SI units, degC.
Fractions: gain_err and drift are fractions/1 per degC (the loader converts % and ppm/degC from component.toml).
Only equations the datasheet prints are here, plus one combined error function marked "Not a DS equation".
Cites are printed page numbers. Gain (V/V) comes from the variant's `gain` row (per variant, in variants.toml).
"""


def vout(g, vin_p, vin_n, vref1, vref2):
    """VOUT = G x (VIN+ - VIN-) + (VREF1 + VREF2) / 2. DS p.17, 7.4.1 Adjusting the Output With the Reference Pins, Equation 1.
    g: gain, V/V. vin_p, vin_n: IN+ and IN- pin voltages, V. vref1, vref2: REF1 and REF2 voltages, V.
    Returns: VOUT, V. Assumes the ideal reference network (the reference-divider error is a separate DS row)."""
    return g * (vin_p - vin_n) + (vref1 + vref2) / 2


def vsense_ideal(vout_fs, g):
    """VSENSE = VOUT / G. DS p.22, 8.1.1 RSENSE and Device Gain Selection, Table 8-1, row VSENSE.
    vout_fs: output voltage at full scale, V. g: gain, V/V. Returns: differential input voltage VSENSE, V."""
    return vout_fs / g


def rsense_ideal(vsense, imax):
    """RSENSE = VSENSE / IMAX. DS p.22, 8.1.1 RSENSE and Device Gain Selection, Table 8-1, row RSENSE.
    vsense: differential input at full scale, V. imax: full-scale current, A. Returns: RSENSE, ohm."""
    return vsense / imax


def psense(rsense, imax):
    """PSENSE = RSENSE x IMAX^2. DS p.22, 8.1.1 RSENSE and Device Gain Selection, Table 8-1, row PSENSE.
    rsense: ohm. imax: A. Returns: power dissipated in RSENSE, W."""
    return rsense * imax ** 2


def rsense_max_power(pdmax, imax):
    """RSENSE < PDMAX / IMAX^2 (strict). DS p.21, 8.1.1 RSENSE and Device Gain Selection, Equation 2.
    Returns the limit (the largest RSENSE allowed by the power budget), ohm. pdmax: W. imax: A."""
    return pdmax / imax ** 2


def vout_at_imax(imax, rsense, g):
    """VOUT_MAX = IMAX x RSENSE x G. DS p.21, 7.4.4 High Signal Throughput, Table 7-1 (VOUT_MAX row).
    Also the left side of DS p.21 Equation 3 (IMAX x RSENSE x GAIN < VSP) and DS p.22 Equation 4 (IMIN x RSENSE x GAIN > VSN):
    compare the result with the positive swing VSP (DS p.6, swing to VS) or the negative swing VSN.
    imax: A. rsense: ohm. g: V/V. Returns: output voltage, V."""
    return imax * rsense * g


def tresponse(vout_thr, sr):
    """Tresponse = VOUT_THR / SR. DS p.21, 7.4.4 High Signal Throughput, Table 7-1 (Tresponse row).
    vout_thr: output voltage at the threshold current, V. sr: slew rate, V/s (the DS SR row is V/us; the loader gives V/s).
    Returns: response time, s. Uses the typical slew rate (INPUTS sr = slew_rate_25c.typ)."""
    return vout_thr / sr


def current_error(rsense, vsense, gain_err, gain_drift, t_c, vos, vos_drift):
    """Not a DS equation: input-referred current-measurement error for one device, in A, combining the printed
    gain error, its drift, the input offset and its drift (DS p.6 GERR, DS p.5 Vos and dVos/dT, DS p.17 Equation 1).
    gf = (1 + gain_err) x (1 + gain_drift x (T - 25)) is the actual gain relative to the nominal G (SPEC recipe:
    25 degC row plus drift x (T - 25)); vos_t = vos + vos_drift x (T - 25).
    The output is VOUT = G x gf x (VSENSE + vos_t) + VREF, so the sensed VSENSE is gf x (VSENSE + vos_t) and the error
    is vsense x (gf - 1) + gf x vos_t, divided by RSENSE to give current.
    rsense: ohm. vsense: true differential input at this current (= I x RSENSE), V. gain_err: fraction, signed.
    gain_drift: 1/degC, signed. t_c: degC. vos: V, signed. vos_drift: V/degC, signed. Returns: current error, A.
    Corners are not monotone in t_c (t_c enters with a product of drift terms), so use wca samples for T.
    Gain (G) cancels, so the nominal gain is not an input. Gain error is a 25 degC row (curve-free).
    Limits: valid only at the EC table conditions (DS p.5 header: VCM = 48 V, VS = 5 V, VREF1 = VREF2 = VS/2).
    Not included: CMRR x (VCM - 48 V), PSRR x (VS - 5 V) and RVRR x (VREF - VS/2) offset terms (DS p.5 CMRR and
    PSRR rows, DS p.6 RVRR row). Away from those conditions add them to vos yourself; for A devices they can be
    as large as the offset."""
    gf = (1 + gain_err) * (1 + gain_drift * (t_c - 25))
    vos_t = vos + vos_drift * (t_c - 25)
    return (vsense * (gf - 1) + gf * vos_t) / rsense


EXAMPLES = [
    # (function, kwargs, expected, relative tolerance, cite)
    # Equation 1 with the Table 8-1 design (full scale 5 V at G = 10, VSENSE 500 mV, reference set to 0 V).
    ("vout", {"g": 10, "vin_p": 0.5, "vin_n": 0.0, "vref1": 0.0, "vref2": 0.0}, 5.0, 1e-3,
     "DS p.22, Table 8-1 (VSENSE = 500 mV at G = 10, output 5 V), with Equation 1 and VREF = 0 V"),
    # Equation 1 mid-point statement: output is the mid-point of REF1 and REF2 at VSENSE = 0 (DS p.17 text).
    ("vout", {"g": 10, "vin_p": 0.0, "vin_n": 0.0, "vref1": 5.0, "vref2": 0.0}, 2.5, 1e-3,
     "DS p.17, 7.4.1, Equation 1 and text: mid-point of REF1 and REF2 at VSENSE = 0"),
    # Table 8-1, five gains, VOUT full scale 5 V.
    ("vsense_ideal", {"vout_fs": 5, "g": 10}, 0.5, 1e-3, "DS p.22, Table 8-1, G 10 V/V, VSENSE 500 mV"),
    ("vsense_ideal", {"vout_fs": 5, "g": 20}, 0.25, 1e-3, "DS p.22, Table 8-1, G 20 V/V, VSENSE 250 mV"),
    ("vsense_ideal", {"vout_fs": 5, "g": 50}, 0.1, 1e-3, "DS p.22, Table 8-1, G 50 V/V, VSENSE 100 mV"),
    ("vsense_ideal", {"vout_fs": 5, "g": 100}, 0.05, 1e-3, "DS p.22, Table 8-1, G 100 V/V, VSENSE 50 mV"),
    ("vsense_ideal", {"vout_fs": 5, "g": 200}, 0.025, 1e-3, "DS p.22, Table 8-1, G 200 V/V, VSENSE 25 mV"),
    ("rsense_ideal", {"vsense": 0.5, "imax": 10}, 0.05, 1e-3, "DS p.22, Table 8-1, G 10 V/V, RSENSE 50 mohm"),
    ("rsense_ideal", {"vsense": 0.25, "imax": 10}, 0.025, 1e-3, "DS p.22, Table 8-1, G 20 V/V, RSENSE 25 mohm"),
    ("rsense_ideal", {"vsense": 0.1, "imax": 10}, 0.01, 1e-3, "DS p.22, Table 8-1, G 50 V/V, RSENSE 10 mohm"),
    ("rsense_ideal", {"vsense": 0.05, "imax": 10}, 0.005, 1e-3, "DS p.22, Table 8-1, G 100 V/V, RSENSE 5 mohm"),
    ("rsense_ideal", {"vsense": 0.025, "imax": 10}, 0.0025, 1e-3, "DS p.22, Table 8-1, G 200 V/V, RSENSE 2.5 mohm"),
    ("psense", {"rsense": 0.05, "imax": 10}, 5, 1e-3, "DS p.22, Table 8-1, G 10 V/V, PSENSE 5 W"),
    ("psense", {"rsense": 0.025, "imax": 10}, 2.5, 1e-3, "DS p.22, Table 8-1, G 20 V/V, PSENSE 2.5 W"),
    ("psense", {"rsense": 0.01, "imax": 10}, 1, 1e-3, "DS p.22, Table 8-1, G 50 V/V, PSENSE 1 W"),
    ("psense", {"rsense": 0.005, "imax": 10}, 0.5, 1e-3, "DS p.22, Table 8-1, G 100 V/V, PSENSE 0.5 W"),
    ("psense", {"rsense": 0.0025, "imax": 10}, 0.25, 1e-3, "DS p.22, Table 8-1, G 200 V/V, PSENSE 0.25 W"),
    # Equation 2 limit at the Table 8-1 design: 5 W at 10 A gives RSENSE < 50 mohm (Table 8-1 RSENSE 50 mohm).
    ("rsense_max_power", {"pdmax": 5, "imax": 10}, 0.05, 1e-3, "DS p.21, Equation 2 with DS p.22, Table 8-1 (5 W, 10 A)"),
    # Table 7-1 design (INA241A2, G 20, RSENSE 2 mohm, IMAX 100 A, ITHR 75 A): VOUT_MAX 4 V, VOUT_THR 3 V.
    ("vout_at_imax", {"imax": 100, "rsense": 0.002, "g": 20}, 4.0, 1e-3, "DS p.21, Table 7-1, VOUT_MAX 4 V"),
    ("vout_at_imax", {"imax": 75, "rsense": 0.002, "g": 20}, 3.0, 1e-3, "DS p.21, Table 7-1, VOUT_THR 3 V"),
    # Sanity: zero gain error, drift and offset give zero current error (no DS value).
    ("current_error", {"rsense": 0.1, "vsense": 0.0, "gain_err": 0.0, "gain_drift": 0.0, "t_c": 25.0,
                       "vos": 0.0, "vos_drift": 0.0}, 0.0, 1e-3, "Sanity: no error terms give zero (not a DS value)"),
    # Table 7-1 response-time example: VOUT_THR 3 V at SR 8 V/us (DS prints "< 1 us").
    ("tresponse", {"vout_thr": 3.0, "sr": 8e6}, 3.75e-7, 1e-3,
     "DS p.21, Table 7-1: Tresponse = VOUT_THR / SR = 3 V / 8 V/us (DS prints < 1 us)"),
]

INPUTS = {
    # function: {argument: component.toml key or key.field}. Design choices (imax, rsense, vout, vin, t_c) are not listed.
    # gain is typical only (DS p.5 G row, no MIN or MAX): gain.typ. Per-variant value (variants.toml).
    "vout": {"g": "gain.typ"},
    "vsense_ideal": {"g": "gain.typ"},
    "rsense_ideal": {},
    "psense": {},
    "rsense_max_power": {},
    "vout_at_imax": {"g": "gain.typ"},
    "tresponse": {"sr": "slew_rate_25c.typ"},  # SR is typical only (DS p.6 SR row)
    "current_error": {
        "gain_err": "gain_err_25c",
        "gain_drift": "gain_drift_full",
        "vos": "vos_25c",
        "vos_drift": "vos_drift_full",
    },
}
