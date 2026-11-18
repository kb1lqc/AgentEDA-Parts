def mpn(r_ohm, tol_code):
    """Orderable number: RSER2-<value><code>, for example RSER2-4.7D.  r_ohm: ohm.  tol_code: B, D or F.  Returns: text."""
    return "RSER2-" + format(r_ohm, "g") + tol_code


def dissipation(v, r):
    """P = V^2 / R.  v: V.  r: ohm.  Returns: W."""
    return v * v / r


EXAMPLES = [
    ("dissipation", {"v": 1.0, "r": 10.0}, 0.1, 1e-3, "DS p.1, Ratings, example"),
]

INPUTS = {
    "dissipation": {},
    "mpn": {},
}
