"""STM32H723ZET6 (LQFP144) datasheet equations, DS13313 Rev 5.

DS: docs/datasheets/stm32h723ze.pdf. Printed page numbers are cited. Units: V, A, W, degC, degC/W.
Arguments are plain floats in SI units (V, A, degC, W). INPUTS maps each function's arguments to the
component.toml param key that supplies them. Design choices (currents, load, output levels) are not mapped.
Only the math module is imported.
"""

import math


def tj_max(ta, pd, theta_ja):
    """TJmax = TA + PD x theta_JA. DS p.228, Section 7.6 Thermal characteristics (equation).
    ta: ambient temperature, degC (TA max for the grade). pd: total power dissipation PD = PINT + PI/O, W.
    theta_ja: junction-to-ambient thermal resistance, degC/W (Table 127, LQFP144). Returns: junction temperature, degC.
    INPUTS: ta -> ta_range6_max_power.max (85 degC); theta_ja -> theta_ja_lqfp144.max (44.8 degC/W).
    The DS gives TA and PD as maxima; the caller passes the worst-case values."""
    return ta + pd * theta_ja


def p_int(idd, vdd):
    """PINT = IDD x VDD. DS p.228, Section 7.6 Thermal characteristics: 'PINT max is the product of IDD and VDD'.
    idd: supply current into the chip, A. vdd: supply voltage, V. Returns: power, W.
    INPUTS: vdd -> vdd_op.max (3.6 V)."""
    return idd * vdd


def p_io_ol(vol, iol):
    """One output pin term of PI/O max, low level: VOL x IOL. DS p.228, Section 7.6, PI/O max equation (first sum).
    Sum this over all outputs at low level. vol: V. iol: A. Returns: W. INPUTS: none (operating point of the design)."""
    return vol * iol


def p_io_oh(vdd, voh, ioh):
    """One output pin term of PI/O max, high level: (VDD - VOH) x IOH. DS p.228, Section 7.6, PI/O max equation (second sum).
    Sum this over all outputs at high level. vdd: V. voh: V. ioh: A (magnitude). Returns: W.
    INPUTS: vdd -> vdd_op.max."""
    return (vdd - voh) * ioh


def vin_ft_max(vdd, vdda, vdd33usb, vbat):
    """VIN max on FT_xxx pins = Min(Min(VDD, VDDA, VDD33USB, VBAT) + 4.0, 6 V). DS p.88, Table 9 (formula, notes 3, 4, 5).
    The 4.0 V offset and 6 V cap are as printed. The result is only valid for the supplies related to the pin's IO structure
    (DS note 3); pull-ups/pull-downs must be disabled to reach it (note 4). vdd, vdda, vdd33usb, vbat: V.
    Returns: V. INPUTS: vdd -> vdd_op, vdda -> vdda_op_adc, vdd33usb -> vdd33usb_op_nousb, vbat -> vbat_op.
    Whole rows: the limit grows with the supply, so the worst-case bound is the result min (lowest supply; VDD33USB = 0 V when USB is unused gives 0 + offset)."""
    return min(min(vdd, vdda, vdd33usb, vbat) + 4.0, 6.0)


def vin_tt_max(vdd):
    """VIN max on TT_xx I/O (except Pxy_C) = VDD + 0.3 V. DS p.90, Table 12, I/O input voltage row TT_xx I/O except Pxy_C.
    vdd: V. Returns: V. INPUTS: vdd -> vdd_op.
    Whole rows: the limit grows with the supply, so the worst-case bound is the result min (lowest supply)."""
    return vdd + 0.3


def vin_pxyc_max(vdda, vdd):
    """VIN max on Pxy_C I/O = Min(VDDA, VDD) + 0.3 V. DS p.90, Table 12, I/O input voltage row Pxy_C I/O.
    vdda, vdd: V. Returns: V. INPUTS: vdda -> vdda_op_adc, vdd -> vdd_op.
    Whole rows: the limit grows with the supply, so the worst-case bound is the result min (lowest supply)."""
    return min(vdda, vdd) + 0.3


