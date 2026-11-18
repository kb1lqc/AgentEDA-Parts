---
name: zener-wrapper
description: Generate or debug a component's Zener wrapper (<Value>.zen) from its component.toml, write its test harness and CASES, or instantiate a library part from a Zener module.
---

# Zener wrappers in this repo

Check rows are chosen in `component.toml` (docs/spec/extract.md, "Check-row defaults"); what the generator emits is
docs/spec/wrapper.md. `<Value>.zen` is generated: change the TOML, regenerate.

## 1. Generate

```sh
python3 -m lib.check
python3 -m lib.zen [components/<Mfr>/<Value>]   # writes <Value>.zen + empty pcb.toml, then pcb fmt
pcb build -Wstyle -Dwarnings components/<Mfr>/<Value>   # one directory per call; must exit 0
python3 -m lib.readme
```

Read the generated wrapper top to bottom once: the `# UNCHECKED:` list, the pins, the configs, one commented
`_limit(...)` per checked pin. Families get one wrapper per variant (`<Variant>.zen`, one `pcb.toml`).

If `lib.zen` prints `ERROR:` lines, fix the TOML. Do not edit `lib/zen.py` to get around a data problem. If the
generator needs a Zener construct it does not already emit, confirm it in the stdlib source
(`pcb list -m -json @stdlib`), `pcb <cmd> --help` or a scratchpad build, add a `tests/test_zen.py` generator test,
and update docs/spec/wrapper.md. There is no `pcb doc` or `pcb search`.

Series gotchas: a required config reads 0 when the module file is first loaded, so do not
`error()` on the value at top level. Real series also get `CASES` rows; fixture builds live in
`tests/test_series.py` and `tests/test_capacitor.py` (`tests/zen/Series_harness.zen`, `Capacitor_harness.zen`).

## 2. Test harness and cases

`tests/zen/<Value>_harness.zen` instantiates the wrapper (`U = Module("./<Value>.zen")`; the test copies the file next
to the wrapper as `_harness.zen`). For a family it is `<family dir>_harness.zen` instantiating one variant's
`./<Variant>.zen`, with a case per variant-specific check (each grade's ambient range).
- Defaults are the nominal passing case; comment each with its range and why it passes.
- Every net needs a name (`Net("X")`); an unnamed `Net()` is an error.
- An "unset" option gives a named net with no voltage: `Net(name) if v == "unset" else Net(name, voltage=v)`.
- `None` cannot be passed to a typed `config()`: omit an optional input with
  `**({} if ta == "unset" else {"ambient": ta})`, which must be the LAST argument.

Add rows to `CASES` in `tests/test_zen.py`: `(component dir, case, ["key=value", ...], "pass"|"error"|"warning",
"text that must appear")`. Cover: nominal pass; each check pushed just outside its limit (error or warning as
derived); a waiver clearing a warning; an unset net (`UNVERIFIED <check>`); ambient out of range and unset. When a
case moves several nets, say so in the case name. Prove one new case can fail by flipping its expectation once. Run
`python3 -m unittest tests.test_zen -v`; it also asserts every committed wrapper equals fresh generator output.

## 3. Using wrappers from a Zener module

Load by URL (`Module("github.com/kb1lqc/zener-library/components/<Mfr>/<Value>/<Value>.zen")`); relative paths that
leave a package fail ("escapes beyond package root"). The first build fails with "Run `pcb sync`": run it.
```zen
INA = Module("github.com/kb1lqc/zener-library/components/TexasInstruments/INA821IDGK/INA821IDGK.zen")
INA(name="U1", VS_P=Power("V15", voltage="15V 5%"), IN_P=Net("SNS_P", voltage="0V to 130mV"),
    ambient=ambient, derate=derate)   # remaining pins as in the wrapper
```
Declare a voltage range with tolerance on every checked net (an undeclared one reports UNVERIFIED and fails
`-Dwarnings`). Pass `derate`, `ambient` and any `waive_<key>` down; never hard-code them. A waiver is a rationale with a
cite. Compute design values (RG, dividers) in Python from `calc.py`, snap with the stdlib E-series helpers, never
re-derive datasheet equations in Zener. Topology stays stable (see `zener-language`).
