def vout(vref, r1, r2):
    """Vout = Vref * (1 + R1/R2)."""
    return vref * (1 + r1 / r2)


EXAMPLES = [("vout", {"vref": 1.0, "r1": 10e3, "r2": 10e3}, 3.0, 1e-3, "DS p.9, bogus")]