def vin_io_max(vdd, vdda, vdd33usb):
    """VIN max on all I/Os except BOOT0, TT_xx and Pxy_C = Min(Min(VDD, VDDA, VDD33USB) + 3.6, 5.5 V). DS p.90, Table 12,
    footnote 3 (formula; the 5.5 V cap is as printed). vdd, vdda, vdd33usb: V. Returns: V.
    INPUTS: vdd -> vdd_op, vdda -> vdda_op_adc, vdd33usb -> vdd33usb_op_nousb.
    Whole rows: the limit grows with the supply, so the worst-case bound is the result min (lowest supply; VDD33USB = 0 V when USB is unused gives 0 + offset)."""
    return min(min(vdd, vdda, vdd33usb) + 3.6, 5.5)


# ---- Clocks, PLL, flash, supply current (DS 6.3.7-6.3.12) ----


def hsi48_delta_f(acc_rel, dvdd):
    """Delta f_HSI = ACCHSI48_REL + Delta VDD(HSI48). DS p.115, Table 35, footnote 4 (repeated as footnote 5, DS p.116).
    acc_rel: ACCHSI48_REL, fraction (signed). dvdd: Delta VDD(HSI48), fraction (magnitude; worst sign taken by wca).
    Returns: relative frequency error of HSI48, fraction (signed)."""
    return acc_rel + dvdd


def hsi48_freq_worst(acc_rel, dvdd):
    """Not a DS equation: f_HSI48 = 48 MHz x (1 + Delta f_HSI). The DS defines Delta f_HSI in Table 35 footnote 4
    (DS p.115) and gives f_HSI48 = 48 MHz as the nominal (Table 35, row fHSI48 Typ). Combines hsi48_delta_f with the
    nominal frequency.
    acc_rel: ACCHSI48_REL, fraction. dvdd: Delta VDD(HSI48), fraction. Returns: HSI48 frequency, Hz."""
    return 48e6 * (1 + hsi48_delta_f(acc_rel, dvdd))


def vdd_drift(f_hi, f_ref):
    """Delta VDD = (Freq(3.6 V) - Freq(3.0 V)) / Freq(3.0 V), or (Freq(3.6 V) - Freq(1.62 V)) / Freq(1.62 V).
    DS p.116, Table 35, footnote 6 (HSI48 oscillator frequency drift with VDD; the reference is 3.3 V).
    f_hi: frequency at the upper supply voltage, Hz. f_ref: frequency at the lower supply voltage, Hz.
    Returns: fraction (signed)."""
    return (f_hi - f_ref) / f_ref


def io_switching_current(vdd, fsw, cl):
    """I_SW = VDDx x fSW x CL. DS p.103, 6.3.7 Supply current characteristics, I/O dynamic current consumption (equation
    as printed; the DS gives it without a number).
    vdd: MCU supply voltage, V. fsw: I/O switching frequency, Hz. cl: total capacitance seen by the pin (C_INT + C_EXT), F.
    Returns: current sunk by the switching I/O, A."""
    return vdd * fsw * cl


def periph_current(a_per_hz, f_hz):
    """Not a DS equation: I_peripheral = (value in uA/MHz) x fCK in MHz. DS p.104, Table 29 prints the per-MHz value
    (uA/MHz) at TA = 25 degC, VDD = 3.3 V; the current is the per-MHz value multiplied by the clock frequency.
    a_per_hz: Table 29 value converted to A/Hz (uA/MHz = 1e-6 A per 1e6 Hz = 1e-12 A/Hz). f_hz: CPU clock f_rcc_c_ck, Hz (DS p.104: Table 29 values are per MHz of the CPU clock, with fHCLK = CPU/2 and fPCLK = CPU/4; passing the bus clock under-states the current).
    Returns: peripheral supply current, A (typ only)."""
    return a_per_hz * f_hz


