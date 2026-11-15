# Component library: agent rules

Reusable component library: datasheet numbers + datasheet equations + KiCad files, so a person or an AI can design
a circuit and compute its nominal and worst-case performance. No boards live here. I review every diff.
Correctness beats speed. Never guess a number. Simple beats clever: plain TOML, plain Python (stdlib + matplotlib),
standard KiCad files.

## Two layers, one source of truth
- **TOML + Python** (`component.toml`, `calc.py`) is the source of truth: every datasheet number with min/typ/max,
  units, conditions and a cite; every datasheet equation as a plain function. Humans verify this layer against the
  PDF. All analysis (worst case, nominal, tables, plots) runs in Python (`lib/`, `examples/`).
- **Zener** (`<Value>.zen` + empty `pcb.toml`) is GENERATED from `component.toml` by `python3 -m lib.zen`. It is
  for circuit capture: typed pins, KiCad symbol/footprint, part info, and DC checks on the voltages each instance
  declares, selected in the TOML with `check_pins` / `check_ambient` (rationale in `unchecked`). Never hand-edit a
  wrapper and never put a datasheet number or equation in Zener by hand: change the TOML and regenerate.
- Zener modules (hierarchical circuits) instantiate the wrappers; Python analyses the same parts. A number lives in
  exactly one place.

The format contract is [docs/SPEC.md](docs/SPEC.md); KiCad rules are [docs/KICAD.md](docs/KICAD.md). Where this file
and SPEC disagree, SPEC wins for the format, and this file wins for the procedure. Read both at the start of every
component task. Reference packages: `components/TexasInstruments/INA821IDGK/` (amplifier, sym rows, INPUTS),
`components/AnalogDevices/LTC4364MS/` (family with variants.toml; controller, negative rows, pin-referenced abs max, extended equations),
`components/Vishay/WSK2512R0250D/` (passive, no abs-max table, curve values, text rows).

## Ground truth
- Reads outside the repo are blocked. Datasheets go in `docs/datasheets/`, vendor downloads in `docs/vendor/<Value>/`
  (both git-ignored). Do not look elsewhere. Never copy a PDF into `components/`.
- No web access: revision currency, errata, PCN and lifecycle are open items ("not checked"), never questions.
- Work on a branch. Touch only files the task needs. Do not commit unless I ask.
- After every change, from the repo root, in order:
  `python3 -m lib.check` -> `python3 -m lib.zen` -> `python3 -m lib.readme` ->
  `pcb build -Wstyle -Dwarnings components/<Mfr>/<Value>` -> `python3 -m unittest discover -s tests`.
  Never call a task done until all pass with 0 errors and 0 warnings. Judge by exit code, never by the absence of
  `✗` (a build that cannot start prints none). Delete `__pycache__/` dirs afterwards.
- Toolchain: pcb 0.4.x. Root `pcb.toml` has `pcb-version = "0.4"` (major.minor only; "0.4.95" breaks every build).
  The `pcb` shim updates itself, even on `--help`; `pcb +0.4.101 <cmd>` runs an exact version. There is no `pcb doc`
  or `pcb search`. Before using any Zener construct the generator does not already emit, confirm it in the stdlib
  source (`pcb list -m -json @stdlib` gives the path), `pcb <cmd> --help`, or a throwaway build in the scratchpad;
  otherwise do not use it. Use the `zener-language` skill for Zener syntax and the `zener-wrapper` skill for this
  repo's generator. I am not logged in to `pcb auth`: no registry or web search.
- Read datasheet tables as rendered images, never extracted text (it scrambles columns):
  `pdftoppm -r 150 -png -f N -l N <pdf> <scratch>/p`, then Read the PNG (use -r 200-300 for small print). Use
  `pdftotext -layout` only to find which page holds which table.

