"""LTC4364-1 (latch-off, H grade, MS package) datasheet application equations.

DS: docs/datasheets/ltc4364.pdf, LTC4364-1/LTC4364-2 Rev. B (1/23), printed pages cited per function.
Units: V, A, ohm, F, s, W, W*s; temperatures in degC. Parameters are arguments so the worst-case engine can sweep
them. Stored negative currents (component.toml) are signed; functions that need a magnitude apply abs() and say so.
INPUTS maps each function's datasheet arguments to the component.toml param key that supplies them. Design choices
(resistors, capacitors, load, targets) are not mapped; a function with no mapped argument has an empty INPUTS entry.
"""

import math


def rsns(dvsns, ilim):
    """RSNS = dVSNS / ILIM. DS p.12, Overcurrent Fault, equation; DS p.19, Design Example.
    INPUTS uses dvsns_full (min 43 mV, -40 to 125 degC): its range contains the C (0 to 70 degC), I (-40 to 85 degC)
    and H (-40 to 125 degC) grade ranges, so it is valid for all six variants. The DS design example (p.19) uses the
    0-125 degC 45 mV row (dvsns_0c125c), which is full-range data for the C variants only.
    dvsns: overcurrent sense threshold, V. ilim: desired current limit, A. Returns: ohm."""
    return dvsns / ilim


def vreg(r7, r8, vfb, iin=0):
    """VREG = VFB * (R7 + R8) / R8 + iin * R7. Output clamp regulated by the FB divider OUT-R7-FB-R8-GND.
    DS p.19, Design Example (VREG = 1.25 V (R7 + R8)/R8); FB divider Figure 1 (DS p.12); VFB DS p.3.
    With iin != 0 this is Not a DS equation: adds the IFB (DS p.3) error through the divider's Thevenin resistance.
    Derivation: KCL at FB (f): (VOUT - f)/R7 = f/R8 + iin, with iin the current drawn out of the FB pin. Solve for VOUT
    with f = VFB: VOUT = VFB (R7+R8)/R8 + iin R7. The node Thevenin resistance is R7||R8; the node error iin*R7||R8
    referred to VOUT is multiplied by (R7+R8)/R8, giving iin*R7.
    r7: OUT to FB, ohm. r8: FB to GND, ohm. vfb: FB servo voltage, V. iin: FB pin current, A, positive into the pin.
    Returns: VREG, V.
    INPUTS: vfb -> vfb, iin -> ifb (FB = 1.25 V, min -1 uA, max 1 uA)."""
    return vfb * (r7 + r8) / r8 + iin * r7


def r7_for_vreg(vreg_target, r8, vfb):
    """R7 = (VREG - VFB) * R8 / VFB, the solved form of vreg() without iin. DS p.19, Design Example
    (R7 = (27V - 1.25V) * R8 / 1.25V = 102.8k). vreg_target: V. r8: ohm. vfb: V. Returns: ohm."""
    return (vreg_target - vfb) * r8 / vfb


def vin_uv(r1, r2, r3, vth, iin=0, iin_ov=0):
    """VIN falling UV trip = VTH * (R1+R2+R3)/(R2+R3) + iin * R1 + iin_ov * R1 * R3/(R2+R3).
    Divider VIN-R1-UV-R2-OV-R3-GND. DS p.19, Design Example (6V / (R1+R2+R3) = 1.25V / (R2+R3)); Figure 1, UV = 6 V
    (DS p.12). With iin != 0 or iin_ov != 0 this is Not a DS equation: adds the IIN (DS p.4) error through the
    divider's Thevenin resistance.
    Derivation: pin currents are positive into the pin, so they leave the divider node. KCL at UV (u) and OV (o):
      (VIN - u)/R1 = (u - o)/R2 + iin
      (u - o)/R2   = o/R3 + iin_ov
    Eliminating o gives u = [VIN - R1*iin - R1*iin_ov*R3/(R2+R3)] * (R2+R3)/(R1+R2+R3). Setting u = VTH and solving
    for VIN gives the formula. The UV-node Thevenin resistance is Rth = R1*(R2+R3)/(R1+R2+R3), so the UV-node error is
    iin*Rth; referred to VIN (multiply by (R1+R2+R3)/(R2+R3)) it is iin*R1.
    Rising trip (the turn-on point): pass vth = VUV + VUV(HYST), i.e. keys vuv + vuv_hyst (DS p.13: UV must rise above
    the UV threshold plus the hysteresis). Keys: vuv (falling, DS p.4) and vuv_hyst (DS p.4).
    r1, r2, r3: ohm. vth: V. iin: UV pin current, A. iin_ov: OV pin current, A. Returns: V.
    INPUTS: vth -> vuv (falling trip), iin -> iin_uvov_pos (UV at 1.25 V), iin_ov -> iin_uvov_pos (OV at 1.25 V)."""
    return vth * (r1 + r2 + r3) / (r2 + r3) + iin * r1 + iin_ov * r1 * r3 / (r2 + r3)


