# Series components and numbered rows

## Series of numbered rows

Keys `<prefix>_<n>` (decimal n, for example `vovc_thr_0` ... `vovc_thr_15`) form a series:
`part.series("vovc_thr")` returns `{0: Param, 1: Param, ...}` sorted by n (numeric, so 2 before 16). A key suffix
equals its symbol's suffix.

## Series components (the value is a design input)

A passive whose value the designer chooses (a resistor series: one directory per package, ERJ-3EKF 0603) is a
series component. (A capacitor series, whose values come from a catalog file, is the next section.) It is an ordinary
component directory plus these `[part]` keys:

```toml
[part]
value          = "ERJ-3EKF"              # directory name; no `mpn` key: calc.mpn(value) gives it
series         = "resistor"              # marks a series component: "resistor" (here) or "capacitor" (next section)
value_param    = "res_range"             # param row: allowed resistance range, min and max, unit ohm
e_series       = ["E24", "E96"]          # allowed values: these IEC 60063 series inside the range
series_power   = "p70"                   # param row: power rating at 70 degC (W, max)
series_vlimit  = "v_limit"               # param row: limiting element voltage (V, max)
series_tol     = "tol"                   # param row: tolerance (%, min and max, e.g. -1 / 1)
series_eseries_min = { E96 = 100 }       # optional: lowest value (ohm) taken from one E-series (here E96)
```

Optional keys, each described below: `series_vlimit` may be absent, `series_tolerances` replaces `series_tol`,
`series_tcr` selects a TCR row per value, `series_pins` names the two current terminals of a 4-terminal part.

- `calc.py` must define `mpn(value)` (value in ohm, returns the orderable MPN text; `mpn(value, tol_code)` for a
  series with tolerance options). It is the single source of the part number: `[part] mpn` must be absent. The README
  gives three example values.
- The allowed values are every `E24` / `E96` mantissa (literal lists in `lib/series.py`, 24 and 96 values per decade)
  times a power of ten that falls in the `value_param` range, sorted and unique (E24 has values E96 lacks, for
  example 2.7). Each is the float nearest its printed decimal: 2.61 x 10^3 is `2610.0`, the same float `2.61e3` gives.
- `series_eseries_min` (optional, keys from `e_series`, positive ohm) drops that E-series' values below its minimum
  (use it where the catalog prints no part-number code for them); a value that another listed series contains stays
  allowed (E24 47 ohm with `E96 = 100`; E96 47.5 ohm is out). `lib.check`, `part.values()` and the wrapper's
  `value_allowed` all use the reduced set.
- **Decade value set.** `e_series = ["VISHAY-DECADE"]` allows every two-significant-digit value 10..99 per decade
  (mantissas 1.0 ... 9.9: 90 values per decade; `lib.series.DECADE`), from Vishay Dale "Standard resistance decade
  values", document 30117, rev 04-Oct-06 (titled "WSL Type Resistors": "Resistance values must be within the
  resistance range listed on the most current datasheet"). It combines with E24/E96 in one list like any other name.
- **No limiting element voltage.** `series_vlimit` is optional. Without it the rated voltage is `sqrt(P70 x R)` only
  (`lib.series.rated_voltage(r, p70)`; the wrapper compares squares and has no `vlim` argument; the README says the
  datasheet prints none).
- **Tolerance options.** Instead of one `series_tol` row, a series may list several orderable tolerances, each with its
  own resistance range (a datasheet that prints a range per tolerance column):

  ```toml
  series_tolerances = { B = { tol = "tol_b", range = "r_range_b" }, D = { tol = "tol_d", range = "r_range_d" } }
  ```

  The key is the tolerance code as printed in the part number (letters/digits). `tol` names a param row (%, min and
  max, like `series_tol`), `range` names a param row (ohm, min and max) holding that option's range as printed, so every
  number keeps its row, unit and cite. `series_tol` and `series_tolerances` are exclusive. `value_param` stays the
  directory's range; each option's range is **clipped** to it (`max(low) .. min(high)`), so one datasheet table splits
  over several directories (`WSK2512-LOW`, `WSK2512`) without editing the printed rows. An option with no value left
  after clipping is ERROR (leave it out of that directory). The allowed set is the sorted list of
  `(value, tolerance code)` pairs; a value is orderable with every code whose clipped range holds it.
- **TCR by range.** `series_tcr = [{ tcr = "tcr_a", range = "tcr_a_range" }, ...]` pairs each TCR row (ppm/degC, min
  and max) with a range row (ohm) for datasheets that print a TCR per resistance range. Every allowed value must fall
  in exactly one range (ERROR for none or several). `part.tcr(value)` returns the Param of that row (a fraction per
  degC), for `wca(calc.resistance_worst, r0=value, tol=part.tolerance(code), tcr=part.tcr(value), ...)`. `INPUTS` cannot
  map the TCR argument when there are several rows (the row depends on the value); with a single row it may map it as
  usual. The rows named by `series_tolerances` and `series_tcr` need no `check_pins` / `unchecked`.
- **Four-terminal parts.** A series has exactly 2 pins unless `series_pins = ["I1", "I2"]` names two different `[[pin]]`
  names (the current terminals): the wrapper's `rated_voltage` check is taken between those nets (default: pins `1`
  and `2`). The other pins (Kelvin sense) are ordinary pass-through nets.
- `part.values(tol=None)` returns the sorted allowed values (ohm); with tolerance options, `tol` = a code gives that
  code's values and `None` the values any code allows. `part.pairs()` returns the sorted `(value, code)` list
  (`code` is `None` without options), `part.tolerances()` the codes, `part.tolerance(code)` the tolerance Param
  (fraction). `part.mpn(value, tol=None)` returns `calc.mpn(value)` (or `calc.mpn(value, code)`) for an allowed value;
  `tol` may be left out only when exactly one code allows the value, otherwise `ValueError` "ambiguous: ... pass tol".
  `part.series_value(value, tol=None)` returns a `Param` with typ = value and min/max =
  value x (1 + tol.min), value x (1 + tol.max), in ohm (the row of the code), ready for `wca`:
  `rg = erj.series_value(2.61e3)`. `mpn` and `series_value` raise `ValueError` for a value (or value/code pair) that is
  not allowed or a code that is not an option.
- `lib.readme` adds a "Series" section: value range, E-series, tolerance, MPN rule with three example values,
  the rated-voltage formula and a table of rated voltage at the decade values (10 ohm ... 1 Mohm) inside the range,
  "computed from" the power and voltage-limit rows.
- Zener: see "Zener wrapper", "Series wrapper".
- A series cannot be a family. The rows the series reads need no `check_pins` / `unchecked`.