Terms: **MPN** = exact orderable number with reel suffix (LTC4364HMS-1#TRPBF). **Value** = MPN without the reel
suffix (LTC4364HMS-1); it names the directory, or a variant in a family's `variants.toml`. **Cite** = `DS p.<printed page>, <table or figure title>, <row>`
(printed page numbers; pages with no printed number: `DS PDF p.<n>, <drawing number>`).

## Agent roles (default for every component task)
The main session (Opus) orchestrates, owns every decision, every stop, and the final report. Subagents cannot reach
me; they return evidence.
- **Electrical engineer, one Haiku per part:** extracts `component.toml` and writes `calc.py` from page images, and
  proposes `check_pins` / `check_ambient` / `unchecked` for every abs_max and rec_op row. Writes only those two
  files. Reports params count, pin table, equations, check selection, every judgement call.
- **Independent verifier, one fresh Haiku per part (not the extractor):** READ-ONLY. Checks every number, column,
  unit, scope and cite against the page images; lists missing table rows. Reports problems only.
- **Software engineer, Sonnet:** only when `lib/` needs a change. Adds tests for every change.
- **Adversarial reviewer, Sonnet, electrical + software:** READ-ONLY. Re-derives every calc equation from the
  datasheet, hunts conventions that would mislead worst-case analysis (one-sided ± values, sign errors, % / ppm
  units, typ used as a bound, curve values as bounds), challenges the Zener check selection (a pin the circuit sets
  but left unchecked, a part-driven pin checked, a wrong reference pin), spot-checks 10+ high-impact numbers, runs
  the tools.
  Output: `severity | file:line | problem | evidence | exact fix`.
- At most two Sonnet agents at once; Haiku agents as needed. Give every agent absolute paths, the SPEC path, the DS
  path, its scratch dir, and the files it may write.

## Component procedure (one Value per directory)
0. **Pre-flight.** Check `docs/datasheets/<pdf>`, `docs/vendor/<Value>/` (symbol, footprint, STEP), `pdftoppm`,
   `python3` (3.11+, matplotlib). If anything I must supply is missing, send ONE message listing all of it with exact
   paths, then do everything that does not need it. Datasheet missing: send the message and stop. STEP missing:
   continue, `step = "none"`, open item.
1. **Intake.** Datasheet revision and date, MPN decode from the ordering table / package addendum (package, grade,
   finish, packaging, MSL), lifecycle status as printed. Several packages, grades or options and the task does not
   name one: **Stop** and ask. Orderables that share one package (same symbol, footprint, STEP) and differ only in
   grade or option are one family directory named for the package (`LTC4364MS`) with `variants.toml` (SPEC
   "Families and variants"): rows that differ are restricted with `variants = [...]` or overridden per variant; each
   variant sets its own `mpn`. Another package is another directory and needs its own KiCad files.
   MLCC series: catalog from the vendor export, one directory per size+thickness code (`python3 -m lib.catalog`, SPEC
   "Capacitor series"); no family, per-dielectric rows use `dielectric = ...`, per-part rows `parts = [...]`.
2. **KiCad files** (docs/KICAD.md). Vendor files come in L/N/M densities: use N. Copy symbol and footprint into
   `components/<Manufacturer>/<Value>/<Value>.kicad_sym` / `.kicad_mod`. If the copied symbol's `(version ...)` is below
   20251024 (KiCad 6/7 exports always are), upgrade it with `kicad-cli sym upgrade --force` BEFORE the fix-ups, then
   confirm pins and properties are unchanged and that Description and other curated properties survived (the upgrade
   can overwrite Description from ki_description: restore it). Fix them up by editing the S-expressions:
   properties (Value, MPN, Manufacturer, Datasheet URL, Description, Footprint link), pin names verbatim from the DS,
   pin electrical types from the DS function text, same-name pins that are separate nodes renamed apart (RG1/RG2),
   pads equal to the DS land pattern, courtyard, pin-1 marker. Never hand-draw a symbol or footprint. Copy the STEP
   as `<Value>.step` and reference it from the footprint, or keep an existing embedded model; never substitute
   another part's model. **Stop** if the vendor footprint is mirrored or rotated, or pad count, pitch or pin-1 corner
   disagrees with the DS.
3. **Extract** (EE agent). `component.toml` per SPEC: every row of Absolute Maximum Ratings, ESD, Recommended
   Operating Conditions, Thermal Information (this package's column), and every Electrical Characteristics row, as
   separate `_25c` / `_full` keys where both exist; mechanical rows in mm. `[[pin]]` must match the symbol exactly.
4. **Equations** (same EE agent). `calc.py` per SPEC: one function per DS equation, SI floats, cite + units in the
   docstring, only `import math`. `EXAMPLES` from numbers the DS prints (gain tables, design example); a tolerance
   looser than 1e-3 needs a comment saying why. `INPUTS` for every function. One combined function for the part's
   main quantity per the SPEC temperature recipe (`gain_actual`, `resistance_worst`).
5. **Zener wrapper.** Every abs_max and rec_op row gets `check_pins` (pins the circuit sets: supplies, signal
   inputs, pull-up rails, divider inputs), `check_ambient` (the grade's temperature range) or `unchecked` with a
   reason (part-driven pins, covered by a stricter row, `owner: module|board|assembly`); `lib.check` warns on a
   row with none. Run `python3 -m lib.zen` (writes `<Value>.zen`, an empty `pcb.toml`, then `pcb fmt`). Write
   `tests/zen/<Value>_harness.zen`: the wrapper instantiated with nominal passing voltages, each default commented
   with its range and why it passes. Add `CASES` rows in `tests/test_zen.py`: nominal pass; each check pushed just
   outside its limit and failing at its severity; one waiver for a warning-level check; one unset net (UNVERIFIED);
   ambient out of range. Prove one new case can fail by flipping its expectation once.
6. **Verify** (fresh Haiku verifier per part + adversarial Sonnet, in parallel). Apply findings that cite the DS or
   SPEC; log the rest as open items. If a finding changes the format, update SPEC first, then the data, then `lib/`
   with tests. Re-review only what changed (one targeted round).
7. **Generate.** `python3 -m lib.readme` (its "Zener checks" section lists every check and unchecked reason). Add
   the part to the table in the root README.md. If the part is used in an example, re-run that example.
8. **Report** (Done list below).

## Defaults instead of questions
Apply the default, add a Decision Log row, add the open item, continue.

| Case | Default |
|---|---|
| DS prints `±X` as a limit | `min = -X, max = X` |
| DS prints an unsigned magnitude for a quantity that can be either sign (VOS, IB, IOS, offset drift) | `max` (and `typ`) as printed, `sym = true`, note. Never for a quantity that cannot be negative (IQ) |
| DS prints `±X` in the TYP column (gain error) | `typ = X`, `typ_pm = true`. Not when ± means source/sink of a magnitude (ISC): store the magnitude, note |
| DS prints negative values in magnitude order (MIN -10, MAX -30) | Store numerically: printed MAX -> `min`, printed MIN -> `max`; note quotes the printed columns |
| Rating stated in words or as a formula ("Continuous", "(P x R)^1/2") | `text` field, no numbers |
| Abs-max row with no stated reference pin | Store as printed; note says how it applies (each pin vs the part's ground/common). If the DS states a reference anywhere ("all voltages referenced to GND"), set `min_ref`/`max_ref` to that pin name and cite it. Pin-pair rows (VGS, SENSE-OUT) use the second pin as ref |
| Rail-relative range ((V-)+2 V to (V+)-2 V) | Offsets with `min_ref`/`max_ref` = pin names; users call `part.resolve()` |
| Row covers only part of the grade's temperature range (0-125 °C on an H part) | `scope = "partial"`; note names the row to use instead |
| Value read off a graph | `curve = true`, cite names the figure/graph. A calc that uses it says "curve-based estimate" in its docstring |
| Typical-only value | Store as typ. Never a bound. INPUTS maps it as `key.typ` |
| Function fitted to a typical curve | Name ends `_typ`; docstring names the guaranteed rows |
| Rating (power, current, voltage max) printed with no MIN/TYP/MAX label | `max` |
| Quantity printed per N pieces (63.6 g / 1000 pcs) | Per-part value in a unit that keeps the printed digits (63.6 mg); printed wording in `conditions` |
| % or ppm in the DS | Store as printed (`%`, `ppm/degC`); the loader converts to fractions. calc args are fractions |
| Negative (sourcing) current used as a magnitude in an equation | Keep signed in TOML; the calc function applies `abs()` and says so |
| Equation needed to use the DS correctly but not printed (pin bias current through a divider) | Allowed only with `Not a DS equation:` and a derivation; as an optional argument whose default reproduces the DS equation exactly |
| "Specified by characterization" | Store as guaranteed; note "characterized, not production tested (DS note N)" |
| DS contradicts itself | Priority: pin function text > pin diagram > I/O column; table > feature bullets. Record as open item. **Stop** if pin number, position or count disagree between diagram and table |
| NC / DNC / exposed pad | DS wording, quoted in the pin `function`. Exposed pad that must connect to X: a pin sharing X's name. Wording missing: **Stop** |
| No Absolute Maximum Ratings table (passives) | Map the DS's own rating tables to `rec_op` / `electrical` honestly; say so in a TOML comment |
| Range-dependent rows (resistor value ranges) | Use only the row covering this Value; name the row in `cite` |
| Land-pattern dimensions labelled only by letter | Neutral name ("Land pattern dimension c (DS p.2 diagram)"); inferred meaning in note, marked inferred; unconfirmed ones are open items |
| Rating row on a pin the part drives (OUT, gate drive, TMR, COMP, SS) or whose voltage external parts set (MOSFET SOURCE, SW) | `unchecked = "<reason>; owner: module"` |
| Abs-max row looser than a checked rec-op row on the same quantity (TA abs vs grade, supply abs vs rec-op span) | `unchecked = "covered by <key>"` on the looser row; check the stricter one |
| Abs-max row with no reference pin, part has no ground pin (amplifiers) | `check_pins` with no ref: checked against system 0 V; note says so |
| One abs-max row covers several pins, some part-driven (FB, TMR) | `check_pins` on the circuit-set pins, `unchecked` names the rest and why |
| Supply span printed as single and dual ranges | Check the span once (`check_pins = ["+VS"]`, refs `-VS`); the other row `unchecked = "same span as <key>"` |
| Storage, lead/solder temperature, ESD | `unchecked = "owner: assembly"` |
| Alternates | Only the same part in other packaging (reel/tube). Other grades, tolerances or second sources: open item |
| Revision currency, errata, PCN, lifecycle, lead finish / MSL missing | Open item "not checked (no web access)" / "no data in DS" |
| Vendor symbol older than KiCad 10 format | upgrade with kicad-cli, verify pins/properties, restore curated Description |

**Stop** (ask me) only for: missing datasheet; unnamed package/grade/option choice; mirrored/rotated/mismatched
footprint; pin count or position conflict in the DS; missing NC/EP wording; two defaults that conflict; anything
unsafe.

## Done: evidence to show
1. Pin table (number, name, type, function, cite) and confirmation it matches the symbol (lib.check); symbol format version (KiCad 10).
2. Footprint: DS land pattern vs footprint pads per dimension; courtyard; pin-1 marker; STEP status.
3. Params summary: counts per kind, every judgement call, every DS ambiguity.
4. Equations list with cites; EXAMPLES results; INPUTS present for every function.
5. Verifier and adversarial findings: applied (with the change) or logged (as open item).
6. Verbatim tail of `python3 -m lib.check` (0 errors, 0 warnings), `pcb build -Wstyle -Dwarnings <dir>`, and the
   unittest summary (including tests/test_zen.py: wrappers current, harness cases as expected).
7. Zener check table (the README "Zener checks" section) and the waiver grep:
   `grep -rn 'waive_[a-z_0-9]*=' --include='*.zen' . | grep -v '/.pcb/'` (or "none").
8. Decision Log: every default applied | case | open item.
9. Open items: DS ambiguities, 25 °C-only and curve-based values, revision/errata/PCN/lifecycle, lead finish,
   unverified second sources, 3D-model pin-1 check in KiCad.

## Zener modules (hierarchical circuits)
- Design modules and boards with the `ee-design` skill (worst-case analysis, part and value choices, default
  design rules) and draw and review their schematics with the `schematic-style` skill.
- Run schematic generation and arrangement (and any agent delegation for it) with the `schematic-capture` skill.
- Build from the generated wrappers: `Module("github.com/kb1lqc/zener-library/components/<Mfr>/<Value>/<Value>.zen")`
  (relative paths that leave a package fail), then `pcb sync`.
- Give every checked net a voltage range with tolerance (`Power("V15", voltage="15V 5%")`); an undeclared voltage
  reports UNVERIFIED and fails `-Dwarnings`.
- Pass `derate`, `ambient` and any `waive_<key>` down to each wrapper; never hard-code them. A waiver is a
  rationale with a cite; list every waiver in the report.
- Design-intent configs (gain, Vout, current limit) live on the module. Compute values in Python from `calc.py`
  and snap with the stdlib E-series helpers; do not re-implement datasheet equations in Zener.
- Keep topology stable: configs change values and `dnp`, never add, remove or reconnect instances.

## Using the library in a circuit (examples/)
- Load numbers through `part.param(key)` / `part.inputs(fn)`; never retype a datasheet number.
- Every non-datasheet value is a named DESIGN CHOICE constant with a comment.
- Worst case through `wca` (all min/max corners); nominal via typ. For a bound-only spec, state the nominal with
  `Param.with_typ(...)` in code.
- Use `full` rows over temperature; otherwise the SPEC temperature recipe. Curve and `_typ` values never decide
  pass/fail without saying so in the output.
- Output: a generated markdown report (inputs with cites, results table, rating checks with PASS/FAIL, plots, and a
  "limits of this analysis" line: DC steady state, 25 °C-only rows, curve estimates).
