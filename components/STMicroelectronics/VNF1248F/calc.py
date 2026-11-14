"""VNF1248F datasheet equations (DS14109 Rev 8, 09-Jul-2026; printed page numbers cited per function).

Units: V, A, ohm, s, degC. Arguments and returns are SI floats (the ADC codes are unitless integers as floats).
Parameters are arguments so the worst-case engine can sweep them. INPUTS maps each function's datasheet argument to the
component.toml key that supplies it; design choices (resistors, currents, codes) are not mapped.
"""


def vsense_from_csa_code(code):
    """VSENSE [mV] = VSENSE_ADC[14:2] * 160 / 8192. DS p.13, Table 17, test condition of VSENSE_ADC_CONV:
    VSENSE_ADC[14:2] = min(VSENSE / 160 * 8192, 8191), solved for VSENSE.
    DS CONFLICT, resolved: Table 17 footnote 1 prints "* 160 / 1024", a misprint copied from the 10-bit HSC ADC
    (DS p.14, Table 18 footnote 1, field [9:0]). The field [14:2] is 13 bits (0 to 8191), and only /8192 gives the
    160 mV full scale of VSENSE_FSR (DS p.11, Table 15); /1024 would give 1.28 V. Table > footnote (CLAUDE.md).
    code: VSENSE_ADC[14:2] field value, 0 to 8191. Returns: VSENSE, V. INPUTS: none."""
    return code * 160e-3 / 8192


def i_load_from_vsense(vsense, rsense):
    """IOUT [A] = VSENSE [mV] / RSENSE [ohm]. DS p.13, Table 17 footnote 2 (current sense ADC) and DS p.14, Table 18
    footnote 2 (HSC ADC, IOUT [A] = VSENSE [mV] / RSENSE [mohm], same ratio). vsense: V. rsense: ohm. Returns: A.
    The DS prints mV / ohm = mA; in SI, V / ohm = A. INPUTS: none (vsense is an ADC result, rsense a design choice)."""
    return vsense / rsense


def vsense_from_hsc_code(code):
    """VSENSE [mV] = VHSC_ADC[9:0] * 160 / 1024. DS p.14, Table 18, footnote 1 (10-bit HSC ADC; 1023 gives 160 mV full scale).
    code: VHSC_ADC[9:0] field value, 0 to 1023. Returns: VSENSE, V. INPUTS: none."""
    return code * 160e-3 / 1024


def vds_from_adc_code(code):
    """VDS [V] = VDS_ADC[22:13] * 2.4 / 1280 - 0.05. DS p.13, Table 16, footnote 2 (external MOSFET VDS fast ADC).
    code: VDS_ADC[22:13] field value, 0 to 1023. Returns: VDS, V. INPUTS: none.
    Check: code 0 gives -0.05 V (DS p.13 min); code 1023 gives 1.868 V (DS prints 1.87 V, rounded)."""
    return code * 2.4 / 1280 - 0.05


def vout_from_adc_code(code):
    """VOUT = VOUT_ADC[11:2] * 1.2 * 51 / 1024. DS p.15, Table 20, footnote 1. The DS prints the result as [mV], but
    the numbers give volts (full scale 61.1 V for code 1023; Table 20 accuracy is specified up to 60 V), so the result is
    in V. OPEN ITEM: unit label in the DS. code: VOUT_ADC[11:2] field value, 0 to 1023. Returns: VOUT, V. INPUTS: none."""
    return code * 1.2 * 51 / 1024


def tj_from_adc_code(code):
    """TJ [degC] = TJ_ADC[22:13] / 3 - 72. DS p.11, Table 14, footnote 1 (junction temperature ADC, 1/3 degC per code).
    code: TJ_ADC[22:13] field value, 0 to 1023 (TJ -72 to 269 degC over the code range). Returns: degC. INPUTS: none."""
    return code / 3 - 72


def vntc_from_adc_code(code):
    """VNTC [V] = VNTC_ADC[11:2] * 1.2 / 1024. DS p.16, Table 21, footnote 1 (external MOSFET NTC ADC).
    code: VNTC_ADC[11:2] field value, 0 to 1023. Returns: VNTC, V. INPUTS: none."""
    return code * 1.2 / 1024


def r_ntc(vntc, rt_ref, vbg):
    """RNTC [ohm] = VNTC * RT_REF / (VBG - VNTC). DS p.16, Table 21, footnote 1 (second line). RT_REF = 12 kohm +/-1 %
    (DS p.17, Figure 4 note; DS p.68, Table 64). VBG = 1.2 V typ (DS p.17, Figure 4 note; DS p.39). vntc: V (from
    vntc_from_adc_code). rt_ref: ohm (design choice). vbg: V. Returns: ohm. INPUTS: vbg -> vbg.typ (typical only)."""
    return vntc * rt_ref / (vbg - vntc)


