def vout(vref, r1, r2):
    """Vout = Vref * (1 + R1/R2).  DS p.9, Eq. 1.
    vref: V.  r1, r2: ohm.  Returns: V."""
    return vref * (1 + r1 / r2)


def _hidden():
    """Not public."""


EXAMPLES = [
    # (function, kwargs, expected, relative tolerance, cite)
    ("vout", {"vref": 1.0, "r1": 10e3, "r2": 10e3}, 2.0, 1e-3, "DS p.9, Table 1, 2 V row"),
]

INPUTS = {
    # function: {argument: param key}
    "vout": {"vref": "vref"},
}
