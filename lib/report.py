"""Markdown tables and PNG plots of worst-case results."""

import matplotlib

matplotlib.use("Agg")  # no window; write files only
import matplotlib.pyplot as plt

from .units import eng_scale
from .wca import sweep


def _cells(p):
    """(min, typ, max, unit) strings for one Param, sharing one engineering prefix."""
    values = [p.min, p.typ, p.max]
    divisor, unit = eng_scale(values, p.unit)
    nums = ["-" if v is None else f"{v / divisor:.4g}" for v in values]
    return nums + [unit]


def table(rows):
    """GitHub markdown table. rows = [(name, Param, notes), ...]."""
    lines = ["| Name | Min | Typ | Max | Unit | Notes |", "|---|---|---|---|---|---|"]
    for name, p, notes in rows:
        lo, typ, hi, unit = _cells(p)
        lines.append(f"| {name} | {lo} | {typ} | {hi} | {unit} | {notes} |")
    return "\n".join(lines) + "\n"


def plot_band(fn, name, values, out_png, xlabel="", ylabel="", title="", **kwargs):
    """Sweep input `name` over values and save min/typ/max curves to out_png. Returns out_png."""
    points = sweep(fn, name, values, **kwargs)
    xs = [x for x, _ in points]
    fig, ax = plt.subplots()
    for field, style in (("min", "r--"), ("typ", "k-"), ("max", "b--")):
        ys = [getattr(p, field) for _, p in points]
        if all(y is not None for y in ys):
            ax.plot(xs, ys, style, label=field)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True)
    ax.legend()
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    return out_png
