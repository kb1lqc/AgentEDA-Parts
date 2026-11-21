"""Component library: load parts, run worst-case math, make tables and plots.

Exports resolve lazily (PEP 562), so `import lib.component` (stamp and hash helpers, as tools/check_stamps.py and
tools/stamp.py use) needs only the stdlib; matplotlib loads on first use of a lib.report name.
"""

import importlib

_EXPORTS = {
    "load": "component", "reset_inputs": "component", "unverified_inputs": "component", "used_inputs": "component",
    "human_review_needed": "component",
    "Param": "param",
    "inputs_section": "report", "plot_band": "report", "table": "report", "verdict": "report",
    "sweep": "wca", "wca": "wca",
}

__all__ = ["load", "Param", "wca", "sweep", "table", "plot_band", "unverified_inputs", "used_inputs", "reset_inputs", "verdict",
           "inputs_section", "human_review_needed"]


def __getattr__(name):
    mod = _EXPORTS.get(name)
    if mod is None:
        raise AttributeError(f"module 'lib' has no attribute {name!r}")
    value = getattr(importlib.import_module(f".{mod}", __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