def vin_ov(r1, r2, r3, vth, iin=0, iin_uv=0):
    """VIN rising OV trip = VTH * (R1+R2+R3)/R3 + iin * (R1+R2) + iin_uv * R1.
    DS p.19, Design Example (60V / (R1+R2+R3) = 1.25V / R3); Figure 1, OV = 60 V (DS p.12).
    With iin != 0 or iin_uv != 0 this is Not a DS equation: adds the IIN (DS p.4) error through the divider's Thevenin
    resistance.
    Derivation (same KCL as vin_uv, with the OV node o = VTH): from the OV node, u = o (R2+R3)/R3 + iin * R2, where
    iin is the OV pin current. Then VIN = u (R1+R2+R3)/(R2+R3) + iin * R1 R3/(R2+R3) + iin_uv * R1, with iin_uv the UV
    pin current. Substituting u: the iin coefficient is R2 (R1+R2+R3)/(R2+R3) + R1 R3/(R2+R3) = R1 + R2.
    r1, r2, r3: ohm. vth: OV threshold, V. iin: OV pin current, A. iin_uv: UV pin current, A. Returns: V.
    INPUTS: vth -> vov, iin -> iin_uvov_pos (OV at 1.25 V), iin_uv -> iin_uvov_pos (UV at 1.25 V)."""
    return vth * (r1 + r2 + r3) / r3 + iin * (r1 + r2) + iin_uv * r1


def uv_ov_r2(vuv, vov, r3):
    """R2 = (VOV / VUV - 1) * R3. DS p.19, Design Example (R2 = (60V/6V - 1) * R3 = 90k). vuv, vov: target trip
    points, V (design choices). r3: ohm. Returns: ohm. INPUTS: none (design choices)."""
    return (vov / vuv - 1) * r3


def uv_r1(vuv, vth, r2, r3):
    """R1 = (VUV / VTH - 1) * (R2 + R3). DS p.19, Design Example (R1 = (6V/1.25V - 1) * (R2+R3) = 380k).
    vuv: target falling trip, V. vth: UV threshold, V. r2, r3: ohm. Returns: ohm.
    INPUTS: vth -> vuv (falling UV threshold, typ 1.25 V)."""
    return (vuv / vth - 1) * (r2 + r3)


def c_tmr_for_warning(t_warn, i_warn, dv_warn):
    """CTMR = tWARNING * |ITMR(UP,warn)| / dVTMR. DS p.19, Design Example (1 ms * 5 uA / 100 mV = 50 nF), solved from
    the DS p.14 equation tWARNING = CTMR * 100 mV / 5 uA. i_warn is the stored signed current: abs() is applied, so a
    negative param gives a positive capacitance. t_warn: s (design choice). dv_warn: V. Returns: F.
    INPUTS: i_warn -> itmr_up_warn (DS p.4, typ -5 uA), dv_warn -> dvtmr (DS p.4, typ 100 mV)."""
    return t_warn * abs(i_warn) / dv_warn


def t_warning(ctmr, i_warn, dv_warn):
    """tWARNING = CTMR * dVTMR / |ITMR(UP,warn)|. DS p.14, Fault Timer equation (100 mV / 5 uA): the interval between
    FLT asserting and HGATE turn-off. abs() is applied to i_warn, so a negative stored param works.
    ctmr: F (design choice). i_warn: A, signed. dv_warn: V. Returns: s.
    INPUTS: i_warn -> itmr_up_warn, dv_warn -> dvtmr."""
    return ctmr * dv_warn / abs(i_warn)


