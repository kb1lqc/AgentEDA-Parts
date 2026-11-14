"""Worst-case analysis: evaluate a function at every min/max corner of its inputs."""

import itertools

from .param import Param


def _as_param(name, value):
    """Floats are exact values; Params pass through."""
    if isinstance(value, Param):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Param(min=value, typ=value, max=value)
    raise TypeError(f"wca input '{name}' must be a Param or a number, got {value!r}")


def _points(name, p, samples):
    """Values to try for one input: min, N evenly spaced interior points, max."""
    if p.text is not None:
        raise ValueError(f"wca input '{name}' is a text rating ({p.text!r}), not a number")
    if p.min is None or p.max is None:
        missing = "min" if p.min is None else "max"
        raise ValueError(f"wca input '{name}' has no {missing}; give it one explicitly")
    step = (p.max - p.min) / (samples + 1)
    points = [p.min + i * step for i in range(1, samples + 1)]
    return list(dict.fromkeys([p.min] + points + [p.max]))


def wca(fn, samples=0, unit="", **kwargs):
    """Worst-case result of fn(**kwargs) as a Param (SI units).

    typ: fn at every input's typ (None if any input has no typ).
    min/max: lowest and highest result over all 2^n min/max corners.
    samples=N also tries N interior points per input (for non-monotonic fn).
    unit: unit label for the result Param.
    """
    inputs = {k: _as_param(k, v) for k, v in kwargs.items()}
    typ = None
    if all(p.typ is not None for p in inputs.values()):
        typ = fn(**{k: p.typ for k, p in inputs.items()})
    names = list(inputs)
    choices = [_points(k, inputs[k], samples) for k in names]
    results = [fn(**dict(zip(names, combo))) for combo in itertools.product(*choices)]
    return Param(min=min(results), typ=typ, max=max(results), unit=unit)


def sweep(fn, name, values, **kwargs):
    """Run wca once per value of input `name`. Returns [(x, Param), ...] for plotting."""
    return [(x, wca(fn, **{name: x}, **kwargs)) for x in values]
