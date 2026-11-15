"""Unit strings from component.toml -> SI numbers, and engineering-prefix formatting.

A unit is [prefix]base[suffix]: prefix f p n u m k M G, base V A ohm W F H Hz s C J,
suffix pp /rtHz /degC /us /MHz /V (/MHz -> /Hz: 23.4 uA/MHz -> 2.34e-11 A/Hz; /V is
transconductance, mA/V -> A/V; uV/V and mV/V are converted first, to fractions). A few units
are converted (mm, g, mg, %, ppm, ppm/degC, ppm/V, kcycles -> cycles) and a few are kept as printed
(degC, degC/W, dB, bits, LSB, cycles, years, ""). The SI base A/Hz also takes prefixes (pA/Hz).
"""

SCALABLE = {"V", "A", "ohm", "W", "F", "H", "Hz", "s", "C", "J"}
SUFFIXES = ["pp", "/rtHz", "/degC", "/us", "/MHz", "/V", "/Hz"]  # "/Hz" only so eng() can prefix A/Hz
UNSCALED = {"", "dB", "degC", "degC/W", "bits", "LSB", "cycles", "years"}
# Printed unit -> (power of ten, SI base unit) for units that are converted.
CONVERTED = {"mm": (-3, "m"), "g": (-3, "kg"), "mg": (-6, "kg"),
             "%": (-2, "1"), "m%": (-5, "1"), "ppm": (-6, "1"), "ppm/degC": (-6, "1/degC"), "ppm/V": (-6, "1/V"),
             "uV/V": (-6, "1"), "mV/V": (-3, "1"), "mdegC": (-3, "degC"),
             "kcycles": (3, "cycles")}
PREFIX_POWER = {"f": -15, "p": -12, "n": -9, "u": -6, "m": -3, "k": 3, "M": 6, "G": 9}


def split_unit(unit):
    """Split 'nV/rtHz' into ('n', 'V', '/rtHz'). Raise ValueError for an unknown unit."""
    suffix = ""
    for s in SUFFIXES:
        if unit.endswith(s) and unit != s:
            unit, suffix = unit[: -len(s)], s
            break
    if unit in SCALABLE:
        return "", unit, suffix
    if unit[:1] in PREFIX_POWER and unit[1:] in SCALABLE:
        return unit[0], unit[1:], suffix
    raise ValueError(f"unknown unit '{unit + suffix}'")


def to_si(value, unit):
    """Convert a printed value and unit to (float in SI base unit, base unit).

    to_si(5.49, 'kohm') -> (5490.0, 'ohm');  to_si(0.5, '%') -> (0.005, '1').
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"value {value!r} is not a number")
    if unit in UNSCALED:
        power, base = 0, unit
    elif unit in CONVERTED:
        power, base = CONVERTED[unit]
    else:
        prefix, core, suffix = split_unit(unit)
        power, base = PREFIX_POWER.get(prefix, 0), core + suffix
        if suffix == "/us":  # per microsecond -> per second, so slew rates are SI (V/s)
            power, base = power + 6, core + "/s"
        elif suffix == "/MHz":  # per megahertz -> per hertz (uA/MHz -> A/Hz)
            power, base = power - 6, core + "/Hz"
    # Divide by an integer power of ten for small prefixes: 80/10**6 rounds better than 80*1e-6.
    scaled = value * 10**power if power >= 0 else value / 10**-power
    return float(scaled), base


# Largest first, so the first prefix that fits is the right one.
_ENG = [(9, "G"), (6, "M"), (3, "k"), (0, ""), (-3, "m"), (-6, "u"), (-9, "n"), (-12, "p"), (-15, "f")]


def eng_scale(values, unit):
    """Pick one engineering prefix for a group of SI values. Returns (divisor, prefixed unit).

    eng_scale([80e-6], 'V') -> (1e-06, 'uV'). Units that do not scale come back as (1, unit);
    the plain-number unit '1' is shown as ''.
    """
    try:
        _, core, suffix = split_unit(unit)
    except ValueError:
        return 1, ("" if unit == "1" else unit)
    biggest = max([abs(v) for v in values if v is not None] or [0])
    if biggest == 0:
        return 1, unit
    for power, letter in _ENG:
        if biggest >= 10**power * 0.9999999:
            return (10**power if power >= 0 else 1 / 10**-power), letter + core + suffix
    return 1e-15, "f" + core + suffix


def eng(x, unit):
    """Format an SI value with an engineering prefix: eng(5490, 'ohm') -> '5.49 kohm'."""
    if x is None:
        return "-"
    divisor, shown = eng_scale([x], unit)
    text = f"{x / divisor:.4g}"
    return f"{text} {shown}" if shown else text
