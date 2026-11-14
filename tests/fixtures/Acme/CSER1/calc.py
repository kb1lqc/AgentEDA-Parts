def capacitance_worst_pct(c0, tol, tc):
    """Not a DS equation: C = C0 * (1 + tol) * (1 + tc), tc a fraction (percent-change class).
    c0: F.  tol: fraction.  tc: fraction.  Returns: F."""
    if tc != 0 and abs(tc) < 1e-3:
        raise ValueError("tc looks like a ppm/degC coefficient: use capacitance_worst_ppm")
    return c0 * (1 + tol) * (1 + tc)


def capacitance_worst_ppm(c0, tol, tc, dt):
    """Not a DS equation: C = C0 * (1 + tol) * (1 + tc * dt), tc in 1/degC, dt = T - 25 degC required, 0 to 100.
    c0: F.  tol: fraction.  tc: 1/degC.  dt: degC.  Returns: F."""
    if not 0 <= dt <= 100:
        raise ValueError("dt outside 0 to 100")
    if abs(tc) > 1e-3:
        raise ValueError("tc looks like a fraction: use capacitance_worst_pct")
    return c0 * (1 + tol) * (1 + tc * dt)


EXAMPLES = [
    ("capacitance_worst_pct", {"c0": 0.1e-6, "tol": -0.10, "tc": -0.15}, 0.0765e-6, 1e-9, "DS p.1, Ratings, X7R"),
    ("capacitance_worst_ppm", {"c0": 100e-12, "tol": -0.02, "tc": -30e-6, "dt": 100}, 97.706e-12, 1e-9, "DS p.1, Ratings, C0G"),
]

INPUTS = {
    "capacitance_worst_pct": {"c0": "capacitance.typ", "tol": "tolerance", "tc": "tc"},
    "capacitance_worst_ppm": {"c0": "capacitance.typ", "tol": "tolerance", "tc": "tc"},
}
