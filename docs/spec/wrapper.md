# Zener wrapper (generated)

The wrapper is generated from `component.toml` by `python3 -m lib.zen`; never hand-edit it and never put a datasheet number or equation in Zener. Which rows become checks: docs/spec/extract.md, "Check-row defaults".

What the generator emits, so a reviewer can predict the file from the TOML:
- One `io()` per connected `[[pin]]`, named from the pin name (`+IN` -> `IN_P`, `-VS` -> `VS_N`, `V+` -> `V_P`).
  Ground-named pins (`GND AGND DGND PGND SGND VSS VSSA`) are `io(Ground)`; every other pin is `io(Net)`. `power_in`
  and `power_out` pins are cast to `Power(net, voltage=net.voltage)` at the component, so a negative rail or GND can drive them.
  `no_connect` pins are omitted (auto NotConnected). Same-name pins (two GND pins, an exposed pad named GND) are
  one node: one `io()` and one `pins={}` entry.
- `derate` config (default 1.0, must be in (0, 1]), `ambient` config when any row has `check_ambient`, and
  `waive_<key>` config for every warning-level check.
- One check per `check_pins` entry, named `<key>_<IO>`: worst case `v.min >= min + min_ref.max` and
  `v.max <= max + max_ref.min` (no ref = absolute volts). `abs_max` limits are multiplied by `derate` on the side
  away from zero. Severity: `abs_max`/`rec_op`/other rows with scope `full`/`na` are errors; scope `25C`/`partial`
  are warnings, waivable with `waive_<key>` (a non-empty rationale with a cite drops it to advice; errors cannot be
  waived).
- Pin-pair rows: a `check_pins` row with exactly one check pin, one non-ground reference pin (`min_ref`/`max_ref`,
  whichever are set, all naming that pin) and a reference on every limited end (for example `vgs` G rel S, `abs_cs_pair`
  CS+ rel CS-) gets an optional config `v_<key> = config(Voltage, optional=True)`: the module's worst-case range of
  V(pin) - V(ref), taken from its own worst-case analysis (not a datasheet value; the module justifies it in a comment
  at the instance). When set, the check compares that declared range with the row's `min`/`max` (same `derate` on
  abs_max, same severity and waiver) and needs no net voltage, so the two nets may stay undeclared for that check.
  When unset, the check is unchanged and evaluates the two nets' ranges independently (pessimistic on a bus where
  both nets swing together: the generator cannot know they are correlated). Rows referenced to a ground-named pin,
  with several check pins, with two different references, or with an unreferenced limited end get no `v_<key>`.
  The check name stays `<key>_<IO>`; the config is `v_<key>`.
- One check per `check_ambient` row, named `<key>_ambient`, against the `ambient` config.
- A checked net with no declared voltage is `UNVERIFIED` (warning, fails `-Dwarnings`); when the wrapper is built
  alone it is advice, so `pcb build <dir>` stays green.
- Every `abs_max`/`rec_op` row without a check is listed as `# UNCHECKED: <key>: <name> (<cite>); <reason>`.
- Checks are DC steady state only (stated in the wrapper docstring).

### Series wrapper

A resistor series component (see "Series components") gets one wrapper, `<Value>.zen`. It differs from the above as follows:
- `value = config(Resistance, ...)`: required, no default (an instance without it fails to build).
- With tolerance options, `tolerance = config(str, default="")`, the code as printed (`D`). It may stay empty only when
  exactly one code allows the value; otherwise `value_allowed` fails and lists the codes. `_MPN` is keyed by
  `(micro-ohm integer, code)`, `_CODES` lists the codes per value, and an unorderable pair gets the sentinel MPN
  `UNORDERABLE` (as in the capacitor wrapper), never a real part number. `value_allowed` checks the pair is a key of
  `_MPN` and its message names every code's clipped range.
- Pins `"1"` and `"2"` become `P1` and `P2` (a purely numeric pin name gets a `P` prefix: `io_name("1") = "P1"`).
  With `series_pins` the voltage across the part is taken between those two pins' nets (`I1`, `I2`).
- `_MPN = {<micro-ohm integer>: "<MPN>", ...}`, generated from `calc.mpn` over every allowed value, and
  `Part(mpn=_MPN_STR, ...)` with `_MPN_STR = _MPN[int(value x 1e6 + 0.5)]`. Keys are integers because float text differs
  between Python and Zener (`1e+06`).
