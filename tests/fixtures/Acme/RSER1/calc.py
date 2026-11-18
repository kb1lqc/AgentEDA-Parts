def mpn(r_ohm):
    """Orderable number: RSER1-<value>R, for example RSER1-2400R.  r_ohm: ohm.  Returns: text."""
    return "RSER1-" + format(r_ohm, "g") + "R"


def dissipation(v, r):
    """P = V^2 / R.  v: V.  r: ohm.  Returns: W."""
    return v * v / r


EXAMPLES = [
    ("dissipation", {"v": 10.0, "r": 1000.0}, 0.1, 1e-3, "DS p.1, Ratings, example"),
]

INPUTS = {
    "dissipation": {},
    "mpn": {},
}
