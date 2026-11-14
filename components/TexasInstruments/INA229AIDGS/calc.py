"""INA229 datasheet equations (TI SLYS023A, Rev. A, revised May 2022). Plain floats, SI units, temperatures in degC.
Data lives in component.toml; these functions take their numbers as arguments so a worst-case engine can sweep them.
Register arguments are the integers the DS tables call "Returned Value" (two's complement where the DS says so, DS p.36).
Only equations the datasheet prints are here, except current_error, which is marked "Not a DS equation". Cites give
printed page numbers. Fractions: no function takes a percent or ppm argument (tempco is 1/degC).
"""


def current_lsb(i_max):
    """CURRENT_LSB = maximum expected current / 2^19. DS p.30, 8.1.2 Current, Power, Energy, and Charge Calculations,
    Equation 3. i_max: maximum expected current, A. Returns: CURRENT_LSB, A per count."""
    return i_max / 2 ** 19


def shunt_cal(i_lsb, rshunt, adcrange=0):
    """SHUNT_CAL = 13107.2e6 x CURRENT_LSB x RSHUNT. DS p.30, 8.1.2 Current, Power, Energy, and Charge Calculations,
    Equation 2. For ADCRANGE = 1 the value is multiplied by 4 (DS p.30, bullet under Equation 2).
    i_lsb: CURRENT_LSB, A. rshunt: shunt resistance, ohm. adcrange: 0 or 1 (CONFIG bit 4).
    Returns: SHUNT_CAL register value, unitless. The register takes an integer: round before writing.
    Checked against the DS design example (p.35, 8.2.2.3): 19.0735 uA and 16.2 mohm give 4050d."""
    if adcrange not in (0, 1):
        raise ValueError("adcrange must be 0 or 1")
    return 13107.2e6 * i_lsb * rshunt * (4 if adcrange == 1 else 1)


def rshunt_max(vsense_max, i_max):
    """RSHUNT < VSENSE_MAX / IMAX. DS p.35, 8.2.2.1 Select the Shunt Resistor, Equation 8 (strict upper bound).
    vsense_max: largest differential shunt voltage for the chosen ADC range, V (0.16384 for ADCRANGE = 0).
    i_max: maximum current to be sensed, A. Returns: upper bound on RSHUNT, ohm (not inclusive)."""
    return vsense_max / i_max


def current(i_lsb, current_reg):
    """Current [A] = CURRENT_LSB x CURRENT. DS p.30, 8.1.2 Current, Power, Energy, and Charge Calculations, Equation 4.
    i_lsb: CURRENT_LSB, A. current_reg: CURRENT register, signed integer. Returns: current, A (signed)."""
    return i_lsb * current_reg


def power(i_lsb, power_reg):
    """Power [W] = 3.2 x CURRENT_LSB x POWER. DS p.30, 8.1.2 Current, Power, Energy, and Charge Calculations, Equation 5.
    i_lsb: CURRENT_LSB, A. power_reg: POWER register, unsigned integer. Returns: power, W."""
    return 3.2 * i_lsb * power_reg


def energy(i_lsb, energy_reg):
    """Energy [J] = 16 x 3.2 x CURRENT_LSB x ENERGY. DS p.30, 8.1.2 Current, Power, Energy, and Charge Calculations,
    Equation 6. i_lsb: CURRENT_LSB, A. energy_reg: ENERGY register, unsigned integer. Returns: energy, J."""
    return 16 * 3.2 * i_lsb * energy_reg


def charge(i_lsb, charge_reg):
    """Charge [C] = CURRENT_LSB x CHARGE. DS p.31, 8.1.2 Current, Power, Energy, and Charge Calculations, Equation 7.
    i_lsb: CURRENT_LSB, A. charge_reg: CHARGE register, signed integer. Returns: charge, C (signed)."""
    return i_lsb * charge_reg


def shunt_voltage(vshunt_reg, lsb):
    """V_SHUNT = VSHUNT x LSB. DS p.29, 8.1.1 Device Measurement Range and Resolution ("multiplying the digital value
    by its respective resolution size"); LSB from DS p.23, Table 7-9 (312.5 nV/LSB for ADCRANGE = 0, 78.125 nV/LSB
    for ADCRANGE = 1). vshunt_reg: VSHUNT register, signed integer. lsb: V per count. Returns: voltage, V (signed)."""
    return vshunt_reg * lsb