- Check `value_allowed` (error): the configured value is one of the table's keys. It is a check, not an `error()` call,
  because Zener evaluates the module once with a placeholder value of 0 when it is loaded; standalone it is advice.
- Check `rated_voltage` (error, through `_limit`, so an unset net is UNVERIFIED): the worst-case voltage across the
  part, max(P1.max - P2.min, P2.max - P1.min), is at most `derate x min(sqrt(P x R), Vlimit)`, with P from
  `series_power`, Vlimit from `series_vlimit` (their `max`) and R the configured value. Zener has no sqrt, so the
  generated code compares squares. Both rows are generated literals, like every other limit. Without `series_vlimit`
  the limit is `derate x sqrt(P x R)`. The voltage is the declared `v_across` when it is set (below); otherwise the
  net-range expression above.
- Optional config `v_across = config(Voltage, optional=True)`: the declared worst-case voltage across the part, a
  point value or a range, signed or not (the check uses the magnitude, max(|min|, |max|)). The module supplies it from
  its own analysis, for example I_max x worst-case R for a current shunt, or the worst-case drop for a termination
  between two logic nets. It replaces the independent net ranges in `rated_voltage`, so the two nets may stay
  undeclared without an UNVERIFIED for that check. When unset, `rated_voltage` is unchanged. The module owns the
  number and must justify it in a comment at the instance (design analysis; it is not a datasheet value and is not
  in component.toml). The check severity is unchanged: an error, not waivable, and `derate` still shrinks the limit.
- Power derating above 70 degC is a curve (`calc.rated_power`) and is not checked in Zener; the wrapper lists it as
  `# UNCHECKED ... owner: module`. The four series rows are not listed as UNCHECKED (the series check reads them).
- The ambient check comes from the normal `check_ambient` row.


### Capacitor wrapper

A capacitor series (see "Capacitor series") gets one wrapper, `<Value>.zen` (`GCM155.zen`). It differs from the above as
follows:
- Pins `"1"` and `"2"` become `P1` and `P2`, as in the resistor wrapper.
- Required configs: `value = config(Capacitance)`, `rated_v = config(Voltage)` (the rated DC voltage that selects the
  catalog part, `50V`) and `dielectric = config(str)` (as printed in the catalog, `X7R`). Optional `tolerance =
  config(str, default="")`, ASCII as printed (`+/-10%`), needed only when the catalog lists several for that value.
- `_VALUE = {(dielectric, femtofarad, millivolt, tolerance): "<catalog value>", ...}`, generated from `catalog.csv`
  (one row per orderable value, with a trailing comment of the printed values; an unorderable combination gets the sentinel MPN `UNORDERABLE`, never a real part number), and `_TOLS`, the tolerances listed for
  each (dielectric, femtofarad, millivolt). Keys are integers (`int(C x 1e15 + 0.5)`, `int(V x 1e3 + 0.5)`; the same
  arithmetic in `lib.capacitor.zen_key`) because float text differs between Python and Zener. The wrapper adds the
  package letter: `Part(mpn=_MPN_STR)` with `_MPN_STR = <value> + package_default`, and the alternates property is
  `<value> + each package_alternates` (empty when unorderable). Two catalog values with the same key are a generator problem.
- Check `part_orderable` (error; advice when the wrapper is built alone): the configured combination is a key of
  `_VALUE`. The message names the tolerances the catalog lists for it. A check, not an `error()` call, because Zener
  loads the module once with placeholder configs.
- Check `rated_voltage` (error, through `_limit`, so an unset net is UNVERIFIED): max(P1.max - P2.min, P2.max - P1.min)
  is at most `derate x rated_v` (non-polarized, either polarity). `derate` applies, as for the resistor series.
- Check `ambient_range` (error): the `ambient` config inside the `check_ambient` row of the configured dielectric
  (`_AMBIENT = {dielectric: (lo, hi)}`, one `check_ambient` row per dielectric, kelvin). An ambient row must be
  error severity (not 25C or partial).
- Rows restricted to parts, and rating rows restricted to a dielectric without a check, are listed as
  `# UNCHECKED: <key> [parts ...]: ...; <reason>`. DC-bias capacitance loss, aging and AC stress are listed as unchecked
  (owner: module). No `check_pins` in a capacitor series: the rated voltage comes from the catalog.