def crystal_load_cap(c1, c2, cstray):
    """Not a DS equation: C_L = C1 x C2 / (C1 + C2) + C_stray. Series combination of the two load capacitors on the
    crystal (DS p.113 Figure 15 and DS p.114 Figure 16 show the CL1/CL2 network without a formula), plus stray capacitance.
    The DS uses CL = 10 pF as the Table 33 test condition; the formula is the standard series relation, not printed.
    c1, c2: load capacitors on OSC_IN and OSC_OUT, F. cstray: board and pin stray capacitance, F.
    Returns: effective load capacitance, F."""
    return c1 * c2 / (c1 + c2) + cstray


def gm_margin(gm_crit_crystal, gm_critmax):
    """Not a DS equation: oscillator gain margin = Gm_critmax / gm_crit of the crystal. The DS (DS p.113, Table 33,
    Gm_critmax, "Maximum critical crystal gm") gives the oscillator's capability: the largest critical gm of a crystal
    it can start. The crystal's own gm_crit is a design input computed from its ESR, C0 and CL (ST AN2867:
    gm_crit = 4 x ESR x (2 x pi x F)^2 x (C0 + CL)^2; not in the DS). The crystal is usable when the result is >= 1;
    the DS prints no recommended margin.
    gm_crit_crystal: A/V (design input). gm_critmax: A/V (DS prints mA/V; loaded from the param).
    Returns: dimensionless margin."""
    return gm_critmax / gm_crit_crystal


# ---- I/O ports, NRST, injection, EMC (DS 6.3.13-6.3.17) ----


def vil_cmos_max(vdd):
    """VIL (I/O input low, except BOOT0, CMOS requirement) = 0.3 x VDD.
    DS p.126, 6.3.16 I/O port characteristics, Table 51. I/O static characteristics, VIL row 1 (footnote 1).
    vdd: VDD supply, V. Returns: V."""
    return 0.3 * vdd


def vil_max(vdd):
    """VIL (I/O input low, except BOOT0, 1.62 V < VDD < 3.6 V) = 0.4 x VDD - 0.1.
    DS p.126, 6.3.16 I/O port characteristics, Table 51. I/O static characteristics, VIL row 2 (footnote 2).
    vdd: VDD supply, V. Returns: V."""
    return 0.4 * vdd - 0.1


def vil_boot0_max(vdd):
    """VIL (BOOT0 I/O input low) = 0.19 x VDD + 0.1.
    DS p.126, 6.3.16 I/O port characteristics, Table 51. I/O static characteristics, VIL row 3 (footnote 2).
    vdd: VDD supply, V. Returns: V."""
    return 0.19 * vdd + 0.1


def vih_cmos_min(vdd):
    """VIH (I/O input high, except BOOT0 and Pxy_C; also Pxy_C with footnote 3) = 0.7 x VDD.
    DS p.126, 6.3.16 I/O port characteristics, Table 51. I/O static characteristics, VIH rows 1 and 2.
    vdd: VDD supply, V. Returns: V."""
    return 0.7 * vdd


def vih_min(vdd):
    """VIH (I/O input high, except BOOT0, footnote 2) = 0.47 x VDD + 0.25.
    DS p.126, 6.3.16 I/O port characteristics, Table 51. I/O static characteristics, VIH row 3.
    vdd: VDD supply, V. Returns: V."""
    return 0.47 * vdd + 0.25


def vih_boot0_min(vdd):
    """VIH (BOOT0 I/O input high) = 0.17 x VDD + 0.6.
    DS p.126, 6.3.16 I/O port characteristics, Table 51. I/O static characteristics, VIH row 4.
    vdd: VDD supply, V. Returns: V."""
    return 0.17 * vdd + 0.6


