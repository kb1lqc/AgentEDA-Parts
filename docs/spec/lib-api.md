# Using a part (lib API) and analysis rules

```python
from lib import load, Param, wca, table, plot_band

ina = load("TexasInstruments/INA821IDGK")
ina.param("vosi_full")             # Param(min=None, typ=None, max=80e-6, unit='V', cite=...)
rg  = Param.tol(5.49e3, 0.001, "ohm")       # 5.49 kohm +/-0.1 %
g   = wca(ina.calc.gain, rg=rg)  # Param(min=..., typ=..., max=...)
print(table([("Gain", g, "")]))
```

A resistor series component (`[part] series = "resistor"`) also gives `part.values()`, `part.mpn(value)` and
`part.series_value(value)` (with tolerance options also `part.pairs()`, `part.tolerance(code)`, `part.tcr(value)`; see
"Series components"): `wca(fn, r=load("Panasonic/ERJ-3EKF").series_value(2.61e3))`.
A capacitor series gives `part.catalog()` and `part.select(capacitance, rated_voltage, dielectric, tolerance=None)`
(see "Capacitor series"): `sel = load("Murata/GCM155").select(0.1e-6, 50, "X7R", "+/-10%")`, `sel.mpn`, and
`wca(sel.part.calc.capacitance_worst_pct, **sel.part.inputs("capacitance_worst_pct"))` (X7R; `capacitance_worst_ppm` for C0G).

Worst-case method (`wca`), stated so a human can check it by hand:
1. typ = function evaluated with every input at its typ value. If any input has no typ, result typ is `None`.
2. min/max = lowest and highest result over every combination of input min/max values (all 2^n corners).
   Any input with no min or max is a hard error, unless the caller supplies the missing bound explicitly.
3. Corners are exact for functions that are monotonic in each input over the range. For other functions, pass
   `samples=N` to also evaluate N evenly spaced interior points per input.

## Analysis rules (examples/)
- Load numbers through `part.param(key)` / `part.inputs(fn)`; never retype a datasheet number.
- Every non-datasheet value is a named DESIGN CHOICE constant with a comment.
- Worst case through `wca` (all min/max corners); nominal via typ. For a bound-only spec, state the nominal with
  `Param.with_typ(...)` in code.
- Use `full` rows over temperature; otherwise the temperature recipe (docs/spec/extract.md, "Temperature and combined
  errors (the one recipe)"). Curve and `_typ` values never decide pass/fail without saying so in the output.
- Output: a generated markdown report (inputs with cites, results table, rating checks with PASS/FAIL, plots, and a
  "limits of this analysis" line: DC steady state, 25 °C-only rows, curve estimates).
- A Zener module takes derate, ambient and waivers from its parent; list every waiver (rationale with a cite) in the report.
- Verified inputs: every row read through `part.param` / `part.inputs` / `part.series` / `part.select` (and the helpers
  built on them) is recorded; read rows only through these, never `part.params[...]`. An unverified read stays listed even
  if the same row is read verified later; a selected capacitor records as `<Value>[<catalog value>]:<key>`, its `tc` as
  the dielectric's own row. If `lib.unverified_inputs()` ("<Value>:<key>" of rows without `verified`) is not empty when the report
  is written, every judged PASS reads `PASS (UNVERIFIED INPUTS)` and the report lists those rows. `lib.used_inputs()`
  lists all rows read; `lib.reset_inputs()` clears the record. `lib.verdict(ok)` gives the right word;
  `lib.inputs_section()` gives the report's "Input verification" section.