def bus_voltage(vbus_reg, lsb):
    """V_BUS = VBUS x LSB. DS p.29, 8.1.1 Device Measurement Range and Resolution; LSB from DS p.23, Table 7-10
    (195.3125 uV/LSB). vbus_reg: VBUS register, unsigned in practice (always positive, DS p.23).
    lsb: V per count. Returns: voltage, V."""
    return vbus_reg * lsb


def die_temperature(dietemp_reg, lsb):
    """T_DIE = DIETEMP x LSB. DS p.29, 8.1.1 Device Measurement Range and Resolution; LSB from DS p.24, Table 7-11
    (7.8125 m degC/LSB). dietemp_reg: DIETEMP register, signed integer. lsb: degC per count.
    Returns: die temperature, degC (signed)."""
    return dietemp_reg * lsb


def shunt_tempco_radj(rnom, dietemp, tempco):
    """RADJ = RNOM x (1 + TEMPCO x (DIETEMP - 25)). DS p.16, 7.3.5 Shunt Resistor Drift Compensation, Equation 1
    (printed as RNOM + RNOM x (DIETEMP - 25) x SHUNT_TEMPCO / 10^6). Algebra on Equation 1: tempco = SHUNT_TEMPCO / 10^6,
    in 1/degC (the register value in ppm/degC divided by 1e6).
    rnom: shunt resistance at 25 degC, ohm. dietemp: die temperature, degC. tempco: shunt temperature coefficient, 1/degC.
    Returns: compensated shunt resistance, ohm. Assumes TEMPCO bit in CONFIG is set (DS p.16)."""
    return rnom * (1 + tempco * (dietemp - 25))


def current_error(i_true, rshunt, vos25, vos_drift, gserr, gs_drift, t_c):
    """Not a DS equation: measured-current error from shunt offset and shunt gain error, at temperature t_c.
    The DS prints the terms (Vos and dVos/dT, GSERR and GS_DRFT, p.5) and the current scaling (Equations 2 and 4, p.30),
    but not their combination. Derivation: the CURRENT register reports the shunt voltage divided by RSHUNT (the
    calibration of Equation 2 sets that scale). With V_true = i_true x rshunt, the measured shunt voltage is
    V_true x (1 + g) + vos, where (SPEC temperature recipe, step 2: X(T) = X25 + drift x (T - 25)):
        g(T)   = gserr + gs_drift x (T - 25)     gserr: GSERR row, gs_drift: GS_DRFT row (DS p.5)
        vos(T) = vos25 + vos_drift x (T - 25)    vos25: Vos row (DS p.5), vos_drift: dVos/dT row (DS p.5)
    so the measured current minus the true current is i_true x g(T) + vos(T) / rshunt.
    Bilinear in (gs_drift, t_c) and (vos_drift, t_c), so the wca corners are exact. Pass t_c as Param(min=-40, max=125).
    i_true: true current, A, signed. rshunt: shunt resistance, ohm (pass with its tolerance). vos25: V, signed.
    vos_drift: V/degC, signed. gserr: fraction, signed. gs_drift: 1/degC, signed. t_c: degC.
    Partial budget: excludes CMRR, PSRR, INL, 1-LSB quantisation and SHUNT_CAL integer rounding.
    Returns: current error, A, signed (positive = reads high)."""
    g = gserr + gs_drift * (t_c - 25)
    vos = vos25 + vos_drift * (t_c - 25)
    return i_true * g + vos / rshunt