def voh_cmos_min(vdd):
    """VOH (CMOS port, IIO = -8 mA or -4 mA) = VDD - 0.4.
    DS p.129, 6.3.16 I/O port characteristics, Table 52. Output voltage characteristics, CMOS VOH rows.
    vdd: VDD supply, V. Returns: V (minimum output high voltage)."""
    return vdd - 0.4


def voh_20ma_min(vdd):
    """VOH (IIO = -20 mA, 2.7 V <= VDD <= 3.6 V) = VDD - 1.3.
    DS p.129, 6.3.16 I/O port characteristics, Table 52. Output voltage characteristics, VOH IIO = -20 mA row.
    vdd: VDD supply, V. Returns: V (minimum output high voltage)."""
    return vdd - 1.3


def voh_pxyc_min(vdd, vdda):
    """VOH (Pxy_C pins, IIO = 1 mA) = Min(VDD - 0.4, VDDA + 0.3).
    DS p.129, 6.3.16 I/O port characteristics, Table 52. Output voltage characteristics, Pxy_C VOH row (footnote 4).
    vdd: VDD supply, V. vdda: analog supply VDDA, V. Returns: V (minimum output high voltage)."""
    return min(vdd - 0.4, vdda + 0.3)


def pad_leakage_total_max(n_io, ilkg_max):
    """Total product pad leakage, maximum: ITotal_Ieak_max = 10 uA + n_io x Ilkg(max).
    DS p.127, 6.3.16 I/O port characteristics, Table 51 footnote 4.
    n_io: number of I/Os where VIN is applied (count, design choice). ilkg_max: Ilkg(max) of one I/O, A.
    Returns: A. INPUTS maps ilkg_max to the largest printed row (FT_u, VIN above the supplies, 5000 nA), which is
    conservative; for pads inside the supply range use the in-range row of the pad type (250 or 350 nA)."""
    return 10e-6 + n_io * ilkg_max


def nrst_pulse_class(width, vf_max, vnf_min):
    """Not a DS equation: classifies an NRST low pulse against the printed Table 57 limits.
    A pulse no longer than vf_max (DS p.134, VF(NRST) max) is filtered; a pulse no shorter than vnf_min
    (DS p.134, VNF(NRST) min, 1.62 V < VDD < 3.6 V row, 1000 ns; the 1.71 V row is 350 ns) is not filtered; between them is undefined.
    width: pulse width, s. vf_max: s. vnf_min: s. Returns: "filtered", "not_filtered" or "undefined"."""
    if width <= vf_max:
        return "filtered"
    if width >= vnf_min:
        return "not_filtered"
    return "undefined"


# ---- Analog: ADC, DAC, VREFBUF, sensors, COMP, OPAMP (DS 6.3.21-6.3.30) ----


def adc16_tconv_s(ts_cycles, n_bits, f_adc):
    """Total conversion time, 16-bit ADC: tCONV = (ts + 0.5 + N/2) / fADC.
    DS p.164, Table 80. 16-bit ADC characteristics, tCONV: printed as "ts + 0.5 + N/2" in 1/fADC.
    ts_cycles: sampling time, ADC clock cycles (dimensionless count).
    n_bits: ADC resolution N, bits.
    f_adc: ADC clock frequency, Hz.
    Returns: conversion time, s.
    """
    return (ts_cycles + 0.5 + n_bits / 2.0) / f_adc


def adc12_tconv_s(ts_cycles, n_bits, f_adc):
    """Total conversion time, 12-bit ADC: tCONV = (ts + 0.5 + N) / fADC.
    DS p.173, Table 83. 12-bit ADC characteristics, tCONV: printed as "ts + 0.5 + N" in 1/fADC.
    ts_cycles: sampling time, ADC clock cycles (dimensionless count).
    n_bits: ADC resolution N, bits.
    f_adc: ADC clock frequency, Hz.
    Returns: conversion time, s.
    """
    return (ts_cycles + 0.5 + n_bits) / f_adc