def i_threshold(v_thr, rsense):
    """I = VTHR / RSENSE. DS p.18, eFuse function text: load hard short circuit threshold IHSC = VHSC_THR_x / RSENSE and
    eFuse nominal current INOM = VOVC_THR_x / RSENSE (the same ratio). v_thr: threshold, V (one stored setting, e.g.
    vhsc_thr_12 typ 105.6 mV or vovc_thr_16 typ 26.5 mV; pass the typical or a bound of that setting). rsense: ohm.
    Returns: A. INPUTS: none (the setting is chosen by the caller)."""
    return v_thr / rsense


def i_trip(v_thr, acc, rsense):
    """Not a DS equation: I_TRIP = VTHR * (1 + acc) / RSENSE. Combines the DS p.18 threshold ratio (i_threshold) with the
    printed threshold accuracy of the chosen setting. acc is a fraction (-0.05 = -5 %), chosen by the setting's range:
    - HSC (VHSC_THR_x, DS p.13-14 Table 18): acc -> vhsc_thr_acc, -5 % to +5 % for all 16 codes.
    - OVC (VOVC_THR_x, DS p.14-15 Table 19), by decimal code n: n = 0 to 2 -> vovc_acc_0_2 (-12 % to +12 %);
      n = 3 to 12 -> vovc_acc_3_12 (-7 % to +7 %); n = 13 to 31 -> vovc_acc_13_31 (-5 % to +5 %).
      The group boundaries are the merged cells of Table 19 (0x00-0x02, 0x03-0x0C, 0x0D-0x17 on p.14; 0x18-0x1F on p.15).
    v_thr: setting value, V (design choice from the Table 18 or 19 typ). rsense: ohm (design choice). Returns: A.
    Worst case: wca min at acc = lo, max at acc = hi. INPUTS: default acc -> vhsc_thr_acc (HSC). For OVC, the caller
    passes the group key (e.g. vovc_acc_13_31) as the acc argument's Param."""
    return v_thr * (1 + acc) / rsense


def vntc_from_rntc(rntc, rt_ref, vbg):
    """VNTC [V] = VBG * RNTC / (RT_REF + RNTC). DS p.39, 11.3 External MOSFET overtemperature shutdown, Equation (1).
    Forward form of the Table 21 footnote 1 (r_ntc is its inverse). VBG = (VISNS_N - VNTC_M), typ 1.2 V (DS p.39).
    rntc: ohm (NTC resistance; DS p.17 Figure 4 note: B57232V5103F360, 10 kohm at 25 degC). rt_ref: ohm (12 kohm +/-1 %,
    DS p.17 Figure 4 note). vbg: V. Returns: V. INPUTS: vbg -> vbg.typ (typical only)."""
    return vbg * rntc / (rt_ref + rntc)


def r_ntc(vntc, rt_ref, vbg):
    """RNTC [ohm] = VNTC * RT_REF / (VBG - VNTC). DS p.16, Table 21, footnote 1 (second line); inverse of DS p.39 Eq. (1).
    RT_REF = 12 kohm +/-1 % (DS p.17, Figure 4 note; DS p.68, Table 64). VBG = 1.2 V typ (DS p.17 Figure 4 note; DS p.39).
    vntc: V (from vntc_from_adc_code or vntc_from_rntc). rt_ref: ohm (design choice). vbg: V.
    Returns: ohm. INPUTS: vbg -> vbg.typ (typical only)."""
    return vntc * rt_ref / (vbg - vntc)


def i_time_tol_min(t):
    """Minimum of the I-t time step tolerance: (t - 10 %) - 32 = 0.9 * t - 32 us. DS p.15, Table 19, row i-time_tol_t
    (Min column, printed '(t-10%) - 32', unit us). The 32 is read in us from the printed unit column.
    t: time step, s. Returns: s. INPUTS: none (t is the step being evaluated)."""
    return 0.9 * t - 32e-6


def i_time_tol_max(t):
    """Maximum of the I-t time step tolerance: (t + 10 %) + 32 = 1.1 * t + 32 us. DS p.15, Table 19, row i-time_tol_t
    (Max column, printed '(t+10%) + 32', unit us). Same unit reading as i_time_tol_min. t: s. Returns: s. INPUTS: none."""
    return 1.1 * t + 32e-6