EXAMPLES = [
    # (function, kwargs, expected, relative tolerance (absolute if expected == 0), cite)
    ("current_lsb", {"i_max": 10.0}, 19.073486e-6, 1e-6,
     "DS p.36, Table 8-4, Current LSB 10 A / 2^19 = 19.073486 uA/LSB"),
    ("rshunt_max", {"vsense_max": 0.16384, "i_max": 10.0}, 16.38e-3, 1e-3,
     "DS p.35, 8.2.2.1, Equation 8: RSHUNT max 16.38 mohm. The DS prints 16.38 (rounded); exact 16.384 mohm, 2.4e-4 high"),
    ("shunt_cal", {"i_lsb": 10.0 / 2 ** 19, "rshunt": 16.2e-3}, 4050, 1e-3,
     "DS p.35, 8.2.2.3, SHUNT_CAL = 4050d (FD2h) for 10 A design, 16.2 mohm shunt"),
    ("shunt_cal", {"i_lsb": 10.0 / 2 ** 19, "rshunt": 16.2e-3, "adcrange": 1}, 16200, 1e-3,
     "DS p.30, Equation 2 bullet: x4 for ADCRANGE = 1 (4 x 4050)"),
    ("current", {"i_lsb": 19.073486e-6, "current_reg": 314572}, 6.0, 1e-3,
     "DS p.36, Table 8-4, Current 314572d -> 6 A"),
    ("power", {"i_lsb": 19.073486e-6, "power_reg": 4718604}, 288.0, 1e-3,
     "DS p.36, Table 8-4, Power 4718604d -> 288 W"),
    ("energy", {"i_lsb": 19.073486e-6, "energy_reg": 1061683200}, 1036800.0, 1e-3,
     "DS p.36, Table 8-4, Energy 1061683200d -> 1036800 J"),
    ("charge", {"i_lsb": 19.073486e-6, "charge_reg": 1132462080}, 21600.0, 1e-3,
     "DS p.36, Table 8-4, Charge 1132462080d -> 21600 C"),
    ("shunt_voltage", {"vshunt_reg": 311040, "lsb": 312.5e-9}, 0.0972, 1e-3,
     "DS p.36, Table 8-4, Shunt voltage 311040d -> 0.0972 V"),
    ("bus_voltage", {"vbus_reg": 245760, "lsb": 195.3125e-6}, 48.0, 1e-3,
     "DS p.36, Table 8-4, Bus voltage 245760d -> 48 V"),
    ("die_temperature", {"dietemp_reg": 3200, "lsb": 0.0078125}, 25.0, 1e-3,
     "DS p.36, Table 8-4, Temperature 3200d -> 25 degC"),
    ("shunt_tempco_radj", {"rnom": 0.0162, "dietemp": 25.0, "tempco": 100e-6}, 0.0162, 1e-9,
     "DS p.16, Equation 1 at DIETEMP = 25 degC (reference temperature): RADJ = RNOM"),
    ("current_error", {"i_true": 10.0, "rshunt": 0.0162, "vos25": 0.0, "vos_drift": 0.0,
                       "gserr": 0.0, "gs_drift": 0.0, "t_c": 25.0}, 0.0, 1e-12,
     "Not a DS equation: zero offset, gain error and drift give zero error"),
    ("current_error", {"i_true": 10.0, "rshunt": 0.0162, "vos25": 0.0, "vos_drift": 0.0,
                       "gserr": 0.0005, "gs_drift": 0.0, "t_c": 25.0}, 0.005, 1e-3,
     "Not a DS equation: GSERR MAX 0.05 % on 10 A = 5 mA (DS p.5)"),
    ("current_error", {"i_true": 0.0, "rshunt": 0.0162, "vos25": 1e-6, "vos_drift": 0.0,
                       "gserr": 0.0, "gs_drift": 0.0, "t_c": 25.0}, 1e-6 / 0.0162, 1e-3,
     "Not a DS equation: Vos MAX 1 uV over 16.2 mohm = 61.7 uA (DS p.5)"),
]

INPUTS = {
    # function: {argument: component.toml param key}. Design choices (i_lsb, rshunt, i_max, register values) are not listed.
    "current_lsb": {},
    "shunt_cal": {},
    "rshunt_max": {},
    "current": {},
    "power": {},
    "energy": {},
    "charge": {},
    # ADCRANGE = 0 LSB. For ADCRANGE = 1 use lsb_vshunt_adcr1_25c.typ.
    "shunt_voltage": {"lsb": "lsb_vshunt_adcr0_25c.typ"},
    "bus_voltage": {"lsb": "lsb_vbus_25c.typ"},
    "die_temperature": {"lsb": "lsb_temp_25c.typ"},
    "shunt_tempco_radj": {},
    # VCM = 48 V offset row. For VCM = 0 V use vos_vcm0_25c.
    "current_error": {"vos25": "vos_vcm48_25c", "vos_drift": "vos_drift_full",
                      "gserr": "gserr_25c", "gs_drift": "gs_drift_25c"},
}