def opamp_pga_gain_noninv(r2, r1):
    """Non-inverting PGA gain: G = 1 + R2/R1.
    DS p.187, Table 97. Operational amplifier characteristics (continued), footnote 3: "PGA gain = 1 + R2/R1".
    r2: internal feedback resistance, ohm. r1: internal resistance to ground, ohm. Returns: gain, V/V.
    """
    return 1.0 + r2 / r1


def opamp_pga_gain_inv(r2, r1):
    """Inverting PGA gain: G = -R2/R1.
    Not a DS equation: DS p.187 Table 97 prints only the R2/R1 values for inverting gains -1, -3, -7, -15 (footnote 3
    defines R2 and R1 but prints no inverting formula). The sign follows from the inverting topology: the printed
    R2/R1 values 10/10, 30/10, 70/10, 150/10 give gains -1, -3, -7, -15 with this relation.
    r2: internal feedback resistance, ohm. r1: internal resistance to ground, ohm. Returns: gain, V/V (negative).
    """
    return -r2 / r1


EXAMPLES = [
    # (function, kwargs, expected, tolerance, cite). Expected values are the arithmetic of the printed formula and caps.
    ("vin_ft_max", {"vdd": 1.62, "vdda": 1.62, "vdd33usb": 1.62, "vbat": 1.62}, 5.62, 1e-9,
     "DS p.88, Table 9, VIN FT_xxx formula with all supplies at 1.62 V (4.0 V offset, below the 6 V cap)"),
    ("vin_ft_max", {"vdd": 3.6, "vdda": 3.6, "vdd33usb": 3.6, "vbat": 3.6}, 6.0, 1e-9,
     "DS p.88, Table 9, VIN FT_xxx formula, 6 V cap reached at 3.6 V supplies"),
    ("vin_tt_max", {"vdd": 3.6}, 3.9, 1e-9, "DS p.90, Table 12, VDD + 0.3 V at VDD = 3.6 V"),
    ("vin_io_max", {"vdd": 3.6, "vdda": 3.6, "vdd33usb": 3.6}, 5.5, 1e-9,
     "DS p.90, Table 12 footnote 3: 3.6 V offset plus 3.6 V supplies reaches the 5.5 V cap"),
    ("vin_pxyc_max", {"vdda": 3.6, "vdd": 3.6}, 3.9, 1e-9, "DS p.90, Table 12, Min(VDDA, VDD) + 0.3 V at 3.6 V"),
    ("tj_max", {"ta": 85.0, "pd": 0.0, "theta_ja": 44.8}, 85.0, 1e-9,
     "DS p.228, Section 7.6: with PD = 0 the junction equals the ambient maximum"),
    # ---- Clocks, PLL, flash, supply current (DS 6.3.7-6.3.12) ----
    # (function, kwargs, expected, tolerance, cite). Arithmetic checks on printed numbers where the DS prints no example.
    ("hsi48_delta_f", {"acc_rel": 0.035, "dvdd": 0.001}, 0.036, 1e-9,
     "DS p.115, Table 35 footnote 4 (arithmetic check on printed max values 3.5 % and 0.1 %)"),
    ("hsi48_delta_f", {"acc_rel": -0.045, "dvdd": 0.0005}, -0.0445, 1e-9,
     "DS p.115, Table 35 (arithmetic check on printed min -4.5 % and typ 0.05 %)"),
    ("hsi48_freq_worst", {"acc_rel": 0.035, "dvdd": 0.001}, 49.728e6, 1e-9,
     "DS p.115, Table 35 footnote 4 (arithmetic check: 48 MHz x 1.036)"),
    ("vdd_drift", {"f_hi": 48.024e6, "f_ref": 48e6}, 0.0005, 1e-6,
     "DS p.116, Table 35 footnote 6 (arithmetic check; no DS example printed)"),
    ("io_switching_current", {"vdd": 3.3, "fsw": 1e6, "cl": 10e-12}, 3.3e-5, 1e-9,
     "DS p.103, I/O dynamic current consumption (arithmetic check; no DS example printed)"),
    ("periph_current", {"a_per_hz": 3.70e-12, "f_hz": 550e6}, 2.035e-3, 1e-9,
     "DS p.104, Table 29, MDMA VOS0 3.70 uA/MHz at fCK 550 MHz (arithmetic check)"),
    ("crystal_load_cap", {"c1": 20e-12, "c2": 20e-12, "cstray": 2e-12}, 12e-12, 1e-9,
     "Not a DS equation: series load capacitance check (20 pF, 20 pF, 2 pF stray = 12 pF)"),
    ("gm_margin", {"gm_crit_crystal": 0.3e-3, "gm_critmax": 1.5e-3}, 5.0, 1e-9,
     "DS p.113, Table 33 Gm_critmax 1.5 mA/V (arithmetic check; gm_crit_crystal is an example value)"),
    # ---- I/O ports, NRST, injection, EMC (DS 6.3.13-6.3.17) ----
    # (function, kwargs, expected, tolerance, cite)
    # VIL/VIH/VOH formulas at VDD = 3.3 V (arithmetic of the printed coefficients; the DS prints no worked value).
    ("vil_max", {"vdd": 3.3}, 1.22, 1e-9, "DS p.126, Table 51, VIL 0.4 x VDD - 0.1 at VDD = 3.3 V"),
    ("vih_min", {"vdd": 3.3}, 1.8010, 1e-9, "DS p.126, Table 51, VIH 0.47 x VDD + 0.25 at VDD = 3.3 V"),
    ("voh_cmos_min", {"vdd": 3.3}, 2.9, 1e-9, "DS p.129, Table 52, VOH VDD - 0.4 at VDD = 3.3 V"),
    ("pad_leakage_total_max", {"n_io": 0, "ilkg_max": 0.0}, 10e-6, 1e-3,
     "DS p.127, Table 51 footnote 4: 10 uA constant term"),
    # ---- Analog: ADC, DAC, VREFBUF, sensors, COMP, OPAMP (DS 6.3.21-6.3.30) ----
    # (function, kwargs, expected, tolerance, cite). Formula evaluated with DS-printed relation; no DS-printed number.
    ("adc16_tconv_s", {"ts_cycles": 2.5, "n_bits": 16, "f_adc": 25e6}, 4.4e-7, 1e-9,
     "DS p.164, Table 80 tCONV formula, evaluated: (2.5 + 0.5 + 8) / 25 MHz"),
    ("adc12_tconv_s", {"ts_cycles": 2.5, "n_bits": 12, "f_adc": 25e6}, 6.0e-7, 1e-9,
     "DS p.173, Table 83 tCONV formula, evaluated: (2.5 + 0.5 + 12) / 25 MHz"),
    ("opamp_pga_gain_noninv", {"r2": 10e3, "r1": 10e3}, 2.0, 1e-9, "DS p.187, Table 97 footnote 3, PGA gain = 2 (R2/R1 = 10/10)"),
    ("opamp_pga_gain_noninv", {"r2": 30e3, "r1": 10e3}, 4.0, 1e-9, "DS p.187, Table 97 footnote 3, PGA gain = 4 (R2/R1 = 30/10)"),
    ("opamp_pga_gain_noninv", {"r2": 150e3, "r1": 10e3}, 16.0, 1e-9, "DS p.187, Table 97 footnote 3, PGA gain = 16 (R2/R1 = 150/10)"),
    ("opamp_pga_gain_inv", {"r2": 10e3, "r1": 10e3}, -1.0, 1e-9, "DS p.187, Table 97 R2/R1 inverting, PGA gain = -1 (10/10)"),
    ("opamp_pga_gain_inv", {"r2": 30e3, "r1": 10e3}, -3.0, 1e-9, "DS p.187, Table 97 R2/R1 inverting, PGA gain = -3 (30/10)"),
    ("opamp_pga_gain_inv", {"r2": 150e3, "r1": 10e3}, -15.0, 1e-9, "DS p.187, Table 97 R2/R1 inverting, PGA gain = -15 (150/10)"),
]