def itmr_up_ov_typ(dv):
    """ITMR(UP)OV = 2 uA + 0.644 uA/V * (VCC - VOUT - 0.5 V). DS p.14, Fault Timer, overvoltage fault timer current
    (fit to Figure 3a). TYPICAL curve fit: never a worst-case bound. The guaranteed points are the DS p.4 rows
    itmr_up_ov_lo (VCC-OUT = 0.5 V, min -1.3 max -3 uA as printed, stored as min -3 max -1.3 uA) and itmr_up_ov_hi
    (VCC-OUT = 75 V, stored min -60 max -40 uA). dv = VCC - VOUT, V. Returns: A (positive). INPUTS: none (dv is an
    operating condition)."""
    return 2e-6 + 0.644e-6 * (dv - 0.5)


def itmr_up_oc_typ(dv):
    """ITMR(UP)OC = 10 uA + 3.36 uA/V * (VCC - VOUT - 0.5 V). DS p.14, overcurrent fault timer current (fit to
    Figure 3b). TYPICAL curve fit: never a worst-case bound. The guaranteed points are the DS p.4 rows itmr_up_oc_lo
    (VCC-OUT = 0.5 V) and itmr_up_oc_hi (VCC-OUT = 75 V). dv = VCC - VOUT, V. Returns: A (positive).
    INPUTS: none (dv is an operating condition)."""
    return 10e-6 + 3.36e-6 * (dv - 0.5)


def t_flt(ctmr, i_up, vtmr_f):
    """Time to FLT asserting = CTMR * VTMR(F) / |ITMR(UP)|. DS p.14 (first term of tOV); Figure 3 labels tFLT.
    abs() is applied to i_up. ctmr: F (design choice). i_up: A, signed. vtmr_f: FLT threshold, V. Returns: s.
    INPUTS: i_up -> itmr_up_ov_hi (overvoltage, VCC-OUT = 75 V row). For overcurrent use itmr_up_oc_hi, or
    itmr_up_ov_lo/itmr_up_oc_lo for VCC-OUT = 0.5 V; the caller picks the row for the operating point.
    vtmr_f -> vtmr_f."""
    return ctmr * vtmr_f / abs(i_up)


def t_ov(ctmr, i_up_ov, i_warn, vtmr_f, dv_warn):
    """tOV = CTMR * VTMR(F) / |ITMR(UP)OV| + CTMR * dVTMR / |ITMR(UP)warn|. DS p.14, overvoltage fault: time from the
    start of the fault to HGATE turn-off (time to FLT plus the warning window). abs() is applied to both currents.
    ctmr: F (design choice). i_up_ov: A, signed. i_warn: A, signed. vtmr_f: V. dv_warn: V. Returns: s.
    INPUTS: i_up_ov -> itmr_up_ov_hi (75 V row; see t_flt for other rows), i_warn -> itmr_up_warn, vtmr_f -> vtmr_f,
    dv_warn -> dvtmr."""
    return ctmr * vtmr_f / abs(i_up_ov) + ctmr * dv_warn / abs(i_warn)


def t_oc(ctmr, i_up_oc, vtmr_g):
    """tOC = CTMR * VTMR(G) / |ITMR(UP)OC|. DS p.14, overcurrent fault time to HGATE turn-off (the timer current is not
    reduced to 5 uA after FLT in overcurrent). abs() is applied to i_up_oc. ctmr: F (design choice). i_up_oc: A, signed.
    vtmr_g: TMR gate-off threshold, V. Returns: s.
    INPUTS: i_up_oc -> itmr_up_oc_hi (75 V row), vtmr_g -> vtmr_g."""
    return ctmr * vtmr_g / abs(i_up_oc)


