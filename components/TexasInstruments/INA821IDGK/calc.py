"""INA821 datasheet equations (TI SBOS893D, Rev. D, June 2020). Plain floats, SI units, temperatures in degC.
Fractions: gain_err is a plain fraction (0.025 % = 0.00025) and gain_drift is 1/degC (1 ppm/degC = 1e-6 /degC).
The loader converts % and ppm/degC from component.toml; no function here takes a percent or ppm argument.
Data lives in component.toml; these functions take their parameters as arguments so a worst-case engine can sweep them.
Only equations the datasheet states are here (cites give printed page numbers). Algebra on a stated equation is marked.
"""


def gain(rg):
    """G = 1 + 49.4 kohm / RG. DS p.20, 8.3.1 Setting the Gain, Equation 1.
    rg: gain resistor between the RG pins (pins 2 and 3), ohm. Returns: gain G, V/V (unitless)."""
    return 1 + 49.4e3 / rg


def rg_for_gain(g):
    """RG = 49.4 kohm / (G - 1). Algebra on DS p.20, Equation 1 (the DS prints Equation 1 only, not this form).
    g: target gain, V/V, must be > 1 (G = 1 is RG open, DS p.20 Table 2 NC). Returns: RG, ohm.
    Ideal value; the nearest standard resistor changes the gain (DS p.20 Table 2 gives both)."""
    return 49.4e3 / (g - 1)


def vos_rti(vosi, voso, g):
    """VOS(RTI) = VOSI + VOSO / G. DS p.6, 7.5 Electrical Characteristics, footnote (1).
    vosi: input stage offset voltage, V, signed (sym param: magnitude bound). voso: output stage offset voltage, V,
    signed (sym param). g: gain, V/V. Returns: total offset referred to input, V, signed."""
    return vosi + voso / g


def dvos_rti(dvosi, dvoso, g):
    """dVOS(RTI) = sqrt(dVOSI^2 + (dVOSO / G)^2). DS p.6, 7.5 Electrical Characteristics, footnote (2)
    (offset drifts are uncorrelated). dvosi, dvoso: offset drifts, V/degC (magnitudes; the square makes sign irrelevant).
    g: gain, V/V. Returns: V/degC."""
    return (dvosi ** 2 + (dvoso / g) ** 2) ** 0.5


def en_rti(eni, eno, g):
    """eN(RTI) = sqrt(eNI^2 + (eNO / G)^2). DS p.6, 7.5 Electrical Characteristics, footnote (5).
    eni: input stage voltage noise, V/rtHz (or Vpp, as printed for the row). eno: output stage voltage noise, same unit.
    g: gain, V/V. Returns: total RTI voltage noise in the same unit as eni and eno."""
    return (eni ** 2 + (eno / g) ** 2) ** 0.5


def vout(g, vin_p, vin_n, vref):
    """VO = G * (VIN+ - VIN-) + VREF. DS p.20, 8.3.1 Setting the Gain, Figure 55 output equation.
    g: gain, V/V. vin_p: +IN voltage, V. vin_n: -IN voltage, V. vref: REF voltage, V. Returns: VO, V."""
    return g * (vin_p - vin_n) + vref


def gain_actual(rg, gain_err, gain_drift, t_c):
    """Not a DS equation: gain at temperature t_c with gain error and gain drift applied to Equation 1.
    G(T) = gain(rg) * (1 + gain_err) * (1 + gain_drift * (T - 25)). Combines three sources:
    - gain(rg): DS p.20, 8.3.1 Setting the Gain, Equation 1 (RG tolerance and RG tempco are the caller's rg input,
      so pass rg as a wca input with its own tolerance and TCR);
    - gain_err: 25 degC gain error row, DS p.7, 7.5 Electrical Characteristics, Gain error (no full-temperature
      gain-error row exists, so SPEC recipe step 2 applies: 25 degC row plus drift);
    - gain_drift: DS p.7, 7.5 Electrical Characteristics, Gain vs temperature (6). Footnote (6): the G > 1 value
      excludes the effect of the external RG.
    rg: ohm. gain_err: fraction, signed (+/- spread as in the DS). gain_drift: 1/degC, signed.
    t_c: temperature, degC. Returns: gain, V/V."""
    return gain(rg) * (1 + gain_err) * (1 + gain_drift * (t_c - 25))


EXAMPLES = [
    # (function, kwargs, expected, relative tolerance, cite)
    # Gain-resistor values printed in DS p.20 Table 2 (RG column, DESIRED GAIN column). The DS prints RG rounded
    # (3 to 4 significant figures), so the tolerance is set to the rounding of each printed RG.
    ("gain", {"rg": 49.4e3}, 2, 1e-3, "DS p.20, Table 2, DESIRED GAIN 2, RG 49.4 k"),
    ("gain", {"rg": 12.35e3}, 5, 1e-3, "DS p.20, Table 2, DESIRED GAIN 5, RG 12.35 k"),
    ("gain", {"rg": 5.489e3}, 10, 1e-3, "DS p.20, Table 2, DESIRED GAIN 10, RG 5.489 k"),
    ("gain", {"rg": 2.600e3}, 20, 1e-3, "DS p.20, Table 2, DESIRED GAIN 20, RG 2.600 k"),
    ("gain", {"rg": 1.008e3}, 50, 1e-3, "DS p.20, Table 2, DESIRED GAIN 50, RG 1.008 k"),
    ("gain", {"rg": 499}, 100, 1e-3, "DS p.20, Table 2, DESIRED GAIN 100, RG 499"),
    ("gain", {"rg": 248}, 200, 1e-3, "DS p.20, Table 2, DESIRED GAIN 200, RG 248"),
    ("gain", {"rg": 99}, 500, 1e-3, "DS p.20, Table 2, DESIRED GAIN 500, RG 99"),
    # DS prints RG 49.4 ohm for G = 1000. Exact RG is 49.45 ohm; the printed value gives G = 1001 (0.1 % high).
    ("gain", {"rg": 49.4}, 1000, 2e-3, "DS p.20, Table 2, DESIRED GAIN 1000, RG 49.4 (printed rounded; exact 49.45)"),
    # Sanity: zero gain error and drift at 25 degC must return the Table 2 gain (G = 10 row, RG 5.489 k).
    ("gain_actual", {"rg": 5.489e3, "gain_err": 0.0, "gain_drift": 0.0, "t_c": 25}, 10, 1e-3,
     "DS p.20, Table 2, DESIRED GAIN 10, RG 5.489 k (with zero error and drift)"),
]

INPUTS = {
    # function: {argument: component.toml param key}. Design choices (rg, g, t_c, vin, vref) are not listed.
    "gain": {},
    "rg_for_gain": {},
    "vos_rti": {"vosi": "vosi_full", "voso": "vos_o_full"},
    "dvos_rti": {"dvosi": "vosi_drift_full", "dvoso": "vos_o_drift_full"},
    # eni is printed at G = 100 only (DS p.6, eNI row condition): valid as printed for G = 100.
    "en_rti": {"eni": "eni_g100_1khz.typ", "eno": "eno_1khz.typ"},  # noise is typical only: nominal, not a bound
    "vout": {},
    # Example mapping uses the G = 10 rows. For another gain pick the row for that gain (G = 1: gain_err_g1_25c and
    # gain_drift_g1_full; G = 100: gain_err_g100_25c and gain_drift_gt1_full). The user must pick the row.
    "gain_actual": {"gain_err": "gain_err_g10_25c", "gain_drift": "gain_drift_gt1_full"},
}