INPUTS = {
    "tj_max": {"ta": "ta_range6_max_power.max", "theta_ja": "theta_ja_lqfp144.max"},
    "p_int": {"vdd": "vdd_op.max"},
    "p_io_ol": {},
    "p_io_oh": {"vdd": "vdd_op.max"},
    "vin_ft_max": {"vdd": "vdd_op", "vdda": "vdda_op_adc",
                   "vdd33usb": "vdd33usb_op_nousb", "vbat": "vbat_op"},
    "vin_tt_max": {"vdd": "vdd_op"},
    "vin_pxyc_max": {"vdda": "vdda_op_adc", "vdd": "vdd_op"},
    "vin_io_max": {"vdd": "vdd_op", "vdda": "vdda_op_adc", "vdd33usb": "vdd33usb_op_nousb"},
    # ---- Clocks, PLL, flash, supply current (DS 6.3.7-6.3.12) ----
    # function: {argument: param key}; "key" passes the whole Param (wca sweeps min and max), "key.max" one number.
    "hsi48_delta_f": {"acc_rel": "hsi48_accuracy", "dvdd": "hsi48_dvdd_1v62_3v6"},
    "hsi48_freq_worst": {"acc_rel": "hsi48_accuracy", "dvdd": "hsi48_dvdd_1v62_3v6"},
    "vdd_drift": {},
    "io_switching_current": {},
    "periph_current": {},
    "crystal_load_cap": {},
    "gm_margin": {"gm_critmax": "hse_xtal_gm_critmax.max"},  # gm_crit_crystal is a design input
    # ---- I/O ports, NRST, injection, EMC (DS 6.3.13-6.3.17) ----
    # function: {argument: param key}; "vdd_op" and "vdda_op_adc" are the VDD / VDDA rows of Table 12 (evaluate at the design VDD: the wca range over 1.62-3.6 V is for plotting, not a bound)
    "vil_cmos_max": {"vdd": "vdd_op"},
    "vil_max": {"vdd": "vdd_op"},
    "vil_boot0_max": {"vdd": "vdd_op"},
    "vih_cmos_min": {"vdd": "vdd_op"},
    "vih_min": {"vdd": "vdd_op"},
    "vih_boot0_min": {"vdd": "vdd_op"},
    "voh_cmos_min": {"vdd": "vdd_op"},
    "voh_20ma_min": {"vdd": "vdd_op"},
    "voh_pxyc_min": {"vdd": "vdd_op", "vdda": "vdda_op_adc"},
    "pad_leakage_total_max": {"ilkg_max": "io_ilkg_ft_u_above_vdd.max"},
    "nrst_pulse_class": {"vf_max": "nrst_vf_filtered.max", "vnf_min": "nrst_vnf_lo.min"},  # 1000 ns row (1.62 V < VDD): conservative
    # ---- Analog: ADC, DAC, VREFBUF, sensors, COMP, OPAMP (DS 6.3.21-6.3.30) ----
    # function: {argument: param key}. Design choices (n_bits, resistor values) are not listed.
    # Worst-case conversion time: longest sampling time and the lowest ADC clock in BOOST = 11.
    "adc16_tconv_s": {"ts_cycles": "adc16_ts.max", "f_adc": "adc16_fadc_boost11.min"},
    "adc12_tconv_s": {"ts_cycles": "adc12_ts.max", "f_adc": "adc12_fadc.min"},
    "opamp_pga_gain_noninv": {},
    "opamp_pga_gain_inv": {},
}