def t_cool(ctmr, i_cycle, dv_cycle, i_up=None):
    """tCOOL = 63 * CTMR * 1.2 V / 2 uA. DS p.15, Cool Down Period and Restart. The TMR pin cycles 32 times between
    0.15 V and 1.35 V (DS p.14); the 63 is as printed. The -1 option also runs these cool-down cycles and then latches
    (DS p.15), so this applies to -1. abs() is applied to i_cycle. ctmr: F (design choice). i_cycle: A, 2 uA printed as
    typical (DS p.14, p.15); the guaranteed retry-function rows are itmr_dn_retry (1.1 to 2.7 uA) and itmr_up_retry
    (-1.3 to -3 uA). dv_cycle: V, 1.2 V printed (= VTMR(G) - VTMR(R) nominal: keys vtmr_g and vtmr_r). Returns: s.
    INPUTS: i_cycle -> itmr_dn_retry (discharge leg), i_up -> itmr_up_retry (charge leg).
    With i_up given this is Not a DS equation: the 63 legs are split evenly between the discharge current i_cycle
    and the charge current i_up, tCOOL = 63/2 * CTMR * dv_cycle * (1/|i_cycle| + 1/|i_up|), so worst case uses both
    guaranteed currents. The DS does not state the split; with i_up == i_cycle it equals the DS equation."""
    if i_up is None:
        return 63 * ctmr * dv_cycle / abs(i_cycle)
    return 63 / 2 * ctmr * dv_cycle * (1 / abs(i_cycle) + 1 / abs(i_up))


def c_hgate_for_inrush(i_hgate_up, i_inrush, c_load):
    """CHG = |IHGATE(UP)| * CL / IINRUSH. HGATE-to-GND capacitor for a target inrush current. DS p.17, Limiting Inrush
    Current. abs() is applied to i_hgate_up (stored negative). i_inrush: A (design choice). c_load: F (design choice).
    Returns: F. The DS minimum of 6.8 nF (DS p.8, HGATE pin) is a separate requirement and is not applied here.
    INPUTS: i_hgate_up -> ihgate_up (DS p.3, typ -20 uA)."""
    return abs(i_hgate_up) * c_load / i_inrush


def r4_max(vin_min, vcc_min, icc_max):
    """R4 <= (VIN(min) - VCC(min)) / ICC(max). Series resistor so VCC stays at or above 4 V. DS p.19, Design Example
    (R4 = (6V - 4V) / 0.75 mA = 2.7k). vin_min: V (design choice). vcc_min: V. icc_max: A. Returns: ohm (maximum).
    INPUTS: vcc_min -> vcc_op (min 4 V), icc_max -> icc (max 750 uA)."""
    return (vin_min - vcc_min) / icc_max


def i_d1_peak(vin_max, vz_min, r4):
    """I(D1,PK) = (VIN(max) - VZ(min)) / R4. Transient current in the VCC clamp Zener. DS p.19, Design Example
    ((200V - 64V) / 2.2k = 62 mA). vin_max: V (design choice). vz_min: Zener minimum voltage, V (external part, not in
    this component). r4: ohm. Returns: A. INPUTS: none."""
    return (vin_max - vz_min) / r4


def p_m1_oc(vds, dvsns, rsns_ohm):
    """P = dVDS(M1) * dVSNS(MAX) / RSNS. Power in M1 during an overcurrent limit. DS p.20, Design Example
    (14 V * 32 mV / 10 mohm = 45 W; 12 V * 55 mV / 10 mohm = 66 W). vds: VCC - OUT, V (operating point). dvsns: V.
    rsns_ohm: ohm. Returns: W. INPUTS: dvsns -> dvsns_full (max 57 mV at H grade)."""
    return vds * dvsns / rsns_ohm


def rdson_m2_max(vfw, i_load_max):
    """RDS(ON) <= VFW / ILOAD(MAX). Ideal diode MOSFET M2 on-resistance for a forward drop VFW. DS p.20, MOSFET
    Selection (0.25 V / 5.5 A = 45.5 mohm). vfw, i_load_max: design choices. Returns: ohm. INPUTS: none."""
    return vfw / i_load_max


def p2t_simple(i_load, vpk, vreg_v, tau):
    """P^2t = 1/2 * ILOAD^2 * (VPK - VREG)^2 * tau. Simplified transient stress for VREG ~ VIN and tau >> tr.
    DS p.17, Calculating Transient Stress (18.4 W^2 s for 3 A, 80 V, 16 V, 1 ms). All arguments are design or
    transient-waveform choices. i_load: A. vpk, vreg_v: V. tau: s. Returns: W^2 s. INPUTS: none."""
    return 0.5 * i_load * i_load * (vpk - vreg_v) ** 2 * tau


