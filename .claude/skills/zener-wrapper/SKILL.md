---
name: zener-wrapper
description: Generate, update or debug a component's Zener wrapper (<Value>.zen) in this repo from its component.toml, choose which datasheet rows become Zener checks (check_pins / check_ambient / unchecked), and write the wrapper's test harness and cases. Use whenever a component is added or its component.toml changes, when a .zen wrapper is stale or fails to build, or when a Zener module needs to instantiate a library part.
---

# Zener wrappers in this repo

Two layers, one source of truth (CLAUDE.md, "Two layers"; docs/SPEC.md, "Zener wrapper"):
- `component.toml` + `calc.py` hold every number and equation. Humans verify these.
- `<Value>.zen` is GENERATED from `component.toml` by `python3 -m lib.zen`. Never hand-edit it. Never type a
  datasheet number or equation into Zener. Change the TOML, regenerate.

## 1. Choose the check rows (in component.toml)

Every `abs_max` and `rec_op` row gets exactly one disposition (`python3 -m lib.check` warns on a row with none):

| Row is about | Field |
|---|---|
| A voltage the circuit sets on a pin: supply, signal input, pull-up rail, divider input, REF | `check_pins = ["PIN", ...]` (names exactly as in `[[pin]]`) |
| A limit relative to another pin (pin-pair row, rail-relative window, supply span) | `check_pins` plus `min_ref` / `max_ref` = that pin's name |
| The grade's temperature range | `check_ambient = true` (degC, min and max) |
| A pin the part drives (OUT, gate drive, TMR, COMP, SS) or set by external parts (MOSFET SOURCE, SW) | `unchecked = "<why>; owner: module"` |
| A looser row covered by a stricter checked row | `unchecked = "covered by <key>"` |
| Storage, solder, ESD | `unchecked = "owner: assembly"` |
| One row covering checked and part-driven pins (FB, TMR) | `check_pins = ["FB"]` and `unchecked = "TMR not checked: <why>"` |

A rec-op-like Electrical Characteristics row (VCC operating range) may also get `check_pins`; it becomes an error.

Severity is derived, not chosen: `scope = "25C"` or `"partial"` -> warning, waivable with `waive_<key>`; anything
else -> error. `abs_max` limits are multiplied by `derate` on the side away from zero; other kinds are not.
Never put check fields on `curve = true` or `text` rows.

## 2. Generate

```sh
python3 -m lib.check                      # data valid, check fields valid
python3 -m lib.zen [components/<Mfr>/<Value>]   # writes <Value>.zen + empty pcb.toml, then runs pcb fmt
pcb build -Wstyle -Dwarnings components/<Mfr>/<Value>   # must exit 0 (UNVERIFIED is advice when built alone)
python3 -m lib.readme                     # README "Zener checks" table
```

Read the generated wrapper top to bottom once: the `# UNCHECKED:` list, the pins (`+IN` -> `IN_P`, `-VS` -> `VS_N`;
ground-named pins are `io(Ground)`; `power_in` pins are cast to `Power` at the component; `no_connect` pins
omitted), the configs (`derate`, `ambient`, `waive_<key>`), and one commented `_limit(...)` per checked pin.

If `lib.zen` prints `ERROR:` lines, fix the TOML (unknown pin, non-voltage row in `check_pins`, ambient row without
min/max). Do not edit `lib/zen.py` to get around a data problem. If the generator itself needs a new Zener
construct, confirm it in the stdlib source (`pcb list -m -json @stdlib`) or a scratch build first, add a
`tests/test_zen.py` generator test, and update docs/SPEC.md "Zener wrapper".

Families (a directory with `variants.toml`): `lib.zen` writes one wrapper per variant, `<Variant>.zen`, all in the
family directory with one `pcb.toml`; each uses that variant's merged rows (its own ambient check, its own
restricted rows). Check fields go on the shared or overridden rows like any other row.

Series components (`[part] series = "resistor"`, docs/SPEC.md "Series components"): one wrapper per directory with a
required `value = config(Resistance)`, pins `P1`/`P2`, a generated `_MPN` table (integer micro-ohm keys, from
`calc.mpn`), and two errors: `value_allowed` and `rated_voltage` (voltage across the part vs
`derate x min(sqrt(P x R), Vlimit)`). The four rows named in `[part]` need no `check_pins`/`unchecked`. Instances pass
`value="2.61kohm"`. Harness: `tests/zen/Series_harness.zen` shows value, both pin voltages, `derate` and ambient as
configs; the fixture build tests live in `tests/test_series.py` (a real series also gets `CASES` rows in
`tests/test_zen.py`). Zener has no sqrt or `**`, and a required config reads 0 when the module file is first loaded:
do not `error()` on the value at top level.

## 3. Test harness and cases

`tests/zen/<Value>_harness.zen` (for a family: `<family dir>_harness.zen`, instantiating one variant's
`./<Variant>.zen`; add a case per variant-specific check, e.g. each grade's ambient range) instantiates the wrapper (`U = Module("./<Value>.zen")`; the test copies the file
next to the wrapper as `_harness.zen`). Rules, learned the hard way:
- Defaults are the nominal passing case; comment each with its range and why it passes.
- Every net needs a name (`Net("X")`); an unnamed `Net()` is an error.
- An "unset" option gives a named net with no voltage: `Net(name) if v == "unset" else Net(name, voltage=v)`.
- `None` cannot be passed to a typed `config()`: omit an optional input with
  `**({} if ta == "unset" else {"ambient": ta})`, which must be the LAST argument.
- Give both ends of a temperature range a unit: `"-40°C to 85°C"` (`"-40 to 85°C"` parses as -313.15 °C).

Add rows to `CASES` in `tests/test_zen.py`: `(component dir, case, ["key=value", ...], "pass"|"error"|"warning",
"text that must appear")`. Cover: nominal pass; each check pushed just outside its limit (error or warning as
derived); a waiver clearing a warning; an unset net (`UNVERIFIED <check>`); ambient out of range and unset.
When a case moves several nets (raising VCC also moves OUT/SENSE), say so in the case name. Prove one new case
can fail by flipping its expectation once. Run `python3 -m unittest tests.test_zen -v`; it also asserts every
committed wrapper equals fresh generator output.

## 4. Using wrappers from a Zener module

Verified on pcb 0.4.101 (scratch package inside the workspace):
```zen
load("@stdlib/units.zen", "Temperature")

ambient = config(Temperature, default="-40°C to 85°C", help="Board ambient")
derate = config(float, default=1.0, help="Derating")

INA = Module("github.com/kb1lqc/zener-library/components/TexasInstruments/INA821IDGK/INA821IDGK.zen")
INA(
    name="U1",
    VS_P=Power("V15", voltage="15V 5%"),
    VS_N=Power("VN15", voltage="-15V 5%"),
    IN_P=Net("SNS_P", voltage="0V to 130mV"),
    IN_N=Net("SNS_N", voltage="0V"),
    RG1=Net("RG1"),
    RG2=Net("RG2"),
    REF=Net("REF", voltage="0V"),
    OUT=Net("VOUT"),
    ambient=ambient,
    derate=derate,
)
```
The first build fails with "Run `pcb sync`"; `pcb sync` adds the component to the module package's
`[dependencies]` in its `pcb.toml`. Relative paths that leave a package fail ("escapes beyond package root").
Declare a voltage range with tolerance on every checked net. Pass `derate`, `ambient` and waivers down; never
hard-code them. Values (RG, dividers) are computed in Python from `calc.py`, not re-derived in Zener.