EXAMPLES = [
    # (function, kwargs, expected, relative tolerance, cite)
    # Full scale: code 8191 -> 159.98 mV vs VSENSE_FSR 160 mV max (DS p.11, Table 15); tol 2e-4 covers the 1-LSB clamp.
    ("vsense_from_csa_code", {"code": 8191}, 0.160, 2e-4, "DS p.11, Table 15, VSENSE_FSR; DS p.13, Table 17 test condition"),
    # HSC full scale: code 1023 is one LSB (0.156 mV) below VHSC_THR_RANGE max 160 mV (DS p.13, Table 18). tol 2e-3 (looser
    # than 1e-3) because one LSB is 0.1 % of 160 mV and the top code is 1023, not 1024.
    ("vsense_from_hsc_code", {"code": 1023}, 0.160, 2e-3, "DS p.13, Table 18, VHSC_THR_RANGE max 160 mV at the top code"),
    ("vds_from_adc_code", {"code": 0}, -0.05, 1e-3, "DS p.13, Table 16, VDS_ADC_CONV min -0.05 V"),
    # tol 0.002: DS prints the full scale as 1.87 V (rounded); exact 1.868125 V.
    ("vds_from_adc_code", {"code": 1023}, 1.87, 0.002, "DS p.13, Table 16, VDS_ADC_CONV max 1.87 V (rounded in the DS)"),
    ("i_threshold", {"v_thr": 26.5e-3, "rsense": 1e-3}, 26.5, 1e-3,
     "DS p.18, eFuse text: VOVC_THR_16 = 26.5 mV with RSENSE = 1 mohm (DS p.68, Table 64 value) gives 26.5 A"),
    ("i_threshold", {"v_thr": 105.6e-3, "rsense": 1e-3}, 105.6, 1e-3,
     "DS p.18, eFuse text: VHSC_THR_12 = 105.60 mV with RSENSE = 1 mohm gives 105.6 A"),
    ("i_trip", {"v_thr": 105.6e-3, "acc": 0.0, "rsense": 1e-3}, 105.6, 1e-3,
     "DS p.18 example VHSC_THR_12 = 105.60 mV with 0 % accuracy, RSENSE = 1 mohm"),
    ("i_trip", {"v_thr": 160e-3, "acc": -0.05, "rsense": 1e-3}, 152.0, 1e-3,
     "DS p.13-14, Table 18, VHSC_THR_15 = 160 mV at the -5 % accuracy corner (160 * 0.95 = 152 A at 1 mohm)"),
    ("i_trip", {"v_thr": 26.5e-3, "acc": -0.05, "rsense": 1e-3}, 25.175, 1e-3,
     "DS p.15, Table 19, VOVC_THR_16 = 26.5 mV in the 13-31 group (-5 %), 1 mohm: 26.5 * 0.95 = 25.175 A"),
    # Round trip of DS p.39 Eq. (1) with printed values: RNTC = 10 kohm at 25 degC (DS p.17 Figure 4 note), RT_REF = 12 kohm,
    # VBG = 1.2 V (DS p.17). Expected 6/11 V = 1.2 * 10 / 22. Exact identity, so tol 1e-9.
    ("vntc_from_rntc", {"rntc": 10e3, "rt_ref": 12e3, "vbg": 1.2}, 6 / 11, 1e-9,
     "DS p.39, Equation (1) with RNTC 10 kohm, RT_REF 12 kohm, VBG 1.2 V (DS p.17 Figure 4 notes)"),
    ("r_ntc", {"vntc": 6 / 11, "rt_ref": 12e3, "vbg": 1.2}, 10e3, 1e-9,
     "Inverse of DS p.39 Eq. (1) (Table 21 footnote 1): round trip back to RNTC = 10 kohm"),
]
# No EXAMPLES for vout_from_adc_code, tj_from_adc_code, vntc_from_adc_code: the DS prints no code/voltage pair for them
# (VOUT accuracy bands in Table 20 and TTSD 175 degC in Table 14 are not codes). i_time_tol_min/max: no printed time pair.

INPUTS = {
    # function: {argument: component.toml key}
    "vsense_from_csa_code": {},
    "i_load_from_vsense": {},
    "vsense_from_hsc_code": {},
    "vds_from_adc_code": {},
    "vout_from_adc_code": {},
    "tj_from_adc_code": {},
    "vntc_from_adc_code": {},
    "vntc_from_rntc": {"vbg": "vbg.typ"},
    "r_ntc": {"vbg": "vbg.typ"},
    "i_threshold": {},
    "i_trip": {"acc": "vhsc_thr_acc"},
    "i_time_tol_min": {},
    "i_time_tol_max": {},
}