def p2t_transient(i_load, tr, tau, vpk, vin, vreg_v):
    """P^2t = ILOAD^2 * [ (1/3) * tr * (b-a)^3 / b + (1/2) * tau * (2 a^2 ln(b/a) + 3 a^2 + b^2 - 4 a b) ] with
    a = VREG - VIN, b = VPK - VIN, for the linear-rise, exponential-decay transient of DS Figure 5. DS p.16,
    Calculating Transient Stress. All arguments are waveform or design choices. i_load: A. tr: rise time, s.
    tau: decay time constant, s. vpk, vin, vreg_v: V. Returns: W^2 s. Needs VIN < VREG < VPK. INPUTS: none."""
    a = vreg_v - vin
    b = vpk - vin
    if a <= 0 or b <= a:
        raise ValueError("p2t_transient needs VIN < VREG < VPK")
    return i_load * i_load * (
        (1.0 / 3.0) * tr * (b - a) ** 3 / b
        + 0.5 * tau * (2 * a * a * math.log(b / a) + 3 * a * a + b * b - 4 * a * b)
    )


def p2t_short(vin, dvsns, rsns_ohm, t_oc_s):
    """P^2t = (VIN * dVSNS / RSNS)^2 * tOC. Short-circuit stress on M1. DS p.17, Short-Circuit Stress
    (15 V, 25 mV, 12 mohm, 100 nF gives 2.2 W^2 s). vin: V (operating point). dvsns: V. rsns_ohm: ohm. t_oc_s: s, the
    output of t_oc(). Returns: W^2 s. INPUTS: dvsns -> dvsns_full."""
    return (vin * dvsns / rsns_ohm) ** 2 * t_oc_s


def tau_parallel_rc(r_a, r_b, c):
    """tau = (R_a || R_b) * C, the UV/OV start-up RC used for the tau_UV / tau_OV skew. DS p.13, Figure 2
    (tau_UV = (383k || 100k) * 10 nF, tau_OV = (475k || 10k) * 1 nF; DS requires tau_UV / tau_OV > 50).
    r_a, r_b: ohm. c: F. Returns: s. INPUTS: none."""
    return (r_a * r_b / (r_a + r_b)) * c


# INPUTS: {function name: {datasheet argument: component.toml param key}}. Every key must exist in component.toml.
INPUTS = {
    "rsns": {"dvsns": "dvsns_full"},
    "vreg": {"vfb": "vfb", "iin": "ifb"},
    "r7_for_vreg": {"vfb": "vfb"},
    "vin_uv": {"vth": "vuv", "iin": "iin_uvov_pos", "iin_ov": "iin_uvov_pos"},
    "vin_ov": {"vth": "vov", "iin": "iin_uvov_pos", "iin_uv": "iin_uvov_pos"},
    "uv_ov_r2": {},
    "uv_r1": {"vth": "vuv"},
    "c_tmr_for_warning": {"i_warn": "itmr_up_warn", "dv_warn": "dvtmr"},
    "t_warning": {"i_warn": "itmr_up_warn", "dv_warn": "dvtmr"},
    "itmr_up_ov_typ": {},
    "itmr_up_oc_typ": {},
    "t_flt": {"i_up": "itmr_up_ov_hi", "vtmr_f": "vtmr_f"},
    "t_ov": {"i_up_ov": "itmr_up_ov_hi", "i_warn": "itmr_up_warn", "vtmr_f": "vtmr_f", "dv_warn": "dvtmr"},
    "t_oc": {"i_up_oc": "itmr_up_oc_hi", "vtmr_g": "vtmr_g"},
    "t_cool": {"i_cycle": "itmr_dn_retry", "i_up": "itmr_up_retry"},
    "c_hgate_for_inrush": {"i_hgate_up": "ihgate_up"},
    "r4_max": {"vcc_min": "vcc_op.min", "icc_max": "icc.max"},
    "i_d1_peak": {},
    "p_m1_oc": {"dvsns": "dvsns_full"},
    "rdson_m2_max": {},
    "p2t_simple": {},
    "p2t_transient": {},
    "p2t_short": {"dvsns": "dvsns_full"},
    "tau_parallel_rc": {},
}


# EXAMPLES: datasheet printed numbers that the functions must reproduce.
# (function name, kwargs, expected, relative tolerance, cite). Tolerances above 1e-3 are commented on the row above.
EXAMPLES = [
    # tol 0.03: DS prints 11 mohm (rounded down); exact 11.25 mohm.
    ("rsns", {"dvsns": 45e-3, "ilim": 4.0}, 11e-3, 0.03, "DS p.19, Design Example, RSNS = 45 mV / 4 A = 11 mohm"),
    # tol 0.002: DS prints 27 V (rounded); exact 27.0015 V.
    ("vreg", {"r7": 102.8e3, "r8": 4.99e3, "vfb": 1.25}, 27.0, 0.002, "DS p.19, Design Example, VREG = 27 V (R7 = 102.8k, R8 = 4.99k)"),
    # tol 0.002: DS prints 102.8k (rounded to 0.1k); exact 102.794k.
    ("r7_for_vreg", {"vreg_target": 27.0, "r8": 4.99e3, "vfb": 1.25}, 102.8e3, 0.002, "DS p.19, Design Example, R7 = 102.8k"),
    ("vin_uv", {"r1": 380e3, "r2": 90e3, "r3": 10e3, "vth": 1.25}, 6.0, 0.001, "DS p.19, Design Example, UV = 6 V (R1 380k, R2 90k, R3 10k)"),
    ("vin_ov", {"r1": 380e3, "r2": 90e3, "r3": 10e3, "vth": 1.25}, 60.0, 0.001, "DS p.19, Design Example, OV = 60 V (same divider)"),
    # tol 0.01: DS prints UV = 6 V (rounded); exact 5.9948 V for these standard values.
    ("vin_uv", {"r1": 383e3, "r2": 90.9e3, "r3": 10e3, "vth": 1.25}, 6.0, 0.01, "DS p.12, Figure 1, UV = 6 V (383k, 90.9k, 10k)"),
    # tol 0.02: DS prints OV = 60 V (rounded); exact 60.4875 V for these standard values.
    ("vin_ov", {"r1": 383e3, "r2": 90.9e3, "r3": 10e3, "vth": 1.25}, 60.0, 0.02, "DS p.12, Figure 1, OV = 60 V (383k, 90.9k, 10k)"),
    ("uv_ov_r2", {"vuv": 6.0, "vov": 60.0, "r3": 10e3}, 90e3, 0.001, "DS p.19, Design Example, R2 = 90k"),
    ("uv_r1", {"vuv": 6.0, "vth": 1.25, "r2": 90e3, "r3": 10e3}, 380e3, 0.001, "DS p.19, Design Example, R1 = 380k"),
    ("c_tmr_for_warning", {"t_warn": 1e-3, "i_warn": 5e-6, "dv_warn": 0.1}, 50e-9, 0.001, "DS p.19, Design Example, CTMR = 50 nF"),
    ("c_tmr_for_warning", {"t_warn": 1e-3, "i_warn": -5e-6, "dv_warn": 0.1}, 50e-9, 0.001, "DS p.19 with the signed stored param (itmr_up_warn is negative): abs() gives 50 nF"),
    ("t_warning", {"ctmr": 1e-6, "i_warn": 5e-6, "dv_warn": 0.1}, 20e-3, 0.001, "DS p.14, Figure 3a label tWARNING = 20 ms/uF"),
    ("t_warning", {"ctmr": 1e-6, "i_warn": -5e-6, "dv_warn": 0.1}, 20e-3, 0.001, "DS p.4 stored sign: itmr_up_warn negative, abs() gives 20 ms/uF"),
    # tol 0.01: DS label rounded to 50 uA; exact fit value 49.978 uA.
    ("itmr_up_ov_typ", {"dv": 75.0}, 50e-6, 0.01, "DS p.14, Figure 3a label ITMR = 50 uA at VCC-VOUT = 75 V"),
    # tol 0.02: DS label rounded to 8 uA; exact fit value 8.118 uA.
    ("itmr_up_ov_typ", {"dv": 10.0}, 8e-6, 0.02, "DS p.14, Figure 3a label ITMR = 8 uA at VCC-VOUT = 10 V"),
    # tol 0.01: DS label rounded to 260 uA; exact fit value 260.32 uA.
    ("itmr_up_oc_typ", {"dv": 75.0}, 260e-6, 0.01, "DS p.14, Figure 3b label ITMR = 260 uA at VCC-VOUT = 75 V"),
    # tol 0.01: DS label rounded to 42 uA; exact fit value 41.92 uA.
    ("itmr_up_oc_typ", {"dv": 10.0}, 42e-6, 0.01, "DS p.14, Figure 3b label ITMR = 42 uA at VCC-VOUT = 10 V"),
    ("t_flt", {"ctmr": 1e-6, "i_up": -50e-6, "vtmr_f": 1.25}, 25e-3, 0.001, "DS p.14, Figure 3a label tFLT = 25 ms/uF, stored negative current"),
    # tol 0.002: DS label rounded to 4.8 ms; exact 4.8077 ms.
    ("t_flt", {"ctmr": 1e-6, "i_up": 260e-6, "vtmr_f": 1.25}, 4.8e-3, 0.002, "DS p.14, Figure 3b label tFLT = 4.8 ms/uF"),
    ("t_ov", {"ctmr": 1e-6, "i_up_ov": -50e-6, "i_warn": -5e-6, "vtmr_f": 1.25, "dv_warn": 0.1}, 45e-3, 0.001, "DS p.14, Figure 3a labels tFLT 25 + tWARNING 20 = 45 ms/uF, stored negative currents"),
    # tol 0.005: the DS labels are rounded and sum to 5.18 ms; exact 5.1923 ms (1.35 V / 260 uA).
    ("t_oc", {"ctmr": 1e-6, "i_up_oc": 260e-6, "vtmr_g": 1.35}, 5.18e-3, 0.005, "DS p.14, Figure 3b labels tFLT 4.8 + tWARNING 0.38 = 5.18 ms/uF"),
    # tol 0.005: DS prints 1.15 ms (rounded); exact 1.15364 ms.
    ("t_oc", {"ctmr": 47e-9, "i_up_oc": 55e-6, "vtmr_g": 1.35}, 1.15e-3, 0.005, "DS p.19, Design Example, tOC = 1.15 ms"),
    # tol 0.01: DS prints 1.3 ms (rounded); exact 1.29490 ms.
    ("t_oc", {"ctmr": 47e-9, "i_up_oc": 49e-6, "vtmr_g": 1.35}, 1.3e-3, 0.01, "DS p.20, tOC = 1.3 ms at VOUT = 2 V (49 uA)"),
    # tol 0.02: DS prints 2.7k, rounded up from the exact 2666.67 ohm.
    ("r4_max", {"vin_min": 6.0, "vcc_min": 4.0, "icc_max": 750e-6}, 2700.0, 0.02, "DS p.19, Design Example, R4 = 2.7k"),
    # tol 0.01: DS prints 62 mA (rounded); exact 61.818 mA.
    ("i_d1_peak", {"vin_max": 200.0, "vz_min": 64.0, "r4": 2.2e3}, 62e-3, 0.01, "DS p.19, Design Example, ID1(PK) = 62 mA"),
    # tol 0.01: DS prints 45 W (rounded); exact 44.8 W.
    ("p_m1_oc", {"vds": 14.0, "dvsns": 32e-3, "rsns_ohm": 10e-3}, 45.0, 0.01, "DS p.20, Design Example, P = 45 W"),
    ("p_m1_oc", {"vds": 12.0, "dvsns": 55e-3, "rsns_ohm": 10e-3}, 66.0, 0.001, "DS p.20, Design Example, P = 66 W"),
    # tol 0.002: DS prints 45.5 mohm (rounded); exact 45.4545 mohm.
    ("rdson_m2_max", {"vfw": 0.25, "i_load_max": 5.5}, 45.5e-3, 0.002, "DS p.20, MOSFET Selection, RDS(ON) = 45.5 mohm"),
    # tol 0.005: DS prints 18.4 W^2 s (rounded); exact 18.432 W^2 s (simplified formula).
    ("p2t_simple", {"i_load": 3.0, "vpk": 80.0, "vreg_v": 16.0, "tau": 1e-3}, 18.4, 0.005, "DS p.17, Calculating Transient Stress, P2t = 18.4 W^2 s"),
    # tol 0.025: DS prints 2.2 W^2 s; exact 2.2452 W^2 s with tOC = 2.2990 ms from 100 nF and the ITMR(UP)OC typical fit at 15 V.
    ("p2t_short", {"vin": 15.0, "dvsns": 25e-3, "rsns_ohm": 12e-3, "t_oc_s": t_oc(100e-9, itmr_up_oc_typ(15.0), 1.35)}, 2.2, 0.025, "DS p.17, Short-Circuit Stress, P2t = 2.2 W^2 s"),
]
